from __future__ import annotations

from coco_flow.config import Settings

from .generate import generate_doc_only_plan_markdown
from .models import STATUS_PLANNED, PlanEngineResult, PlanExecutionGraph, PlanWorkItem
from .skills import build_plan_skills_bundle
from .source import prepare_plan_input


def run_plan_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> PlanEngineResult:
    on_log("plan_prepare_start: true")
    prepared = prepare_plan_input(task_dir, task_meta)
    on_log(f"plan_prepare_ok: repos={len(prepared.repo_scopes)}, title={prepared.title}")

    on_log("plan_skills_start: true")
    skills_brief_markdown, skills_selection_payload, selected_skill_ids = build_plan_skills_bundle(prepared, settings)
    prepared.skills_brief_markdown = skills_brief_markdown
    prepared.skills_selection_payload = skills_selection_payload
    prepared.selected_skill_ids = selected_skill_ids
    on_log(f"plan_skills_ok: selected={len(selected_skill_ids)}")

    on_log("plan_writer_start: true")
    plan_markdown, mode = generate_doc_only_plan_markdown(prepared, settings, on_log)
    on_log(f"plan_writer_ok: mode={mode}")
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        plan_markdown=plan_markdown,
        intermediate_artifacts={},
    )


def _sync_work_item_dependencies_from_graph(work_items: list[PlanWorkItem], graph: PlanExecutionGraph) -> None:
    item_by_id = {item.id: item for item in work_items}
    for edge in graph.edges:
        if edge.type != "hard_dependency":
            continue
        if edge.from_task_id not in item_by_id or edge.to_task_id not in item_by_id:
            continue
        target = item_by_id[edge.to_task_id]
        if edge.from_task_id not in target.depends_on:
            target.depends_on.append(edge.from_task_id)
