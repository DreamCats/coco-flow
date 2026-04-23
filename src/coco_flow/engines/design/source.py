from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.engines.shared.research import (
    build_design_research_signals,
    build_repo_researches,
    parse_refined_sections,
    parse_repo_scopes,
    read_text_if_exists,
    score_complexity,
)
from coco_flow.services.queries.task_detail import read_json_file

from .models import DesignPreparedInput


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    primary = settings.task_root / task_id
    if primary.is_dir():
        return primary
    return None


def prepare_design_input(task_dir: Path, task_meta: dict[str, object], settings: Settings) -> DesignPreparedInput:
    """读取 Design 依赖的全部上游产物，并归一化成统一输入。"""
    task_id = task_dir.name
    input_meta = read_json_file(task_dir / "input.json")
    refine_intent_payload = read_json_file(task_dir / "refine-intent.json")
    refine_skills_selection_payload = read_json_file(task_dir / "refine-skills-selection.json")
    refine_skills_read_markdown = read_text_if_exists(task_dir / "refine-skills-read.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    repos_meta = read_json_file(task_dir / "repos.json")
    title = str(task_meta.get("title") or input_meta.get("title") or task_id)
    repo_scopes = parse_repo_scopes(repos_meta)
    repo_discovery_payload = {
        "mode": "bound" if repo_scopes else "none",
        "bound_repo_count": len(repo_scopes),
        "inferred_repo_count": 0,
        "selected_skill_ids": _selection_ids(refine_skills_selection_payload),
    }
    repo_lines = [f"- {scope.repo_id} ({scope.repo_path})" for scope in repo_scopes]
    sections = parse_refined_sections(refined_markdown)
    repo_researches = build_repo_researches(repo_scopes, title, sections)
    repo_root = repo_scopes[0].repo_path if repo_scopes else None
    research_signals = build_design_research_signals(repo_researches, sections)
    assessment = score_complexity(
        sections,
        type(
            "Finding",
            (),
            {
                "matched_terms": [item for repo in repo_researches for item in repo.finding.matched_terms],
                "unmatched_terms": [item for repo in repo_researches for item in repo.finding.unmatched_terms],
                "candidate_files": [item for repo in repo_researches for item in repo.finding.candidate_files],
                "candidate_dirs": [item for repo in repo_researches for item in repo.finding.candidate_dirs],
                "notes": [item for repo in repo_researches for item in repo.finding.notes],
            },
        )(),
    )
    return DesignPreparedInput(
        task_dir=task_dir,
        task_id=task_id,
        title=title,
        refined_markdown=refined_markdown,
        input_meta=input_meta,
        refine_intent_payload=refine_intent_payload,
        refine_skills_selection_payload=refine_skills_selection_payload,
        refine_skills_read_markdown=refine_skills_read_markdown,
        repo_lines=repo_lines,
        repo_scopes=repo_scopes,
        repo_researches=repo_researches,
        repo_ids={scope.repo_id for scope in repo_scopes},
        repo_root=repo_root,
        sections=sections,
        research_signals=research_signals,
        assessment=assessment,
        repo_discovery_payload=repo_discovery_payload,
        research_payload={},
    )


def _selection_ids(payload: dict[str, object]) -> list[str]:
    values = payload.get("selected_skill_ids")
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]
