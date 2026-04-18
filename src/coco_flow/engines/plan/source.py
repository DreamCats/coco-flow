from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.engines.plan_models import RefinedSections
from coco_flow.engines.plan_research import parse_refined_sections, parse_repo_scopes, read_text_if_exists
from coco_flow.services.queries.task_detail import read_json_file

from .models import PlanPreparedInput


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    candidate = settings.task_root / task_id
    if candidate.is_dir():
        return candidate
    return None


def prepare_plan_input(task_dir: Path, task_meta: dict[str, object]) -> PlanPreparedInput:
    task_id = task_dir.name
    input_meta = read_json_file(task_dir / "input.json")
    repos_meta = read_json_file(task_dir / "repos.json")
    design_repo_binding_payload = read_json_file(task_dir / "design-repo-binding.json")
    design_sections_payload = read_json_file(task_dir / "design-sections.json")
    design_result_payload = read_json_file(task_dir / "design-result.json")
    design_markdown = read_text_if_exists(task_dir / "design.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    title = str(task_meta.get("title") or input_meta.get("title") or task_id)
    repo_scopes = parse_repo_scopes(repos_meta)

    _require_non_empty(design_markdown, "design.md 为空，无法执行 plan")
    _require_payload(design_repo_binding_payload, "design-repo-binding.json 缺失，无法执行 plan")
    _require_payload(design_sections_payload, "design-sections.json 缺失，无法执行 plan")

    refined_sections = parse_refined_sections(refined_markdown)
    if not _has_meaningful_refined_sections(refined_sections):
        raise ValueError("prd-refined.md 缺失有效内容，无法执行 plan")

    return PlanPreparedInput(
        task_dir=task_dir,
        task_id=task_id,
        title=title,
        design_markdown=design_markdown,
        refined_markdown=refined_markdown,
        input_meta=input_meta,
        task_meta=task_meta,
        design_repo_binding_payload=design_repo_binding_payload,
        design_sections_payload=design_sections_payload,
        design_result_payload=design_result_payload,
        repos_meta=repos_meta,
        repo_scopes=repo_scopes,
        repo_ids={scope.repo_id for scope in repo_scopes},
        refined_sections=refined_sections,
    )


def _require_payload(payload: dict[str, object], message: str) -> None:
    if not payload:
        raise ValueError(message)


def _require_non_empty(content: str, message: str) -> None:
    if not content.strip():
        raise ValueError(message)


def _has_meaningful_refined_sections(sections: RefinedSections) -> bool:
    return bool(
        sections.raw.strip()
        or sections.change_scope
        or sections.non_goals
        or sections.key_constraints
        or sections.acceptance_criteria
        or sections.open_questions
    )
