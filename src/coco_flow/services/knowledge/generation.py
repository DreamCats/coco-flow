from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from json import JSONDecodeError, JSONDecoder
from pathlib import Path
import json
import re
import uuid

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.models.knowledge import KnowledgeDocument, KnowledgeEvidence

KNOWLEDGE_KIND_ORDER = ("domain", "flow", "rule")
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
SKIP_DIR_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
SEARCHABLE_SUFFIXES = {
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
TERM_HINTS = {
    "表达层": ["表达层", "render", "view", "ui", "card"],
    "讲解卡": ["讲解卡", "explain_card", "explain", "card"],
    "购物袋": ["购物袋", "shopping_bag", "bag"],
    "竞拍": ["竞拍", "auction", "bid"],
    "链路": ["链路", "flow", "pipeline"],
    "规则": ["规则", "rule", "policy"],
    "渲染": ["渲染", "render", "renderer"],
    "入口": ["入口", "entry", "handler"],
}


@dataclass(frozen=True)
class KnowledgeDraftInput:
    description: str
    selected_paths: list[str]
    kinds: list[str]
    notes: str = ""


@dataclass(frozen=True)
class KnowledgeGenerationResult:
    documents: list[KnowledgeDocument]
    trace_id: str
    open_questions: list[str]
    trace_files: dict[str, object]
    validation_errors: list[str]


ProgressHandler = Callable[[str, int, str], None]


def generate_knowledge_drafts(
    payload: KnowledgeDraftInput,
    settings: Settings,
    on_progress: ProgressHandler | None = None,
) -> KnowledgeGenerationResult:
    description = payload.description.strip()
    if not description:
        raise ValueError("description is required")

    selected_paths = normalize_selected_paths(payload.selected_paths)
    if not selected_paths:
        raise ValueError("selected_paths is required")

    requested_kinds = normalize_kinds(payload.kinds)
    requested_executor = normalize_executor(settings.knowledge_executor)
    now = datetime.now().astimezone()
    trace_id = f"knowledge-{now:%Y%m%d}-{uuid.uuid4().hex[:8]}"
    _emit_progress(on_progress, "intent_normalizing", 10, "正在收敛描述和生成类型")
    intent_payload = build_intent_payload(description, requested_kinds, payload.notes)
    _emit_progress(on_progress, "repo_discovering", 35, "正在扫描已选路径和 repo 上下文")
    discovery_payload = assign_repo_ids(
        [discover_repo(Path(raw_path).expanduser(), intent_payload["search_terms"]) for raw_path in selected_paths]
    )
    _emit_progress(on_progress, "repo_researching", 60, "正在归纳各 repo 在链路中的角色")
    repo_research_payloads = [
        build_repo_research(intent_payload, discovery, settings, requested_executor)
        for discovery in discovery_payload
    ]
    _emit_progress(on_progress, "synthesizing", 80, "正在生成知识草稿")
    documents = build_documents(
        intent_payload=intent_payload,
        repo_research_payloads=repo_research_payloads,
        selected_paths=selected_paths,
        requested_kinds=requested_kinds,
        trace_id=trace_id,
        timestamp=now.strftime("%Y-%m-%d %H:%M"),
        settings=settings,
        requested_executor=requested_executor,
    )
    open_questions = unique_strings(
        [
            *intent_payload["open_questions"],
            *collect_repo_questions(repo_research_payloads),
            *collect_document_questions(documents),
        ]
    )
    knowledge_draft_payload = {
        "trace_id": trace_id,
        "documents": [serialize_document(document) for document in documents],
        "open_questions": open_questions,
    }
    _emit_progress(on_progress, "validating", 92, "正在校验生成结果")
    validation_errors = validate_documents(documents)
    validation_payload = {
        "trace_id": trace_id,
        "ok": not validation_errors,
        "errors": validation_errors,
        "document_count": len(documents),
    }
    trace_files: dict[str, object] = {
        "intent.json": intent_payload,
        "repo-discovery.json": {
            "trace_id": trace_id,
            "requested_executor": requested_executor,
            "repos": discovery_payload,
        },
        "knowledge-draft.json": knowledge_draft_payload,
        "validation-result.json": validation_payload,
    }
    for research_payload in repo_research_payloads:
        trace_files[f"repo-research/{research_payload['repo_id']}.json"] = research_payload

    return KnowledgeGenerationResult(
        documents=documents,
        trace_id=trace_id,
        open_questions=open_questions,
        trace_files=trace_files,
        validation_errors=validation_errors,
    )


def _emit_progress(on_progress: ProgressHandler | None, status: str, progress: int, message: str) -> None:
    if on_progress is None:
        return
    on_progress(status, progress, message)


def normalize_selected_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_path in paths:
        value = str(raw_path).strip()
        if not value:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def normalize_kinds(kinds: list[str]) -> list[str]:
    normalized = [kind for kind in kinds if kind in KNOWLEDGE_KIND_ORDER]
    if "flow" not in normalized:
        normalized.insert(0, "flow")
    ordered = [kind for kind in KNOWLEDGE_KIND_ORDER if kind in normalized]
    return ordered or ["flow"]


def normalize_executor(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {EXECUTOR_LOCAL, EXECUTOR_NATIVE}:
        return normalized
    raise ValueError(f"unknown knowledge executor: {value}")


def build_intent_payload(description: str, requested_kinds: list[str], notes: str) -> dict[str, object]:
    domain_name = infer_domain_name(description)
    domain_candidate = slugify_domain(domain_name)
    normalized_intent = description if "链路" in description else f"{description}系统链路"
    search_terms = infer_search_terms(description, notes, domain_candidate)
    open_questions = [
        "是否还有未选择但会影响主链路的上游或下游 repo。",
        "当前命中的候选文件是否已经覆盖真实入口。",
    ]
    return {
        "description": description,
        "domain_candidate": domain_candidate,
        "domain_name": domain_name,
        "requested_kinds": requested_kinds,
        "normalized_intent": normalized_intent,
        "notes": notes.strip(),
        "search_terms": search_terms,
        "open_questions": open_questions,
    }


def discover_repo(raw_path: Path, search_terms: list[str]) -> dict[str, object]:
    resolved_path = raw_path.resolve()
    if not resolved_path.exists():
        raise ValueError(f"selected path not found: {raw_path}")

    requested_path = resolved_path if resolved_path.is_dir() else resolved_path.parent
    repo_root = find_repo_root(requested_path)
    scan_root = repo_root or requested_path
    agents_path = scan_root / "AGENTS.md"
    context_root = scan_root / ".livecoding" / "context"
    matched_files, matched_keywords = scan_candidate_files(scan_root, search_terms)
    candidate_dirs = unique_strings([str(Path(path).parent) for path in matched_files if str(Path(path).parent) != "."])
    if not candidate_dirs:
        candidate_dirs = list_top_level_dirs(scan_root)
    context_hits = scan_context_hits(context_root, search_terms)
    return {
        "repo_id": scan_root.name or requested_path.name,
        "requested_path": str(requested_path),
        "repo_path": str(scan_root),
        "is_git_repo": repo_root is not None,
        "agents_present": agents_path.is_file(),
        "context_present": context_root.is_dir(),
        "candidate_dirs": candidate_dirs[:8],
        "candidate_files": matched_files[:12],
        "matched_keywords": matched_keywords,
        "context_hits": context_hits,
    }


def assign_repo_ids(discovery_payload: list[dict[str, object]]) -> list[dict[str, object]]:
    counts: dict[str, int] = {}
    normalized_payload: list[dict[str, object]] = []
    for item in discovery_payload:
        base_id = slugify_repo_id(str(item["repo_id"]))
        next_count = counts.get(base_id, 0) + 1
        counts[base_id] = next_count
        repo_id = base_id if next_count == 1 else f"{base_id}-{next_count}"
        normalized_payload.append({**item, "repo_id": repo_id})
    return normalized_payload


def build_repo_research(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_repo_research_native(intent_payload, discovery, settings)
        except ValueError as error:
            local = build_repo_research_local(intent_payload, discovery)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_repo_research_local(intent_payload, discovery)


def build_repo_research_local(intent_payload: dict[str, object], discovery: dict[str, object]) -> dict[str, object]:
    matched_keywords = [str(item) for item in discovery["matched_keywords"]]
    candidate_dirs = [str(item) for item in discovery["candidate_dirs"]]
    candidate_files = [str(item) for item in discovery["candidate_files"]]
    context_hits = [str(item) for item in discovery["context_hits"]]
    primary = bool(candidate_files or matched_keywords or context_hits)
    role = "primary" if primary else "supporting"
    facts = [
        f"repo_path={discovery['repo_path']}",
        "git repo" if discovery["is_git_repo"] else "selected path is not inside a git repo",
        "AGENTS.md present" if discovery["agents_present"] else "AGENTS.md missing",
        "context present" if discovery["context_present"] else "context missing",
    ]
    inferences = [
        (
            f"该 repo 更可能承接 `{intent_payload['normalized_intent']}` 的主入口或主链路。"
            if primary
            else "当前 repo 更像补充依赖方，需要结合人工判断决定是否继续深挖。"
        )
    ]
    risks = []
    if not candidate_files:
        risks.append("尚未命中高信号 candidate files，后续可能需要人工补充入口文件。")
    if not context_hits:
        risks.append("未命中 repo context，链路推断主要来自目录和文件名。")
    if not discovery["agents_present"]:
        risks.append("缺少 AGENTS.md，仓库协作约束需要人工确认。")
    open_questions = []
    if not discovery["is_git_repo"]:
        open_questions.append("该路径不是 git repo，是否应上卷到真实仓库根目录。")
    if not matched_keywords:
        open_questions.append("当前关键词未命中明显模块名，是否需要补充别名或业务术语。")
    if candidate_dirs:
        open_questions.append(f"是否以 `{candidate_dirs[0]}` 为第一跳入口目录。")
    return {
        "repo_id": discovery["repo_id"],
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "role": role,
        "likely_modules": candidate_dirs[:6],
        "candidate_files": candidate_files[:8],
        "risks": risks,
        "facts": facts,
        "inferences": inferences,
        "context_hits": context_hits,
        "open_questions": open_questions,
        "matched_keywords": matched_keywords,
    }


def build_repo_research_native(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    fallback = build_repo_research_local(intent_payload, discovery)
    repo_path = str(discovery["repo_path"]).strip()
    if not repo_path:
        raise ValueError("native repo research missing repo_path")
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_readonly_agent(
        build_repo_research_prompt(intent_payload, discovery),
        settings.native_query_timeout,
        cwd=repo_path,
    )
    parsed = extract_repo_research_output(raw)
    result = fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "role": parsed["role"],
        "likely_modules": parsed["likely_modules"] or fallback["likely_modules"],
        "risks": parsed["risks"] or fallback["risks"],
        "facts": parsed["facts"] or fallback["facts"],
        "inferences": parsed["inferences"] or fallback["inferences"],
        "open_questions": unique_strings(parsed["open_questions"] + fallback["open_questions"]),
    }
    return result


def build_documents(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    selected_paths: list[str],
    requested_kinds: list[str],
    trace_id: str,
    timestamp: str,
    settings: Settings,
    requested_executor: str,
) -> list[KnowledgeDocument]:
    local_documents = build_documents_local(
        intent_payload=intent_payload,
        repo_research_payloads=repo_research_payloads,
        selected_paths=selected_paths,
        requested_kinds=requested_kinds,
        trace_id=trace_id,
        timestamp=timestamp,
        requested_executor=requested_executor,
        synthesis_executor=EXECUTOR_LOCAL,
    )
    if requested_executor != EXECUTOR_NATIVE:
        return local_documents
    try:
        return build_documents_native(
            intent_payload=intent_payload,
            repo_research_payloads=repo_research_payloads,
            selected_paths=selected_paths,
            requested_kinds=requested_kinds,
            trace_id=trace_id,
            timestamp=timestamp,
            settings=settings,
            fallback_documents=local_documents,
        )
    except ValueError as error:
        return annotate_documents(
            local_documents,
            requested_executor=requested_executor,
            synthesis_executor=EXECUTOR_LOCAL,
            synthesis_fallback_reason=str(error),
        )


def build_documents_local(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    selected_paths: list[str],
    requested_kinds: list[str],
    trace_id: str,
    timestamp: str,
    requested_executor: str,
    synthesis_executor: str,
) -> list[KnowledgeDocument]:
    domain_name = str(intent_payload["domain_name"])
    domain_id = str(intent_payload["domain_candidate"])
    repo_ids = [str(item["repo_id"]) for item in repo_research_payloads]
    repo_paths = [str(item["repo_path"]) for item in repo_research_payloads]
    display_paths = build_display_paths(selected_paths, repo_research_payloads)
    keyword_matches = unique_strings(
        [str(keyword) for item in repo_research_payloads for keyword in item["matched_keywords"]]
    )
    candidate_files = unique_strings(
        [str(path) for item in repo_research_payloads for path in item["candidate_files"]]
    )
    context_hits = unique_strings(
        [str(hit) for item in repo_research_payloads for hit in item["context_hits"]]
    )
    open_questions = unique_strings(
        [str(question) for item in repo_research_payloads for question in item["open_questions"]]
    )
    documents: list[KnowledgeDocument] = []
    for kind in requested_kinds:
        document = KnowledgeDocument(
            id=f"{kind}-{domain_id}-{uuid.uuid4().hex[:8]}",
            traceId=trace_id,
            kind=kind,
            status="draft",
            title=build_title(kind),
            desc=build_description(kind, str(intent_payload["normalized_intent"])),
            domainId=domain_id,
            domainName=domain_name,
            engines=infer_engines(kind),
            repos=repo_ids,
            paths=repo_paths,
            keywords=keyword_matches,
            priority="high" if kind == "flow" else "medium",
            confidence="medium" if candidate_files else "low",
            updatedAt=timestamp,
            owner="Maifeng",
            body=build_body(kind, intent_payload, repo_research_payloads, display_paths, open_questions),
            evidence=KnowledgeEvidence(
                inputDescription=str(intent_payload["description"]),
                repoMatches=repo_ids,
                keywordMatches=keyword_matches,
                pathMatches=selected_paths,
                candidateFiles=candidate_files,
                contextHits=context_hits,
                retrievalNotes=[],
                openQuestions=open_questions,
            ),
        )
        documents.append(document)
    return annotate_documents(
        documents,
        requested_executor=requested_executor,
        synthesis_executor=synthesis_executor,
        notes=str(intent_payload["notes"]),
        repo_research_payloads=repo_research_payloads,
    )


def build_documents_native(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    selected_paths: list[str],
    requested_kinds: list[str],
    trace_id: str,
    timestamp: str,
    settings: Settings,
    fallback_documents: list[KnowledgeDocument],
) -> list[KnowledgeDocument]:
    display_paths = build_display_paths(selected_paths, repo_research_payloads)
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(repo_research_payloads[0]["repo_path"]) if repo_research_payloads else None
    raw = client.run_prompt_only(
        build_knowledge_synthesis_prompt(intent_payload, repo_research_payloads, display_paths, requested_kinds),
        settings.native_query_timeout,
        cwd=cwd,
    )
    outputs = extract_knowledge_synthesis_output(raw, requested_kinds)
    documents = apply_synthesis_outputs(fallback_documents, outputs, display_paths)
    documents = annotate_documents(
        documents,
        requested_executor=EXECUTOR_NATIVE,
        synthesis_executor=EXECUTOR_NATIVE,
        notes=str(intent_payload["notes"]),
        repo_research_payloads=repo_research_payloads,
    )
    errors = validate_documents(documents)
    if errors:
        raise ValueError("; ".join(errors))
    return documents


def infer_engines(kind: str) -> list[str]:
    if kind == "flow":
        return ["plan", "refine"]
    return ["refine", "plan"]


def build_title(kind: str) -> str:
    if kind == "flow":
        return "系统链路"
    if kind == "rule":
        return "业务规则"
    return "业务方向概览"


def build_description(kind: str, normalized_intent: str) -> str:
    if kind == "flow":
        return f"归纳 {normalized_intent} 的主链路、关键 repo 角色和 repo hints。"
    if kind == "rule":
        return f"整理 {normalized_intent} 相关的默认规则线索和待确认边界。"
    return f"概览 {normalized_intent} 对应的业务方向、相关 repo 和上下文线索。"


def build_body(
    kind: str,
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    selected_paths: list[str],
    open_questions: list[str],
) -> str:
    if kind == "flow":
        return build_flow_body(intent_payload, repo_research_payloads, selected_paths, open_questions)
    if kind == "rule":
        return build_rule_body(intent_payload, repo_research_payloads, open_questions)
    return build_domain_body(intent_payload, repo_research_payloads, open_questions)


def build_flow_body(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    selected_paths: list[str],
    open_questions: list[str],
) -> str:
    dependency_lines = []
    for item in repo_research_payloads:
        module_hint = ", ".join(item["likely_modules"][:3]) if item["likely_modules"] else "待补充"
        dependency_lines.append(f"- `{item['repo_id']}`: role={item['role']}，模块线索={module_hint}")

    repo_hint_sections = []
    for item in repo_research_payloads:
        dirs = "\n".join(f"- `{path}`" for path in item["likely_modules"]) or "- 待补充"
        files = "\n".join(f"- `{path}`" for path in item["candidate_files"]) or "- 待补充"
        context_hits = "\n".join(f"- {hit}" for hit in item["context_hits"]) or "- 未命中 repo context"
        repo_hint_sections.append(
            "\n".join(
                [
                    f"### `{item['repo_id']}`",
                    "",
                    f"- requested path: `{item['requested_path']}`",
                    f"- repo path: `{item['repo_path']}`",
                    f"- role: `{item['role']}`",
                    "",
                    "#### Candidate Dirs",
                    dirs,
                    "",
                    "#### Candidate Files",
                    files,
                    "",
                    "#### Context Hits",
                    context_hits,
                ]
            )
        )

    question_lines = "\n".join(f"- {question}" for question in open_questions) or "- 待补充"
    path_lines = "\n".join(f"- `{path}`" for path in selected_paths)
    return "\n".join(
        [
            "## Summary",
            "",
            f"{intent_payload['normalized_intent']} 当前处于第一阶段知识草稿，重点先确认主链路涉及哪些 repo、入口目录和高信号文件，再决定是否继续补 domain / rule。",
            "",
            "## Main Flow",
            "",
            "1. 根据用户描述收敛业务意图，并把选中的路径映射到 repo 或工作目录。",
            "2. 基于目录结构、文件名、AGENTS.md 和 `.livecoding/context/` 做轻量 discovery。",
            "3. 先从 primary repo 开始确认入口和关键模块，再补 supporting repo 的依赖关系。",
            "4. 所有未确认内容都保留在 `Open Questions`，不直接提升为已批准知识。",
            "",
            "## Selected Paths",
            "",
            path_lines,
            "",
            "## Dependencies",
            "",
            *dependency_lines,
            "",
            "## Repo Hints",
            "",
            "\n\n".join(repo_hint_sections),
            "",
            "## Open Questions",
            "",
            question_lines,
        ]
    ).strip()


def build_domain_body(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    open_questions: list[str],
) -> str:
    repo_lines = "\n".join(f"- `{item['repo_id']}`: {item['role']}" for item in repo_research_payloads) or "- 待补充"
    question_lines = "\n".join(f"- {question}" for question in open_questions) or "- 待补充"
    return "\n".join(
        [
            "## Summary",
            "",
            f"`{intent_payload['domain_name']}` 当前作为领域入口草稿，用于聚合相关 flow / rule，并记录多 repo 的基础发现。",
            "",
            "## Repo Coverage",
            "",
            repo_lines,
            "",
            "## Open Questions",
            "",
            question_lines,
        ]
    ).strip()


def build_rule_body(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    open_questions: list[str],
) -> str:
    risk_lines = "\n".join(f"- {risk}" for item in repo_research_payloads for risk in item["risks"]) or "- 待补充"
    question_lines = "\n".join(f"- {question}" for question in open_questions) or "- 待补充"
    return "\n".join(
        [
            "## Statement",
            "",
            f"`{intent_payload['normalized_intent']}` 当前只发现规则线索，不直接宣称为稳定业务规则。",
            "",
            "## Evidence Risks",
            "",
            risk_lines,
            "",
            "## Open Questions",
            "",
            question_lines,
        ]
    ).strip()


def validate_documents(documents: list[KnowledgeDocument]) -> list[str]:
    errors: list[str] = []
    for document in documents:
        if document.kind not in KNOWLEDGE_KIND_ORDER:
            errors.append(f"{document.id}: invalid kind `{document.kind}`")
        if not document.title.strip():
            errors.append(f"{document.id}: title is empty")
        if not document.body.strip():
            errors.append(f"{document.id}: body is empty")
        if document.kind == "flow" and "## Repo Hints" not in document.body:
            errors.append(f"{document.id}: flow body missing Repo Hints")
        if "## Open Questions" not in document.body:
            errors.append(f"{document.id}: body missing Open Questions")
    return errors


def serialize_document(document: KnowledgeDocument) -> dict[str, object]:
    payload = document.model_dump()
    payload["evidence"] = document.evidence.model_dump()
    return payload


def collect_repo_questions(repo_research_payloads: list[dict[str, object]]) -> list[str]:
    return [str(question) for item in repo_research_payloads for question in item["open_questions"]]


def collect_document_questions(documents: list[KnowledgeDocument]) -> list[str]:
    return [question for document in documents for question in document.evidence.openQuestions]


def summarize_research_executors(repo_research_payloads: list[dict[str, object]]) -> str:
    executors = unique_strings([str(item.get("executor") or EXECUTOR_LOCAL) for item in repo_research_payloads])
    if not executors:
        return EXECUTOR_LOCAL
    return ", ".join(executors)


def annotate_documents(
    documents: list[KnowledgeDocument],
    *,
    requested_executor: str,
    synthesis_executor: str,
    notes: str = "",
    repo_research_payloads: list[dict[str, object]] | None = None,
    synthesis_fallback_reason: str = "",
) -> list[KnowledgeDocument]:
    retrieval_notes = [
        (
            f"repo research executor: {summarize_research_executors(repo_research_payloads or [])}。"
            if repo_research_payloads
            else "repo research executor: local。"
        ),
        f"knowledge synthesis executor: {synthesis_executor} (requested={requested_executor})。",
        "候选目录和文件只作为 Repo Hints，不应直接固化成长期代码地图。",
    ]
    if synthesis_fallback_reason:
        retrieval_notes.append(f"knowledge synthesis fallback: {synthesis_fallback_reason}")
    if notes:
        retrieval_notes.append(f"补充材料：{notes}")

    return [
        document.model_copy(
            update={
                "title": build_title(document.kind),
                "evidence": document.evidence.model_copy(
                    update={
                        "retrievalNotes": retrieval_notes,
                    }
                )
            }
        )
        for document in documents
    ]


def build_repo_research_prompt(intent_payload: dict[str, object], discovery: dict[str, object]) -> str:
    discovery_payload = {
        "repo_id": discovery["repo_id"],
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "agents_present": discovery["agents_present"],
        "context_present": discovery["context_present"],
        "candidate_dirs": discovery["candidate_dirs"],
        "candidate_files": discovery["candidate_files"],
        "matched_keywords": discovery["matched_keywords"],
        "context_hits": discovery["context_hits"],
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 repo research。\n"
        "目标：针对单个 repo，基于给定 discovery 结果，归纳它在当前需求中的角色。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 输出必须是一个可解析 JSON object，不要输出 markdown，不要输出解释，不要包 code fence。\n"
        "2. 必须严格包含这些字段：role, likely_modules, risks, facts, inferences, open_questions。\n"
        "3. role 只能是 primary、supporting、unknown 之一。\n"
        "4. facts 只能写输入里可直接观察到的事实；inferences 才能写推断。\n"
        "5. likely_modules 最多 6 条；risks/facts/inferences/open_questions 各最多 5 条。\n"
        "6. 不要复述 schema 说明，不要输出空洞话术，不要写“需要进一步分析”这类没有信息增量的句子。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- candidate_files、candidate_dirs、context_hits、matched_keywords 越集中，越倾向 primary。\n"
        "- 如果 repo 只命中少量外围目录且缺少高信号文件，可判为 supporting。\n"
        "- 优先引用输入里的真实路径和术语，避免泛化成抽象模块名。\n"
        "- 如果证据不足，明确写进 risks 或 open_questions，而不是把推断写成事实。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 路径、repo_id、关键词保持原样。\n"
        "- 每条尽量简短、具体、可核对。\n"
        "</style>\n\n"
        "<intent>\n"
        f"{json.dumps({'normalized_intent': intent_payload['normalized_intent'], 'domain_candidate': intent_payload['domain_candidate'], 'notes': intent_payload['notes'] or '无'}, ensure_ascii=False, indent=2)}\n"
        "</intent>\n\n"
        "<repo_discovery>\n"
        f"{json.dumps(discovery_payload, ensure_ascii=False, indent=2)}\n"
        "</repo_discovery>\n\n"
        "<example_output>\n"
        '{"role":"primary","likely_modules":["app/foo","service/bar"],'
        '"risks":["当前上下游边界仍需人工确认"],'
        '"facts":["candidate_files 命中 app/foo/handler.go"],'
        '"inferences":["该 repo 更可能承接主入口"],'
        '"open_questions":["是否还有未扫描的上游网关"]}\n'
        "</example_output>\n"
    )


def extract_repo_research_output(raw: str) -> dict[str, list[str] | str]:
    parsed = extract_json_object(raw)
    role = str(parsed.get("role") or "unknown").strip().lower()
    if role not in {"primary", "supporting", "unknown"}:
        role = "unknown"
    result = {
        "role": role,
        "likely_modules": _as_string_list(parsed.get("likely_modules"))[:6],
        "risks": _as_string_list(parsed.get("risks"))[:5],
        "facts": _as_string_list(parsed.get("facts"))[:5],
        "inferences": _as_string_list(parsed.get("inferences"))[:5],
        "open_questions": _as_string_list(parsed.get("open_questions"))[:5],
    }
    if not any(result[key] for key in ("likely_modules", "risks", "facts", "inferences", "open_questions")):
        raise ValueError("native repo research returned empty structured content")
    return result


def build_knowledge_synthesis_prompt(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    display_paths: list[str],
    requested_kinds: list[str],
) -> str:
    synthesis_input = {
        "normalized_intent": intent_payload["normalized_intent"],
        "domain_candidate": intent_payload["domain_candidate"],
        "domain_name": intent_payload["domain_name"],
        "requested_kinds": requested_kinds,
        "selected_paths": display_paths,
        "notes": intent_payload["notes"],
        "repo_research": repo_research_payloads,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Knowledge Synthesis。\n"
        "目标：根据结构化 repo research，生成 flow/domain/rule 草稿正文。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown 解释，不要包 code fence。\n"
        '2. JSON 结构必须是 {"documents": [...]}。\n'
        "3. 每个 document 必须包含 kind, title, desc, body, open_questions。\n"
        "4. flow 的 body 必须包含：## Summary, ## Main Flow, ## Selected Paths, ## Dependencies, ## Repo Hints, ## Open Questions。\n"
        "5. domain 的 body 必须包含：## Summary, ## Repo Coverage, ## Open Questions。\n"
        "6. rule 的 body 必须包含：## Statement, ## Evidence Risks, ## Open Questions。\n"
        "7. open_questions 要与 body 里的 Open Questions 对齐。\n"
        "8. 不要输出空泛模板话术；要优先利用 repo research 里的 role、likely_modules、facts、risks、open_questions。\n"
        "</success_criteria>\n\n"
        "<grounding_rules>\n"
        "- 只能使用输入里已有的 repo_id、路径、模块线索、事实和风险。\n"
        "- 如果证据弱，可以明确写“当前仅基于候选目录/文件推断”，但不要编造不存在的系统、接口或文件。\n"
        "- 优先写“这条链路如何经过这些 repo / 模块”，而不是重复意图描述。\n"
        "- 语言保持中文，代码路径和 repo_id 保持原样。\n"
        "- 避免使用“第一阶段草稿”“待补充”等程序味很重的话术，除非输入证据确实不足。\n"
        "</grounding_rules>\n\n"
        "<style>\n"
        "- Summary 用 2~4 句，直接说明链路或规则的核心。\n"
        "- Main Flow 用 3~6 条编号步骤，尽量写出 repo 角色或模块动作。\n"
        "- Dependencies / Repo Coverage / Evidence Risks 尽量引用具体 repo 和模块线索。\n"
        "- Open Questions 只保留真正未确认的问题，不要重复 Summary。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(synthesis_input, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"documents":[{"kind":"flow","title":"系统链路","desc":"归纳某能力的主链路和 repo hints。",'
        '"body":"## Summary\\n\\n该链路由 `repo-a` 承接入口，由 `repo-b` 提供下游能力。\\n\\n## Main Flow\\n\\n1. ...\\n\\n## Selected Paths\\n\\n- `/path/a`\\n\\n## Dependencies\\n\\n- `repo-a`: role=primary\\n\\n## Repo Hints\\n\\n### `repo-a`\\n\\n- role: `primary`\\n\\n## Open Questions\\n\\n- 是否存在额外上游网关",'
        '"open_questions":["是否存在额外上游网关"]}]}\n'
        "</example_output>\n"
    )


def extract_knowledge_synthesis_output(raw: str, requested_kinds: list[str]) -> dict[str, dict[str, object]]:
    payload = extract_json_object(raw)
    documents = payload.get("documents")
    if not isinstance(documents, list):
        raise ValueError("native knowledge synthesis did not return documents list")
    outputs: dict[str, dict[str, object]] = {}
    for item in documents:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in requested_kinds:
            continue
        outputs[kind] = {
            "title": str(item.get("title") or "").strip(),
            "desc": str(item.get("desc") or "").strip(),
            "body": str(item.get("body") or "").strip(),
            "open_questions": _as_string_list(item.get("open_questions")),
        }
    missing = [kind for kind in requested_kinds if kind not in outputs]
    if missing:
        raise ValueError(f"native knowledge synthesis missing kinds: {', '.join(missing)}")
    return outputs


def apply_synthesis_outputs(
    fallback_documents: list[KnowledgeDocument],
    outputs: dict[str, dict[str, object]],
    display_paths: list[str],
) -> list[KnowledgeDocument]:
    documents: list[KnowledgeDocument] = []
    for document in fallback_documents:
        output = outputs.get(document.kind)
        if output is None:
            raise ValueError(f"missing synthesis output for kind: {document.kind}")
        open_questions = unique_strings(
            [*output["open_questions"], *document.evidence.openQuestions]
        )
        body = str(output["body"] or document.body)
        body = normalize_selected_paths_section(body, display_paths)
        documents.append(
            document.model_copy(
                update={
                    "title": build_title(document.kind),
                    "desc": str(output["desc"] or document.desc),
                    "body": body,
                    "evidence": document.evidence.model_copy(
                        update={
                            "openQuestions": open_questions,
                        }
                    ),
                }
            )
        )
    return documents


def extract_json_object(raw: str) -> dict[str, object]:
    decoder = JSONDecoder()
    text = raw.strip()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("native repo research did not return a JSON object")


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return unique_strings([str(item) for item in value if str(item).strip()])


def build_display_paths(
    selected_paths: list[str],
    repo_research_payloads: list[dict[str, object]],
) -> list[str]:
    display_paths: list[str] = []
    for raw_path in selected_paths:
        current = str(raw_path).strip()
        if not current:
            continue
        display_paths.append(format_display_path(current, repo_research_payloads))
    return unique_strings(display_paths)


def format_display_path(path: str, repo_research_payloads: list[dict[str, object]]) -> str:
    target = Path(path).expanduser()
    try:
        resolved = target.resolve()
    except OSError:
        resolved = target

    best_match: tuple[int, str] | None = None
    for item in repo_research_payloads:
        repo_path = str(item.get("repo_path") or "").strip()
        repo_id = str(item.get("repo_id") or "").strip() or "repo"
        if not repo_path:
            continue
        repo_root = Path(repo_path).expanduser()
        try:
            relative = resolved.relative_to(repo_root.resolve())
        except (OSError, ValueError):
            continue
        rendered = f"{repo_id}:/" if str(relative) == "." else f"{repo_id}/{relative.as_posix()}"
        score = len(repo_root.as_posix())
        if best_match is None or score > best_match[0]:
            best_match = (score, rendered)
    if best_match is not None:
        return best_match[1]
    return resolved.name or path


def normalize_selected_paths_section(body: str, display_paths: list[str]) -> str:
    marker = "## Selected Paths"
    next_marker = "\n## "
    if marker not in body:
        return body
    start = body.find(marker)
    content_start = body.find("\n\n", start)
    if content_start == -1:
        return body
    content_start += 2
    next_section = body.find(next_marker, content_start)
    if next_section == -1:
        next_section = len(body)
    rendered_paths = "\n".join(f"- `{path}`" for path in display_paths) if display_paths else "- 待补充"
    return body[:content_start] + rendered_paths + body[next_section:]


def infer_domain_name(description: str) -> str:
    normalized = description
    for term in ("系统链路", "表达层", "默认业务规则", "业务规则", "链路"):
        normalized = normalized.replace(term, "")
    return normalized.strip() or description.strip() or "未命名领域"


def slugify_domain(name: str) -> str:
    if "讲解卡" in name:
        return "auction-explain-card"
    if "购物袋" in name:
        return "auction-shopping-bag"
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    if tokens:
        return "-".join(tokens[:4])
    return f"knowledge-{uuid.uuid4().hex[:8]}"


def infer_search_terms(description: str, notes: str, domain_candidate: str) -> list[str]:
    search_terms: list[str] = []
    for source in (description, notes):
        current = source.strip()
        if not current:
            continue
        search_terms.extend(term for term in re.findall(r"[A-Za-z0-9_/-]+", current.lower()) if len(term) >= 2)
        for literal in TERM_HINTS:
            if literal in current:
                search_terms.extend(TERM_HINTS[literal])
    search_terms.extend(domain_candidate.split("-"))
    search_terms.extend(re.findall(r"[\u4e00-\u9fff]{2,6}", description))
    return unique_strings([term for term in search_terms if len(term.strip()) >= 2])


def find_repo_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def scan_candidate_files(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    matched_files: list[str] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 1600:
            break
        relative_path = str(path.relative_to(root))
        haystack = relative_path.lower()
        hits = [term for term in search_terms if term.lower() in haystack]
        if not hits:
            continue
        matched_files.append(relative_path)
        matched_keywords.extend(hits)
        if len(matched_files) >= 24:
            break
    return matched_files, unique_strings(matched_keywords)


def iter_repo_files(root: Path):
    for current_root, dirnames, filenames in root.walk():
        dirnames[:] = [
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIR_NAMES and not dirname.startswith(".")
        ]
        for filename in filenames:
            path = current_root / filename
            if path.suffix.lower() not in SEARCHABLE_SUFFIXES:
                continue
            yield path


def scan_context_hits(context_root: Path, search_terms: list[str]) -> list[str]:
    if not context_root.is_dir():
        return []
    hits: list[str] = []
    for path in sorted(context_root.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in SEARCHABLE_SUFFIXES:
            continue
        if len(hits) >= 6:
            break
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = content.lower()
        matched = [term for term in search_terms if term.lower() in lowered]
        if not matched:
            continue
        relative_path = str(path.relative_to(context_root))
        hits.append(f"{relative_path} 命中 {', '.join(unique_strings(matched)[:4])}")
    return hits


def list_top_level_dirs(root: Path) -> list[str]:
    directories = [
        item.name
        for item in sorted(root.iterdir())
        if item.is_dir() and item.name not in SKIP_DIR_NAMES and not item.name.startswith(".")
    ]
    return directories[:6]


def slugify_repo_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "repo"


def unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        current = str(value).strip()
        if not current or current in result:
            continue
        result.append(current)
    return result
