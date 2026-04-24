from __future__ import annotations

from .models import DesignInputBundle
from .utils import as_str_list


def build_design_input_payload(prepared: DesignInputBundle) -> dict[str, object]:
    return {
        "task_id": prepared.task_id,
        "title": prepared.title,
        "repos": [{"repo_id": item.repo_id, "repo_path": item.repo_path} for item in prepared.repo_scopes],
        "selected_skill_ids": prepared.selected_skill_ids,
        "design_selected_skill_ids": prepared.design_selected_skill_ids,
        "design_skills_selection": prepared.design_skills_selection_payload,
        "refined_scope": prepared.sections.change_scope,
        "manual_change_points": _manual_change_points(prepared),
        "constraints": prepared.sections.key_constraints,
        "non_goals": prepared.sections.non_goals,
        "open_questions": prepared.sections.open_questions,
    }


def build_design_input_markdown(prepared: DesignInputBundle) -> str:
    parts = [
        f"# Design Input: {prepared.title}",
        "",
        "## Bound Repos",
        *[f"- {repo.repo_id}: {repo.repo_path}" for repo in prepared.repo_scopes],
        "",
        "## Refined PRD",
        prepared.refined_markdown.strip(),
    ]
    if prepared.refine_skills_read_markdown.strip():
        parts.extend(["", "## Refine Skills Brief", prepared.refine_skills_read_markdown.strip()])
    if prepared.design_skills_brief_markdown.strip():
        parts.extend(["", "## Design Skills Brief", prepared.design_skills_brief_markdown.strip()])
    return "\n".join(parts).rstrip() + "\n"


def _manual_change_points(prepared: DesignInputBundle) -> list[str]:
    raw = prepared.refine_brief_payload.get("change_points") or prepared.refine_intent_payload.get("change_points")
    return as_str_list(raw)
