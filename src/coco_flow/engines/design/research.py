from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import re
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.design import (
    build_design_repo_research_agent_prompt,
    build_design_repo_research_template_json,
)

from .models import DesignPreparedInput, EXECUTOR_NATIVE


def build_design_research_payload(
    prepared: DesignPreparedInput,
    settings: Settings,
    knowledge_brief_markdown: str,
    on_log,
) -> dict[str, object]:
    """在最终 binding 前补深对 repo 的理解。

    这一步会先在本地做 candidate repo 的预筛，再按需并行调用 agent，把
    候选 repo 补成更完整的 repo brief。
    """
    local_payload = build_local_design_research_payload(prepared)
    if settings.plan_executor.strip().lower() != EXECUTOR_NATIVE:
        return local_payload

    candidate_repo_ids = [
        str(repo_id)
        for repo_id in ((local_payload.get("prefilter") or {}).get("candidate_repo_ids") or [])
        if str(repo_id).strip()
    ]
    if not candidate_repo_ids:
        return local_payload

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    local_entries = {
        str(item.get("repo_id") or ""): item
        for item in (local_payload.get("repos") or [])
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip()
    }

    on_log(f"repo_research_prefilter_candidates: {', '.join(candidate_repo_ids)}")
    on_log(f"repo_research_parallel: {'true' if len(candidate_repo_ids) > 1 else 'false'}")

    explored_entries: dict[str, dict[str, object]] = {}
    if len(candidate_repo_ids) > 1:
        max_workers = min(len(candidate_repo_ids), 4)
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="design-research") as executor:
            futures = {}
            for repo_id in candidate_repo_ids:
                on_log(f"repo_research_guided_paths: {_format_guided_paths(repo_id, local_entries.get(repo_id, {}))}")
                futures[
                    executor.submit(
                        _explore_repo_with_agent,
                        prepared,
                        settings,
                        knowledge_brief_markdown,
                        client,
                        repo_id,
                        local_entries.get(repo_id, {}),
                    )
                ] = repo_id
            for future in as_completed(futures):
                repo_id = futures[future]
                try:
                    explored_entries[repo_id] = future.result()
                    on_log(f"repo_research_agent_ok: {repo_id}")
                except Exception as error:
                    on_log(f"repo_research_agent_fallback: {repo_id}: {error}")
                    explored_entries[repo_id] = _mark_entry_fallback(
                        prepared,
                        repo_id,
                        local_entries.get(repo_id, {}),
                        str(error),
                    )
    else:
        repo_id = candidate_repo_ids[0]
        try:
            on_log(f"repo_research_guided_paths: {_format_guided_paths(repo_id, local_entries.get(repo_id, {}))}")
            explored_entries[repo_id] = _explore_repo_with_agent(
                prepared,
                settings,
                knowledge_brief_markdown,
                client,
                repo_id,
                local_entries.get(repo_id, {}),
            )
            on_log(f"repo_research_agent_ok: {repo_id}")
        except Exception as error:
            on_log(f"repo_research_agent_fallback: {repo_id}: {error}")
            explored_entries[repo_id] = _mark_entry_fallback(
                prepared,
                repo_id,
                local_entries.get(repo_id, {}),
                str(error),
            )

    merged_entries: list[dict[str, object]] = []
    for item in (local_payload.get("repos") or []):
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "")
        merged_entries.append(explored_entries.get(repo_id, item))

    merged_modes = {
        str(item.get("exploration_mode") or "").strip()
        for item in merged_entries
        if isinstance(item, dict) and str(item.get("exploration_mode") or "").strip()
    }
    if any(mode.endswith("fallback_scan") or mode.endswith("fallback") for mode in merged_modes):
        mode = "fallback_parallel" if len(candidate_repo_ids) > 1 else "fallback_single"
    else:
        mode = "llm_parallel" if len(candidate_repo_ids) > 1 else "llm_single"
    return {
        "mode": mode,
        "prefilter": local_payload.get("prefilter") or {},
        "repos": merged_entries,
    }


def build_local_design_research_payload(prepared: DesignPreparedInput) -> dict[str, object]:
    """基于术语命中和候选文件，生成确定性的本地 repo briefs。

    它既是 local fallback，也是 native repo exploration 的预筛输入。
    """
    scores = _compute_prefilter_scores(prepared)
    candidate_repo_ids = _select_candidate_repo_ids(scores)
    skipped_repo_ids = [item["repo_id"] for item in scores if item["repo_id"] not in candidate_repo_ids]
    assignment_by_repo = _repo_assignment_map(prepared.repo_assignment_payload)

    repos: list[dict[str, object]] = []
    for item in scores:
        repo = item["repo"]
        repo_id = item["repo_id"]
        selected = repo_id in candidate_repo_ids
        assignment = assignment_by_repo.get(repo_id, {})
        primary_change_points = [int(value) for value in assignment.get("primary_change_points", []) if str(value).isdigit()]
        secondary_change_points = [int(value) for value in assignment.get("secondary_change_points", []) if str(value).isdigit()]
        serves_change_points = primary_change_points or secondary_change_points or [1]

        notes = [str(value) for value in repo.finding.notes[:4] if str(value).strip()]
        evidence = _build_local_evidence(repo)
        repos.append(
            {
                "repo_id": repo_id,
                "repo_path": repo.repo_path,
                "prefilter_score": item["score"],
                "prefilter_reasons": item["reasons"],
                "selected_for_exploration": selected,
                "explored": selected,
                "exploration_mode": "heuristic",
                "decision": "in_scope_candidate" if selected else "out_of_scope",
                "serves_change_points": serves_change_points,
                "primary_change_points": primary_change_points,
                "secondary_change_points": secondary_change_points,
                "summary": _build_local_summary(prepared, repo.repo_id, selected, primary_change_points, secondary_change_points),
                "matched_terms": [entry.business for entry in repo.finding.matched_terms[:6]],
                "candidate_dirs": [str(value) for value in repo.finding.candidate_dirs[:6] if str(value).strip()],
                "candidate_files": [str(value) for value in repo.finding.candidate_files[:8] if str(value).strip()],
                "dependencies": [],
                "parallelizable_with": [value for value in candidate_repo_ids if value != repo_id] if selected else [],
                "evidence": evidence,
                "notes": notes,
                "confidence": _confidence_from_score(item["score"]),
            }
        )

    return {
        "mode": "local",
        "prefilter": {
            "parallel": len(candidate_repo_ids) > 1,
            "candidate_repo_ids": candidate_repo_ids,
            "skipped_repo_ids": skipped_repo_ids,
            "scores": [
                {
                    "repo_id": item["repo_id"],
                    "score": item["score"],
                    "reasons": item["reasons"],
                }
                for item in scores
            ],
        },
        "repos": repos,
    }


def _compute_prefilter_scores(prepared: DesignPreparedInput) -> list[dict[str, object]]:
    scored: list[dict[str, object]] = []
    for repo in prepared.repo_researches:
        matched_term_count = len(repo.finding.matched_terms)
        candidate_file_count = len(repo.finding.candidate_files)
        candidate_dir_count = len(repo.finding.candidate_dirs)
        note_count = len(repo.finding.notes)
        score = matched_term_count * 4 + candidate_file_count * 2 + candidate_dir_count + min(note_count, 2)
        reasons: list[str] = []
        if matched_term_count:
            reasons.append(f"命中术语 {matched_term_count} 个")
        if candidate_file_count:
            reasons.append(f"发现候选文件 {candidate_file_count} 个")
        if candidate_dir_count:
            reasons.append(f"发现候选目录 {candidate_dir_count} 个")
        if note_count:
            reasons.append(f"发现额外线索 {note_count} 条")
        if not reasons:
            reasons.append("未命中明显信号，先降为低优先级仓库")
        scored.append(
            {
                "repo_id": repo.repo_id,
                "score": score,
                "reasons": reasons,
                "repo": repo,
            }
        )
    scored.sort(key=lambda item: (-int(item["score"]), str(item["repo_id"])))
    return scored


def _select_candidate_repo_ids(scores: list[dict[str, object]]) -> list[str]:
    if not scores:
        return []
    candidates = [str(item["repo_id"]) for item in scores if int(item["score"]) > 0]
    if candidates:
        return candidates
    return [str(scores[0]["repo_id"])]


def _confidence_from_score(score: int) -> str:
    if score >= 10:
        return "high"
    if score > 0:
        return "medium"
    return "low"


def _build_local_summary(
    prepared: DesignPreparedInput,
    repo_id: str,
    selected: bool,
    primary_change_points: list[int],
    secondary_change_points: list[int],
) -> str:
    if selected and primary_change_points:
        return f"{repo_id} 直接承接 change points {', '.join(str(item) for item in primary_change_points)}，建议进入 Design 深挖。"
    if selected and secondary_change_points:
        return f"{repo_id} 与 change points {', '.join(str(item) for item in secondary_change_points)} 相关，适合作为辅助探索仓库。"
    if selected:
        return f"{repo_id} 在当前 refined 范围内存在明确改动信号，建议进入 Design 深挖。"
    return f"{repo_id} 当前命中信号较弱，暂不作为本轮 Design 的优先探索仓库。"


def _build_local_evidence(repo) -> list[str]:
    evidence: list[str] = []
    if repo.finding.matched_terms:
        evidence.append("术语命中：" + "、".join(entry.business for entry in repo.finding.matched_terms[:3]))
    if repo.finding.candidate_dirs:
        evidence.append("候选目录：" + "、".join(str(value) for value in repo.finding.candidate_dirs[:3]))
    if repo.finding.candidate_files:
        evidence.append("候选文件：" + "、".join(str(value) for value in repo.finding.candidate_files[:3]))
    evidence.extend(str(value) for value in repo.finding.notes[:2] if str(value).strip())
    return evidence[:6]


def _explore_repo_with_agent(
    prepared: DesignPreparedInput,
    settings: Settings,
    knowledge_brief_markdown: str,
    client: CocoACPClient,
    repo_id: str,
    local_entry: dict[str, object],
) -> dict[str, object]:
    repo_scope = next((scope for scope in prepared.repo_scopes if scope.repo_id == repo_id), None)
    if repo_scope is None:
        raise ValueError(f"repo_scope_not_found:{repo_id}")
    repo_root = Path(repo_scope.repo_path)
    if not repo_root.is_dir():
        raise ValueError(f"repo_path_missing:{repo_scope.repo_path}")

    template_path = _write_repo_research_template(prepared.task_dir)
    assignment = _repo_assignment_map(prepared.repo_assignment_payload).get(repo_id, {})
    try:
        client.run_agent(
            build_design_repo_research_agent_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
                repo_id=repo_id,
                repo_path=repo_scope.repo_path,
                prefilter_score=int(local_entry.get("prefilter_score") or 0),
                prefilter_reasons=[str(value) for value in local_entry.get("prefilter_reasons", []) if str(value).strip()],
                change_points=[item for item in prepared.change_points_payload.get("change_points", []) if isinstance(item, dict)],
                primary_change_points=[int(value) for value in assignment.get("primary_change_points", []) if str(value).isdigit()],
                secondary_change_points=[int(value) for value in assignment.get("secondary_change_points", []) if str(value).isdigit()],
                candidate_dirs=[str(value) for value in local_entry.get("candidate_dirs", []) if str(value).strip()],
                candidate_files=[str(value) for value in local_entry.get("candidate_files", []) if str(value).strip()],
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(repo_root),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()

    if "__FILL__" in raw:
        raise ValueError("design_repo_research_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("design_repo_research_output_not_object")
    parsed = _normalize_agent_entry(
        payload,
        local_entry,
        repo_scope.repo_path,
        expected_repo_id=repo_id,
    )
    parsed = _augment_entry_with_local_scan(prepared, repo_id, parsed)
    if not parsed["candidate_dirs"] and not parsed["candidate_files"] and not parsed["matched_terms"]:
        raise ValueError("design_repo_research_output_missing_signals")
    parsed["selected_for_exploration"] = True
    parsed["explored"] = True
    parsed["exploration_mode"] = "llm"
    return parsed


def _normalize_agent_entry(
    payload: dict[str, object],
    local_entry: dict[str, object],
    repo_path: str,
    *,
    expected_repo_id: str = "",
) -> dict[str, object]:
    def _string_list(key: str, fallback_key: str | None = None, limit: int = 8) -> list[str]:
        values = payload.get(key)
        if not isinstance(values, list):
            values = local_entry.get(fallback_key or key, [])
        if not isinstance(values, list):
            return []
        result = [str(value).strip() for value in values if str(value).strip()]
        return result[:limit]

    payload_repo_id = str(payload.get("repo_id") or "").strip()
    repo_id = expected_repo_id.strip() or str(local_entry.get("repo_id") or "").strip() or payload_repo_id
    if not repo_id:
        raise ValueError("design_repo_research_repo_id_missing")
    notes = _string_list("notes", limit=6)
    if payload_repo_id and payload_repo_id != repo_id:
        notes.append(f"normalized repo_id from {payload_repo_id} to {repo_id}")
    return {
        "repo_id": repo_id,
        "repo_path": str(repo_path or local_entry.get("repo_path") or payload.get("repo_path") or "").strip(),
        "prefilter_score": int(local_entry.get("prefilter_score") or 0),
        "prefilter_reasons": [str(value) for value in local_entry.get("prefilter_reasons", []) if str(value).strip()],
        "selected_for_exploration": True,
        "explored": True,
        "exploration_mode": "llm",
        "decision": str(payload.get("decision") or "uncertain").strip() or "uncertain",
        "serves_change_points": [
            int(value)
            for value in payload.get("serves_change_points", [])
            if str(value).strip().isdigit()
        ] or [
            int(value)
            for value in local_entry.get("serves_change_points", [])
            if str(value).strip().isdigit()
        ],
        "primary_change_points": [
            int(value)
            for value in payload.get("primary_change_points", [])
            if str(value).strip().isdigit()
        ] or [
            int(value)
            for value in local_entry.get("primary_change_points", [])
            if str(value).strip().isdigit()
        ],
        "secondary_change_points": [
            int(value)
            for value in payload.get("secondary_change_points", [])
            if str(value).strip().isdigit()
        ] or [
            int(value)
            for value in local_entry.get("secondary_change_points", [])
            if str(value).strip().isdigit()
        ],
        "summary": str(payload.get("summary") or local_entry.get("summary") or "").strip(),
        "matched_terms": _string_list("matched_terms", limit=6),
        "candidate_dirs": _string_list("candidate_dirs", limit=6),
        "candidate_files": _string_list("candidate_files", limit=8),
        "dependencies": _string_list("dependencies", limit=6),
        "parallelizable_with": _string_list("parallelizable_with", limit=6),
        "evidence": _string_list("evidence", limit=6),
        "notes": notes[:6],
        "confidence": str(payload.get("confidence") or local_entry.get("confidence") or "medium").strip() or "medium",
    }


def _mark_entry_fallback(
    prepared: DesignPreparedInput,
    repo_id: str,
    local_entry: dict[str, object],
    error: str,
) -> dict[str, object]:
    merged = dict(local_entry)
    fallback_scan = _discover_fallback_paths(prepared, repo_id, merged)
    if fallback_scan["candidate_files"]:
        merged["candidate_files"] = fallback_scan["candidate_files"]
    if fallback_scan["candidate_dirs"]:
        merged["candidate_dirs"] = fallback_scan["candidate_dirs"]
    if fallback_scan["evidence"]:
        merged["evidence"] = fallback_scan["evidence"]
    if fallback_scan["summary"]:
        merged["summary"] = fallback_scan["summary"]
    notes = [str(value) for value in merged.get("notes", []) if str(value).strip()]
    notes.append(f"agent fallback: {error}")
    if fallback_scan["candidate_files"]:
        notes.append("applied deterministic fallback scan to recover likely implementation paths")
    merged["notes"] = notes[:6]
    merged["confidence"] = "low"
    merged["exploration_mode"] = "heuristic_fallback_scan" if fallback_scan["candidate_files"] else "heuristic_fallback"
    merged["explored"] = True
    merged["selected_for_exploration"] = True
    return merged


def _augment_entry_with_local_scan(
    prepared: DesignPreparedInput,
    repo_id: str,
    entry: dict[str, object],
) -> dict[str, object]:
    merged = dict(entry)
    merged["candidate_files"] = _filter_non_goal_paths(
        prepared,
        [str(value) for value in merged.get("candidate_files", []) if str(value).strip()],
    )
    merged["candidate_dirs"] = _filter_non_goal_paths(
        prepared,
        [str(value) for value in merged.get("candidate_dirs", []) if str(value).strip()],
    )
    supplement = _discover_fallback_paths(prepared, repo_id, merged)
    if supplement["candidate_files"]:
        merged["candidate_files"] = _dedupe_strings(
            [*merged["candidate_files"], *supplement["candidate_files"]]
        )
    if supplement["candidate_dirs"]:
        merged["candidate_dirs"] = _dedupe_strings(
            [*merged["candidate_dirs"], *supplement["candidate_dirs"]]
        )
    if supplement["evidence"]:
        merged["evidence"] = _dedupe_strings(
            [*(str(value) for value in merged.get("evidence", []) if str(value).strip()), *supplement["evidence"]]
        )[:6]
    merged["candidate_files"] = sorted(
        [str(value) for value in merged.get("candidate_files", []) if str(value).strip()],
        key=lambda value: (-_rank_candidate_file(value), value),
    )[:8]
    merged["candidate_dirs"] = sorted(
        [str(value) for value in merged.get("candidate_dirs", []) if str(value).strip()],
        key=lambda value: (-_rank_candidate_dir(value), value),
    )[:6]
    return merged


def _discover_fallback_paths(
    prepared: DesignPreparedInput,
    repo_id: str,
    local_entry: dict[str, object],
) -> dict[str, object]:
    repo_scope = next((scope for scope in prepared.repo_scopes if scope.repo_id == repo_id), None)
    if repo_scope is None:
        return {"candidate_files": [], "candidate_dirs": [], "evidence": [], "summary": ""}
    repo_root = Path(repo_scope.repo_path)
    if not repo_root.is_dir():
        return {"candidate_files": [], "candidate_dirs": [], "evidence": [], "summary": ""}

    search_terms = _collect_fallback_search_terms(prepared, local_entry)
    scored_paths: list[tuple[int, str, Path]] = []
    for path in repo_root.rglob("*.go"):
        relative = path.relative_to(repo_root).as_posix()
        if _should_skip_fallback_path(relative):
            continue
        score = _score_fallback_path(relative, path, search_terms)
        if score <= 0:
            continue
        scored_paths.append((score, relative, path))
    if not scored_paths:
        return {"candidate_files": [], "candidate_dirs": [], "evidence": [], "summary": ""}
    scored_paths.sort(key=lambda item: (-item[0], item[1]))
    candidate_files = _filter_non_goal_paths(prepared, [relative for _, relative, _ in scored_paths[:12]])[:8]
    candidate_dirs = _filter_non_goal_paths(
        prepared,
        _dedupe_strings(str(Path(relative).parent).strip() for relative in candidate_files if str(Path(relative).parent) != "."),
    )[:6]
    evidence = _dedupe_strings(
        [
            "fallback scan 命中实现路径：" + "、".join(candidate_files[:3]),
            "fallback scan 优先检查状态判定、loader、converter、engine 等实现路径。",
        ]
    )[:6]
    summary = (
        f"{repo_id} 的 agent research 失败，已回退为本地确定性扫描；"
        f"当前优先关注 {'、'.join(candidate_files[:3])}。"
    )
    return {
        "candidate_files": candidate_files,
        "candidate_dirs": candidate_dirs,
        "evidence": evidence,
        "summary": summary,
    }


def _collect_fallback_search_terms(prepared: DesignPreparedInput, local_entry: dict[str, object]) -> set[str]:
    tokens = {
        "auction",
        "status",
        "success",
        "loader",
        "converter",
        "engine",
        "product",
        "card",
        "state",
    }
    source_texts = [
        prepared.title,
        prepared.refined_markdown,
        *(str(value) for value in local_entry.get("candidate_dirs", []) if str(value).strip()),
        *(str(value) for value in local_entry.get("candidate_files", []) if str(value).strip()),
        *(str(value) for value in local_entry.get("notes", []) if str(value).strip()),
    ]
    for text in source_texts:
        tokens.update(
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9_]{2,}", str(text))
            if len(token) >= 3
        )
    return {token for token in tokens if token and token not in {"the", "and", "with", "for"}}


def _should_skip_fallback_path(relative: str) -> bool:
    lowered = relative.lower()
    return any(part in lowered for part in ("/vendor/", "/mock/", "/mocks/", "/testdata/", "/.git/"))


def _score_fallback_path(relative: str, path: Path, search_terms: set[str]) -> int:
    lowered = relative.lower()
    score = 0
    for token in search_terms:
        if token in lowered:
            score += 3
    for token in ("status", "success", "loader", "converter", "engine"):
        if token in lowered:
            score += 4
    if all(token in lowered for token in ("product", "auction", "loader")):
        score += 10
    if all(token in lowered for token in ("regular", "auction", "converter")):
        score += 10
    for token in ("meta", "model", "helper", "helpers", "list", "refresh", "config", "constdef"):
        if token in lowered:
            score -= 5
    try:
        sample = path.read_text(encoding="utf-8", errors="ignore")[:8000].lower()
    except OSError:
        sample = ""
    for token in search_terms:
        if token in sample:
            score += 1
    for token in ("auctionstatus_success", "getauctionstatussuccess", "auctiontexttype", "auctionstatus"):
        if token in sample:
            score += 5
    return score


def _dedupe_strings(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _filter_non_goal_paths(prepared: DesignPreparedInput, paths: list[str]) -> list[str]:
    non_goal_text = " ".join(str(value) for value in prepared.sections.non_goals[:6]).lower()
    filtered: list[str] = []
    for raw in paths:
        path = str(raw).strip()
        if not path:
            continue
        lowered = path.lower()
        if ("购物袋" in non_goal_text or "bag" in non_goal_text) and ("bag_" in lowered or "/bag" in lowered):
            continue
        if any(keyword in non_goal_text for keyword in ("惊喜盲盒", "盲盒", "surprise")) and "surprise" in lowered:
            continue
        filtered.append(path)
    return _dedupe_strings(filtered)


def _rank_candidate_file(path: str) -> int:
    lowered = path.lower()
    score = 0
    for token in ("status", "success", "state", "loader", "converter", "engine", "handler"):
        if token in lowered:
            score += 6
    for token in ("product", "auction", "card", "data_loader"):
        if token in lowered:
            score += 3
    if all(token in lowered for token in ("product", "auction", "loader")):
        score += 10
    if all(token in lowered for token in ("regular", "auction", "converter")):
        score += 10
    for token in ("constdef", "config", "tcc", "schema", "dto_builder", "builder"):
        if token in lowered:
            score -= 4
    for token in ("meta", "model", "helper", "helpers", "list", "refresh"):
        if token in lowered:
            score -= 6
    if lowered.endswith("_test.go"):
        score -= 10
    return score


def _rank_candidate_dir(path: str) -> int:
    lowered = path.lower()
    score = 0
    for token in ("loader", "converter", "engine", "handler"):
        if token in lowered:
            score += 4
    for token in ("auction", "product", "card", "status"):
        if token in lowered:
            score += 2
    for token in ("constdef", "config", "tcc", "schema"):
        if token in lowered:
            score -= 3
    return score


def _format_guided_paths(repo_id: str, local_entry: dict[str, object]) -> str:
    candidate_dirs = [str(value) for value in local_entry.get("candidate_dirs", []) if str(value).strip()]
    candidate_files = [str(value) for value in local_entry.get("candidate_files", []) if str(value).strip()]
    if not candidate_dirs and not candidate_files:
        return f"{repo_id}: none"
    parts: list[str] = [repo_id]
    if candidate_dirs:
        parts.append("dirs=" + ", ".join(candidate_dirs[:4]))
    if candidate_files:
        parts.append("files=" + ", ".join(candidate_files[:6]))
    return "; ".join(parts)


def _write_repo_research_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".design-research-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_design_repo_research_template_json())
        handle.flush()
        return Path(handle.name)


def _repo_assignment_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    repo_briefs = payload.get("repo_briefs")
    if not isinstance(repo_briefs, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for item in repo_briefs:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        result[repo_id] = item
    return result
