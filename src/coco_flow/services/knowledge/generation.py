from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
from json import JSONDecodeError, JSONDecoder
from pathlib import Path
import json
import re
import subprocess
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
GENERIC_TERM_STOPWORDS = {
    "api",
    "app",
    "biz",
    "cmd",
    "common",
    "config",
    "context",
    "controller",
    "core",
    "default",
    "domain",
    "entry",
    "handler",
    "impl",
    "infra",
    "internal",
    "local",
    "main",
    "manager",
    "model",
    "module",
    "pkg",
    "repo",
    "request",
    "response",
    "route",
    "router",
    "rpc",
    "schema",
    "service",
    "task",
    "test",
    "types",
    "util",
    "utils",
}
LOW_SIGNAL_SEARCH_TERMS = {
    "flow",
    "knowledge",
    "pipeline",
    "talent",
}
SYMBOL_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9_]{2,}\b")
ROUTE_PATTERN = re.compile(r'["\'](/[^"\']+)["\']')
ANCHOR_PATH_KEYWORDS = {
    "router": 8,
    "route": 8,
    "handler": 7,
    "service": 6,
    "rpc": 6,
    "promotion": 5,
    "flash_sale": 7,
    "creator_promotion": 7,
    "exclusive": 7,
    "proto": 4,
    "pb_gen": 4,
    "idl": 4,
    "flow": 1,
    "pack": 1,
    "mw": 0,
}


@dataclass(frozen=True)
class KnowledgeDraftInput:
    title: str
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
    title = payload.title.strip()
    description = payload.description.strip()
    if not title:
        raise ValueError("title is required")
    if not description:
        raise ValueError("description is required")

    selected_paths = normalize_selected_paths(payload.selected_paths)
    if not selected_paths:
        raise ValueError("selected_paths is required")

    requested_kinds = normalize_kinds(payload.kinds)
    requested_executor = normalize_executor(settings.knowledge_executor)
    now = datetime.now().astimezone()
    trace_id = f"knowledge-{now:%Y%m%d}-{uuid.uuid4().hex[:8]}"
    repo_targets = assign_repo_ids([resolve_selected_path(Path(raw_path).expanduser()) for raw_path in selected_paths])
    _emit_progress(on_progress, "intent_normalizing", 10, "正在收敛描述和生成类型")
    intent_payload = build_intent_payload(title, description, requested_kinds, payload.notes)
    _emit_progress(on_progress, "term_mapping", 24, "正在对齐业务词和仓库术语")
    term_mapping_payload = build_term_mapping(intent_payload, repo_targets, settings, requested_executor)
    discovery_search_terms = unique_strings(
        [
            *[str(term) for term in intent_payload["search_terms"]],
            *[str(term) for term in term_mapping_payload["search_terms"]],
        ]
    )
    _emit_progress(on_progress, "repo_discovering", 40, "正在扫描已选路径和 repo 上下文")
    discovery_payload = [discover_repo(target, discovery_search_terms) for target in repo_targets]
    _emit_progress(on_progress, "anchor_selecting", 54, "正在筛选各 repo 的主锚点")
    anchor_selection_payloads = [
        build_anchor_selection(intent_payload, discovery, settings, requested_executor)
        for discovery in discovery_payload
    ]
    _emit_progress(on_progress, "repo_researching", 66, "正在归纳各 repo 在链路中的角色")
    repo_research_payloads = [
        build_repo_research(intent_payload, discovery, anchor_selection, settings, requested_executor)
        for discovery, anchor_selection in zip(discovery_payload, anchor_selection_payloads, strict=False)
    ]
    _emit_progress(on_progress, "synthesizing", 82, "正在生成知识草稿")
    documents = build_documents(
        intent_payload=intent_payload,
        term_mapping_payload=term_mapping_payload,
        anchor_selection_payloads=anchor_selection_payloads,
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
            *[str(question) for question in term_mapping_payload["open_questions"]],
            *collect_anchor_questions(anchor_selection_payloads),
            *collect_repo_questions(repo_research_payloads),
            *collect_document_questions(documents),
        ]
    )
    open_questions = unique_questions(open_questions)
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
        "term-mapping.json": term_mapping_payload,
        "repo-discovery.json": {
            "trace_id": trace_id,
            "requested_executor": requested_executor,
            "search_terms": discovery_search_terms,
            "repos": discovery_payload,
        },
        "anchor-selection.json": {
            "trace_id": trace_id,
            "requested_executor": requested_executor,
            "repos": anchor_selection_payloads,
        },
        "knowledge-draft.json": knowledge_draft_payload,
        "validation-result.json": validation_payload,
    }
    for anchor_payload in anchor_selection_payloads:
        trace_files[f"anchor-selection/{anchor_payload['repo_id']}.json"] = anchor_payload
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


def resolve_selected_path(raw_path: Path) -> dict[str, object]:
    resolved_path = raw_path.resolve()
    if not resolved_path.exists():
        raise ValueError(f"selected path not found: {raw_path}")

    requested_path = resolved_path if resolved_path.is_dir() else resolved_path.parent
    repo_root = find_repo_root(requested_path)
    scan_root = repo_root or requested_path
    agents_path = scan_root / "AGENTS.md"
    context_root = scan_root / ".livecoding" / "context"
    return {
        "repo_id": scan_root.name or requested_path.name,
        "requested_path": str(requested_path),
        "repo_path": str(scan_root),
        "is_git_repo": repo_root is not None,
        "agents_present": agents_path.is_file(),
        "context_present": context_root.is_dir(),
    }


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


def build_intent_payload(title: str, description: str, requested_kinds: list[str], notes: str) -> dict[str, object]:
    domain_name = infer_domain_name(title)
    domain_candidate = slugify_domain(domain_name)
    normalized_intent = title if "链路" in title else f"{title}系统链路"
    query_terms = infer_query_terms(title, description, notes)
    search_terms = infer_search_terms(query_terms, domain_candidate)
    open_questions = [
        "是否还有未选择但会影响主链路的上游或下游 repo。",
        "当前命中的候选文件是否已经覆盖真实入口。",
    ]
    return {
        "title": title,
        "description": description,
        "domain_candidate": domain_candidate,
        "domain_name": domain_name,
        "requested_kinds": requested_kinds,
        "normalized_intent": normalized_intent,
        "notes": notes.strip(),
        "query_terms": query_terms,
        "search_terms": search_terms,
        "open_questions": open_questions,
    }


def discover_repo(target: dict[str, object], search_terms: list[str]) -> dict[str, object]:
    scan_root = Path(str(target["repo_path"]))
    context_root = scan_root / ".livecoding" / "context"
    matched_files, path_keywords = scan_candidate_files(scan_root, search_terms)
    matched_dirs, dir_keywords = scan_candidate_dirs(scan_root, search_terms)
    route_hits, route_keywords = scan_route_hits(scan_root, search_terms)
    symbol_hits, symbol_keywords = scan_symbol_hits(scan_root, search_terms)
    commit_hits, commit_keywords = scan_recent_commit_hits(scan_root, search_terms)
    candidate_dirs = unique_strings(
        [
            *matched_dirs,
            *[str(Path(path).parent) for path in matched_files if str(Path(path).parent) != "."],
        ]
    )
    if not candidate_dirs:
        candidate_dirs = list_top_level_dirs(scan_root)
    context_hits = scan_context_hits(context_root, search_terms)
    return {
        "repo_id": target["repo_id"],
        "requested_path": target["requested_path"],
        "repo_path": target["repo_path"],
        "is_git_repo": target["is_git_repo"],
        "agents_present": target["agents_present"],
        "context_present": target["context_present"],
        "candidate_dirs": candidate_dirs[:8],
        "candidate_files": matched_files[:12],
        "route_hits": route_hits[:6],
        "symbol_hits": symbol_hits[:8],
        "commit_hits": commit_hits[:6],
        "matched_keywords": unique_strings([*path_keywords, *dir_keywords, *route_keywords, *symbol_keywords]),
        "commit_keywords": commit_keywords[:6],
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


def build_term_mapping(
    intent_payload: dict[str, object],
    repo_targets: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    repo_candidates = [collect_repo_term_candidates(target) for target in repo_targets]
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_term_mapping_native(intent_payload, repo_candidates, settings)
        except ValueError as error:
            local = build_term_mapping_local(intent_payload, repo_candidates)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_term_mapping_local(intent_payload, repo_candidates)


def collect_repo_term_candidates(target: dict[str, object]) -> dict[str, object]:
    root = Path(str(target["repo_path"]))
    return {
        "repo_id": target["repo_id"],
        "repo_path": target["repo_path"],
        "requested_path": target["requested_path"],
        "top_level_dirs": list_top_level_dirs(root),
        "file_terms": collect_repo_file_terms(root),
        "route_terms": collect_repo_route_terms(root),
        "symbol_terms": collect_repo_symbol_terms(root),
        "commit_terms": collect_recent_commit_keywords(root),
        "context_aliases": collect_context_aliases(root),
    }


def build_term_mapping_local(
    intent_payload: dict[str, object],
    repo_candidates: list[dict[str, object]],
) -> dict[str, object]:
    query_terms = [str(term) for term in intent_payload["query_terms"]]
    search_terms = [str(term) for term in intent_payload["search_terms"]]
    mapped_terms: list[dict[str, object]] = []
    for user_term in query_terms[:8]:
        repo_terms = infer_repo_terms_for_user_term(user_term, repo_candidates)
        if not repo_terms:
            continue
        repo_ids = [
            str(candidate["repo_id"])
            for candidate in repo_candidates
            if any(term in candidate_terms(candidate) for term in repo_terms)
        ]
        mapped_terms.append(
            {
                "user_term": user_term,
                "repo_terms": repo_terms[:6],
                "repo_ids": unique_strings(repo_ids),
                "confidence": "medium",
                "reason": "基于目录名、文件名和符号名做本地术语对齐。",
            }
        )
        search_terms.extend(repo_terms)
    open_questions = []
    if not mapped_terms:
        open_questions.append("当前业务词还没有稳定映射到 repo 术语，可能需要补充别名或更具体的模块名。")
    return {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "query_terms": query_terms,
        "repo_candidates": repo_candidates,
        "mapped_terms": mapped_terms,
        "search_terms": sanitize_search_terms(search_terms),
        "open_questions": unique_questions(open_questions),
    }


def build_term_mapping_native(
    intent_payload: dict[str, object],
    repo_candidates: list[dict[str, object]],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(repo_candidates[0]["repo_path"]) if repo_candidates else None
    raw = client.run_prompt_only(
        build_term_mapping_prompt(intent_payload, repo_candidates),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_term_mapping_output(raw)
    return {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "query_terms": [str(term) for term in intent_payload["query_terms"]],
        "repo_candidates": repo_candidates,
        "mapped_terms": parsed["mapped_terms"],
        "search_terms": sanitize_search_terms(
            [
                *[str(term) for term in intent_payload["search_terms"]],
                *[str(term) for term in parsed["search_terms"]],
            ]
        ),
        "open_questions": unique_questions(parsed["open_questions"]),
    }


def build_anchor_selection(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_anchor_selection_native(intent_payload, discovery, settings)
        except ValueError as error:
            local = build_anchor_selection_local(intent_payload, discovery)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_anchor_selection_local(intent_payload, discovery)


def build_anchor_selection_local(intent_payload: dict[str, object], discovery: dict[str, object]) -> dict[str, object]:
    anchors = extract_repo_anchors(discovery)
    anchors["route_signals"] = select_core_route_signals(anchors["route_signals"], intent_payload)
    strongest_terms = unique_strings(
        [
            *anchors["business_symbols"],
            *anchors["keywords"],
            *[str(term) for term in discovery.get("matched_keywords", []) if is_meaningful_term(str(term))],
        ]
    )[:8]
    discarded_noise = extract_discarded_noise(discovery, strongest_terms)
    open_questions: list[str] = []
    if not anchors["entry_files"]:
        open_questions.append("当前还没有稳定识别出入口文件，可能需要补充更具体的动作或接口名。")
    if not anchors["business_symbols"]:
        open_questions.append("当前还没有稳定识别出业务枚举或核心符号，可能需要补充业务术语。")
    return {
        "repo_id": discovery["repo_id"],
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "strongest_terms": strongest_terms,
        "entry_files": anchors["entry_files"],
        "business_symbols": anchors["business_symbols"],
        "route_signals": anchors["route_signals"],
        "discarded_noise": discarded_noise,
        "reason": "基于 route/file/symbol 信号做本地主锚点筛选。",
        "open_questions": unique_questions(open_questions),
    }


def build_anchor_selection_native(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    repo_path = str(discovery["repo_path"]).strip()
    raw = client.run_prompt_only(
        build_anchor_selection_prompt(intent_payload, discovery),
        settings.native_query_timeout,
        cwd=repo_path or None,
    )
    parsed = extract_anchor_selection_output(raw)
    fallback = build_anchor_selection_local(intent_payload, discovery)
    return fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "strongest_terms": parsed["strongest_terms"] or fallback["strongest_terms"],
        "entry_files": parsed["entry_files"] or fallback["entry_files"],
        "business_symbols": parsed["business_symbols"] or fallback["business_symbols"],
        "route_signals": select_core_route_signals(parsed["route_signals"] or fallback["route_signals"], intent_payload),
        "discarded_noise": unique_strings(parsed["discarded_noise"] + fallback["discarded_noise"]),
        "reason": parsed["reason"] or fallback["reason"],
        "open_questions": unique_questions(parsed["open_questions"] + fallback["open_questions"]),
    }


def build_repo_research(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    anchor_selection: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_repo_research_native(intent_payload, discovery, anchor_selection, settings)
        except ValueError as error:
            local = build_repo_research_local(intent_payload, discovery, anchor_selection)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_repo_research_local(intent_payload, discovery, anchor_selection)


def build_repo_research_local(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    anchor_selection: dict[str, object],
) -> dict[str, object]:
    matched_keywords = [str(item) for item in discovery["matched_keywords"]]
    candidate_dirs = [str(item) for item in discovery["candidate_dirs"]]
    candidate_files = [str(item) for item in discovery["candidate_files"]]
    route_hits = select_core_route_signals([str(item) for item in discovery.get("route_hits", [])], intent_payload)
    symbol_hits = [str(item) for item in discovery.get("symbol_hits", [])]
    commit_hits = [str(item) for item in discovery.get("commit_hits", [])]
    context_hits = [str(item) for item in discovery["context_hits"]]
    anchors = {
        "entry_files": [str(item) for item in anchor_selection.get("entry_files", [])],
        "business_symbols": [str(item) for item in anchor_selection.get("business_symbols", [])],
        "route_signals": [str(item) for item in anchor_selection.get("route_signals", [])],
        "keywords": [str(item) for item in anchor_selection.get("strongest_terms", [])],
    }
    primary = bool(candidate_files or matched_keywords or context_hits or symbol_hits or route_hits or commit_hits)
    role = "primary" if primary else "supporting"
    facts = [
        f"repo_path={discovery['repo_path']}",
        "git repo" if discovery["is_git_repo"] else "selected path is not inside a git repo",
        "AGENTS.md present" if discovery["agents_present"] else "AGENTS.md missing",
        "context present" if discovery["context_present"] else "context missing",
    ]
    if anchor_selection.get("strongest_terms"):
        facts.append(f"anchor strongest_terms={', '.join([str(item) for item in anchor_selection['strongest_terms'][:4]])}")
    if symbol_hits:
        facts.append(f"symbol_hits 命中 {len(symbol_hits)} 条")
    if route_hits:
        facts.append(f"route_hits 命中 {len(route_hits)} 条")
    if commit_hits:
        facts.append(f"recent_commit_hits 命中 {len(commit_hits)} 条")
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
    if not route_hits:
        risks.append("尚未命中明确路由或 API 入口，入口判断仍依赖 handler/service 线索。")
    if not symbol_hits:
        risks.append("尚未命中高信号符号名，主链路判断仍偏向路径和目录启发式。")
    if not context_hits:
        risks.append("未命中 repo context，链路推断主要来自目录、文件名和符号名。")
    if not discovery["agents_present"]:
        risks.append("缺少 AGENTS.md，仓库协作约束需要人工确认。")
    open_questions = [str(question) for question in anchor_selection.get("open_questions", [])]
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
        "likely_modules": rank_likely_modules(candidate_dirs, anchors, discovery)[:6],
        "candidate_files": unique_strings([*anchors["entry_files"], *candidate_files])[:8],
        "route_hits": route_hits,
        "risks": risks,
        "facts": facts,
        "inferences": inferences,
        "context_hits": context_hits,
        "symbol_hits": symbol_hits,
        "commit_hits": commit_hits,
        "anchors": anchors,
        "open_questions": unique_questions(open_questions),
        "matched_keywords": matched_keywords,
    }


def build_repo_research_native(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    anchor_selection: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    fallback = build_repo_research_local(intent_payload, discovery, anchor_selection)
    repo_path = str(discovery["repo_path"]).strip()
    if not repo_path:
        raise ValueError("native repo research missing repo_path")
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_readonly_agent(
        build_repo_research_prompt(intent_payload, discovery, anchor_selection),
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
        "open_questions": unique_questions(parsed["open_questions"] + fallback["open_questions"]),
    }
    return result


def build_documents(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
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
        term_mapping_payload=term_mapping_payload,
        anchor_selection_payloads=anchor_selection_payloads,
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
            term_mapping_payload=term_mapping_payload,
            anchor_selection_payloads=anchor_selection_payloads,
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
            term_mapping_payload=term_mapping_payload,
            anchor_selection_payloads=anchor_selection_payloads,
            synthesis_executor=EXECUTOR_LOCAL,
            repo_research_payloads=repo_research_payloads,
            synthesis_fallback_reason=str(error),
        )


def build_documents_local(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
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
    route_hits = unique_strings(
        [str(hit) for item in repo_research_payloads for hit in item.get("route_hits", [])]
    )
    candidate_files = unique_strings(
        [str(path) for item in repo_research_payloads for path in item["candidate_files"]]
    )
    symbol_hits = unique_strings(
        [str(hit) for item in repo_research_payloads for hit in item.get("symbol_hits", [])]
    )
    strongest_terms = unique_strings(
        [str(term) for item in repo_research_payloads for term in item.get("anchors", {}).get("keywords", [])]
    )
    keyword_matches = clean_document_keywords(
        [
            *[str(keyword) for item in repo_research_payloads for keyword in item["matched_keywords"]],
            *strongest_terms,
        ]
    )
    context_hits = unique_strings(
        [str(hit) for item in repo_research_payloads for hit in item["context_hits"]]
    )
    open_questions = unique_questions(
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
            body=soften_weak_claims(build_body(kind, intent_payload, repo_research_payloads, display_paths, open_questions)),
            evidence=KnowledgeEvidence(
                inputDescription=str(intent_payload["description"]),
                inputTitle=str(intent_payload["title"]),
                repoMatches=repo_ids,
                keywordMatches=keyword_matches,
                pathMatches=selected_paths,
                candidateFiles=candidate_files,
                contextHits=unique_strings([*route_hits[:4], *symbol_hits[:6], *context_hits]),
                retrievalNotes=[],
                openQuestions=open_questions,
            ),
        )
        documents.append(document)
    return annotate_documents(
        documents,
        requested_executor=requested_executor,
        term_mapping_payload=term_mapping_payload,
        anchor_selection_payloads=anchor_selection_payloads,
        synthesis_executor=synthesis_executor,
        notes=str(intent_payload["notes"]),
        repo_research_payloads=repo_research_payloads,
    )


def build_documents_native(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
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
        build_knowledge_synthesis_prompt(
            intent_payload,
            term_mapping_payload,
            anchor_selection_payloads,
            repo_research_payloads,
            display_paths,
            requested_kinds,
        ),
        settings.native_query_timeout,
        cwd=cwd,
    )
    outputs = extract_knowledge_synthesis_output(raw, requested_kinds)
    documents = apply_synthesis_outputs(fallback_documents, outputs, display_paths)
    documents = annotate_documents(
        documents,
        requested_executor=EXECUTOR_NATIVE,
        term_mapping_payload=term_mapping_payload,
        anchor_selection_payloads=anchor_selection_payloads,
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
        anchors = item.get("anchors", {})
        dirs = "\n".join(f"- `{path}`" for path in item["likely_modules"]) or "- 待补充"
        files = "\n".join(f"- `{path}`" for path in item["candidate_files"]) or "- 待补充"
        route_hits = "\n".join(f"- {hit}" for hit in item.get("route_hits", [])) or "- 未命中明确路由入口"
        symbol_hits = "\n".join(f"- {hit}" for hit in item.get("symbol_hits", [])) or "- 未命中高信号符号"
        commit_hits = "\n".join(f"- {hit}" for hit in item.get("commit_hits", [])) or "- 未命中相关提交标题"
        context_hits = "\n".join(f"- {hit}" for hit in item["context_hits"]) or "- 未命中 repo context"
        anchor_files = "\n".join(f"- `{path}`" for path in anchors.get("entry_files", [])) or "- 待补充"
        anchor_symbols = "\n".join(f"- `{value}`" for value in anchors.get("business_symbols", [])) or "- 待补充"
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
                    "#### Key Entry Files",
                    anchor_files,
                    "",
                    "#### Route Hits",
                    route_hits,
                    "",
                    "#### Business Symbols",
                    anchor_symbols,
                    "",
                    "#### Symbol Hits",
                    symbol_hits,
                    "",
                    "#### Recent Commit Hits",
                    commit_hits,
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
            "1. 根据用户标题、描述和补充材料收敛业务意图，并把选中的路径映射到 repo 或工作目录。",
            "2. 先做术语映射，把用户语言对齐到 repo 中的目录名、符号名和业务枚举。",
            "3. 基于目录结构、文件名、符号命中、提交标题、AGENTS.md 和 `.livecoding/context/` 做轻量 discovery。",
            "4. 先从 primary repo 开始确认入口和关键模块，再补 supporting repo 的依赖关系。",
            "5. 所有未确认内容都保留在 `Open Questions`，不直接提升为已批准知识。",
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


def collect_anchor_questions(anchor_selection_payloads: list[dict[str, object]]) -> list[str]:
    return [str(question) for item in anchor_selection_payloads for question in item["open_questions"]]


def collect_document_questions(documents: list[KnowledgeDocument]) -> list[str]:
    return [question for document in documents for question in document.evidence.openQuestions]


def summarize_research_executors(repo_research_payloads: list[dict[str, object]]) -> str:
    executors = unique_strings([str(item.get("executor") or EXECUTOR_LOCAL) for item in repo_research_payloads])
    if not executors:
        return EXECUTOR_LOCAL
    return ", ".join(executors)


def summarize_anchor_executors(anchor_selection_payloads: list[dict[str, object]]) -> str:
    executors = unique_strings([str(item.get("executor") or EXECUTOR_LOCAL) for item in anchor_selection_payloads])
    if not executors:
        return EXECUTOR_LOCAL
    return ", ".join(executors)


def annotate_documents(
    documents: list[KnowledgeDocument],
    *,
    requested_executor: str,
    term_mapping_payload: dict[str, object] | None = None,
    anchor_selection_payloads: list[dict[str, object]] | None = None,
    synthesis_executor: str,
    notes: str = "",
    repo_research_payloads: list[dict[str, object]] | None = None,
    synthesis_fallback_reason: str = "",
) -> list[KnowledgeDocument]:
    retrieval_notes = [
        (
            f"term mapping executor: {term_mapping_payload.get('executor', EXECUTOR_LOCAL)}"
            f" (requested={term_mapping_payload.get('requested_executor', EXECUTOR_LOCAL)})。"
            if term_mapping_payload
            else "term mapping executor: local。"
        ),
        (
            f"repo research executor: {summarize_research_executors(repo_research_payloads or [])}。"
            if repo_research_payloads
            else "repo research executor: local。"
        ),
        (
            f"anchor selection executor: {summarize_anchor_executors(anchor_selection_payloads or [])}。"
            if anchor_selection_payloads
            else "anchor selection executor: local。"
        ),
        f"knowledge synthesis executor: {synthesis_executor} (requested={requested_executor})。",
        "候选目录和文件只作为 Repo Hints，不应直接固化成长期代码地图。",
    ]
    if term_mapping_payload and term_mapping_payload.get("fallback_reason"):
        retrieval_notes.append(f"term mapping fallback: {term_mapping_payload['fallback_reason']}")
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


def build_term_mapping_prompt(intent_payload: dict[str, object], repo_candidates: list[dict[str, object]]) -> str:
    payload = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "query_terms": intent_payload["query_terms"],
        "repo_candidates": repo_candidates,
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Term Mapping。\n"
        "目标：把用户语言映射成 repo 里的真实术语，供后续 discovery/research 使用。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 mapped_terms, search_terms, open_questions 三个字段。\n"
        "3. mapped_terms 中每个对象必须包含 user_term, repo_terms, repo_ids, confidence, reason。\n"
        "4. repo_terms 只允许使用输入里出现过的目录名、文件名、路由片段、符号名或 commit 关键词。\n"
        "5. search_terms 是给 discovery 用的最终检索词，优先放最有辨识度的 repo 术语。\n"
        "6. confidence 只能是 high、medium、low。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- 优先把业务词映射到 repo 内高信号符号，例如 route/path、enum、常量、handler、service、rpc 名。\n"
        "- 如果多个 repo 都有候选词，优先保留最贴近当前意图的 2~4 个 repo 术语。\n"
        "- 不要只重复用户原词；尽量补充 repo 内真实写法，例如 CamelCase、snake_case、目录名。\n"
        "- 不要优先选择 commit 里出现的改造词、rebuild 词；只有它被路径或符号再次印证时才可使用。\n"
        "- 如果证据不足，把问题写进 open_questions，不要硬凑映射。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- repo_terms、repo_ids 和路径保持原样。\n"
        "- reason 简短明确，说明为什么认为这些词相关。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"mapped_terms":[{"user_term":"达人秒杀","repo_terms":["ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
        '"repo_ids":["live-promotion-api","live-promotion-core"],"confidence":"high",'
        '"reason":"repo 中同时出现 flash_sale 路由、CreatorPromotion 服务和 ExclusiveFlashSale 枚举"}],'
        '"search_terms":["达人秒杀","ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
        '"open_questions":["是否还存在 seller 侧的秒杀分支需要并行扫描"]}\n'
        "</example_output>\n"
    )


def extract_term_mapping_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native term mapping did not return a JSON object")
    mapped_terms_raw = payload.get("mapped_terms")
    if not isinstance(mapped_terms_raw, list):
        raise ValueError("native term mapping did not return mapped_terms list")
    mapped_terms: list[dict[str, object]] = []
    search_terms: list[str] = []
    for item in mapped_terms_raw:
        if not isinstance(item, dict):
            continue
        user_term = str(item.get("user_term") or "").strip()
        repo_terms = _as_string_list(item.get("repo_terms"))[:8]
        repo_ids = _as_string_list(item.get("repo_ids"))[:6]
        confidence = str(item.get("confidence") or "low").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        reason = str(item.get("reason") or "").strip()
        if not user_term or not repo_terms:
            continue
        mapped_terms.append(
            {
                "user_term": user_term,
                "repo_terms": repo_terms,
                "repo_ids": repo_ids,
                "confidence": confidence,
                "reason": reason,
            }
        )
        search_terms.extend(repo_terms)
    search_terms.extend(_as_string_list(payload.get("search_terms")))
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not mapped_terms and not search_terms:
        raise ValueError("native term mapping returned empty structured content")
    return {
        "mapped_terms": mapped_terms,
        "search_terms": unique_strings(search_terms),
        "open_questions": open_questions,
    }


def build_anchor_selection_prompt(intent_payload: dict[str, object], discovery: dict[str, object]) -> str:
    payload = {
        "normalized_intent": intent_payload["normalized_intent"],
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "repo_id": discovery["repo_id"],
        "candidate_dirs": discovery["candidate_dirs"],
        "candidate_files": discovery["candidate_files"],
        "route_hits": discovery.get("route_hits", []),
        "symbol_hits": discovery.get("symbol_hits", []),
        "commit_hits": discovery.get("commit_hits", []),
        "matched_keywords": discovery.get("matched_keywords", []),
        "commit_keywords": discovery.get("commit_keywords", []),
    }
    return (
        "<task>\n"
        "你在做 coco-flow knowledge generation 的 Anchor Selection。\n"
        "目标：从单个 repo 的广召回候选里筛出最能代表业务主链路的锚点。\n"
        "</task>\n\n"
        "<success_criteria>\n"
        "1. 只输出一个 JSON object，不要输出 markdown，不要包 code fence。\n"
        "2. JSON 必须包含 strongest_terms, entry_files, business_symbols, route_signals, discarded_noise, reason, open_questions。\n"
        "3. strongest_terms 最多 8 条，entry_files 最多 4 条，business_symbols 最多 6 条，route_signals 最多 4 条，discarded_noise 最多 6 条。\n"
        "4. 只能从输入候选里选择，不要编造不存在的文件、路由或符号。\n"
        "5. 要主动区分主锚点和噪音词，显式把噪音放进 discarded_noise。\n"
        "</success_criteria>\n\n"
        "<heuristics>\n"
        "- route/path、handler、service、rpc、enum、常量优先级最高。\n"
        "- commit 改造词、rebuild、pack、flow_task、middleware 一般视作噪音，除非被 route/file/symbol 再次印证。\n"
        "- 入口文件优先选择真正承接动作的 handler/service/router 文件，不要优先选 spec、archive 或泛文档。\n"
        "- strongest_terms 优先保留业务类型词和核心动作词，例如枚举、领域对象、主接口名。\n"
        "</heuristics>\n\n"
        "<style>\n"
        "- 输出语言用中文。\n"
        "- 文件路径、路由、符号名保持原样。\n"
        "- reason 要说明为什么这些是主锚点、为什么某些候选被丢弃。\n"
        "</style>\n\n"
        "<input>\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "</input>\n\n"
        "<example_output>\n"
        '{"strongest_terms":["ExclusiveFlashSale","CreatorPromotion","flash_sale"],'
        '"entry_files":["biz/router/live_serv/oec_live_promotion_api.go","biz/service/flash_sale/create_promotion.go"],'
        '"business_symbols":["CreatorPromotionType_ExclusiveFlashSale","PromotionType_ExclusiveFlashSale"],'
        '"route_signals":["biz/router/live_serv/oec_live_promotion_api.go#/flash_sale"],'
        '"discarded_noise":["flash_sale_rebuild","flow_task","pack链路"],'
        '"reason":"route、service 和业务枚举直接描述达人秒杀主链路，rebuild/flow_task/pack 更像改造背景或实现细节。",'
        '"open_questions":["启动动作对应的具体 API 子路径是什么"]}\n'
        "</example_output>\n"
    )


def extract_anchor_selection_output(raw: str) -> dict[str, object]:
    payload = extract_json_object(raw, "native anchor selection did not return a JSON object")
    strongest_terms = _as_string_list(payload.get("strongest_terms"))[:8]
    entry_files = _as_string_list(payload.get("entry_files"))[:4]
    business_symbols = _as_string_list(payload.get("business_symbols"))[:6]
    route_signals = _as_string_list(payload.get("route_signals"))[:4]
    discarded_noise = _as_string_list(payload.get("discarded_noise"))[:6]
    reason = str(payload.get("reason") or "").strip()
    open_questions = _as_string_list(payload.get("open_questions"))[:6]
    if not any([strongest_terms, entry_files, business_symbols, route_signals]):
        raise ValueError("native anchor selection returned empty structured content")
    return {
        "strongest_terms": strongest_terms,
        "entry_files": entry_files,
        "business_symbols": business_symbols,
        "route_signals": route_signals,
        "discarded_noise": discarded_noise,
        "reason": reason,
        "open_questions": open_questions,
    }


def build_repo_research_prompt(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    anchor_selection: dict[str, object],
) -> str:
    discovery_payload = {
        "repo_id": discovery["repo_id"],
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "agents_present": discovery["agents_present"],
        "context_present": discovery["context_present"],
        "candidate_dirs": discovery["candidate_dirs"],
        "candidate_files": discovery["candidate_files"],
        "route_hits": discovery.get("route_hits", []),
        "symbol_hits": discovery.get("symbol_hits", []),
        "commit_hits": discovery.get("commit_hits", []),
        "matched_keywords": discovery["matched_keywords"],
        "context_hits": discovery["context_hits"],
    }
    anchor_payload = {
        "strongest_terms": anchor_selection.get("strongest_terms", []),
        "entry_files": anchor_selection.get("entry_files", []),
        "business_symbols": anchor_selection.get("business_symbols", []),
        "route_signals": anchor_selection.get("route_signals", []),
        "discarded_noise": anchor_selection.get("discarded_noise", []),
        "reason": anchor_selection.get("reason", ""),
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
        "- anchor_selection 里的 strongest_terms、entry_files、business_symbols 应视作主判断依据。\n"
        "- candidate_files、route_hits、symbol_hits、candidate_dirs、context_hits 越集中，越倾向 primary。\n"
        "- route/path、handler、service、rpc、enum 比 middleware、flow、pack、commit 改造词更能代表主链路。\n"
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
        "<anchor_selection>\n"
        f"{json.dumps(anchor_payload, ensure_ascii=False, indent=2)}\n"
        "</anchor_selection>\n\n"
        "<example_output>\n"
        '{"role":"primary","likely_modules":["app/foo","service/bar"],'
        '"risks":["当前上下游边界仍需人工确认"],'
        '"facts":["candidate_files 命中 app/foo/handler.go"],'
        '"inferences":["该 repo 更可能承接主入口"],'
        '"open_questions":["是否还有未扫描的上游网关"]}\n'
        "</example_output>\n"
    )


def extract_repo_research_output(raw: str) -> dict[str, list[str] | str]:
    parsed = extract_json_object(raw, "native repo research did not return a JSON object")
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
    term_mapping_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
    display_paths: list[str],
    requested_kinds: list[str],
) -> str:
    synthesis_input = {
        "title": intent_payload["title"],
        "description": intent_payload["description"],
        "normalized_intent": intent_payload["normalized_intent"],
        "domain_candidate": intent_payload["domain_candidate"],
        "domain_name": intent_payload["domain_name"],
        "requested_kinds": requested_kinds,
        "selected_paths": display_paths,
        "notes": intent_payload["notes"],
        "term_mapping": {
            "mapped_terms": term_mapping_payload.get("mapped_terms", []),
            "search_terms": term_mapping_payload.get("search_terms", []),
        },
        "anchor_selection": anchor_selection_payloads,
        "repo_anchors": [
            {
                "repo_id": item["repo_id"],
                "anchors": item.get("anchors", {}),
                "route_hits": item.get("route_hits", []),
            }
            for item in repo_research_payloads
        ],
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
        "- 优先以 repo_anchors 里的 entry_files、business_symbols、route_hits 为主线，不要把实现细节模块当成主入口。\n"
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
    payload = extract_json_object(raw, "native knowledge synthesis did not return a JSON object")
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
        body = soften_weak_claims(body)
        documents.append(
            document.model_copy(
                update={
                    "title": build_title(document.kind),
                    "desc": str(output["desc"] or document.desc),
                    "body": body,
                    "evidence": document.evidence.model_copy(
                        update={
                            "openQuestions": unique_questions(open_questions),
                        }
                    ),
                }
            )
        )
    return documents


def extract_json_object(raw: str, error_message: str) -> dict[str, object]:
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
    raise ValueError(error_message)


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return unique_strings([str(item) for item in value if str(item).strip()])


def unique_questions(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        current = str(value).strip()
        if not current:
            continue
        normalized = normalize_question_key(current)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(current)
    return result


def normalize_question_key(value: str) -> str:
    current = str(value).strip().lower()
    current = current.replace("`", "")
    current = current.replace("（", "(").replace("）", ")")
    current = re.sub(r"[\s\u3000]+", "", current)
    current = re.sub(r"[。！？!?,，、:：;；'\"()\[\]{}<>]+", "", current)
    return current


def soften_weak_claims(body: str) -> str:
    softened = body
    replacements = {
        "可能参与处理。": "当前线索显示其可能参与处理，仍需进一步确认。",
        "可能参与处理": "当前线索显示其可能参与处理，仍需进一步确认",
        "可能调用": "当前更像会调用，仍需进一步确认",
        "可能用于": "当前更像用于，仍需进一步确认",
        "可能与": "当前线索显示可能与",
        "可能由": "当前线索显示可能由",
    }
    for source, target in replacements.items():
        softened = softened.replace(source, target)
    softened = re.sub(r"涉及分布式事务场景时，`([^`]+)` 的 `([^`]+)` 模块可能参与处理。", r"涉及分布式事务场景时，当前线索显示 `\1` 的 `\2` 模块可能参与处理，仍需进一步确认。", softened)
    return softened


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


def infer_domain_name(title: str) -> str:
    normalized = title
    for term in ("系统链路", "表达层", "默认业务规则", "业务规则", "链路"):
        normalized = normalized.replace(term, "")
    return normalized.strip() or title.strip() or "未命名领域"


def slugify_domain(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    if tokens:
        return "-".join(tokens[:4])
    stable_hash = hashlib.sha1(name.strip().encode("utf-8")).hexdigest()[:8]
    return f"knowledge-{stable_hash}"


def infer_query_terms(title: str, description: str, notes: str) -> list[str]:
    terms: list[str] = []
    for source in (title, description, notes):
        current = source.strip()
        if not current:
            continue
        terms.extend(term for term in re.findall(r"[A-Za-z0-9_/-]+", current) if len(term) >= 2)
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,8}", current))
    return unique_strings(terms)


def infer_search_terms(query_terms: list[str], domain_candidate: str) -> list[str]:
    search_terms: list[str] = list(query_terms)
    search_terms.extend([part for part in domain_candidate.split("-") if part])
    return sanitize_search_terms([term for term in search_terms if len(str(term).strip()) >= 2])


def candidate_terms(candidate: dict[str, object]) -> list[str]:
    return unique_strings(
        [
            *[str(item) for item in candidate.get("top_level_dirs", [])],
            *[str(item) for item in candidate.get("file_terms", [])],
            *[str(item) for item in candidate.get("route_terms", [])],
            *[str(item) for item in candidate.get("symbol_terms", [])],
            *[str(item) for item in candidate.get("commit_terms", [])],
        ]
    )


def infer_repo_terms_for_user_term(user_term: str, repo_candidates: list[dict[str, object]]) -> list[str]:
    repo_terms: list[str] = []
    for candidate in repo_candidates:
        for alias in candidate.get("context_aliases", []):
            if not isinstance(alias, dict):
                continue
            source_terms = [str(item) for item in alias.get("source_terms", [])]
            if not any(score_term_match(user_term, source_term) > 0 for source_term in source_terms):
                continue
            repo_terms.extend(str(item) for item in alias.get("repo_terms", []))
        for repo_term in candidate_terms(candidate):
            if score_term_match(user_term, repo_term) <= 0:
                continue
            repo_terms.append(repo_term)
    return unique_strings([term for term in repo_terms if is_meaningful_term(term)])[:8]


def normalize_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value.lower())


def split_match_tokens(value: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", value)
    parts: list[str] = []
    for token in tokens:
        parts.extend(part for part in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+", token) if part)
    normalized = [part.lower() for part in parts if len(part) >= 2]
    if "_" in value or "-" in value or "/" in value:
        normalized.extend(part.lower() for part in re.split(r"[_/\-]+", value) if len(part) >= 2)
    return unique_strings(normalized)


def score_term_match(user_term: str, repo_term: str) -> int:
    normalized_user = normalize_match_text(user_term)
    normalized_repo = normalize_match_text(repo_term)
    if not normalized_user or not normalized_repo:
        return 0
    if normalized_user in normalized_repo or normalized_repo in normalized_user:
        return 3
    user_tokens = set(split_match_tokens(user_term))
    repo_tokens = set(split_match_tokens(repo_term))
    overlap = len(user_tokens & repo_tokens)
    if overlap:
        return overlap + 1
    return 0


def is_meaningful_term(value: str) -> bool:
    current = str(value).strip()
    if len(current) < 2:
        return False
    if current.lower() in GENERIC_TERM_STOPWORDS:
        return False
    return True


def sanitize_search_terms(values: list[str]) -> list[str]:
    sanitized: list[str] = []
    for value in values:
        current = str(value).strip()
        lowered = current.lower()
        if not current:
            continue
        if lowered in LOW_SIGNAL_SEARCH_TERMS:
            continue
        if lowered in {"knowledge", "talent", "pipeline"}:
            continue
        if lowered in GENERIC_TERM_STOPWORDS and "_" not in current and current == lowered:
            continue
        sanitized.append(current)
    return unique_strings(sanitized)


def clean_document_keywords(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen_normalized: set[str] = set()
    for value in values:
        current = str(value).strip()
        if not current:
            continue
        normalized = normalize_keyword_for_document(current)
        if not normalized:
            continue
        dedupe_key = normalized.lower()
        if dedupe_key in seen_normalized:
            continue
        seen_normalized.add(dedupe_key)
        cleaned.append(normalized)
    return cleaned


def normalize_keyword_for_document(value: str) -> str:
    current = str(value).strip()
    lowered = current.lower()
    if not current:
        return ""
    if re.fullmatch(r"[a-f0-9]{8,}", lowered):
        return ""
    if lowered.startswith("knowledge-"):
        return ""
    if lowered in LOW_SIGNAL_SEARCH_TERMS:
        return ""
    if lowered in {"flash", "sale", "create", "update", "launch", "deactivate", "operate", "save"}:
        return ""
    if lowered in {"live promotion", "live_promotion"}:
        return ""
    if " " in current and current.lower() == current:
        current = current.replace(" ", "_")
        lowered = current.lower()
    if re.fullmatch(r"[A-Z][a-z]+", current):
        current = lowered
    return current


def find_repo_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def scan_candidate_files(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    matched_files: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 1600:
            break
        relative_path = str(path.relative_to(root))
        hits = matched_search_terms(relative_path, search_terms)
        if not hits:
            continue
        matched_files.append((score_path_signal(relative_path, hits), relative_path))
        matched_keywords.extend(hits)
    matched_files.sort(key=lambda item: (-item[0], item[1]))
    return [path for _, path in matched_files[:24]], unique_strings(matched_keywords)


def scan_candidate_dirs(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    scored_dirs: dict[str, int] = {}
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 1200:
            break
        relative_path = Path(path.relative_to(root))
        for parent in relative_path.parents:
            current = str(parent)
            if current in {"", "."}:
                continue
            hits = matched_search_terms(current, search_terms)
            if not hits:
                continue
            scored_dirs[current] = max(scored_dirs.get(current, 0), score_path_signal(current, hits))
            matched_keywords.extend(hits)
    matched_dirs = [path for path, _ in sorted(scored_dirs.items(), key=lambda item: (-item[1], item[0]))]
    return matched_dirs[:16], unique_strings(matched_keywords)


def scan_route_hits(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    hits: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 240:
            break
        relative_path = str(path.relative_to(root))
        if not any(token in relative_path.lower() for token in ("router", "route", "handler", "api")):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for route in unique_strings(ROUTE_PATTERN.findall(content))[:24]:
            current_hits = matched_search_terms(route, search_terms)
            if not current_hits:
                continue
            rendered = f"{relative_path}#{route} 命中 {', '.join(current_hits[:3])}"
            hits.append((score_path_signal(relative_path, current_hits) + 6, rendered))
            matched_keywords.extend(current_hits)
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, item in hits[:8]], unique_strings(matched_keywords)


def scan_symbol_hits(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    hits: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 180:
            break
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > 120_000:
            content = content[:120_000]
        identifiers = unique_strings(SYMBOL_PATTERN.findall(content))[:120]
        for identifier in identifiers:
            current_hits = matched_search_terms(identifier, search_terms)
            if not current_hits:
                continue
            relative_path = str(path.relative_to(root))
            hits.append(
                (
                    score_symbol_signal(relative_path, identifier, current_hits),
                    f"{relative_path}#{identifier} 命中 {', '.join(current_hits[:3])}",
                )
            )
            matched_keywords.extend(current_hits)
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, item in hits[:12]], unique_strings(matched_keywords)


def scan_recent_commit_hits(root: Path, search_terms: list[str]) -> tuple[list[str], list[str]]:
    commit_titles = collect_recent_commit_terms(root, limit=20)
    hits: list[tuple[int, str]] = []
    matched_keywords: list[str] = []
    for title in commit_titles:
        current_hits = matched_search_terms(title, search_terms)
        if not current_hits:
            continue
        hits.append((score_commit_signal(title, current_hits), f"{title} 命中 {', '.join(current_hits[:3])}"))
        matched_keywords.extend(current_hits)
    hits.sort(key=lambda item: (-item[0], item[1]))
    return [item for _, item in hits[:6]], unique_strings(matched_keywords[:12])


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


def collect_repo_file_terms(root: Path, limit: int = 24) -> list[str]:
    terms: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 180:
            break
        relative_path = str(path.relative_to(root))
        terms.extend(extract_path_terms(relative_path))
        if len(unique_strings(terms)) >= limit:
            break
    return [term for term in unique_strings(terms) if is_meaningful_term(term)][:limit]


def collect_repo_route_terms(root: Path, limit: int = 18) -> list[str]:
    terms: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 200:
            break
        relative_path = str(path.relative_to(root))
        if not any(token in relative_path.lower() for token in ("router", "route", "handler", "api")):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for route in unique_strings(ROUTE_PATTERN.findall(content))[:24]:
            for token in re.split(r"[/_\-]+", route):
                if is_meaningful_term(token):
                    terms.append(token)
    return unique_strings(terms)[:limit]


def collect_context_aliases(root: Path, limit: int = 16) -> list[dict[str, list[str]]]:
    candidates = [
        root / ".livecoding" / "context",
        root / "AGENTS.md",
        root / "README.md",
        root / "README.zh-CN.md",
    ]
    aliases: list[dict[str, list[str]]] = []
    for candidate in candidates:
        if candidate.is_dir():
            paths = sorted(path for path in candidate.rglob("*") if path.is_file() and path.suffix.lower() in SEARCHABLE_SUFFIXES)
        elif candidate.is_file():
            paths = [candidate]
        else:
            continue
        for path in paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for line in lines[:120]:
                source_terms = unique_strings(re.findall(r"[\u4e00-\u9fff]{2,8}", line))
                repo_terms = unique_strings(
                    [
                        token
                        for token in re.findall(r"[A-Za-z0-9_/-]+", line)
                        if len(token) >= 2 and is_meaningful_term(token)
                    ]
                )
                if not source_terms or not repo_terms:
                    continue
                aliases.append({"source_terms": source_terms[:4], "repo_terms": repo_terms[:6]})
                if len(aliases) >= limit:
                    return aliases[:limit]
    return aliases[:limit]


def collect_repo_symbol_terms(root: Path, limit: int = 28) -> list[str]:
    terms: list[str] = []
    scanned = 0
    for path in iter_repo_files(root):
        scanned += 1
        if scanned > 120:
            break
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(content) > 120_000:
            content = content[:120_000]
        for identifier in unique_strings(SYMBOL_PATTERN.findall(content)):
            if not is_meaningful_term(identifier):
                continue
            if identifier.lower() in GENERIC_TERM_STOPWORDS:
                continue
            terms.append(identifier)
            if len(unique_strings(terms)) >= limit:
                return unique_strings(terms)[:limit]
    return unique_strings(terms)[:limit]


def collect_recent_commit_terms(root: Path, limit: int = 12) -> list[str]:
    git_dir = root / ".git"
    if not git_dir.exists():
        return []
    try:
        completed = subprocess.run(
            ["git", "log", "-n", str(max(limit, 20)), "--pretty=%s"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if completed.returncode != 0:
        return []
    titles = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return unique_strings(titles)[:limit]


def collect_recent_commit_keywords(root: Path, limit: int = 12) -> list[str]:
    keywords: list[str] = []
    for title in collect_recent_commit_terms(root, limit=max(limit, 20)):
        for token in split_match_tokens(title):
            if not is_meaningful_term(token):
                continue
            if token in {"merge", "branch", "master", "feat", "fix", "development", "task", "build", "pass"}:
                continue
            keywords.append(token)
            if len(unique_strings(keywords)) >= limit:
                return unique_strings(keywords)[:limit]
    return unique_strings(keywords)[:limit]


def extract_path_terms(relative_path: str) -> list[str]:
    parts = list(Path(relative_path).parts)
    stem = Path(relative_path).stem
    terms: list[str] = []
    for part in [*parts, stem]:
        terms.extend(split_match_tokens(part))
        if is_meaningful_term(part):
            terms.append(part)
    return unique_strings(terms)


def matched_search_terms(text: str, search_terms: list[str]) -> list[str]:
    matches: list[str] = []
    normalized_text = normalize_match_text(text)
    text_tokens = set(split_match_tokens(text))
    for term in search_terms:
        current = str(term).strip()
        normalized_term = normalize_match_text(current)
        if not normalized_term:
            continue
        if normalized_term in normalized_text or normalized_text in normalized_term:
            matches.append(current)
            continue
        term_tokens = set(split_match_tokens(current))
        if term_tokens and term_tokens & text_tokens:
            matches.append(current)
    return unique_strings(matches)


def score_path_signal(path: str, hits: list[str]) -> int:
    score = len(unique_strings(hits)) * 10
    lowered = path.lower()
    for keyword, bonus in ANCHOR_PATH_KEYWORDS.items():
        if keyword in lowered:
            score += bonus
    return score


def score_symbol_signal(path: str, identifier: str, hits: list[str]) -> int:
    score = score_path_signal(path, hits) + len(split_match_tokens(identifier))
    lowered = identifier.lower()
    for keyword, bonus in ANCHOR_PATH_KEYWORDS.items():
        if keyword in lowered:
            score += bonus + 1
    if any(token in identifier for token in ("Request", "Response", "Service", "Handler", "Promotion", "FlashSale", "Exclusive")):
        score += 4
    return score


def score_commit_signal(title: str, hits: list[str]) -> int:
    score = len(unique_strings(hits)) * 4
    lowered = title.lower()
    if "rebuild" in lowered:
        score -= 3
    if "merge branch" in lowered:
        score -= 4
    if any(token in lowered for token in ("flash_sale", "creator", "promotion", "exclusive", "秒杀")):
        score += 2
    return score


def extract_repo_anchors(discovery: dict[str, object]) -> dict[str, list[str]]:
    candidate_files = [str(item) for item in discovery.get("candidate_files", [])]
    route_hits = [str(item) for item in discovery.get("route_hits", [])]
    symbol_hits = [str(item) for item in discovery.get("symbol_hits", [])]
    matched_keywords = [str(item) for item in discovery.get("matched_keywords", [])]
    entry_files = [
        path
        for path in candidate_files
        if any(token in path.lower() for token in ("router", "route", "handler", "service", "rpc"))
    ][:4]
    if not entry_files:
        entry_files = candidate_files[:4]
    business_symbols: list[str] = []
    for hit in symbol_hits:
        _, _, tail = hit.partition("#")
        identifier = tail.split(" 命中 ", 1)[0].strip()
        if not identifier:
            continue
        business_symbols.append(identifier)
    return {
        "entry_files": unique_strings(entry_files)[:4],
        "business_symbols": unique_strings([value for value in business_symbols if is_meaningful_term(value)])[:6],
        "route_signals": unique_strings(route_hits)[:4],
        "keywords": unique_strings([value for value in matched_keywords if is_meaningful_term(value)])[:6],
    }


def derive_modules_from_entry_files(entry_files: list[str]) -> list[str]:
    modules: list[str] = []
    for raw_path in entry_files:
        parent = str(Path(raw_path).parent)
        if parent in {"", "."}:
            continue
        modules.append(parent)
    return unique_strings(modules)


def select_core_route_signals(route_signals: list[str], intent_payload: dict[str, object]) -> list[str]:
    scored: list[tuple[int, str]] = []
    intent_text = " ".join([str(intent_payload.get("title") or ""), str(intent_payload.get("description") or "")]).lower()
    has_business_prefix = any(any(token in str(signal).lower() for token in ("/flash_sale", "/live_promotion")) for signal in route_signals)
    for signal in route_signals:
        current = str(signal).strip()
        lowered = current.lower()
        score = 0
        if "/flash_sale" in lowered or "/live_promotion" in lowered:
            score += 8
        if any(token in lowered for token in ("/create", "/update", "/launch", "/deactivate", "/delete", "/status")):
            score += 5
        if has_business_prefix and not any(token in lowered for token in ("/flash_sale", "/live_promotion")):
            score -= 8
        if "/operate" in lowered:
            score -= 6
        if "/save_template" in lowered or "/template" in lowered:
            score -= 12
        if "启动" in intent_text and any(token in lowered for token in ("/launch", "/status")):
            score += 2
        if "更新" in intent_text and "/update" in lowered:
            score += 2
        if "删除" in intent_text and any(token in lowered for token in ("/delete", "/deactivate")):
            score += 2
        scored.append((score, current))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [value for score, value in scored if score > 0][:3]
    if selected:
        return unique_strings(selected)
    return unique_strings(route_signals[:2])


def rank_likely_modules(
    candidate_dirs: list[str],
    anchors: dict[str, list[str]],
    discovery: dict[str, object],
) -> list[str]:
    strongest_terms = [str(item).lower() for item in anchors.get("keywords", [])]
    entry_modules = derive_modules_from_entry_files(anchors.get("entry_files", []))
    scored: dict[str, int] = {}
    for module in candidate_dirs:
        lowered = module.lower()
        score = 0
        if module in entry_modules:
            score += 12
        if any(term and term.replace("_", "").lower() in lowered.replace("_", "") for term in strongest_terms):
            score += 6
        if any(token in lowered for token in ("router", "route", "handler", "service", "rpc", "flash_sale", "promotion")):
            score += 4
        if any(token in lowered for token in ("billboard", "flow_task", "packer", "archive", "openspec", "specs", "developing")):
            score -= 6
        scored[module] = score
    ranked = [value for value, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))]
    return unique_strings([*entry_modules, *ranked])


def extract_discarded_noise(discovery: dict[str, object], strongest_terms: list[str]) -> list[str]:
    strongest = {str(item).lower() for item in strongest_terms}
    noise: list[str] = []
    for source in (
        discovery.get("commit_keywords", []),
        discovery.get("matched_keywords", []),
    ):
        for item in source:
            current = str(item).strip()
            lowered = current.lower()
            if not current or lowered in strongest:
                continue
            if any(token in lowered for token in ("rebuild", "merge", "pack", "flow", "mw", "middleware", "pipeline")):
                noise.append(current)
    for path in discovery.get("candidate_files", []):
        current = str(path).strip()
        lowered = current.lower()
        if any(token in lowered for token in ("openspec/", "/spec.", "archive/", "readme", "build.sh")):
            noise.append(current)
    return unique_strings(noise)[:6]


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
