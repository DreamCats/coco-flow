from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
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
    build_knowledge_synthesis_prompt,
    build_repo_research_prompt,
    build_term_family_prompt,
    build_term_mapping_prompt,
    extract_candidate_ranking_output,
    extract_anchor_selection_output,
    extract_knowledge_synthesis_output,
    extract_repo_research_output,
    extract_term_family_output,
    extract_term_mapping_output,
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
    _emit_progress(on_progress, "repo_researching", 78, "正在归纳各 repo 在链路中的角色")
    repo_research_payloads = [
        build_repo_research(
            intent_payload,
            discovery,
            candidate_ranking,
            anchor_selection,
            term_family_payload,
            settings,
            requested_executor,
        )
        for discovery, candidate_ranking, anchor_selection in zip(
            discovery_payload, candidate_ranking_payloads, anchor_selection_payloads, strict=False
        )
    ]
    _emit_progress(on_progress, "synthesizing", 88, "正在生成知识草稿")
    documents = build_documents(
        intent_payload=intent_payload,
        term_mapping_payload=term_mapping_payload,
        term_family_payload=term_family_payload,
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
            *[str(question) for question in term_family_payload["open_questions"]],
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


def build_candidate_ranking(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_candidate_ranking_native(intent_payload, discovery, settings)
        except ValueError as error:
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
        except ValueError as error:
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
        except ValueError as error:
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
    settings: Settings,
    requested_executor: str,
) -> dict[str, object]:
    if requested_executor == EXECUTOR_NATIVE:
        try:
            return build_repo_research_native(intent_payload, discovery, candidate_ranking, anchor_selection, term_family, settings)
        except ValueError as error:
            local = build_repo_research_local(intent_payload, discovery, candidate_ranking, anchor_selection, term_family)
            local["requested_executor"] = requested_executor
            local["fallback_reason"] = str(error)
            return local
    return build_repo_research_local(intent_payload, discovery, candidate_ranking, anchor_selection, term_family)


def build_repo_research_local(
    intent_payload: dict[str, object],
    discovery: dict[str, object],
    candidate_ranking: dict[str, object],
    anchor_selection: dict[str, object],
    term_family: dict[str, object],
) -> dict[str, object]:
    matched_keywords = [str(item) for item in discovery["matched_keywords"]]
    candidate_dirs = [str(item) for item in discovery["candidate_dirs"]]
    candidate_files = [str(item) for item in discovery["candidate_files"]]
    route_hits = select_core_route_signals([str(item) for item in discovery.get("route_hits", [])], intent_payload)
    symbol_hits = [str(item) for item in discovery.get("symbol_hits", [])]
    commit_hits = [str(item) for item in discovery.get("commit_hits", [])]
    context_hits = [str(item) for item in discovery["context_hits"]]
    ranked_primary_dirs = [str(item) for item in candidate_ranking.get("primary_dirs", [])]
    ranked_primary_files = [str(item) for item in candidate_ranking.get("primary_files", [])]
    ranked_secondary_files = [str(item) for item in candidate_ranking.get("secondary_files", [])]
    anchors = {
        "entry_files": [str(item) for item in anchor_selection.get("entry_files", [])],
        "business_symbols": [str(item) for item in anchor_selection.get("business_symbols", [])],
        "route_signals": [str(item) for item in anchor_selection.get("route_signals", [])],
        "keywords": [str(item) for item in anchor_selection.get("strongest_terms", [])],
    }
    ranked_candidate_files = unique_strings([*ranked_primary_files, *anchors["entry_files"], *ranked_secondary_files, *candidate_files])[:8]
    ranked_candidate_dirs = unique_strings([*ranked_primary_dirs, *candidate_dirs])
    primary = bool(ranked_candidate_files or matched_keywords or context_hits or symbol_hits or route_hits or commit_hits)
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
    strongest_terms = [str(item) for item in term_family.get("primary_family", [])] or [str(item) for item in anchor_selection.get("strongest_terms", [])]
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
    open_questions = [str(question) for question in term_family.get("open_questions", [])] + [str(question) for question in anchor_selection.get("open_questions", [])]
    if not discovery["is_git_repo"]:
        open_questions.append("该路径不是 git repo，是否应上卷到真实仓库根目录。")
    if not matched_keywords:
        open_questions.append("当前关键词未命中明显模块名，是否需要补充别名或业务术语。")
    if entry_files:
        open_questions.append(f"是否以 `{entry_files[0]}` 为第一跳入口文件。")
    elif candidate_dirs:
        open_questions.append(f"是否以 `{candidate_dirs[0]}` 为第一跳入口目录。")
    if strongest_terms and not route_hits:
        open_questions.append(f"缺少明确路由信息，`{strongest_terms[0]}` 对应的 API 路径是什么？")
    return {
        "repo_id": discovery["repo_id"],
        "repo_path": discovery["repo_path"],
        "requested_path": discovery["requested_path"],
        "executor": EXECUTOR_LOCAL,
        "requested_executor": EXECUTOR_LOCAL,
        "role": role,
        "likely_modules": rank_likely_modules(ranked_candidate_dirs, anchors, discovery)[:6],
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
    settings: Settings,
) -> dict[str, object]:
    fallback = build_repo_research_local(intent_payload, discovery, candidate_ranking, anchor_selection, term_family)
    repo_path = str(discovery["repo_path"]).strip()
    if not repo_path:
        raise ValueError("native repo research missing repo_path")
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    raw = client.run_readonly_agent(
        build_repo_research_prompt(intent_payload, discovery, candidate_ranking, anchor_selection, term_family),
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


def build_documents(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
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


def build_documents_native(
    intent_payload: dict[str, object],
    term_mapping_payload: dict[str, object],
    term_family_payload: dict[str, object],
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
