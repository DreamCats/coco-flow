from __future__ import annotations

import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.design import (
    build_design_responsibility_matrix_agent_prompt,
    build_design_responsibility_matrix_template_json,
)

from .models import DesignPreparedInput, EXECUTOR_NATIVE

_LEVELS = ("none", "low", "medium", "high")


def build_design_responsibility_matrix_payload(
    prepared: DesignPreparedInput,
    settings: Settings,
    knowledge_brief_markdown: str,
    on_log,
) -> dict[str, object]:
    fallback = build_local_design_responsibility_matrix_payload(prepared)
    if settings.plan_executor.strip().lower() != EXECUTOR_NATIVE:
        return fallback

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_responsibility_matrix_template(prepared.task_dir)
    try:
        client.run_agent(
            build_design_responsibility_matrix_agent_prompt(
                title=prepared.title,
                refined_markdown=prepared.refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
                change_points_payload=prepared.change_points_payload,
                research_payload=prepared.research_payload,
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
        if "__FILL__" in raw:
            raise ValueError("design_responsibility_matrix_template_unfilled")
        payload = json.loads(raw)
        normalized = _normalize_matrix_payload(payload, prepared)
        if not normalized["repos"]:
            raise ValueError("design_responsibility_matrix_empty")
        return normalized
    except Exception as error:
        on_log(f"design_repo_matrix_fallback: {error}")
        return fallback
    finally:
        if template_path.exists():
            template_path.unlink()


def build_local_design_responsibility_matrix_payload(prepared: DesignPreparedInput) -> dict[str, object]:
    repos_payload = prepared.research_payload.get("repos") if isinstance(prepared.research_payload, dict) else []
    entries = repos_payload if isinstance(repos_payload, list) else []
    normalized_entries = [entry for entry in entries if isinstance(entry, dict)]
    recommended_by_repo: dict[str, str] = {}
    matrix_repos: list[dict[str, object]] = []
    total_repos = len(normalized_entries)
    for item in normalized_entries:
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        profile = _infer_repo_responsibility_profile(item, total_repos=total_repos)
        recommended_by_repo[repo_id] = str(profile["recommended_scope_tier"])
        matrix_repos.append(
            {
                "repo_id": repo_id,
                "state_definition": profile["state_definition"],
                "state_aggregation": profile["state_aggregation"],
                "adapter_or_transform": profile["adapter_or_transform"],
                "presentation_only": profile["presentation_only"],
                "config_or_ab": profile["config_or_ab"],
                "runtime_notification": profile["runtime_notification"],
                "must_change_if_goal_holds": profile["must_change_if_goal_holds"],
                "can_goal_ship_without_this_repo": profile["can_goal_ship_without_this_repo"],
                "more_likely_primary_repos": [],
                "recommended_scope_tier": profile["recommended_scope_tier"],
                "reasoning": profile["reasoning"],
                "evidence": [str(value) for value in item.get("evidence", []) if str(value).strip()][:6],
            }
        )

    must_change_repo_ids = [
        entry["repo_id"] for entry in matrix_repos if entry["recommended_scope_tier"] == "must_change"
    ]
    co_change_repo_ids = [
        entry["repo_id"] for entry in matrix_repos if entry["recommended_scope_tier"] == "co_change"
    ]
    for entry in matrix_repos:
        if entry["recommended_scope_tier"] in {"co_change", "validate_only", "reference_only"}:
            entry["more_likely_primary_repos"] = must_change_repo_ids[:2]
        elif entry["recommended_scope_tier"] == "must_change":
            entry["more_likely_primary_repos"] = []
    summary_parts: list[str] = []
    if must_change_repo_ids:
        summary_parts.append("must_change=" + "、".join(must_change_repo_ids))
    if co_change_repo_ids:
        summary_parts.append("co_change=" + "、".join(co_change_repo_ids))
    return {
        "mode": "local",
        "change_points": [
            {
                "id": int(item.get("id") or index + 1),
                "title": str(item.get("title") or "").strip(),
            }
            for index, item in enumerate(prepared.change_points_payload.get("change_points", []))
            if isinstance(item, dict)
        ],
        "repos": matrix_repos,
        "summary": "；".join(summary_parts) if summary_parts else "matrix 未识别到明确主改仓。",
    }


def _infer_repo_responsibility_profile(item: dict[str, object], *, total_repos: int) -> dict[str, object]:
    repo_id = str(item.get("repo_id") or "").lower()
    text = " ".join(
        str(value)
        for value in [
            repo_id,
            *(item.get("candidate_dirs") or []),
            *(item.get("candidate_files") or []),
            item.get("summary") or "",
            *(item.get("matched_terms") or []),
            *(item.get("notes") or []),
            *(item.get("evidence") or []),
        ]
    ).lower()

    state_definition = _level_from_keywords(text, ("status", "state", "enum", "判定", "定义", "success"))
    state_aggregation = _level_from_keywords(text, ("converter", "loader", "engine", "pack", "dto", "aggregation", "assembler"))
    adapter_or_transform = _level_from_keywords(text, ("bff", "api", "transform", "adapter", "lynx", "formatter", "schema", "pin_card"))
    presentation_only = _level_from_keywords(text, ("render", "view", "ui", "lynx", "presentation"))
    config_or_ab = _level_from_keywords(text, ("abtest", "config", "tcc", "switch", "experiment", "gray", "灰度"))
    runtime_notification = _level_from_keywords(text, ("notify", "event", "message", "refresh", "runtime"))

    if "live_pack" in repo_id:
        state_aggregation = _upgrade_level(state_aggregation, "high")
        state_definition = _upgrade_level(state_definition, "high")
    if "bff" in repo_id or "shopapi" in repo_id:
        adapter_or_transform = _upgrade_level(adapter_or_transform, "high")
    if "common" in repo_id:
        config_or_ab = _upgrade_level(config_or_ab, "high")

    if total_repos == 1 and any(level in {"medium", "high"} for level in (state_definition, state_aggregation, adapter_or_transform, presentation_only)):
        recommended_scope_tier = "must_change"
        must_change_if_goal_holds = True
        can_goal_ship_without = False
    elif config_or_ab == "high" and "common" in repo_id:
        recommended_scope_tier = "reference_only"
        must_change_if_goal_holds = False
        can_goal_ship_without = True
    elif state_definition == "high" or state_aggregation == "high":
        recommended_scope_tier = "must_change"
        must_change_if_goal_holds = True
        can_goal_ship_without = False
    elif adapter_or_transform == "high" and (state_definition in {"medium", "low"} or state_aggregation in {"medium", "low"}):
        recommended_scope_tier = "validate_only"
        must_change_if_goal_holds = False
        can_goal_ship_without = True
    elif config_or_ab == "high":
        recommended_scope_tier = "reference_only"
        must_change_if_goal_holds = False
        can_goal_ship_without = True
    elif runtime_notification in {"high", "medium"}:
        recommended_scope_tier = "validate_only"
        must_change_if_goal_holds = False
        can_goal_ship_without = True
    elif any(level in {"medium", "high"} for level in (state_definition, state_aggregation, adapter_or_transform, presentation_only)):
        recommended_scope_tier = "validate_only"
        must_change_if_goal_holds = False
        can_goal_ship_without = True
    else:
        recommended_scope_tier = "reference_only"
        must_change_if_goal_holds = False
        can_goal_ship_without = True

    reasoning = (
        f"{repo_id} 的职责画像：state_definition={state_definition}, "
        f"state_aggregation={state_aggregation}, adapter_or_transform={adapter_or_transform}, "
        f"config_or_ab={config_or_ab}."
    )
    return {
        "state_definition": state_definition,
        "state_aggregation": state_aggregation,
        "adapter_or_transform": adapter_or_transform,
        "presentation_only": presentation_only,
        "config_or_ab": config_or_ab,
        "runtime_notification": runtime_notification,
        "must_change_if_goal_holds": must_change_if_goal_holds,
        "can_goal_ship_without_this_repo": can_goal_ship_without,
        "recommended_scope_tier": recommended_scope_tier,
        "reasoning": reasoning,
    }


def _level_from_keywords(text: str, keywords: tuple[str, ...]) -> str:
    hits = sum(1 for keyword in keywords if keyword in text)
    if hits >= 2:
        return "high"
    if hits == 1:
        return "medium"
    return "low"


def _upgrade_level(current: str, target: str) -> str:
    if _LEVELS.index(target) > _LEVELS.index(current):
        return target
    return current


def _normalize_matrix_payload(payload: object, prepared: DesignPreparedInput) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("design_responsibility_matrix_output_not_object")
    raw_repos = payload.get("repos")
    if not isinstance(raw_repos, list):
        raise ValueError("design_responsibility_matrix_output_missing_repos")
    repos: list[dict[str, object]] = []
    for item in raw_repos:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("repo_id") or "").strip()
        if not repo_id:
            continue
        repos.append(
            {
                "repo_id": repo_id,
                "state_definition": _normalize_level(item.get("state_definition")),
                "state_aggregation": _normalize_level(item.get("state_aggregation")),
                "adapter_or_transform": _normalize_level(item.get("adapter_or_transform")),
                "presentation_only": _normalize_level(item.get("presentation_only")),
                "config_or_ab": _normalize_level(item.get("config_or_ab")),
                "runtime_notification": _normalize_level(item.get("runtime_notification")),
                "must_change_if_goal_holds": bool(item.get("must_change_if_goal_holds")),
                "can_goal_ship_without_this_repo": bool(item.get("can_goal_ship_without_this_repo")),
                "more_likely_primary_repos": [str(value) for value in item.get("more_likely_primary_repos", []) if str(value).strip()][:4],
                "recommended_scope_tier": _normalize_scope_tier(item.get("recommended_scope_tier")),
                "reasoning": str(item.get("reasoning") or "").strip(),
                "evidence": [str(value) for value in item.get("evidence", []) if str(value).strip()][:6],
            }
        )
    return {
        "mode": "llm",
        "change_points": [
            {
                "id": int(entry.get("id") or index + 1),
                "title": str(entry.get("title") or "").strip(),
            }
            for index, entry in enumerate(prepared.change_points_payload.get("change_points", []))
            if isinstance(entry, dict)
        ],
        "repos": repos,
        "summary": str(payload.get("summary") or "").strip(),
    }


def _normalize_level(value: object) -> str:
    current = str(value or "").strip().lower()
    if current in _LEVELS:
        return current
    return "low"


def _normalize_scope_tier(value: object) -> str:
    current = str(value or "").strip()
    if current in {"must_change", "co_change", "validate_only", "reference_only"}:
        return current
    return "reference_only"


def _write_responsibility_matrix_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".design-repo-matrix-",
        suffix=".json",
        delete=False,
    ) as handle:
        handle.write(build_design_responsibility_matrix_template_json())
        handle.flush()
        return Path(handle.name)
