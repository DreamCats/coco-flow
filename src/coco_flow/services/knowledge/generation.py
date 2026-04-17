from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import re
import uuid

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.models.knowledge import KnowledgeDocument, KnowledgeEvidence
from .common import (
    EXECUTOR_LOCAL,
    EXECUTOR_NATIVE,
    KNOWLEDGE_KIND_ORDER,
    KnowledgeDraftInput,
    KnowledgeGenerationResult,
    ProgressHandler,
    _as_string_list,
    build_display_paths,
    candidate_terms,
    emit_progress as _emit_progress,
    extract_json_object,
    infer_domain_name,
    infer_query_terms,
    infer_repo_terms_for_user_term,
    infer_search_terms,
    is_meaningful_term,
    normalize_executor,
    normalize_kinds,
    normalize_match_text,
    normalize_selected_paths,
    sanitize_search_terms,
    slugify_domain,
    slugify_repo_id,
    split_match_tokens,
    soften_weak_claims,
    unique_questions,
    unique_strings,
)
from .document_builder import (
    annotate_documents,
    apply_synthesis_outputs,
    build_body,
    build_description,
    build_documents_local,
    build_title,
    collect_anchor_questions,
    collect_document_questions,
    collect_repo_questions,
    infer_engines,
    serialize_document,
    validate_documents,
)
from .prompting import (
    build_candidate_ranking_prompt,
    build_anchor_selection_prompt,
    build_focus_boundary_prompt,
    build_flow_judge_prompt,
    build_flow_final_editor_prompt,
    build_flow_final_polisher_prompt,
    build_knowledge_synthesis_prompt,
    build_flow_slot_extraction_prompt,
    build_repo_role_signals_prompt,
    build_repo_research_prompt,
    build_storyline_outline_prompt,
    build_term_family_prompt,
    build_term_mapping_prompt,
    build_topic_adjudication_prompt,
    extract_candidate_ranking_output,
    extract_anchor_selection_output,
    extract_flow_slot_extraction_output,
    extract_focus_boundary_output,
    extract_flow_judge_output,
    extract_flow_final_editor_output,
    extract_flow_final_polisher_output,
    extract_knowledge_synthesis_output,
    extract_repo_role_signals_output,
    extract_repo_research_output,
    extract_storyline_outline_output,
    extract_term_family_output,
    extract_term_mapping_output,
    extract_topic_adjudication_output,
)
from .scan import (
    collect_context_aliases,
    collect_recent_commit_keywords,
    collect_repo_file_terms,
    collect_repo_route_terms,
    collect_repo_symbol_terms,
    extract_discarded_noise,
    extract_repo_anchors,
    find_repo_root,
    list_top_level_dirs,
    rank_likely_modules,
    scan_candidate_dirs,
    scan_candidate_files,
    scan_context_hits,
    scan_route_hits,
    scan_symbol_hits,
    scan_recent_commit_hits,
    select_core_route_signals,
)


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
    _emit_progress(on_progress, "candidate_ranking", 52, "正在裁剪主候选和噪音")
    candidate_ranking_payloads = [
        build_candidate_ranking(intent_payload, discovery, settings, requested_executor)
        for discovery in discovery_payload
    ]
    _emit_progress(on_progress, "anchor_selecting", 62, "正在筛选各 repo 的主锚点")
    anchor_selection_payloads = [
        build_anchor_selection(intent_payload, discovery, candidate_ranking, settings, requested_executor)
        for discovery, candidate_ranking in zip(discovery_payload, candidate_ranking_payloads, strict=False)
    ]
    _emit_progress(on_progress, "term_family", 70, "正在归并主术语族群")
    term_family_payload = build_term_family(
        intent_payload,
        term_mapping_payload,
        candidate_ranking_payloads,
        anchor_selection_payloads,
        settings,
        requested_executor,
    )
    _emit_progress(on_progress, "focus_boundary", 74, "正在收敛主题边界和旁支噪音")
    focus_boundary_payload = build_focus_boundary(
        intent_payload,
        term_mapping_payload,
        term_family_payload,
        candidate_ranking_payloads,
        anchor_selection_payloads,
        settings,
        requested_executor,
    )
    _emit_progress(on_progress, "repo_researching", 80, "正在归纳各 repo 在链路中的角色")
    repo_research_payloads = [
        build_repo_research(
            intent_payload,
            discovery,
            candidate_ranking,
            anchor_selection,
            term_family_payload,
            focus_boundary_payload,
            settings,
            requested_executor,
        )
        for discovery, candidate_ranking, anchor_selection in zip(
            discovery_payload, candidate_ranking_payloads, anchor_selection_payloads, strict=False
        )
    ]
    topic_adjudication_payload = build_topic_adjudication(
        intent_payload,
        focus_boundary_payload,
        repo_research_payloads,
        settings,
        requested_executor,
    )
    repo_role_signal_payloads = build_repo_role_signals(
        intent_payload,
        topic_adjudication_payload,
        repo_research_payloads,
        settings,
        requested_executor,
    )
    flow_slot_payload = build_flow_slot_extraction(
        intent_payload,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        repo_research_payloads,
        settings,
        requested_executor,
    )
    _emit_progress(on_progress, "storyline_outline", 88, "正在收敛系统级知识骨架")
    storyline_outline_payload = build_storyline_outline(
        intent_payload,
        focus_boundary_payload,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        flow_slot_payload,
        repo_research_payloads,
        settings,
        requested_executor,
    )
    _emit_progress(on_progress, "synthesizing", 92, "正在生成知识草稿")
    documents = build_documents(
        intent_payload=intent_payload,
        term_mapping_payload=term_mapping_payload,
        term_family_payload=term_family_payload,
        focus_boundary_payload=focus_boundary_payload,
        storyline_outline_payload=storyline_outline_payload,
        anchor_selection_payloads=anchor_selection_payloads,
        repo_research_payloads=repo_research_payloads,
        selected_paths=selected_paths,
        requested_kinds=requested_kinds,
        trace_id=trace_id,
        timestamp=now.strftime("%Y-%m-%d %H:%M"),
        settings=settings,
        requested_executor=requested_executor,
    )
    flow_judge_payload = build_flow_judge(
        documents,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        flow_slot_payload,
        settings,
        requested_executor,
    )
    documents = apply_flow_judge_notes(
        documents,
        flow_judge_payload,
        intent_payload=intent_payload,
        storyline_outline_payload=storyline_outline_payload,
        flow_slot_payload=flow_slot_payload,
        repo_research_payloads=repo_research_payloads,
        topic_adjudication_payload=topic_adjudication_payload,
    )
    flow_final_editor_payload = build_flow_final_editor(
        documents,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        flow_slot_payload,
        storyline_outline_payload,
        flow_judge_payload,
        settings,
        requested_executor,
    )
    documents = apply_flow_final_editor(documents, flow_final_editor_payload)
    flow_final_polisher_payload = build_flow_final_polisher(
        documents,
        flow_final_editor_payload,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        flow_judge_payload,
        settings,
        requested_executor,
    )
    documents = apply_flow_final_polisher(documents, flow_final_polisher_payload)
    open_questions = unique_strings(
        [
            *intent_payload["open_questions"],
            *[str(question) for question in term_mapping_payload["open_questions"]],
            *[str(question) for question in term_family_payload["open_questions"]],
            *collect_anchor_questions(anchor_selection_payloads),
            *collect_repo_questions(repo_research_payloads),
            *[str(question) for question in topic_adjudication_payload.get("open_questions", [])],
            *[
                str(question)
                for item in repo_role_signal_payloads
                for question in item.get("open_questions", [])
            ],
            *[str(question) for question in flow_slot_payload.get("open_questions", [])],
            *collect_document_questions(documents),
        ]
    )
    open_questions = filter_publishable_open_questions(open_questions, limit=8)
    knowledge_draft_payload = {
        "trace_id": trace_id,
        "documents": [serialize_document(document) for document in documents],
        "open_questions": open_questions,
    }
    _emit_progress(on_progress, "validating", 95, "正在校验生成结果")
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
        "candidate-ranking.json": {
            "trace_id": trace_id,
            "requested_executor": requested_executor,
            "repos": candidate_ranking_payloads,
        },
        "term-family.json": term_family_payload,
        "focus-boundary.json": focus_boundary_payload,
        "topic-adjudication.json": topic_adjudication_payload,
        "anchor-selection.json": {
            "trace_id": trace_id,
            "requested_executor": requested_executor,
            "repos": anchor_selection_payloads,
        },
        "repo-role-signals.json": {
            "trace_id": trace_id,
            "requested_executor": requested_executor,
            "repos": repo_role_signal_payloads,
        },
        "flow-slots.json": flow_slot_payload,
        "storyline-outline.json": storyline_outline_payload,
        "flow-judge.json": flow_judge_payload,
        "flow-final-edit.json": flow_final_editor_payload,
        "flow-final-polish.json": flow_final_polisher_payload,
        "knowledge-draft.json": knowledge_draft_payload,
        "validation-result.json": validation_payload,
    }
    for anchor_payload in anchor_selection_payloads:
        trace_files[f"anchor-selection/{anchor_payload['repo_id']}.json"] = anchor_payload
    for ranking_payload in candidate_ranking_payloads:
        trace_files[f"candidate-ranking/{ranking_payload['repo_id']}.json"] = ranking_payload
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
        "repo_display_name": scan_root.name or requested_path.name,
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
    requested_path = str(target["requested_path"])
    matched_files, path_keywords = scan_candidate_files(scan_root, search_terms, requested_path=requested_path)
    matched_dirs, dir_keywords = scan_candidate_dirs(scan_root, search_terms, requested_path=requested_path)
    route_hits, route_keywords = scan_route_hits(scan_root, search_terms, requested_path=requested_path)
    symbol_hits, symbol_keywords = scan_symbol_hits(scan_root, search_terms, requested_path=requested_path)
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
        "repo_display_name": target.get("repo_display_name", target["repo_id"]),
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
        normalized_payload.append({**item, "repo_id": repo_id, "repo_display_name": item.get("repo_display_name", item["repo_id"])})
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
        except Exception as error:
            local = build_term_mapping_local(intent_payload, repo_candidates)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_term_mapping_local(intent_payload, repo_candidates)


def collect_repo_term_candidates(target: dict[str, object]) -> dict[str, object]:
    root = Path(str(target["repo_path"]))
    return {
        "repo_id": target["repo_id"],
        "repo_display_name": target.get("repo_display_name", target["repo_id"]),
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


def build_focus_boundary(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    del settings
    if requested_executor == EXECUTOR_NATIVE:
        local = build_focus_boundary_local(
            intent_payload,
            term_mapping_payload,
            term_family_payload,
            candidate_ranking_payloads,
            anchor_selection_payloads,
        )
        local["requested_executor"] = requested_executor
        return local
    return build_focus_boundary_local(
        intent_payload,
        term_mapping_payload,
        term_family_payload,
        candidate_ranking_payloads,
        anchor_selection_payloads,
    )


def build_focus_boundary_local(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
) -> dict[str, object]:
    in_scope_terms = unique_strings(
        [str(item) for item in term_family_payload.get("primary_family", []) if is_meaningful_term(str(item))]
    )[:8]
    supporting_terms = unique_strings(
        [
            *[str(item) for item in term_family_payload.get("generic_terms", []) if is_meaningful_term(str(item))],
            *[
                str(item)
                for family in term_family_payload.get("secondary_families", [])
                if isinstance(family, list)
                for item in family
                if is_meaningful_term(str(item))
            ],
        ]
    )[:6]
    out_of_scope_terms = unique_strings(
        [
            *[str(item) for item in term_family_payload.get("noise_terms", [])],
            *[str(item) for item in term_mapping_payload.get("search_terms", []) if not is_meaningful_term(str(item))],
        ]
    )[:8]
    if not in_scope_terms:
        in_scope_terms = unique_strings([str(term) for term in intent_payload["query_terms"] if is_meaningful_term(str(term))])[:6]
    return {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "canonical_subject": str(intent_payload["normalized_intent"]),
        "in_scope_terms": in_scope_terms,
        "supporting_terms": supporting_terms,
        "out_of_scope_terms": out_of_scope_terms,
        "reason": "基于主术语族群、次级族群和噪音词做本地主题边界收敛。",
        "open_questions": unique_questions(_as_string_list(term_family_payload.get("open_questions"))[:4]),
    }


def build_focus_boundary_native(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(candidate_ranking_payloads[0]["repo_path"]) if candidate_ranking_payloads else None
    raw = client.run_prompt_only(
        build_focus_boundary_prompt(
            intent_payload,
            term_mapping_payload,
            term_family_payload,
            anchor_selection_payloads,
            candidate_ranking_payloads,
        ),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_focus_boundary_output(raw)
    fallback = build_focus_boundary_local(
        intent_payload,
        term_mapping_payload,
        term_family_payload,
        candidate_ranking_payloads,
        anchor_selection_payloads,
    )
    return fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "canonical_subject": parsed["canonical_subject"] or fallback["canonical_subject"],
        "in_scope_terms": unique_strings(parsed["in_scope_terms"] or fallback["in_scope_terms"]),
        "supporting_terms": unique_strings(parsed["supporting_terms"] + fallback["supporting_terms"]),
        "out_of_scope_terms": unique_strings(parsed["out_of_scope_terms"] + fallback["out_of_scope_terms"]),
        "reason": parsed["reason"] or fallback["reason"],
        "open_questions": unique_questions(parsed["open_questions"] + fallback["open_questions"]),
    }


def build_candidate_ranking(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_candidate_ranking_native(intent_payload, discovery, settings)
        except Exception as error:
            local = build_candidate_ranking_local(intent_payload, discovery)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_candidate_ranking_local(intent_payload, discovery)


def build_candidate_ranking_local(intent_payload: dict[str, object], discovery: dict[str, object]) -> dict[str, object]:
    candidate_files = [str(item) for item in discovery.get("candidate_files", [])]
    candidate_dirs = [str(item) for item in discovery.get("candidate_dirs", [])]
    route_hits = select_core_route_signals([str(item) for item in discovery.get("route_hits", [])], intent_payload)
    symbol_hits = [str(item) for item in discovery.get("symbol_hits", [])]
    strongest_terms = [str(item).lower() for item in discovery.get("matched_keywords", [])]

    file_scores: list[tuple[int, str]] = []
    for path in candidate_files:
        lowered = path.lower()
        score = 0
        if any(token in lowered for token in ("router", "route")):
            score += 8
        if any(token in lowered for token in ("handler", "service", "rpc")):
            score += 5
        if any(term and term.replace("_", "") in lowered.replace("_", "") for term in strongest_terms):
            score += 4
        if any(token in lowered for token in ("callback", "cycle", "loader", "legacy", "billboard", "developing")):
            score -= 6
        file_scores.append((score, path))
    file_scores.sort(key=lambda item: (-item[0], item[1]))
    ranked_files = [path for _, path in file_scores]
    primary_files = ranked_files[:6]
    secondary_files = [path for path in ranked_files[6:] if path not in primary_files][:6]

    primary_dirs = unique_strings([str(Path(path).parent) for path in primary_files if str(Path(path).parent) not in {"", "."}])
    if not primary_dirs:
        primary_dirs = candidate_dirs[:4]

    preferred_symbols: list[str] = []
    for hit in symbol_hits:
        _, _, tail = hit.partition("#")
        identifier = tail.split(" 命中 ", 1)[0].strip()
        if identifier:
            preferred_symbols.append(identifier)

    discarded_noise = []
    for path in candidate_files:
        lowered = path.lower()
        if any(token in lowered for token in ("callback", "cycle", "loader", "legacy", "billboard", "developing")):
            discarded_noise.append(path)
    open_questions: list[str] = []
    if not primary_files:
        open_questions.append("当前还没有稳定筛出主候选文件，可能需要更具体的动作或业务术语。")
    return {
        "repo_id": discovery["repo_id"],
        "repo_display_name": discovery.get("repo_display_name", discovery["repo_id"]),
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "primary_files": primary_files,
        "secondary_files": secondary_files,
        "primary_dirs": primary_dirs[:4],
        "preferred_symbols": unique_strings(preferred_symbols)[:6],
        "preferred_routes": route_hits[:4],
        "discarded_noise": unique_strings(discarded_noise)[:8],
        "reason": "基于结构入口、动作词和当前候选集中度做本地主候选裁剪。",
        "open_questions": unique_questions(open_questions),
    }


def build_candidate_ranking_native(
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
        build_candidate_ranking_prompt(intent_payload, discovery),
        settings.native_query_timeout,
        cwd=repo_path or None,
    )
    parsed = extract_candidate_ranking_output(raw)
    fallback = build_candidate_ranking_local(intent_payload, discovery)
    return fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "primary_files": parsed["primary_files"] or fallback["primary_files"],
        "secondary_files": parsed["secondary_files"] or fallback["secondary_files"],
        "primary_dirs": parsed["primary_dirs"] or fallback["primary_dirs"],
        "preferred_symbols": parsed["preferred_symbols"] or fallback["preferred_symbols"],
        "preferred_routes": select_core_route_signals(parsed["preferred_routes"] or fallback["preferred_routes"], intent_payload),
        "discarded_noise": unique_strings(parsed["discarded_noise"] + fallback["discarded_noise"]),
        "reason": parsed["reason"] or fallback["reason"],
        "open_questions": unique_questions(parsed["open_questions"] + fallback["open_questions"]),
    }


def build_term_family(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_term_family_native(
                intent_payload,
                term_mapping_payload,
                candidate_ranking_payloads,
                anchor_selection_payloads,
                settings,
            )
        except Exception as error:
            local = build_term_family_local(intent_payload, term_mapping_payload, candidate_ranking_payloads, anchor_selection_payloads)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_term_family_local(intent_payload, term_mapping_payload, candidate_ranking_payloads, anchor_selection_payloads)


def build_term_family_local(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
) -> dict[str, object]:
    family_terms: list[str] = []
    for item in term_mapping_payload.get("mapped_terms", []):
        if not isinstance(item, dict):
            continue
        family_terms.extend(str(term) for term in item.get("repo_terms", []))
    for item in anchor_selection_payloads:
        family_terms.extend(str(term) for term in item.get("strongest_terms", []))
        family_terms.extend(str(term) for term in item.get("business_symbols", []))
    for item in candidate_ranking_payloads:
        family_terms.extend(str(term) for term in item.get("preferred_symbols", []))
        family_terms.extend(str(term) for term in item.get("preferred_routes", []))
    candidate_primary = unique_strings([term for term in family_terms if is_meaningful_term(term)])
    action_terms = {"create", "save", "update", "launch", "delete", "deactivate", "status", "get", "list", "detail"}
    direct_terms = collect_direct_family_terms(term_mapping_payload, candidate_ranking_payloads)
    generic_terms = infer_generic_terms(candidate_primary, direct_terms)
    primary_family = [term for term in candidate_primary if term not in generic_terms][:6]
    secondary_terms = [
        term
        for term in unique_strings([str(term) for term in term_mapping_payload.get("search_terms", [])])
        if term.lower() not in action_terms and term not in primary_family and term not in generic_terms
    ][:4]
    noise_terms = unique_strings(
        [str(term) for item in candidate_ranking_payloads for term in item.get("discarded_noise", [])]
    )[:8]
    open_questions: list[str] = []
    if not primary_family:
        open_questions.append("当前还没有稳定识别出主术语族群，可能需要补充更具体的业务词或入口文件。")
    return {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "primary_family": primary_family,
        "secondary_families": [secondary_terms] if secondary_terms else [],
        "generic_terms": generic_terms,
        "noise_terms": noise_terms,
        "reason": "基于 term mapping、候选裁剪和锚点结果归并当前任务的主术语族群。",
        "open_questions": unique_questions(open_questions),
    }


def build_term_family_native(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
    anchor_selection_payloads: list[dict[str, object]],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(candidate_ranking_payloads[0]["repo_path"]) if candidate_ranking_payloads else None
    raw = client.run_prompt_only(
        build_term_family_prompt(intent_payload, term_mapping_payload, candidate_ranking_payloads, anchor_selection_payloads),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_term_family_output(raw)
    fallback = build_term_family_local(intent_payload, term_mapping_payload, candidate_ranking_payloads, anchor_selection_payloads)
    return fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "primary_family": parsed["primary_family"] or fallback["primary_family"],
        "secondary_families": parsed["secondary_families"] or fallback["secondary_families"],
        "generic_terms": unique_strings(parsed["generic_terms"] + fallback["generic_terms"]),
        "noise_terms": unique_strings(parsed["noise_terms"] + fallback["noise_terms"]),
        "reason": parsed["reason"] or fallback["reason"],
        "open_questions": unique_questions(parsed["open_questions"] + fallback["open_questions"]),
    }


def collect_direct_family_terms(
    term_mapping_payload: dict[str, object],
    candidate_ranking_payloads: list[dict[str, object]],
) -> set[str]:
    direct: set[str] = set()
    for item in term_mapping_payload.get("mapped_terms", []):
        if not isinstance(item, dict):
            continue
        direct.update(str(term) for term in item.get("repo_terms", []))
    for item in candidate_ranking_payloads:
        direct.update(str(term) for term in item.get("preferred_routes", []))
        direct.update(str(term) for term in item.get("primary_dirs", []))
    return {term for term in direct if str(term).strip()}


def infer_generic_terms(candidate_terms: list[str], direct_terms: set[str]) -> list[str]:
    generics: list[str] = []
    normalized_direct = {normalize_match_text(term) for term in direct_terms}
    for term in candidate_terms:
        normalized = normalize_match_text(term)
        if not normalized:
            continue
        if normalized in normalized_direct:
            continue
        containing = 0
        for other in candidate_terms:
            if other == term:
                continue
            other_normalized = normalize_match_text(other)
            if not other_normalized:
                continue
            if normalized == other_normalized:
                continue
            if normalized in other_normalized:
                containing += 1
        if containing >= 2:
            generics.append(term)
    return unique_strings(generics)[:4]


def build_anchor_selection(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_anchor_selection_native(intent_payload, discovery, candidate_ranking, settings)
        except Exception as error:
            local = build_anchor_selection_local(intent_payload, discovery, candidate_ranking)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_anchor_selection_local(intent_payload, discovery, candidate_ranking)


def build_anchor_selection_local(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
) -> dict[str, object]:
    anchors = extract_repo_anchors(discovery)
    ranked_primary_files = [str(item) for item in candidate_ranking.get("primary_files", [])]
    ranked_symbols = [str(item) for item in candidate_ranking.get("preferred_symbols", [])]
    ranked_routes = [str(item) for item in candidate_ranking.get("preferred_routes", [])]
    anchors["entry_files"] = unique_strings([*ranked_primary_files, *anchors["entry_files"]])[:4]
    anchors["business_symbols"] = unique_strings([*ranked_symbols, *anchors["business_symbols"]])[:6]
    anchors["route_signals"] = select_core_route_signals([*ranked_routes, *anchors["route_signals"]], intent_payload)
    strongest_terms = unique_strings(
        [
            *anchors["business_symbols"],
            *anchors["keywords"],
            *[str(term) for term in candidate_ranking.get("preferred_symbols", []) if is_meaningful_term(str(term))],
            *[str(term) for term in discovery.get("matched_keywords", []) if is_meaningful_term(str(term))],
        ]
    )[:8]
    discarded_noise = unique_strings(
        [*[str(item) for item in candidate_ranking.get("discarded_noise", [])], *extract_discarded_noise(discovery, strongest_terms)]
    )
    open_questions: list[str] = []
    if not anchors["entry_files"]:
        open_questions.append("当前还没有稳定识别出入口文件，可能需要补充更具体的动作或接口名。")
    if not anchors["business_symbols"]:
        open_questions.append("当前还没有稳定识别出业务枚举或核心符号，可能需要补充业务术语。")
    open_questions.extend([str(item) for item in candidate_ranking.get("open_questions", [])])
    return {
        "repo_id": discovery["repo_id"],
        "repo_display_name": discovery.get("repo_display_name", discovery["repo_id"]),
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
    candidate_ranking: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    repo_path = str(discovery["repo_path"]).strip()
    raw = client.run_prompt_only(
        build_anchor_selection_prompt(intent_payload, discovery, candidate_ranking),
        settings.native_query_timeout,
        cwd=repo_path or None,
    )
    parsed = extract_anchor_selection_output(raw)
    fallback = build_anchor_selection_local(intent_payload, discovery, candidate_ranking)
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
    candidate_ranking: dict[str, object],
    anchor_selection: dict[str, object],
    term_family: dict[str, object],
    focus_boundary: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_repo_research_native(intent_payload, discovery, candidate_ranking, anchor_selection, term_family, focus_boundary, settings)
        except Exception as error:
            local = build_repo_research_local(intent_payload, discovery, candidate_ranking, anchor_selection, term_family, focus_boundary)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_repo_research_local(intent_payload, discovery, candidate_ranking, anchor_selection, term_family, focus_boundary)


def build_repo_research_local(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
    anchor_selection: dict[str, object],
    term_family: dict[str, object],
    focus_boundary: dict[str, object],
) -> dict[str, object]:
    matched_keywords = [str(item) for item in discovery["matched_keywords"]]
    candidate_dirs = [str(item) for item in discovery["candidate_dirs"]]
    candidate_files = [str(item) for item in discovery["candidate_files"]]
    route_hits = filter_text_signals_by_focus_boundary(
        select_core_route_signals([str(item) for item in discovery.get("route_hits", [])], intent_payload),
        focus_boundary,
    )
    symbol_hits = filter_text_signals_by_focus_boundary([str(item) for item in discovery.get("symbol_hits", [])], focus_boundary)
    commit_hits = filter_text_signals_by_focus_boundary([str(item) for item in discovery.get("commit_hits", [])], focus_boundary)
    context_hits = filter_text_signals_by_focus_boundary([str(item) for item in discovery["context_hits"]], focus_boundary)[:8]
    ranked_primary_dirs = [str(item) for item in candidate_ranking.get("primary_dirs", [])]
    ranked_primary_files = [str(item) for item in candidate_ranking.get("primary_files", [])]
    ranked_secondary_files = [str(item) for item in candidate_ranking.get("secondary_files", [])]
    anchors = {
        "entry_files": [str(item) for item in anchor_selection.get("entry_files", [])],
        "business_symbols": [str(item) for item in anchor_selection.get("business_symbols", [])],
        "route_signals": [str(item) for item in anchor_selection.get("route_signals", [])],
        "keywords": [str(item) for item in anchor_selection.get("strongest_terms", [])],
    }
    ranked_candidate_files = filter_candidate_files_by_focus_boundary(
        unique_strings([*ranked_primary_files, *anchors["entry_files"], *ranked_secondary_files, *candidate_files])[:8],
        focus_boundary,
    )
    ranked_candidate_dirs = filter_candidate_files_by_focus_boundary(unique_strings([*ranked_primary_dirs, *candidate_dirs]), focus_boundary)
    primary = bool(ranked_candidate_files or matched_keywords or context_hits or symbol_hits or route_hits or commit_hits)
    role = "primary" if primary else "supporting"
    facts: list[str] = []
    if discovery["agents_present"]:
        facts.append("AGENTS.md present")
    if discovery["context_present"]:
        facts.append("context present")
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
    strongest_terms = [str(item) for item in focus_boundary.get("in_scope_terms", [])] or [str(item) for item in term_family.get("primary_family", [])] or [str(item) for item in anchor_selection.get("strongest_terms", [])]
    generic_terms = {normalize_match_text(str(item)) for item in term_family.get("generic_terms", [])}
    secondary_terms = [
        str(item)
        for family in term_family.get("secondary_families", [])
        if isinstance(family, list)
        for item in family
    ]
    noise_terms = [str(item) for item in term_family.get("noise_terms", [])]
    ranked_candidate_files = filter_candidate_files_by_term_family(
        ranked_candidate_files,
        strongest_terms,
        secondary_terms,
        noise_terms,
    )
    filtered_matched_keywords = [
        keyword for keyword in matched_keywords if normalize_match_text(keyword) not in generic_terms
    ]
    entry_files = [str(item) for item in anchor_selection.get("entry_files", [])]
    open_questions = [str(question) for question in focus_boundary.get("open_questions", [])] + [str(question) for question in term_family.get("open_questions", [])] + [str(question) for question in anchor_selection.get("open_questions", [])]
    if not discovery["is_git_repo"]:
        open_questions.append("该路径不是 git repo，是否应上卷到真实仓库根目录。")
    if not matched_keywords:
        open_questions.append("当前关键词未命中明显模块名，是否需要补充别名或业务术语。")
    if strongest_terms and not route_hits:
        open_questions.append(f"`{strongest_terms[0]}` 对应的外部入口和上下游边界是否已经确认。")
    likely_modules = filter_candidate_files_by_focus_boundary(
        rank_likely_modules(ranked_candidate_dirs, anchors, discovery)[:6],
        focus_boundary,
    )[:6]
    return {
        "repo_id": discovery["repo_id"],
        "repo_display_name": discovery.get("repo_display_name", discovery["repo_id"]),
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "role": role,
        "likely_modules": likely_modules,
        "candidate_files": ranked_candidate_files,
        "route_hits": route_hits,
        "risks": risks,
        "facts": facts,
        "inferences": inferences,
        "context_hits": context_hits,
        "symbol_hits": symbol_hits,
        "commit_hits": commit_hits,
        "anchors": anchors,
        "open_questions": unique_questions(open_questions),
        "matched_keywords": filtered_matched_keywords,
    }


def build_repo_research_native(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
    anchor_selection: dict[str, object],
    term_family: dict[str, object],
    focus_boundary: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    fallback = build_repo_research_local(intent_payload, discovery, candidate_ranking, anchor_selection, term_family, focus_boundary)
    repo_path = str(discovery["repo_path"]).strip()
    if not repo_path:
        raise ValueError("native repo research missing repo_path")
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_readonly_agent(
        build_repo_research_prompt(intent_payload, discovery, candidate_ranking, anchor_selection, term_family, focus_boundary),
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


def filter_candidate_files_by_term_family(
    candidate_files: list[str],
    primary_terms: list[str],
    secondary_terms: list[str],
    noise_terms: list[str],
) -> list[str]:
    primary_normalized = [normalize_match_text(term) for term in primary_terms if normalize_match_text(term)]
    secondary_normalized = [normalize_match_text(term) for term in [*secondary_terms, *noise_terms] if normalize_match_text(term)]
    if not secondary_normalized:
        return candidate_files
    result: list[str] = []
    for index, path in enumerate(candidate_files):
        normalized_path = normalize_match_text(path)
        primary_hits = sum(1 for term in primary_normalized if term and term in normalized_path)
        secondary_hits = sum(1 for term in secondary_normalized if term and term in normalized_path)
        if index >= 3 and secondary_hits > 0 and primary_hits == 0:
            continue
        result.append(path)
    return result[:8]


def filter_text_signals_by_focus_boundary(
    values: list[str],
    focus_boundary: dict[str, object],
) -> list[str]:
    in_scope = [
        normalize_match_text(str(term))
        for term in focus_boundary.get("in_scope_terms", [])
        if normalize_match_text(str(term))
    ]
    supporting = [
        normalize_match_text(str(term))
        for term in focus_boundary.get("supporting_terms", [])
        if normalize_match_text(str(term))
    ]
    out_of_scope = [
        normalize_match_text(str(term))
        for term in focus_boundary.get("out_of_scope_terms", [])
        if normalize_match_text(str(term))
    ]
    if not any([in_scope, supporting, out_of_scope]):
        return unique_strings(values)

    scored: list[tuple[int, str]] = []
    for value in unique_strings(values):
        normalized = normalize_match_text(value)
        if not normalized:
            continue
        score = 0
        if any(term and term in normalized for term in in_scope):
            score += 6
        if any(term and term in normalized for term in supporting):
            score += 2
        if any(term and term in normalized for term in out_of_scope):
            score -= 8
        if score >= 0:
            scored.append((score, value))
    scored.sort(key=lambda item: (-item[0], item[1]))
    filtered = [value for _, value in scored]
    return filtered or unique_strings(values[:4])


def filter_candidate_files_by_focus_boundary(
    values: list[str],
    focus_boundary: dict[str, object],
) -> list[str]:
    in_scope = [
        normalize_match_text(str(term))
        for term in focus_boundary.get("in_scope_terms", [])
        if normalize_match_text(str(term))
    ]
    supporting = [
        normalize_match_text(str(term))
        for term in focus_boundary.get("supporting_terms", [])
        if normalize_match_text(str(term))
    ]
    out_of_scope = [
        normalize_match_text(str(term))
        for term in focus_boundary.get("out_of_scope_terms", [])
        if normalize_match_text(str(term))
    ]
    if not any([in_scope, supporting, out_of_scope]):
        return unique_strings(values)

    scored: list[tuple[int, str]] = []
    for value in unique_strings(values):
        normalized = normalize_match_text(value)
        if not normalized:
            continue
        score = 0
        if any(term and term in normalized for term in in_scope):
            score += 8
        if any(term and term in normalized for term in supporting):
            score += 2
        if any(term and term in normalized for term in out_of_scope):
            score -= 10
        if score >= 0:
            scored.append((score, value))
    scored.sort(key=lambda item: (-item[0], item[1]))
    filtered = [value for _, value in scored]
    return filtered or unique_strings(values[:4])


def build_topic_adjudication(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_topic_adjudication_native(
                intent_payload,
                focus_boundary_payload,
                repo_research_payloads,
                settings,
            )
        except Exception as error:
            local = build_topic_adjudication_local(intent_payload, focus_boundary_payload, repo_research_payloads)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_topic_adjudication_local(intent_payload, focus_boundary_payload, repo_research_payloads)


TOPIC_CONFIG_MARKERS = (
    "config",
    "schema",
    "abtest",
    "ab_test",
    "experiment",
    "gray",
    "grey",
    "flag",
    "switch",
    "toggle",
    "enable",
    "enabled",
    "setting",
    "param",
    "option",
)

OPEN_QUESTION_SELF_REFLECTION_MARKERS = (
    "当前相邻主题是否只应保留为背景",
    "当前主链路场景槽位是否已经覆盖",
    "是否应保留为背景",
    "槽位是否已经覆盖",
)

OPEN_QUESTION_DISCOVERY_MARKERS = (
    "具体实现位置",
    "具体实现文件",
    "具体入口文件",
    "具体对应符号",
    "具体handler",
    "具体 handler",
    "handler 文件",
    "engine 和 converter",
    "engine文件",
    "converter文件",
    "路由是什么",
    "路由入口",
    "相关路由或 handler",
    "未扫描",
    "实现逻辑在哪个文件",
)

OPEN_QUESTION_BOUNDARY_MARKERS = (
    "边界",
    "分工",
    "职责",
    "生产边界",
    "兼容层",
    "交互方式",
)

OPEN_QUESTION_AUTHORITY_MARKERS = (
    "权威源",
    "默认权威源",
    "主来源",
    "来源是否稳定",
    "是否已经成为",
)

OPEN_QUESTION_COMPAT_MARKERS = (
    "新旧架构",
    "双轨",
    "兼容",
    "region",
    "区域",
    "是否仍有有效主链路",
)


def is_publishable_open_question(question: str) -> bool:
    current = str(question).strip()
    if not current:
        return False
    normalized = normalize_match_text(current)
    if any(marker in current for marker in OPEN_QUESTION_SELF_REFLECTION_MARKERS):
        return False
    if any(normalize_match_text(marker) in normalized for marker in OPEN_QUESTION_DISCOVERY_MARKERS):
        return False
    return True


def classify_open_question(question: str) -> str | None:
    current = str(question).strip()
    if not is_publishable_open_question(current):
        return None
    normalized = normalize_match_text(current)
    if any(normalize_match_text(marker) in normalized for marker in OPEN_QUESTION_BOUNDARY_MARKERS):
        return "boundary_question"
    if any(normalize_match_text(marker) in normalized for marker in OPEN_QUESTION_AUTHORITY_MARKERS):
        return "authority_question"
    if any(normalize_match_text(marker) in normalized for marker in OPEN_QUESTION_COMPAT_MARKERS):
        return "compat_question"
    return "general_question"


def filter_publishable_open_questions(questions: list[str], limit: int = 6) -> list[str]:
    classified: dict[str, list[str]] = {
        "boundary_question": [],
        "authority_question": [],
        "compat_question": [],
        "general_question": [],
    }
    for question in unique_questions(questions):
        category = classify_open_question(question)
        if category is None:
            continue
        classified.setdefault(category, []).append(question)
    ordered = [
        *classified["boundary_question"],
        *classified["authority_question"],
        *classified["compat_question"],
        *classified["general_question"],
    ]
    return ordered[:limit]


def soften_repo_responsibility(value: str) -> str:
    current = str(value).strip()
    replacements = (
        ("该repo是竞拍讲解卡系统的核心服务，负责数据组装和业务逻辑处理", "该 repo 负责竞拍讲解卡相关的数据组装与状态收敛"),
        ("核心服务实现", "关键实现层"),
        ("核心服务", "关键环节"),
        ("业务逻辑处理", "数据处理与装配"),
        ("承接竞拍（auction）讲解卡相关的业务逻辑", "承接竞拍讲解卡相关的数据装配与转换"),
        ("承接竞拍讲解卡相关的业务逻辑", "承接竞拍讲解卡相关的数据装配与转换"),
        ("该 repo 是竞拍讲解卡链路的核心服务实现", "该 repo 是竞拍讲解卡链路中的关键实现层"),
    )
    for source, target in replacements:
        current = current.replace(source, target)
    return current


def classify_topic_term(
    term: str,
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
) -> str:
    normalized = normalize_match_text(term)
    if not normalized:
        return "adjacent"
    title_blob = normalize_match_text(
        " ".join(
            [
                str(intent_payload.get("title") or ""),
                str(intent_payload.get("description") or ""),
                str(intent_payload.get("normalized_intent") or ""),
                str(focus_boundary_payload.get("canonical_subject") or ""),
            ]
        )
    )
    in_scope = " ".join(str(item) for item in focus_boundary_payload.get("in_scope_terms", []))
    supporting = " ".join(str(item) for item in focus_boundary_payload.get("supporting_terms", []))
    if any(marker in normalized for marker in TOPIC_CONFIG_MARKERS):
        return "config"
    if "/" in term or "." in term or "_" in term:
        return "technical"
    if normalized in title_blob or title_blob in normalized:
        return "core"
    if normalized in normalize_match_text(in_scope):
        return "core"
    if normalized in normalize_match_text(supporting):
        return "supporting"
    return "adjacent"


def collect_blocked_topic_terms(topic_adjudication_payload: dict[str, object]) -> list[str]:
    return unique_strings(
        [
            *[str(item) for item in topic_adjudication_payload.get("adjacent_subjects", [])],
            *[str(item) for item in topic_adjudication_payload.get("suppressed_terms", [])],
        ]
    )


def post_process_topic_adjudication(
    payload: dict[str, object],
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> dict[str, object]:
    related: list[str] = []
    adjacent: list[str] = []
    suppressed: list[str] = []
    for term in unique_strings(
        [
            *[str(item) for item in payload.get("related_subjects", [])],
            *[str(item) for item in payload.get("adjacent_subjects", [])],
            *[str(item) for item in payload.get("suppressed_terms", [])],
        ]
    ):
        classification = classify_topic_term(term, intent_payload, focus_boundary_payload)
        if classification in {"config", "technical", "adjacent"}:
            adjacent.append(term)
            suppressed.append(term)
        else:
            related.append(term)
    suppressed_normalized = [normalize_match_text(value) for value in unique_strings(suppressed)]
    suppressed_modules = unique_strings(
        [
            str(module)
            for repo in repo_research_payloads
            for module in _as_string_list(repo.get("likely_modules"))
            if any(term and term in normalize_match_text(str(module)) for term in suppressed_normalized)
        ]
    )[:10]
    suppressed_routes = unique_strings(
        [
            str(route)
            for repo in repo_research_payloads
            for route in _as_string_list(repo.get("route_hits"))
            if any(term and term in normalize_match_text(str(route)) for term in suppressed_normalized)
        ]
    )[:10]
    return {
        **payload,
        "related_subjects": unique_strings(related)[:10],
        "adjacent_subjects": unique_strings(adjacent)[:8],
        "suppressed_terms": unique_strings(suppressed)[:8],
        "suppressed_modules": unique_strings(
            [*suppressed_modules, *[str(item) for item in payload.get("suppressed_modules", [])]]
        )[:10],
        "suppressed_routes": unique_strings(
            [*suppressed_routes, *[str(item) for item in payload.get("suppressed_routes", [])]]
        )[:10],
        "open_questions": filter_publishable_open_questions(
            [
                *[str(item) for item in payload.get("open_questions", [])],
                "当前相邻主题是否只应保留为背景，而不进入主链路正文。" if adjacent else "",
            ],
            limit=6,
        ),
    }


def build_topic_adjudication_local(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> dict[str, object]:
    related_subjects = unique_strings(
        [
            *[str(item) for item in focus_boundary_payload.get("in_scope_terms", [])],
            *[str(item) for item in focus_boundary_payload.get("supporting_terms", [])],
        ]
    )[:10]
    adjacent_subjects = unique_strings(
        [str(item) for item in focus_boundary_payload.get("out_of_scope_terms", [])]
    )[:8]
    suppressed_modules = unique_strings(
        [
            module
            for repo in repo_research_payloads
            for module in _as_string_list(repo.get("likely_modules"))
            if any(term and term in normalize_match_text(module) for term in [normalize_match_text(value) for value in adjacent_subjects])
        ]
    )[:10]
    suppressed_routes = unique_strings(
        [
            route
            for repo in repo_research_payloads
            for route in _as_string_list(repo.get("route_hits"))
            if any(term and term in normalize_match_text(route) for term in [normalize_match_text(value) for value in adjacent_subjects])
        ]
    )[:10]
    open_questions = filter_publishable_open_questions(
        [
            *[str(item) for item in focus_boundary_payload.get("open_questions", [])[:2]],
            "当前相邻主题是否只应保留为背景，而不进入主链路正文。" if adjacent_subjects else "",
        ],
    )
    payload = {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "primary_subject": str(focus_boundary_payload.get("canonical_subject") or intent_payload["normalized_intent"]),
        "related_subjects": related_subjects,
        "adjacent_subjects": adjacent_subjects,
        "suppressed_terms": adjacent_subjects,
        "suppressed_modules": suppressed_modules,
        "suppressed_routes": suppressed_routes,
        "reason": "基于主题边界的主术语、辅助术语和旁支术语，先收敛主主题与相邻主题。",
        "open_questions": open_questions,
    }
    return post_process_topic_adjudication(payload, intent_payload, focus_boundary_payload, repo_research_payloads)


def build_topic_adjudication_native(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(repo_research_payloads[0]["repo_path"]) if repo_research_payloads else None
    raw = client.run_prompt_only(
        build_topic_adjudication_prompt(intent_payload, focus_boundary_payload, repo_research_payloads),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_topic_adjudication_output(raw)
    fallback = build_topic_adjudication_local(intent_payload, focus_boundary_payload, repo_research_payloads)
    merged = fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "primary_subject": str(parsed.get("primary_subject") or fallback["primary_subject"]),
        "related_subjects": unique_strings(parsed.get("related_subjects", []) + fallback["related_subjects"])[:10],
        "adjacent_subjects": unique_strings(parsed.get("adjacent_subjects", []) + fallback["adjacent_subjects"])[:8],
        "suppressed_terms": unique_strings(parsed.get("suppressed_terms", []) + fallback["suppressed_terms"])[:8],
        "suppressed_modules": unique_strings(parsed.get("suppressed_modules", []) + fallback["suppressed_modules"])[:10],
        "suppressed_routes": unique_strings(parsed.get("suppressed_routes", []) + fallback["suppressed_routes"])[:10],
        "reason": str(parsed.get("reason") or fallback["reason"]),
        "open_questions": unique_questions(parsed.get("open_questions", []) + fallback["open_questions"]),
    }
    return post_process_topic_adjudication(merged, intent_payload, focus_boundary_payload, repo_research_payloads)


def build_repo_role_signals(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> list[dict[str, object]]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_repo_role_signals_native(
                intent_payload,
                topic_adjudication_payload,
                repo_research_payloads,
                settings,
            )
        except Exception:
            results = build_repo_role_signals_local(intent_payload, topic_adjudication_payload, repo_research_payloads)
            for item in results:
                item["requested_executor"] = requested_executor
            return results
    return build_repo_role_signals_local(intent_payload, topic_adjudication_payload, repo_research_payloads)


def build_repo_role_signals_local(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> list[dict[str, object]]:
    del intent_payload
    suppressed_terms = [normalize_match_text(item) for item in topic_adjudication_payload.get("suppressed_terms", [])]
    results: list[dict[str, object]] = []
    for item in repo_research_payloads:
        modules = " ".join(_as_string_list(item.get("likely_modules"))).lower()
        route_hits = _as_string_list(item.get("route_hits"))
        route_blob = " ".join(route_hits).lower()
        context_blob = " ".join(_as_string_list(item.get("context_hits"))).lower()
        symbol_blob = " ".join(_as_string_list(item.get("symbol_hits"))).lower()
        note_blob = " ".join(_as_string_list(item.get("facts")) + _as_string_list(item.get("inferences"))).lower()
        service_or_room_signal = any(
            token in modules or token in context_blob or token in symbol_blob
            for token in ("enter_room", "room_preview", "room init", "room_info", "notify", "refresh")
        )
        has_external_entry_signal = bool(route_hits) or any(token in modules for token in ("handler", "router", "api", "http"))
        has_http_api_signal = bool(route_hits) or any(token in modules for token in ("router", "api", "http", "preview", "pop"))
        has_orchestration_signal = any(token in modules for token in ("engine", "converter", "provider", "loader", "dto", "assemble", "pack"))
        if "dal/rpc" in modules or ("rpc" in modules and not has_http_api_signal):
            has_orchestration_signal = False
        has_service_aggregation_signal = service_or_room_signal or any(
            token in modules for token in ("service", "handler", "dal/rpc", "notify")
        )
        has_frontend_assembly_signal = any(token in modules for token in ("bff", "lynx", "pincard", "view", "render"))
        has_shared_capability_signal = any(token in modules for token in ("abtest", "schema", "config", "common", "cache", "relation", "util"))
        has_runtime_update_signal = any(token in modules for token in ("notify", "message", "refresh", "im", "callback"))
        suppressed_overlap = sum(
            1
            for term in suppressed_terms
            if term and term in normalize_match_text(" ".join([modules, route_blob, context_blob, symbol_blob, note_blob]))
        )
        if suppressed_overlap >= 2 and has_shared_capability_signal:
            has_external_entry_signal = False
        role_label = resolve_role_label_from_signals(
            has_external_entry_signal=has_external_entry_signal,
            has_http_api_signal=has_http_api_signal,
            has_orchestration_signal=has_orchestration_signal,
            has_service_aggregation_signal=has_service_aggregation_signal,
            has_frontend_assembly_signal=has_frontend_assembly_signal,
            has_shared_capability_signal=has_shared_capability_signal,
            has_runtime_update_signal=has_runtime_update_signal,
        )
        signal_notes = unique_strings(
            [
                "存在对外入口信号" if has_external_entry_signal else "",
                "存在 HTTP/API 信号" if has_http_api_signal else "",
                "存在数据编排信号" if has_orchestration_signal else "",
                "存在服务聚合信号" if has_service_aggregation_signal else "",
                "存在前端/BFF 装配信号" if has_frontend_assembly_signal else "",
                "存在公共能力信号" if has_shared_capability_signal else "",
                "存在运行时刷新信号" if has_runtime_update_signal else "",
                "相邻主题命中较多，已对入口判断降权" if suppressed_overlap >= 2 else "",
            ]
        )
        results.append(
            {
                "repo_id": str(item["repo_id"]),
                "repo_display_name": str(item.get("repo_display_name") or item["repo_id"]),
                "executor": EXECUTOR_LOCAL,
                "requested_executor": EXECUTOR_LOCAL,
                "has_external_entry_signal": has_external_entry_signal,
                "has_http_api_signal": has_http_api_signal,
                "has_orchestration_signal": has_orchestration_signal,
                "has_frontend_assembly_signal": has_frontend_assembly_signal,
                "has_shared_capability_signal": has_shared_capability_signal,
                "has_runtime_update_signal": has_runtime_update_signal,
                "signal_notes": signal_notes,
                "resolved_role_label": role_label,
                "open_questions": filter_publishable_open_questions(
                    ["该 repo 的角色判断是否仍受到相邻主题噪音影响。" if suppressed_overlap >= 2 else ""]
                ),
            }
        )
    return results


def build_repo_role_signals_native(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
) -> list[dict[str, object]]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(repo_research_payloads[0]["repo_path"]) if repo_research_payloads else None
    raw = client.run_prompt_only(
        build_repo_role_signals_prompt(intent_payload, topic_adjudication_payload, repo_research_payloads),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_repo_role_signals_output(raw)
    fallback = {
        item["repo_id"]: item
        for item in build_repo_role_signals_local(intent_payload, topic_adjudication_payload, repo_research_payloads)
    }
    merged: list[dict[str, object]] = []
    for item in parsed:
        repo_id = str(item["repo_id"])
        base = fallback.get(repo_id, {})
        merged.append(
            {
                **base,
                **item,
                "executor": EXECUTOR_NATIVE,
                "requested_executor": EXECUTOR_NATIVE,
                "repo_display_name": str(item.get("repo_display_name") or base.get("repo_display_name") or repo_id),
                "signal_notes": unique_strings(_as_string_list(item.get("signal_notes")) + _as_string_list(base.get("signal_notes"))),
                "open_questions": filter_publishable_open_questions(
                    _as_string_list(item.get("open_questions")) + _as_string_list(base.get("open_questions"))
                ),
            }
        )
    for repo_id, item in fallback.items():
        if not any(str(existing.get("repo_id")) == repo_id for existing in merged):
            merged.append(item)
    return merged


def resolve_role_label_from_signals(
    *,
    has_external_entry_signal: bool,
    has_http_api_signal: bool,
    has_orchestration_signal: bool,
    has_service_aggregation_signal: bool,
    has_frontend_assembly_signal: bool,
    has_shared_capability_signal: bool,
    has_runtime_update_signal: bool,
) -> str:
    if has_frontend_assembly_signal:
        return "前端/BFF 装配层"
    if has_http_api_signal and has_external_entry_signal:
        return "HTTP/API 入口"
    if has_service_aggregation_signal and (has_runtime_update_signal or has_external_entry_signal):
        return "服务聚合入口"
    if has_orchestration_signal and not has_shared_capability_signal:
        return "数据编排层"
    if has_shared_capability_signal and not has_external_entry_signal and not has_http_api_signal:
        return "公共能力底座"
    if has_runtime_update_signal or has_service_aggregation_signal or has_external_entry_signal:
        return "服务聚合入口"
    if has_shared_capability_signal:
        return "公共能力底座"
    return "系统支撑仓库"


def build_flow_slot_extraction(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_flow_slot_extraction_native(
                intent_payload,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                repo_research_payloads,
                settings,
            )
        except Exception as error:
            local = build_flow_slot_extraction_local(
                intent_payload,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                repo_research_payloads,
            )
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_flow_slot_extraction_local(intent_payload, topic_adjudication_payload, repo_role_signal_payloads, repo_research_payloads)


def build_flow_slot_extraction_local(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
) -> dict[str, object]:
    del intent_payload
    signal_map = {str(item["repo_id"]): item for item in repo_role_signal_payloads}
    repo_map = {str(item["repo_id"]): item for item in repo_research_payloads}

    def build_slot(repo_ids: list[str], summary: str, action: str, output: str) -> dict[str, object]:
        evidence = unique_strings(
            [
                *[
                    str(value)
                    for repo_id in repo_ids
                    for value in repo_map.get(repo_id, {}).get("facts", [])[:2]
                ],
                *[
                    str(value)
                    for repo_id in repo_ids
                    for value in signal_map.get(repo_id, {}).get("signal_notes", [])[:2]
                ],
            ]
        )[:6]
        return {
            "repos": repo_ids,
            "primary_repos": repo_ids[:2],
            "summary": summary,
            "action": action,
            "output": output,
            "evidence": evidence,
        }

    sync_repos = [repo_id for repo_id, signal in signal_map.items() if signal.get("resolved_role_label") == "服务聚合入口"]
    async_repos = [repo_id for repo_id, signal in signal_map.items() if signal.get("resolved_role_label") == "HTTP/API 入口"]
    orchestration_repos = [repo_id for repo_id, signal in signal_map.items() if signal.get("resolved_role_label") == "数据编排层"]
    runtime_repos = [repo_id for repo_id, signal in signal_map.items() if signal.get("has_runtime_update_signal")]
    frontend_repos = [repo_id for repo_id, signal in signal_map.items() if signal.get("resolved_role_label") == "前端/BFF 装配层"]
    support_repos = [repo_id for repo_id, signal in signal_map.items() if signal.get("resolved_role_label") == "公共能力底座"]

    slots = {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "sync_entry_or_init": build_slot(sync_repos[:2], f"同步入口或初始化通常由 {', '.join(f'`{repo_id}`' for repo_id in sync_repos[:2])} 承接。", "聚合同步进房或初始化参数", "进房初始化数据") if sync_repos else {},
        "async_preview_or_pre_enter": build_slot(async_repos[:2], f"异步预览或进房前链路通常由 {', '.join(f'`{repo_id}`' for repo_id in async_repos[:2])} 承接。", "提供 preview/pop 等异步入口", "预览态讲解卡数据") if async_repos else {},
        "data_orchestration": build_slot(orchestration_repos[:2], f"主数据编排通常由 {', '.join(f'`{repo_id}`' for repo_id in orchestration_repos[:2])} 完成。", "收敛配置、状态和商品模型", "竞拍卡数据结构") if orchestration_repos else {},
        "runtime_update_or_notification": build_slot(runtime_repos[:2], f"运行时刷新或通知通常由 {', '.join(f'`{repo_id}`' for repo_id in runtime_repos[:2])} 负责。", "处理事件刷新或通知分发", "客户端刷新或通知事件") if runtime_repos else {},
        "frontend_bff_transform": build_slot(frontend_repos[:2], f"前端/BFF 形态转换通常由 {', '.join(f'`{repo_id}`' for repo_id in frontend_repos[:2])} 承担。", "把上游数据装配成展示形态", "前端/BFF 可消费结构") if frontend_repos else {},
        "config_or_experiment_support": build_slot(support_repos[:2], f"配置或实验支撑通常由 {', '.join(f'`{repo_id}`' for repo_id in support_repos[:2])} 提供。", "提供配置、AB 和 schema 支撑", "开关与共享配置能力") if support_repos else {},
        "open_questions": filter_publishable_open_questions(
            [
                "当前主链路场景槽位是否已经覆盖同步、异步、编排和展示四类关键阶段。",
            ],
        ),
    }
    return sanitize_flow_slot_payload(slots, topic_adjudication_payload)


def build_flow_slot_extraction_native(
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(repo_research_payloads[0]["repo_path"]) if repo_research_payloads else None
    raw = client.run_prompt_only(
        build_flow_slot_extraction_prompt(intent_payload, topic_adjudication_payload, repo_role_signal_payloads, repo_research_payloads),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_flow_slot_extraction_output(raw)
    fallback = build_flow_slot_extraction_local(intent_payload, topic_adjudication_payload, repo_role_signal_payloads, repo_research_payloads)
    merged = fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "open_questions": filter_publishable_open_questions(
            parsed.get("open_questions", []) + fallback.get("open_questions", [])
        ),
    }
    for slot in (
        "sync_entry_or_init",
        "async_preview_or_pre_enter",
        "data_orchestration",
        "runtime_update_or_notification",
        "frontend_bff_transform",
        "config_or_experiment_support",
    ):
        current = parsed.get(slot) if isinstance(parsed.get(slot), dict) else {}
        merged[slot] = current or fallback.get(slot, {})
    return sanitize_flow_slot_payload(merged, topic_adjudication_payload)


def slot_default_summary(slot: str, repos: list[str]) -> str:
    repo_text = "、".join(f"`{repo_id}`" for repo_id in repos[:3]) or "相关仓库"
    if slot == "sync_entry_or_init":
        return f"同步进房初始化链路由 {repo_text} 承接，负责基础信息和初始化数据聚合。"
    if slot == "async_preview_or_pre_enter":
        return f"异步预览或进房前链路由 {repo_text} 承接，负责预览态或进房前数据获取。"
    if slot == "data_orchestration":
        return f"主数据编排链路由 {repo_text} 完成，负责状态与展示数据收敛。"
    if slot == "runtime_update_or_notification":
        return f"运行时刷新或通知链路由 {repo_text} 负责，承接事件变化后的更新分发。"
    if slot == "frontend_bff_transform":
        return f"前端/BFF 形态转换由 {repo_text} 承担，负责把上游数据组装成前端可消费结构。"
    if slot == "config_or_experiment_support":
        return f"配置与实验支撑由 {repo_text} 提供，负责开关、实验和 schema 等辅助能力。"
    return ""


def render_flow_slot_sentence(slot: dict[str, object], fallback_summary: str) -> str:
    primary_repos = _as_string_list(slot.get("primary_repos")) or _as_string_list(slot.get("repos"))
    action = str(slot.get("action") or "").strip()
    output = str(slot.get("output") or "").strip()
    if not primary_repos or not action or not output:
        return fallback_summary
    repo_text = "、".join(f"`{repo}`" for repo in primary_repos[:2])
    return f"{repo_text} 负责{action}，输出{output}。"


def contains_implementation_symbol(text: str) -> bool:
    return bool(text and re.search(r"\b[A-Z][A-Za-z0-9_]{5,}\b", text))


def sanitize_flow_slot_payload(
    payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
) -> dict[str, object]:
    blocked_terms = [normalize_match_text(item) for item in collect_blocked_topic_terms(topic_adjudication_payload)]
    result = dict(payload)
    for slot in (
        "sync_entry_or_init",
        "async_preview_or_pre_enter",
        "data_orchestration",
        "runtime_update_or_notification",
        "frontend_bff_transform",
        "config_or_experiment_support",
    ):
        current = result.get(slot)
        if not isinstance(current, dict) or not current:
            continue
        summary = str(current.get("summary") or "").strip()
        repos = _as_string_list(current.get("repos"))
        normalized = normalize_match_text(summary)
        if slot != "config_or_experiment_support" and any(
            term and term in normalized for term in blocked_terms
        ):
            current = {**current, "summary": slot_default_summary(slot, repos)}
        elif slot != "config_or_experiment_support" and contains_implementation_symbol(summary):
            current = {**current, "summary": slot_default_summary(slot, repos)}
        elif slot == "config_or_experiment_support" and (
            not summary or any(marker in normalized for marker in TOPIC_CONFIG_MARKERS)
        ):
            current = {**current, "summary": slot_default_summary(slot, repos)}
        if current.get("summary"):
            current = {**current, "summary": render_flow_slot_sentence(current, str(current.get("summary") or ""))}
        result[slot] = current
    return result


def build_flow_judge(
    documents: list[KnowledgeDocument],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_flow_judge_native(
                documents,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                flow_slot_payload,
                settings,
            )
        except Exception as error:
            local = build_flow_judge_local(documents, topic_adjudication_payload, repo_role_signal_payloads, flow_slot_payload)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_flow_judge_local(documents, topic_adjudication_payload, repo_role_signal_payloads, flow_slot_payload)


def build_flow_judge_local(
    documents: list[KnowledgeDocument],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
) -> dict[str, object]:
    blocked_terms = [normalize_match_text(item) for item in collect_blocked_topic_terms(topic_adjudication_payload)]
    public_repos = {
        str(item["repo_id"])
        for item in repo_role_signal_payloads
        if str(item.get("resolved_role_label") or "") == "公共能力底座"
    }
    findings: list[dict[str, object]] = []
    for document in documents:
        if document.kind != "flow":
            continue
        summary_text = extract_markdown_section(document.body, "## Summary")
        main_flow_text = extract_markdown_section(document.body, "## Main Flow")
        open_question_text = extract_markdown_section(document.body, "## Open Questions")
        normalized_summary = normalize_match_text(summary_text)
        normalized_main_flow = normalize_match_text(main_flow_text)
        normalized_questions = normalize_match_text(open_question_text)

        summary_first_paragraph = normalize_match_text(summary_text.split("\n\n")[0] if summary_text else "")
        main_flow_lines = [normalize_match_text(line) for line in main_flow_text.splitlines() if line.strip()]
        main_flow_primary_lines = [
            line for line in main_flow_lines
            if not any(token in line for token in ("配置", "实验", "支撑", "schema", "ab"))
        ]
        hit_terms = [
            term
            for term in blocked_terms
            if term and (term in summary_first_paragraph or any(term in line for line in main_flow_primary_lines[:4]))
        ]
        if hit_terms:
            findings.append(
                {
                    "severity": "high",
                    "code": "suppressed_topic_in_mainline",
                    "document_id": document.id,
                    "message": f"主线正文仍出现被压制的相邻主题：{', '.join(hit_terms[:3])}",
                }
            )

        question_terms = [term for term in blocked_terms if term and term in normalized_questions]
        if question_terms:
            findings.append(
                {
                    "severity": "medium",
                    "code": "suppressed_topic_in_questions",
                    "document_id": document.id,
                    "message": f"Open Questions 仍围绕被压制主题展开：{', '.join(question_terms[:3])}",
                }
            )

        first_step = main_flow_text.splitlines()[0] if main_flow_text.strip() else ""
        for repo_id in public_repos:
            if repo_id in first_step or repo_id in summary_text.splitlines()[0:1]:
                findings.append(
                    {
                        "severity": "medium",
                        "code": "shared_repo_as_entry",
                        "document_id": document.id,
                        "message": f"公共能力仓库 `{repo_id}` 被写到了主入口位置。",
                    }
                )

        if not any(isinstance(flow_slot_payload.get(slot), dict) and flow_slot_payload.get(slot) for slot in (
            "sync_entry_or_init",
            "async_preview_or_pre_enter",
            "data_orchestration",
            "frontend_bff_transform",
        )):
            findings.append(
                {
                    "severity": "medium",
                    "code": "flow_slots_too_sparse",
                    "document_id": document.id,
                    "message": "Main Flow 槽位仍然过 sparse，主链路阶段覆盖不足。",
                }
            )
    must_rewrite_summary = any(item.get("code") == "suppressed_topic_in_mainline" for item in findings)
    must_prune_open_questions = any(
        item.get("code") in {"suppressed_topic_in_questions", "open_questions_around_suppressed_adjacent"}
        for item in findings
    )
    must_rewrite_flow_steps = must_rewrite_summary or any(
        item.get("code") == "shared_repo_as_entry" for item in findings
    )
    return {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "passed": not findings,
        "findings": findings,
        "must_rewrite_summary": must_rewrite_summary,
        "must_rewrite_flow_steps": must_rewrite_flow_steps,
        "must_prune_open_questions": must_prune_open_questions,
    }


def build_flow_judge_native(
    documents: list[KnowledgeDocument],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = None
    raw = client.run_prompt_only(
        build_flow_judge_prompt(
            [serialize_document(document) for document in documents],
            topic_adjudication_payload,
            repo_role_signal_payloads,
            flow_slot_payload,
        ),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_flow_judge_output(raw)
    fallback = build_flow_judge_local(documents, topic_adjudication_payload, repo_role_signal_payloads, flow_slot_payload)
    merged_findings = list(fallback.get("findings", []))
    seen = {
        (
            str(item.get("document_id") or ""),
            str(item.get("code") or ""),
            str(item.get("message") or ""),
        )
        for item in merged_findings
        if isinstance(item, dict)
    }
    for item in parsed.get("findings", []):
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("document_id") or ""),
            str(item.get("code") or ""),
            str(item.get("message") or ""),
        )
        if key in seen:
            continue
        merged_findings.append(item)
        seen.add(key)
    return {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "passed": not merged_findings,
        "findings": merged_findings,
        "must_rewrite_summary": any(item.get("code") == "suppressed_topic_in_mainline" for item in merged_findings),
        "must_rewrite_flow_steps": any(
            item.get("code") in {"suppressed_topic_in_mainline", "shared_repo_as_entry"} for item in merged_findings
        ),
        "must_prune_open_questions": any(
            item.get("code") in {"suppressed_topic_in_questions", "open_questions_around_suppressed_adjacent"}
            for item in merged_findings
        ),
    }


def apply_flow_judge_notes(
    documents: list[KnowledgeDocument],
    flow_judge_payload: dict[str, object],
    *,
    intent_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
    flow_slot_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    topic_adjudication_payload: dict[str, object],
) -> list[KnowledgeDocument]:
    findings_by_doc: dict[str, list[str]] = {}
    for item in flow_judge_payload.get("findings", []):
        if not isinstance(item, dict):
            continue
        document_id = str(item.get("document_id") or "").strip()
        message = str(item.get("message") or "").strip()
        if not document_id or not message:
            continue
        findings_by_doc.setdefault(document_id, []).append(message)
    if not findings_by_doc:
        return documents
    result: list[KnowledgeDocument] = []
    blocked_terms = [normalize_match_text(item) for item in collect_blocked_topic_terms(topic_adjudication_payload)]
    for document in documents:
        notes = findings_by_doc.get(document.id)
        if not notes:
            result.append(document)
            continue
        retrieval_notes = list(document.evidence.retrievalNotes)
        retrieval_notes.append(f"flow judge findings: {'；'.join(notes[:3])}")
        updated_document = document
        if document.kind == "flow":
            rewritten_outline = sanitize_storyline_outline(
                dict(storyline_outline_payload),
                intent_payload,
                topic_adjudication_payload,
            )
            if flow_judge_payload.get("must_rewrite_summary"):
                rewritten_outline["system_summary"] = sanitize_storyline_summary_lines(
                    _as_string_list(rewritten_outline.get("system_summary")),
                    intent_payload,
                )
            if flow_judge_payload.get("must_rewrite_flow_steps"):
                rewritten_outline["main_flow_steps"] = sanitize_storyline_steps(
                    build_storyline_steps_local(flow_slot_payload, rewritten_outline.get("repo_hints", [])),
                    topic_adjudication_payload,
                )
            open_questions = list(document.evidence.openQuestions)
            if flow_judge_payload.get("must_prune_open_questions"):
                open_questions = filter_publishable_open_questions(
                    [
                        question
                        for question in open_questions
                        if not any(term and term in normalize_match_text(question) for term in blocked_terms)
                    ],
                    limit=8,
                )
            rebuilt_body = soften_weak_claims(
                build_body("flow", intent_payload, repo_research_payloads, rewritten_outline, open_questions)
            )
            updated_document = document.model_copy(
                update={
                    "body": rebuilt_body,
                    "evidence": document.evidence.model_copy(
                        update={
                            "openQuestions": filter_publishable_open_questions(open_questions, limit=8),
                            "retrievalNotes": retrieval_notes,
                        }
                    ),
                }
            )
        else:
            updated_document = document.model_copy(
                update={
                    "evidence": document.evidence.model_copy(update={"retrievalNotes": retrieval_notes})
                }
            )
        result.append(updated_document)
    return result


def build_flow_final_editor(
    documents: list[KnowledgeDocument],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
    flow_judge_payload: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_flow_final_editor_native(
                documents,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                flow_slot_payload,
                storyline_outline_payload,
                flow_judge_payload,
                settings,
            )
        except Exception as error:
            return {
                "executor": EXECUTOR_LOCAL,
                "requested_executor": requested_executor,
                "fallback_reason": str(error),
                "documents": [],
            }
    return {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": requested_executor,
        "documents": [],
    }


def build_flow_final_editor_native(
    documents: list[KnowledgeDocument],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    storyline_outline_payload: dict[str, object],
    flow_judge_payload: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    flow_document = next((document for document in documents if document.kind == "flow"), None)
    if flow_document is None:
        return {"executor": EXECUTOR_NATIVE, "requested_executor": EXECUTOR_NATIVE, "documents": []}
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_prompt_only(
        build_flow_final_editor_prompt(
            serialize_document(flow_document),
            topic_adjudication_payload,
            repo_role_signal_payloads,
            flow_slot_payload,
            storyline_outline_payload,
            flow_judge_payload,
        ),
        settings.native_query_timeout,
        cwd=None,
    )
    parsed = extract_flow_final_editor_output(raw)
    return {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "documents": [{"document_id": flow_document.id, **parsed}],
    }


def apply_flow_final_editor(
    documents: list[KnowledgeDocument],
    flow_final_editor_payload: dict[str, object],
) -> list[KnowledgeDocument]:
    edits = {
        str(item.get("document_id") or ""): item
        for item in flow_final_editor_payload.get("documents", [])
        if isinstance(item, dict)
    }
    if not edits:
        return documents
    result: list[KnowledgeDocument] = []
    for document in documents:
        edit = edits.get(document.id)
        if not edit or document.kind != "flow":
            result.append(document)
            continue
        body = document.body
        body = replace_markdown_section(body, "## Summary", "\n\n".join(_as_string_list(edit.get("summary_lines"))))
        body = replace_markdown_section(body, "## Main Flow", "\n".join(render_numbered_lines(_as_string_list(edit.get("main_flow_steps")))))
        body = replace_markdown_section(body, "## Dependencies", "\n".join(render_bulleted_lines(_as_string_list(edit.get("dependency_lines")))))
        body = replace_markdown_section(body, "## Open Questions", "\n".join(render_bulleted_lines(_as_string_list(edit.get("open_questions")))))
        result.append(
            document.model_copy(
                update={
                    "body": body,
                    "evidence": document.evidence.model_copy(
                        update={"openQuestions": filter_publishable_open_questions(_as_string_list(edit.get("open_questions")), limit=6)}
                    ),
                }
            )
        )
    return result


def build_flow_final_polisher(
    documents: list[KnowledgeDocument],
    flow_final_editor_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_judge_payload: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_flow_final_polisher_native(
                documents,
                flow_final_editor_payload,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                flow_judge_payload,
                settings,
            )
        except Exception as error:
            return {
                "executor": EXECUTOR_LOCAL,
                "requested_executor": requested_executor,
                "fallback_reason": str(error),
                "documents": [],
            }
    return {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": requested_executor,
        "documents": [],
    }


def build_flow_final_polisher_native(
    documents: list[KnowledgeDocument],
    flow_final_editor_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_judge_payload: dict[str, object],
    settings: Settings,
) -> dict[str, object]:
    flow_document = next((document for document in documents if document.kind == "flow"), None)
    if flow_document is None:
        return {"executor": EXECUTOR_NATIVE, "requested_executor": EXECUTOR_NATIVE, "documents": []}
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_prompt_only(
        build_flow_final_polisher_prompt(
            serialize_document(flow_document),
            flow_final_editor_payload,
            topic_adjudication_payload,
            repo_role_signal_payloads,
            flow_judge_payload,
        ),
        settings.native_query_timeout,
        cwd=None,
    )
    parsed = extract_flow_final_polisher_output(raw)
    return {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "documents": [{"document_id": flow_document.id, **parsed}],
    }


def apply_flow_final_polisher(
    documents: list[KnowledgeDocument],
    flow_final_polisher_payload: dict[str, object],
) -> list[KnowledgeDocument]:
    edits = {
        str(item.get("document_id") or ""): item
        for item in flow_final_polisher_payload.get("documents", [])
        if isinstance(item, dict)
    }
    if not edits:
        return documents
    result: list[KnowledgeDocument] = []
    for document in documents:
        edit = edits.get(document.id)
        if not edit or document.kind != "flow":
            result.append(document)
            continue
        body = document.body
        body = replace_markdown_section(body, "## Summary", "\n\n".join(_as_string_list(edit.get("summary_lines"))))
        body = replace_markdown_section(body, "## Main Flow", "\n".join(render_numbered_lines(_as_string_list(edit.get("main_flow_steps")))))
        body = replace_markdown_section(body, "## Dependencies", "\n".join(render_bulleted_lines(_as_string_list(edit.get("dependency_lines")))))
        body = replace_markdown_section(body, "## Open Questions", "\n".join(render_bulleted_lines(_as_string_list(edit.get("open_questions")))))
        result.append(
            document.model_copy(
                update={
                    "body": body,
                    "evidence": document.evidence.model_copy(
                        update={"openQuestions": filter_publishable_open_questions(_as_string_list(edit.get("open_questions")), limit=6)}
                    ),
                }
            )
        )
    return result


def replace_markdown_section(body: str, heading: str, new_content: str) -> str:
    marker = f"{heading}\n"
    start = body.find(marker)
    if start == -1:
        return body
    content_start = start + len(marker)
    remainder = body[content_start:]
    next_heading = remainder.find("\n## ")
    if next_heading == -1:
        return body[:content_start] + new_content.strip()
    return body[:content_start] + new_content.strip() + remainder[next_heading:]


def render_numbered_lines(lines: list[str]) -> list[str]:
    return [f"{index}. {str(line).strip()}" for index, line in enumerate(lines, start=1) if str(line).strip()]


def render_bulleted_lines(lines: list[str]) -> list[str]:
    return [f"- {str(line).strip()}" for line in lines if str(line).strip()]


def extract_markdown_section(body: str, heading: str) -> str:
    marker = f"{heading}\n"
    start = body.find(marker)
    if start == -1:
        return ""
    content_start = start + len(marker)
    remainder = body[content_start:]
    next_heading = remainder.find("\n## ")
    if next_heading == -1:
        return remainder.strip()
    return remainder[:next_heading].strip()


def build_storyline_outline(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_storyline_outline_native(
                intent_payload,
                focus_boundary_payload,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                flow_slot_payload,
                repo_research_payloads,
                settings,
            )
        except Exception as error:
            local = build_storyline_outline_local(
                intent_payload,
                focus_boundary_payload,
                topic_adjudication_payload,
                repo_role_signal_payloads,
                flow_slot_payload,
                repo_research_payloads,
            )
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_storyline_outline_local(
        intent_payload,
        focus_boundary_payload,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        flow_slot_payload,
        repo_research_payloads,
    )


def build_storyline_outline_local(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
) -> dict[str, object]:
    signal_map = {str(item["repo_id"]): item for item in repo_role_signal_payloads}
    repo_hints = [
        build_repo_hint_outline(item, signal_map.get(str(item["repo_id"]), {}), topic_adjudication_payload)
        for item in repo_research_payloads
    ]
    ordered_hints = sorted(repo_hints, key=repo_outline_sort_key)
    primary_subject = str(
        topic_adjudication_payload.get("primary_subject")
        or focus_boundary_payload.get("canonical_subject")
        or intent_payload["normalized_intent"]
    )
    system_summary = [
        f"{primary_subject} 主要由 {', '.join(f'`{item['repo_id']}`' for item in ordered_hints[:3])} 等仓库协作完成。"
    ]
    if any(item["role_label"] == "公共能力底座" for item in ordered_hints):
        system_summary.append("公共能力仓库更多提供 AB、schema、配置或共享工具，不直接承担主链路编排。")
    main_flow_steps = build_storyline_steps_local(flow_slot_payload, ordered_hints)
    dependencies = build_dependency_lines_local(ordered_hints, repo_research_payloads)
    open_questions = filter_publishable_open_questions(
        [
            *[str(item) for item in focus_boundary_payload.get("open_questions", [])],
            *[str(item) for item in topic_adjudication_payload.get("open_questions", [])],
            *[str(item) for item in flow_slot_payload.get("open_questions", [])],
            *[str(question) for repo in repo_research_payloads for question in repo.get("open_questions", [])[:1]],
        ],
        limit=6,
    )
    domain_summary = [
        f"{primary_subject} 关注入口、状态、编排和前端展示之间的协作关系。"
    ]
    outline = {
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "system_summary": system_summary[:4],
        "main_flow_steps": main_flow_steps[:6],
        "dependencies": dependencies[:8],
        "repo_hints": ordered_hints,
        "domain_summary": domain_summary[:4],
        "open_questions": open_questions,
    }
    return sanitize_storyline_outline(outline, intent_payload, topic_adjudication_payload)


def build_storyline_outline_native(
    intent_payload: dict[str, object],
    focus_boundary_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
    repo_role_signal_payloads: list[dict[str, object]],
    flow_slot_payload: dict[str, object],
    repo_research_payloads: list[dict[str, object]],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    cwd = str(repo_research_payloads[0]["repo_path"]) if repo_research_payloads else None
    raw = client.run_prompt_only(
        build_storyline_outline_prompt(
            intent_payload,
            focus_boundary_payload,
            topic_adjudication_payload,
            repo_role_signal_payloads,
            flow_slot_payload,
            repo_research_payloads,
        ),
        settings.native_query_timeout,
        cwd=cwd,
    )
    parsed = extract_storyline_outline_output(raw)
    fallback = build_storyline_outline_local(
        intent_payload,
        focus_boundary_payload,
        topic_adjudication_payload,
        repo_role_signal_payloads,
        flow_slot_payload,
        repo_research_payloads,
    )
    merged_repo_hints = merge_storyline_repo_hints(fallback["repo_hints"], parsed["repo_hints"])
    outline = fallback | {
        "executor": EXECUTOR_NATIVE,
        "requested_executor": EXECUTOR_NATIVE,
        "system_summary": parsed["system_summary"] or fallback["system_summary"],
        "main_flow_steps": parsed["main_flow_steps"] or fallback["main_flow_steps"],
        "dependencies": parsed["dependencies"] or fallback["dependencies"],
        "repo_hints": merged_repo_hints or fallback["repo_hints"],
        "domain_summary": parsed["domain_summary"] or fallback["domain_summary"],
        "open_questions": unique_questions(parsed["open_questions"] + fallback["open_questions"]),
    }
    return sanitize_storyline_outline(outline, intent_payload, topic_adjudication_payload)


def build_repo_hint_outline(
    item: dict[str, object],
    role_signal: dict[str, object],
    topic_adjudication_payload: dict[str, object],
) -> dict[str, object]:
    repo_id = str(item["repo_id"])
    repo_display_name = str(item.get("repo_display_name") or repo_id)
    role = str(item.get("role") or "unknown")
    suppressed_terms = [normalize_match_text(value) for value in topic_adjudication_payload.get("suppressed_terms", [])]
    likely_modules = [
        str(value)
        for value in item.get("likely_modules", [])
        if not any(term and term in normalize_match_text(str(value)) for term in suppressed_terms)
    ][:5]
    role_label = str(role_signal.get("resolved_role_label") or infer_repo_role_label(role, likely_modules, item))
    responsibilities = infer_repo_responsibilities(item, role_label)
    upstream = infer_repo_connections(item, "upstream")
    downstream = infer_repo_connections(item, "downstream")
    notes = unique_strings(
        [
            *[str(value) for value in role_signal.get("signal_notes", [])[:2]],
            *[str(value) for value in item.get("risks", [])[:2]],
        ]
    )[:4]
    return {
        "repo_id": repo_id,
        "repo_display_name": repo_display_name,
        "role_label": role_label,
        "key_modules": normalize_outline_modules(likely_modules),
        "responsibilities": responsibilities,
        "upstream": upstream,
        "downstream": downstream,
        "notes": notes,
    }


def sanitize_storyline_summary_lines(
    summary_lines: list[str],
    intent_payload: dict[str, object],
) -> list[str]:
    if not summary_lines:
        return [f"{intent_payload['normalized_intent']} 主要围绕入口收敛、主数据编排和前端展示装配展开。"]
    normalized_intent = str(intent_payload.get("normalized_intent") or "")
    rewritten: list[str] = []
    for line in summary_lines:
        current = str(line).strip()
        if not current:
            continue
        if "由" in current and "承接" in current and "负责" in current and "提供" in current:
            rewritten.append(
                f"{normalized_intent} 由 HTTP/API 入口、数据编排层、前端/BFF 装配层和公共能力底座共同组成。"
            )
            continue
        rewritten.append(current)
    return unique_strings(rewritten)[:4]


def build_role_driven_summary(repo_hints: list[dict[str, object]], intent_payload: dict[str, object]) -> list[str]:
    role_map = {str(item.get("role_label") or ""): str(item.get("repo_display_name") or item.get("repo_id") or "") for item in repo_hints}
    http_repo = role_map.get("HTTP/API 入口", "")
    service_repos = [str(item.get("repo_display_name") or item.get("repo_id") or "") for item in repo_hints if str(item.get("role_label") or "") == "服务聚合入口"]
    orchestration_repos = [str(item.get("repo_display_name") or item.get("repo_id") or "") for item in repo_hints if str(item.get("role_label") or "") == "数据编排层"]
    bff_repo = role_map.get("前端/BFF 装配层", "")
    support_repo = role_map.get("公共能力底座", "")
    parts: list[str] = []
    if http_repo:
        parts.append(f"`{http_repo}` 是 HTTP/API 入口")
    if service_repos:
        parts.append(f"{'、'.join(f'`{repo}`' for repo in service_repos[:2])} 负责服务聚合")
    if orchestration_repos:
        parts.append(f"{'、'.join(f'`{repo}`' for repo in orchestration_repos[:2])} 负责编排")
    if bff_repo:
        parts.append(f"`{bff_repo}` 负责前端/BFF 装配")
    if support_repo:
        parts.append(f"`{support_repo}` 提供公共能力")
    if parts:
        return [f"{intent_payload['normalized_intent']} 中，" + "，".join(parts) + "。"]
    return sanitize_storyline_summary_lines([], intent_payload)


def sanitize_storyline_steps(
    steps: list[str],
    topic_adjudication_payload: dict[str, object],
) -> list[str]:
    blocked_terms = [normalize_match_text(item) for item in collect_blocked_topic_terms(topic_adjudication_payload)]
    sanitized: list[str] = []
    for step in steps:
        current = str(step).strip()
        normalized = normalize_match_text(current)
        if any(term and term in normalized for term in blocked_terms):
            continue
        if contains_implementation_symbol(current):
            continue
        sanitized.append(current)
    return unique_strings(sanitized)[:6]


def sanitize_repo_hint_item(
    item: dict[str, object],
    topic_adjudication_payload: dict[str, object],
) -> dict[str, object]:
    blocked_terms = [normalize_match_text(item) for item in collect_blocked_topic_terms(topic_adjudication_payload)]

    def keep(values: list[str]) -> list[str]:
        return [
            soften_repo_responsibility(value)
            for value in values
            if not any(term and term in normalize_match_text(value) for term in blocked_terms)
            and not contains_implementation_symbol(value)
        ]

    role_label = str(item.get("role_label") or "")
    responsibilities = keep(_as_string_list(item.get("responsibilities")))
    if not responsibilities:
        responsibilities = infer_repo_responsibilities({"facts": [], "inferences": []}, role_label)
    notes = keep(_as_string_list(item.get("notes")))
    key_modules = keep(_as_string_list(item.get("key_modules")))
    responsibilities = enforce_role_specific_responsibilities(role_label, responsibilities)
    notes = enforce_role_specific_notes(role_label, notes)
    return {
        **item,
        "key_modules": unique_strings(key_modules)[:6],
        "responsibilities": unique_strings(responsibilities)[:4],
        "notes": unique_strings(notes)[:4],
    }


def sanitize_storyline_outline(
    outline: dict[str, object],
    intent_payload: dict[str, object],
    topic_adjudication_payload: dict[str, object],
) -> dict[str, object]:
    sanitized_hints = [
        sanitize_repo_hint_item(item, topic_adjudication_payload)
        for item in outline.get("repo_hints", [])
        if isinstance(item, dict)
    ]
    sanitized = {
        **outline,
        "system_summary": build_role_driven_summary(sanitized_hints, intent_payload),
        "main_flow_steps": sanitize_storyline_steps(
            _as_string_list(outline.get("main_flow_steps")),
            topic_adjudication_payload,
        ),
        "repo_hints": sanitized_hints,
        "open_questions": filter_publishable_open_questions(
            [
                question
                for question in _as_string_list(outline.get("open_questions"))
                if not any(
                    term and term in normalize_match_text(question)
                    for term in [normalize_match_text(item) for item in collect_blocked_topic_terms(topic_adjudication_payload)]
                )
            ],
            limit=6,
        ),
    }
    return sanitized




def repo_outline_sort_key(item: dict[str, object]) -> tuple[int, str]:
    role_label = str(item.get("role_label") or "")
    if role_label == "服务聚合入口":
        return (0, str(item.get("repo_id") or ""))
    if role_label == "HTTP/API 入口":
        return (1, str(item.get("repo_id") or ""))
    if role_label == "服务聚合入口":
        return (2, str(item.get("repo_id") or ""))
    if role_label == "数据编排层":
        return (3, str(item.get("repo_id") or ""))
    if role_label == "前端/BFF 装配层":
        return (4, str(item.get("repo_id") or ""))
    if role_label == "公共能力底座":
        return (5, str(item.get("repo_id") or ""))
    return (6, str(item.get("repo_id") or ""))


def enforce_role_specific_responsibilities(role_label: str, responsibilities: list[str]) -> list[str]:
    values = [str(value).strip() for value in responsibilities if str(value).strip()]
    if role_label == "HTTP/API 入口":
        filtered = [
            value
            for value in values
            if "BFF层主入口" not in value and "BFF 层主入口" not in value and "主 BFF 层" not in value
        ]
        return filtered or ["承接 preview/pop 等异步或 API 场景请求，并决定是否走新架构或 BFF 路径。"]
    if role_label == "服务聚合入口":
        filtered = [
            value
            for value in values
            if "BFF层" not in value and "BFF 层" not in value
        ]
        return filtered or ["承接入口请求，并聚合同步进房或主链路场景参数。"]
    if role_label == "数据编排层":
        filtered = [
            value
            for value in values
            if "BFF层" not in value and "BFF 层" not in value and "关键环节" not in value and "主入口" not in value
        ]
        return filtered or ["收敛竞拍配置、状态和商品模型，输出主链路所需数据结构。"]
    if role_label == "前端/BFF 装配层":
        filtered = [
            value
            for value in values
            if "主入口" not in value and "HTTP/API 入口" not in value
        ]
        return filtered or ["把上游竞拍数据转换成前端或 BFF 可消费的展示结构。"]
    if role_label == "公共能力底座":
        return ["提供 AB、schema、配置或共享工具能力，不直接承接主链路。"]
    return values


def enforce_role_specific_notes(role_label: str, notes: list[str]) -> list[str]:
    values = [str(value).strip() for value in notes if str(value).strip()]
    if role_label == "公共能力底座":
        return [value for value in values if "路由" not in value and "入口" not in value][:4]
    if role_label == "前端/BFF 装配层":
        return [value for value in values if "主入口" not in value][:4]
    return values[:4]


def infer_repo_role_label(role: str, likely_modules: list[str], item: dict[str, object]) -> str:
    modules = " ".join(likely_modules).lower()
    route_hits = " ".join(str(value) for value in item.get("route_hits", [])).lower()
    if (
        "handler" in modules
        and (
            route_hits
            or any(token in modules for token in ("router", "api", "http", "preview", "pop"))
        )
    ):
        return "HTTP/API 入口"
    if any(token in modules for token in ("pincard", "bff")):
        return "前端/BFF 装配层"
    if any(token in modules for token in ("engine", "converter", "provider", "loader", "dto")):
        return "数据编排层"
    if any(token in modules for token in ("notify", "enter_room", "room_preview", "dal/rpc", "service", "preview_handler", "handler")):
        return "服务聚合入口"
    if "abtest" in modules or "schema" in modules:
        return "公共能力底座"
    if role == "supporting":
        return "公共能力底座"
    return "系统支撑仓库"


def normalize_outline_modules(modules: list[str]) -> list[str]:
    normalized: list[str] = []
    for module in modules:
        current = str(module).strip().replace(".go", "")
        if current and current not in normalized:
            normalized.append(current)
    return normalized[:5]


def infer_repo_responsibilities(item: dict[str, object], role_label: str) -> list[str]:
    facts = [str(value) for value in item.get("facts", [])]
    inferences = [str(value) for value in item.get("inferences", [])]
    responsibilities: list[str] = []
    if role_label == "服务聚合入口":
        responsibilities.append("承接入口请求，并聚合同步进房或主链路场景参数。")
    elif role_label == "HTTP/API 入口":
        responsibilities.append("承接 preview/pop 等异步或 API 场景请求，并决定是否走新架构或 BFF 路径。")
    elif role_label == "数据编排层":
        responsibilities.append("收敛竞拍配置、状态和商品模型，输出主链路所需数据结构。")
    elif role_label == "前端/BFF 装配层":
        responsibilities.append("把上游竞拍数据转换成前端或 BFF 可消费的展示结构。")
    elif role_label == "公共能力底座":
        responsibilities.append("提供 AB、schema、配置或共享工具能力，不直接承接主链路。")
    stable_fact_prefixes = ("symbol_hits", "route_hits", "recent_commit_hits", "anchor strongest_terms")
    stable_facts = [value for value in facts if value.startswith(stable_fact_prefixes)]
    for value in [*inferences[:2], *stable_facts[:2]]:
        current = str(value).strip()
        if current and current not in responsibilities:
            responsibilities.append(current)
    return responsibilities[:4]


def infer_repo_connections(item: dict[str, object], direction: str) -> list[str]:
    facts = " ".join(str(value) for value in item.get("facts", []))
    likely_modules = " ".join(str(value) for value in item.get("likely_modules", []))
    current: list[str] = []
    if direction == "upstream":
        if "handler" in likely_modules or "route" in facts:
            current.append("客户端或上游调用方")
    else:
        if "dal/rpc" in likely_modules or "rpc" in facts.lower():
            current.append("下游 RPC / 配置服务")
        if "service/im" in likely_modules:
            current.append("消息或刷新通道")
    return current[:3]


def build_storyline_steps_local(
    flow_slot_payload: dict[str, object],
    repo_hints: list[dict[str, object]],
) -> list[str]:
    steps: list[str] = []
    primary_slots = (
        "sync_entry_or_init",
        "async_preview_or_pre_enter",
        "data_orchestration",
        "frontend_bff_transform",
    )
    for slot in primary_slots:
        current = flow_slot_payload.get(slot)
        if isinstance(current, dict):
            summary = str(current.get("summary") or "").strip()
            if summary:
                steps.append(summary)
    runtime_slot = flow_slot_payload.get("runtime_update_or_notification")
    if steps and isinstance(runtime_slot, dict):
        runtime_summary = str(runtime_slot.get("summary") or "").strip()
        if runtime_summary:
            steps.append(runtime_summary)
        return steps[:5]
    if steps:
        return steps[:4]
    http_repos = [item for item in repo_hints if item["role_label"] == "HTTP/API 入口"]
    service_repos = [item for item in repo_hints if item["role_label"] == "服务聚合入口"]
    entry_repos = [*http_repos, *service_repos]
    orchestration_repos = [item for item in repo_hints if item["role_label"] == "数据编排层"]
    bff_repos = [item for item in repo_hints if item["role_label"] == "前端/BFF 装配层"]
    if entry_repos:
        sync_repos = [*service_repos[:1], *http_repos[:1]] or entry_repos[:2]
        async_repos = http_repos[:1] or entry_repos[:1]
        steps.append(f"同步进房初始化通常由 {', '.join(f'`{item.get('repo_display_name', item['repo_id'])}`' for item in sync_repos[:2])} 承接入口与基础信息聚合。")
        steps.append(f"异步预览或进房前链路通常由 {', '.join(f'`{item.get('repo_display_name', item['repo_id'])}`' for item in async_repos[:2])} 提供 preview/pop 等预览态数据。")
    if orchestration_repos:
        steps.append(f"主数据随后由 {', '.join(f'`{item.get('repo_display_name', item['repo_id'])}`' for item in orchestration_repos[:2])} 编排竞拍配置、状态和商品模型。")
    if bff_repos:
        steps.append(f"前端展示前，会由 {', '.join(f'`{item.get('repo_display_name', item['repo_id'])}`' for item in bff_repos[:2])} 转成前端/BFF 可消费结构。")
    runtime_repos = [item for item in repo_hints if item["role_label"] == "服务聚合入口" and any("notify" in note.lower() or "刷新" in note for note in item.get("notes", []))]
    if runtime_repos:
        steps.append(f"运行时状态变化后，会由 {', '.join(f'`{item.get('repo_display_name', item['repo_id'])}`' for item in runtime_repos[:1])} 负责刷新或通知分发。")
    return steps[:5]


def build_dependency_lines_local(
    repo_hints: list[dict[str, object]],
    repo_research_payloads: list[dict[str, object]],
) -> list[str]:
    research_map = {str(item.get("repo_id") or ""): item for item in repo_research_payloads}
    lines: list[str] = []
    for item in repo_hints:
        repo_name = str(item.get("repo_display_name") or item["repo_id"])
        role_label = str(item.get("role_label") or "")
        facts_blob = " ".join(str(value) for value in research_map.get(str(item.get("repo_id") or ""), {}).get("facts", []))
        modules_blob = " ".join(str(value) for value in research_map.get(str(item.get("repo_id") or ""), {}).get("likely_modules", []))
        if role_label == "数据编排层":
            lines.append(f"`{repo_name}` 消费配置、session 和商品 relation 等依赖，收敛成主链路所需数据结构。")
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
    return unique_strings(lines)[:8]


def merge_storyline_repo_hints(
    fallback_hints: list[dict[str, object]],
    parsed_hints: list[dict[str, object]],
) -> list[dict[str, object]]:
    parsed_map = {str(item.get("repo_id") or ""): item for item in parsed_hints}
    merged: list[dict[str, object]] = []
    for item in fallback_hints:
        repo_id = str(item.get("repo_id") or "")
        parsed = parsed_map.get(repo_id)
        if not parsed:
            merged.append(item)
            continue
        merged.append(
            {
                "repo_id": repo_id,
                "repo_display_name": str(parsed.get("repo_display_name") or item.get("repo_display_name") or repo_id),
                "role_label": str(parsed.get("role_label") or item.get("role_label") or ""),
                "key_modules": unique_strings(
                    [*[_ for _ in parsed.get("key_modules", [])], *[_ for _ in item.get("key_modules", [])]]
                )[:6],
                "responsibilities": unique_strings(
                    [*[_ for _ in parsed.get("responsibilities", [])], *[_ for _ in item.get("responsibilities", [])]]
                )[:6],
                "upstream": unique_strings([*[_ for _ in parsed.get("upstream", [])], *[_ for _ in item.get("upstream", [])]])[:6],
                "downstream": unique_strings(
                    [*[_ for _ in parsed.get("downstream", [])], *[_ for _ in item.get("downstream", [])]]
                )[:6],
                "notes": unique_strings([*[_ for _ in parsed.get("notes", [])], *[_ for _ in item.get("notes", [])]])[:6],
            }
        )
    for repo_id, item in parsed_map.items():
        if repo_id and not any(str(existing.get("repo_id") or "") == repo_id for existing in merged):
            merged.append(item)
    return merged


def build_documents(
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
    settings: Settings,
    requested_executor: str,
) -> list[KnowledgeDocument]:
    local_documents = build_documents_local(
        intent_payload=intent_payload,
        term_mapping_payload=term_mapping_payload,
        term_family_payload=term_family_payload,
        focus_boundary_payload=focus_boundary_payload,
        storyline_outline_payload=storyline_outline_payload,
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
            term_family_payload=term_family_payload,
            focus_boundary_payload=focus_boundary_payload,
            storyline_outline_payload=storyline_outline_payload,
            anchor_selection_payloads=anchor_selection_payloads,
            repo_research_payloads=repo_research_payloads,
            selected_paths=selected_paths,
            requested_kinds=requested_kinds,
            trace_id=trace_id,
            timestamp=timestamp,
            settings=settings,
            fallback_documents=local_documents,
        )
    except Exception as error:
        return annotate_documents(
            local_documents,
            requested_executor=requested_executor,
            term_mapping_payload=term_mapping_payload,
            anchor_selection_payloads=anchor_selection_payloads,
            synthesis_executor=EXECUTOR_LOCAL,
            repo_research_payloads=repo_research_payloads,
            synthesis_fallback_reason=str(error),
        )


def build_documents_native(
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
            term_family_payload,
            focus_boundary_payload,
            storyline_outline_payload,
            anchor_selection_payloads,
            repo_research_payloads,
            display_paths,
            requested_kinds,
        ),
        settings.native_query_timeout,
        cwd=cwd,
    )
    outputs = extract_knowledge_synthesis_output(raw, requested_kinds)
    if not outputs:
        raise ValueError("native knowledge synthesis returned empty outputs")
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
