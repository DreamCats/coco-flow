from __future__ import annotations

import re
import uuid

from coco_flow.models.knowledge import KnowledgeDocument, KnowledgeEvidence

from .common import (
    EXECUTOR_LOCAL,
    EXECUTOR_NATIVE,
    KNOWLEDGE_KIND_ORDER,
    soften_weak_claims,
    unique_questions,
    unique_strings,
)


FLOW_REQUIRED_SECTIONS = (
    "## Summary",
    "## Main Flow",
    "## Dependencies",
    "## Repo Hints",
    "## Open Questions",
)
DOMAIN_REQUIRED_SECTIONS = (
    "## Summary",
    "## Repo Coverage",
    "## Open Questions",
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
        return f"归纳 {normalized_intent} 的主链路、关键仓库职责和系统依赖。"
    if kind == "rule":
        return f"整理 {normalized_intent} 相关的稳定约束和待确认边界。"
    return f"概览 {normalized_intent} 对应的业务方向、关键仓库和边界范围。"


def build_body(
    kind: str,
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    storyline_outline_payload: dict[str, object],
    open_questions: list[str],
) -> str:
    if kind == "flow":
        return build_flow_body(intent_payload, repo_research_payloads, storyline_outline_payload, open_questions)
    if kind == "rule":
        return build_rule_body(intent_payload, repo_research_payloads, open_questions)
    return build_domain_body(intent_payload, storyline_outline_payload, open_questions)


def build_flow_body(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    storyline_outline_payload: dict[str, object],
    open_questions: list[str],
) -> str:
    repo_hints = _as_outline_hints(storyline_outline_payload.get("repo_hints"))
    summary_lines = _normalize_lines(storyline_outline_payload.get("system_summary"))
    if not summary_lines:
        summary_lines = [
            f"{intent_payload['normalized_intent']} 主要围绕入口收敛、主数据编排和前端展示装配展开。"
        ]
    main_flow_steps = _normalize_lines(storyline_outline_payload.get("main_flow_steps"))
    if not main_flow_steps:
        main_flow_steps = build_storyline_steps_from_research(repo_hints, repo_research_payloads)
    dependency_lines = _normalize_lines(storyline_outline_payload.get("dependencies"))
    if not dependency_lines:
        dependency_lines = build_dependency_lines_from_research(repo_hints, repo_research_payloads)
    question_lines = unique_questions(open_questions) or ["当前仍需确认是否存在额外上游或下游仓库。"]
    return "\n".join(
        [
            "## Summary",
            "",
            *_paragraphs(summary_lines),
            "",
            "## Main Flow",
            "",
            *_numbered_lines(main_flow_steps),
            "",
            "## Dependencies",
            "",
            *_bulleted_lines(dependency_lines),
            "",
            "## Repo Hints",
            "",
            render_repo_hints(repo_hints),
            "",
            "## Open Questions",
            "",
            *_bulleted_lines(question_lines),
        ]
    ).strip()


def build_domain_body(
    intent_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
    open_questions: list[str],
) -> str:
    summary_lines = _normalize_lines(storyline_outline_payload.get("domain_summary"))
    if not summary_lines:
        summary_lines = [
            f"{intent_payload['domain_name']} 当前主要关注入口、状态、数据编排与前端展示之间的协作关系。"
        ]
    repo_hints = _as_outline_hints(storyline_outline_payload.get("repo_hints"))
    repo_coverage = build_domain_repo_coverage(repo_hints)
    question_lines = unique_questions(open_questions) or ["当前仍需确认是否存在被遗漏的业务边界。"]
    return "\n".join(
        [
            "## Summary",
            "",
            *_paragraphs(summary_lines),
            "",
            "## Repo Coverage",
            "",
            *_bulleted_lines(repo_coverage),
            "",
            "## Open Questions",
            "",
            *_bulleted_lines(question_lines),
        ]
    ).strip()


def build_rule_body(
    intent_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    open_questions: list[str],
) -> str:
    risk_lines = unique_strings([str(risk) for item in repo_research_payloads for risk in item.get("risks", [])])
    if not risk_lines:
        risk_lines = [f"{intent_payload['normalized_intent']} 当前没有足够稳定的规则证据，暂不宜提升为规则知识。"]
    question_lines = unique_questions(open_questions) or ["当前是否存在跨多个需求反复出现的稳定约束。"]
    return "\n".join(
        [
            "## Statement",
            "",
            f"`{intent_payload['normalized_intent']}` 当前只保留稳定约束线索，不把实现注意事项直接提升为规则。",
            "",
            "## Evidence Risks",
            "",
            *_bulleted_lines(risk_lines),
            "",
            "## Open Questions",
            "",
            *_bulleted_lines(question_lines),
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
        if document.kind == "flow":
            for marker in FLOW_REQUIRED_SECTIONS:
                if marker not in document.body:
                    errors.append(f"{document.id}: flow body missing {marker}")
        if document.kind == "domain":
            for marker in DOMAIN_REQUIRED_SECTIONS:
                if marker not in document.body:
                    errors.append(f"{document.id}: domain body missing {marker}")
        if "## Open Questions" not in document.body:
            errors.append(f"{document.id}: body missing Open Questions")
        errors.extend(validate_document_evidence(document))
    return errors


def validate_document_evidence(document: KnowledgeDocument) -> list[str]:
    if document.kind != "flow":
        return []
    errors: list[str] = []
    supported_routes = extract_supported_routes(document)
    supported_actions = extract_supported_route_actions(document)
    body_routes = extract_body_routes(document.body)
    unsupported_routes = [
        route for route in body_routes if not is_supported_route(route, supported_routes, supported_actions)
    ]
    if unsupported_routes:
        errors.append(
            f"{document.id}: body mentions unsupported routes {', '.join(sorted(unsupported_routes)[:3])}"
        )

    supported_symbols = extract_supported_symbols(document)
    body_symbols = extract_body_symbols(document.body)
    unsupported_symbols = [symbol for symbol in body_symbols if not is_supported_symbol(symbol, supported_symbols)]
    if unsupported_symbols:
        errors.append(
            f"{document.id}: body mentions unsupported symbols {', '.join(sorted(unsupported_symbols)[:3])}"
        )
    return errors


def extract_supported_routes(document: KnowledgeDocument) -> list[str]:
    supported: list[str] = []
    for value in document.evidence.contextHits:
        supported.extend(re.findall(r"/[A-Za-z0-9_/\-]+", str(value)))
    supported.extend(re.findall(r"/[A-Za-z0-9_/\-]+", extract_repo_hints_section(document.body)))
    return unique_strings(supported)


def extract_body_routes(body: str) -> list[str]:
    narrative = extract_narrative_body(body)
    values = [value for value in re.findall(r"/[A-Za-z0-9_/\-]+", narrative) if is_business_route_ref(value)]
    return unique_strings(values)


def is_supported_route(route: str, supported_routes: list[str], supported_actions: list[str]) -> bool:
    current = str(route).strip()
    if any(current in supported or supported in current for supported in supported_routes):
        return True
    action = current.strip("/").lower()
    if not action or "/" in action:
        return False
    if not has_supported_route_family(supported_routes):
        return False
    return action in supported_actions


def extract_supported_symbols(document: KnowledgeDocument) -> list[str]:
    supported: list[str] = []
    for value in [*document.evidence.contextHits, extract_repo_hints_section(document.body)]:
        supported.extend(re.findall(r"\b[A-Z][A-Za-z0-9_]{5,}\b", str(value)))
    return unique_strings(supported)


def extract_body_symbols(body: str) -> list[str]:
    narrative = extract_narrative_body(body)
    ignored = {
        "Summary",
        "Main",
        "Flow",
        "Dependencies",
        "Repo",
        "Hints",
        "Key",
        "Modules",
        "Role",
        "Responsibilities",
        "Upstream",
        "Downstream",
        "Notes",
        "Open",
        "Questions",
        "Coverage",
        "Statement",
        "Evidence",
        "Risks",
    }
    values = [
        value
        for value in re.findall(r"\b[A-Z][A-Za-z0-9_]{5,}\b", narrative)
        if value not in ignored
    ]
    return unique_strings(values)


def is_supported_symbol(symbol: str, supported_symbols: list[str]) -> bool:
    current = str(symbol).strip()
    return any(current == supported or current in supported or supported in current for supported in supported_symbols)


def extract_narrative_body(body: str) -> str:
    marker = "\n## Repo Hints"
    if marker in body:
        return body.split(marker, 1)[0]
    return body


def extract_repo_hints_section(body: str) -> str:
    marker = "\n## Repo Hints"
    if marker not in body:
        return ""
    return body.split(marker, 1)[1]


def is_business_route_ref(route: str) -> bool:
    lowered = str(route).strip().lower()
    segments = [segment for segment in lowered.strip("/").split("/") if segment]
    if not segments:
        return False
    if len(segments) >= 2:
        return True
    segment = segments[0]
    return any(segment == action or segment.startswith(f"{action}_") for action in generic_route_actions())


def extract_supported_route_actions(document: KnowledgeDocument) -> list[str]:
    actions: list[str] = []
    for value in document.evidence.contextHits:
        lowered = str(value).lower()
        for action in generic_route_actions():
            if action in lowered:
                actions.append(action)
    return unique_strings(actions)


def has_supported_route_family(supported_routes: list[str]) -> bool:
    return any(len([segment for segment in str(route).strip("/").split("/") if segment]) >= 2 for route in supported_routes)


def generic_route_actions() -> tuple[str, ...]:
    return ("create", "save", "update", "edit", "launch", "start", "deactivate", "delete", "remove", "status", "get", "list", "detail", "preview")


def serialize_document(document: KnowledgeDocument) -> dict[str, object]:
    payload = document.model_dump()
    payload["evidence"] = document.evidence.model_dump()
    return payload


def collect_repo_questions(repo_research_payloads: list[dict[str, object]]) -> list[str]:
    return [str(question) for item in repo_research_payloads for question in item.get("open_questions", [])]


def collect_anchor_questions(anchor_selection_payloads: list[dict[str, object]]) -> list[str]:
    return [str(question) for item in anchor_selection_payloads for question in item.get("open_questions", [])]


def collect_document_questions(documents: list[KnowledgeDocument]) -> list[str]:
    return [question for document in documents for question in document.evidence.openQuestions]


def summarize_research_executors(repo_research_payloads: list[dict[str, object]]) -> str:
    executors = unique_strings([str(item.get("executor") or EXECUTOR_LOCAL) for item in repo_research_payloads])
    return ", ".join(executors) if executors else EXECUTOR_LOCAL


def summarize_anchor_executors(anchor_selection_payloads: list[dict[str, object]]) -> str:
    executors = unique_strings([str(item.get("executor") or EXECUTOR_LOCAL) for item in anchor_selection_payloads])
    return ", ".join(executors) if executors else EXECUTOR_LOCAL


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
        "正式文档只保留稳定知识，候选文件和检索词留在 trace 中。",
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
    del display_paths
    documents: list[KnowledgeDocument] = []
    for document in fallback_documents:
        output = outputs.get(document.kind, {})
        open_questions = unique_strings([*_as_string_list(output.get("open_questions")), *document.evidence.openQuestions])
        body = soften_weak_claims(str(output.get("body") or document.body))
        documents.append(
            document.model_copy(
                update={
                    "title": build_title(document.kind),
                    "desc": str(output.get("desc") or document.desc),
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
    term_family_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
    anchor_selection_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
    selected_paths: list[str],
    requested_kinds: list[str],
    trace_id: str,
    timestamp: str,
    requested_executor: str,
    synthesis_executor: str,
) -> list[KnowledgeDocument]:
    del term_family_payload
    del focus_boundary_payload
    domain_name = str(intent_payload["domain_name"])
    domain_id = str(intent_payload["domain_candidate"])
    repo_ids = [str(item["repo_id"]) for item in repo_research_payloads]
    repo_display_names = [str(item.get("repo_display_name") or item["repo_id"]) for item in repo_research_payloads]
    context_hits = unique_strings(
        [
            *[str(hit) for item in repo_research_payloads for hit in item.get("route_hits", [])[:3]],
            *[str(hit) for item in repo_research_payloads for hit in item.get("symbol_hits", [])[:4]],
            *[str(hit) for item in repo_research_payloads for hit in item.get("context_hits", [])[:4]],
        ]
    )
    open_questions = unique_questions(
        [
            *[str(question) for question in storyline_outline_payload.get("open_questions", [])],
            *[str(question) for item in repo_research_payloads for question in item.get("open_questions", [])[:1]],
        ]
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
            repos=repo_display_names,
            paths=[],
            keywords=[],
            priority="high" if kind == "flow" else "medium",
            confidence="medium" if repo_ids else "low",
            updatedAt=timestamp,
            owner="Maifeng",
            body=soften_weak_claims(
                build_body(kind, intent_payload, repo_research_payloads, storyline_outline_payload, open_questions)
            ),
            evidence=KnowledgeEvidence(
                inputDescription=str(intent_payload["description"]),
                inputTitle=str(intent_payload["title"]),
                repoMatches=repo_display_names,
                keywordMatches=[],
                pathMatches=list(selected_paths),
                candidateFiles=[],
                contextHits=context_hits,
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


def render_repo_hints(repo_hints: list[dict[str, object]]) -> str:
    sections: list[str] = []
    for item in repo_hints:
        sections.extend(
            [
                f"### `{item.get('repo_display_name', item['repo_id'])}`",
                "",
                f"- repo: `{item.get('repo_display_name', item['repo_id'])}`",
                f"- role: `{item['role_label']}`",
                "",
                "#### Key Modules",
                *_bulleted_lines(item.get("key_modules") or ["待补充"]),
                "",
                "#### Responsibilities",
                *_bulleted_lines(item.get("responsibilities") or ["待补充"]),
                "",
            ]
        )
        if item.get("upstream"):
            sections.extend(["#### Upstream", *_bulleted_lines(item["upstream"]), ""])
        if item.get("downstream"):
            sections.extend(["#### Downstream", *_bulleted_lines(item["downstream"]), ""])
        if item.get("notes"):
            sections.extend(["#### Notes", *_bulleted_lines(item["notes"]), ""])
    return "\n".join(sections).strip()


def build_domain_repo_coverage(repo_hints: list[dict[str, object]]) -> list[str]:
    coverage: list[str] = []
    for item in repo_hints:
        first_responsibility = (item.get("responsibilities") or ["承担当前领域的一部分职责。"])[0]
        coverage.append(f"`{item.get('repo_display_name', item['repo_id'])}`：{item['role_label']}，{first_responsibility}")
    return coverage or ["当前尚未收敛出稳定的仓库分工。"]


def build_storyline_steps_from_research(
    repo_hints: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
) -> list[str]:
    del repo_research_payloads
    steps: list[str] = []
    entry_repos = [item for item in repo_hints if item["role_label"] in {"服务聚合入口", "HTTP/API 入口"}]
    orchestration_repos = [item for item in repo_hints if item["role_label"] == "数据编排层"]
    bff_repos = [item for item in repo_hints if item["role_label"] == "前端/BFF 装配层"]
    support_repos = [item for item in repo_hints if item["role_label"] == "公共能力底座"]
    if entry_repos:
        steps.append(f"入口请求通常先由 {', '.join(f'`{item['repo_id']}`' for item in entry_repos[:2])} 收敛场景参数和展示条件。")
    if orchestration_repos:
        steps.append(f"主数据随后由 {', '.join(f'`{item['repo_id']}`' for item in orchestration_repos[:2])} 编排状态、配置和展示所需模型。")
    if bff_repos:
        steps.append(f"前端展示前，会由 {', '.join(f'`{item['repo_id']}`' for item in bff_repos[:2])} 转成前端或 BFF 可消费结构。")
    if support_repos:
        steps.append(f"公共配置、AB 或 schema 能力由 {', '.join(f'`{item['repo_id']}`' for item in support_repos[:2])} 提供支撑。")
    return steps or ["当前仍需结合更多 repo 线索确认稳定的主链路步骤。"]


def build_dependency_lines_from_research(
    repo_hints: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
) -> list[str]:
    research_map = {str(item.get("repo_id") or ""): item for item in repo_research_payloads}
    lines: list[str] = []
    for item in repo_hints:
        repo_name = str(item.get("repo_display_name") or item["repo_id"])
        role_label = str(item.get("role_label") or "")
        research = research_map.get(str(item.get("repo_id") or ""), {})
        facts_blob = " ".join(str(value) for value in research.get("facts", []))
        modules_blob = " ".join(str(value) for value in research.get("likely_modules", []))
        if role_label == "数据编排层":
            lines.append(f"`{repo_name}` 消费配置、session 和商品 relation 等依赖，收敛主链路所需数据结构。")
        elif role_label == "服务聚合入口":
            if "notify" in facts_blob.lower() or "notify" in modules_blob.lower():
                lines.append(f"`{repo_name}` 通过通知或刷新出口把运行时状态变化下发到客户端。")
            else:
                lines.append(f"`{repo_name}` 聚合同步进房或房间侧数据，并向下游入口或客户端返回初始化结果。")
        elif role_label == "HTTP/API 入口":
            lines.append(f"`{repo_name}` 消费上游编排结果，提供 preview/pop 等异步或 API 场景入口。")
        elif role_label == "前端/BFF 装配层":
            lines.append(f"`{repo_name}` 依赖上游入口或编排层提供的数据，装配前端/BFF 可消费结构。")
        elif role_label == "公共能力底座":
            lines.append(f"`{repo_name}` 提供配置、AB、schema 或共享工具能力，不直接承接业务主链。")
    return lines or ["当前仍需补充更明确的系统依赖关系。"]


def _normalize_lines(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_outline_hints(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    hints: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        hints.append(
            {
                "repo_id": repo_id,
                "repo_display_name": str(item.get("repo_display_name") or repo_id).strip(),
                "role_label": str(item.get("role_label") or "系统支撑仓库").strip(),
                "key_modules": _normalize_lines(item.get("key_modules")),
                "responsibilities": _normalize_lines(item.get("responsibilities")),
                "upstream": _normalize_lines(item.get("upstream")),
                "downstream": _normalize_lines(item.get("downstream")),
                "notes": _normalize_lines(item.get("notes")),
            }
        )
    return hints


def _paragraphs(lines: list[str]) -> list[str]:
    return [str(line).strip() for line in lines if str(line).strip()]


def _bulleted_lines(lines: list[str]) -> list[str]:
    return [f"- {str(line).strip()}" for line in lines if str(line).strip()]


def _numbered_lines(lines: list[str]) -> list[str]:
    return [f"{index}. {str(line).strip()}" for index, line in enumerate(lines, start=1) if str(line).strip()]


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
