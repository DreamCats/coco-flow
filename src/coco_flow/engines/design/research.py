from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
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
            futures = {
                executor.submit(
                    _explore_repo_with_agent,
                    prepared,
                    settings,
                    knowledge_brief_markdown,
                    client,
                    repo_id,
                    local_entries.get(repo_id, {}),
                ): repo_id
                for repo_id in candidate_repo_ids
            }
            for future in as_completed(futures):
                repo_id = futures[future]
                try:
                    explored_entries[repo_id] = future.result()
                    on_log(f"repo_research_agent_ok: {repo_id}")
                except Exception as error:
                    on_log(f"repo_research_agent_fallback: {repo_id}: {error}")
                    explored_entries[repo_id] = _mark_entry_fallback(local_entries.get(repo_id, {}), str(error))
    else:
        repo_id = candidate_repo_ids[0]
        try:
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
            explored_entries[repo_id] = _mark_entry_fallback(local_entries.get(repo_id, {}), str(error))

    merged_entries: list[dict[str, object]] = []
    for item in (local_payload.get("repos") or []):
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "")
        merged_entries.append(explored_entries.get(repo_id, item))

    return {
        "mode": "llm_parallel" if len(candidate_repo_ids) > 1 else "llm_single",
        "prefilter": local_payload.get("prefilter") or {},
        "repos": merged_entries,
    }


def build_local_design_research_payload(prepared: DesignPreparedInput) -> dict[str, object]:
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


def _mark_entry_fallback(local_entry: dict[str, object], error: str) -> dict[str, object]:
    merged = dict(local_entry)
    notes = [str(value) for value in merged.get("notes", []) if str(value).strip()]
    notes.append(f"agent fallback: {error}")
    merged["notes"] = notes[:6]
    merged["exploration_mode"] = "heuristic_fallback"
    merged["explored"] = True
    merged["selected_for_exploration"] = True
    return merged


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
