from __future__ import annotations

import uuid

from coco_flow.models.knowledge import KnowledgeDocument, KnowledgeEvidence

from .common import (
    EXECUTOR_LOCAL,
    EXECUTOR_NATIVE,
    KNOWLEDGE_KIND_ORDER,
    build_display_paths,
    clean_document_keywords,
    normalize_selected_paths_section,
    soften_weak_claims,
    unique_questions,
    unique_strings,
)


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
                "evidence": document.evidence.model_copy(update={"retrievalNotes": retrieval_notes}),
            }
        )
        for document in documents
    ]


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
        open_questions = unique_strings([*output["open_questions"], *document.evidence.openQuestions])
        body = str(output["body"] or document.body)
        body = normalize_selected_paths_section(body, display_paths)
        body = soften_weak_claims(body)
        documents.append(
            document.model_copy(
                update={
                    "title": build_title(document.kind),
                    "desc": str(output["desc"] or document.desc),
                    "body": body,
                    "evidence": document.evidence.model_copy(update={"openQuestions": unique_questions(open_questions)}),
                }
            )
        )
    return documents


def build_documents_local(
    *,
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
    route_hits = unique_strings([str(hit) for item in repo_research_payloads for hit in item.get("route_hits", [])])
    candidate_files = unique_strings([str(path) for item in repo_research_payloads for path in item["candidate_files"]])
    symbol_hits = unique_strings([str(hit) for item in repo_research_payloads for hit in item.get("symbol_hits", [])])
    strongest_terms = unique_strings([str(term) for item in repo_research_payloads for term in item.get("anchors", {}).get("keywords", [])])
    keyword_matches = clean_document_keywords(
        [*[str(keyword) for item in repo_research_payloads for keyword in item["matched_keywords"]], *strongest_terms]
    )
    context_hits = unique_strings([str(hit) for item in repo_research_payloads for hit in item["context_hits"]])
    open_questions = unique_questions([str(question) for item in repo_research_payloads for question in item["open_questions"]])
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
