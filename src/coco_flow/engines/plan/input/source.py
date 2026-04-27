"""Plan 输入准备。

把任务目录中的 prd-refined.md、design.md、input.json 和 repos.json
归一成 PlanPreparedInput，并在进入 writer 前做最小完整性校验。
"""

from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.engines.shared.models import RefinedSections
from coco_flow.engines.shared.research import parse_refined_sections, parse_repo_scopes, read_text_if_exists
from coco_flow.services.queries.task_detail import read_json_file

from coco_flow.engines.plan.types import PlanPreparedInput


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    candidate = settings.task_root / task_id
    if candidate.is_dir():
        return candidate
    return None


def prepare_plan_input(task_dir: Path, task_meta: dict[str, object]) -> PlanPreparedInput:
    task_id = task_dir.name
    input_meta = read_json_file(task_dir / "input.json")
    repos_meta = read_json_file(task_dir / "repos.json")
    inherited_design_skills_payload = read_json_file(task_dir / "design-skills.json")
    design_contracts_payload = read_json_file(task_dir / "design-contracts.json")
    design_markdown = read_text_if_exists(task_dir / "design.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    title = str(task_meta.get("title") or input_meta.get("title") or task_id)
    repo_scopes = parse_repo_scopes(repos_meta)

    _require_non_empty(design_markdown, "design.md 为空，无法执行 plan")
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
        repos_meta=repos_meta,
        repo_scopes=repo_scopes,
        repo_ids={scope.repo_id for scope in repo_scopes},
        refined_sections=refined_sections,
        inherited_design_skills_payload=inherited_design_skills_payload,
        design_contracts_payload=design_contracts_payload,
    )


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
