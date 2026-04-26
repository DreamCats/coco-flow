"""Design 输入准备。

负责把任务目录中的 prd-refined.md、input/refine 兼容信息和 repos.json
归一成 DesignInputBundle，供后续 skills、research、writer 共用。
"""

from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.engines.shared.research import parse_refined_sections, parse_repo_scopes, read_text_if_exists
from coco_flow.services.queries.task_detail import read_json_file

from coco_flow.engines.design.types import DesignInputBundle


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    primary = settings.task_root / task_id
    if primary.is_dir():
        return primary
    return None


def prepare_design_input(task_dir: Path, task_meta: dict[str, object], settings: Settings) -> DesignInputBundle:
    del settings
    task_id = task_dir.name
    input_meta = read_json_file(task_dir / "input.json")
    refine_brief_payload = read_json_file(task_dir / "refine-brief.json")
    refine_intent_payload = read_json_file(task_dir / "refine-intent.json")
    refine_skills_selection_payload = read_json_file(task_dir / "refine-skills-selection.json")
    refine_skills_read_markdown = read_text_if_exists(task_dir / "refine-skills-read.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_scopes = parse_repo_scopes(repos_meta)
    title = str(task_meta.get("title") or input_meta.get("title") or task_id)
    selected_skill_ids = _selection_ids(refine_skills_selection_payload)
    return DesignInputBundle(
        task_dir=task_dir,
        task_id=task_id,
        title=title,
        refined_markdown=refined_markdown,
        input_meta=input_meta,
        refine_brief_payload=refine_brief_payload,
        refine_intent_payload=refine_intent_payload,
        refine_skills_selection_payload=refine_skills_selection_payload,
        refine_skills_read_markdown=refine_skills_read_markdown,
        repos_meta=repos_meta,
        repo_scopes=repo_scopes,
        sections=parse_refined_sections(refined_markdown),
        selected_skill_ids=selected_skill_ids,
    )


def _selection_ids(payload: dict[str, object]) -> list[str]:
    values = payload.get("selected_skill_ids")
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]
