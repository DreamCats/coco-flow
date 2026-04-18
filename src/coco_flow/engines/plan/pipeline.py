from __future__ import annotations

from coco_flow.config import Settings

from .generate import generate_plan_markdown
from .graph import build_plan_execution_graph
from .knowledge import build_plan_knowledge_bundle
from .models import PlanEngineResult, STATUS_PLANNED
from .source import prepare_plan_input
from .task_outline import build_plan_work_items
from .validation import build_plan_validation
from .verify import build_plan_verify_payload


def run_plan_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> PlanEngineResult:
    artifacts: dict[str, str | dict[str, object]] = {}

    on_log("plan_prepare_start: true")
    prepared = prepare_plan_input(task_dir, task_meta)
    on_log(f"plan_prepare_ok: repos={len(prepared.repo_scopes)}, title={prepared.title}")

    on_log("plan_knowledge_start: true")
    knowledge_brief_markdown, selection_payload, selected_ids = build_plan_knowledge_bundle(prepared, settings)
    prepared.knowledge_brief_markdown = knowledge_brief_markdown
    prepared.knowledge_selection_payload = selection_payload
    prepared.selected_knowledge_ids = selected_ids
    artifacts["plan-knowledge-selection.json"] = selection_payload
    if knowledge_brief_markdown.strip():
        artifacts["plan-knowledge-brief.md"] = knowledge_brief_markdown
    on_log(f"plan_knowledge_ok: selected={len(selected_ids)}")

    on_log("plan_task_outline_start: true")
    work_items, outline_payload = build_plan_work_items(prepared, settings, knowledge_brief_markdown, on_log)
    if not work_items:
        raise ValueError("plan 未生成任何 work item")
    artifacts["plan-task-outline.json"] = outline_payload
    artifacts["plan-work-items.json"] = {"work_items": [item.to_payload() for item in work_items]}
    on_log(f"plan_task_outline_ok: work_items={len(work_items)}")

    on_log("plan_graph_start: true")
    graph, dependency_notes = build_plan_execution_graph(work_items)
    artifacts["plan-execution-graph.json"] = graph.to_payload()
    artifacts["plan-dependency-notes.json"] = dependency_notes
    on_log(f"plan_graph_ok: edges={len(graph.edges)}, parallel_groups={len(graph.parallel_groups)}")

    on_log("plan_validation_start: true")
    validation_payload, risk_payload = build_plan_validation(prepared, work_items)
    artifacts["plan-validation.json"] = validation_payload
    artifacts["plan-risk-check.json"] = risk_payload
    on_log(f"plan_validation_ok: task_validations={len(validation_payload.get('task_validations', []))}")

    on_log("plan_generate_start: true")
    plan_markdown = generate_plan_markdown(prepared, work_items, graph, validation_payload, settings, on_log)
    on_log("plan_generate_ok: true")

    on_log("plan_verify_start: true")
    verify_payload = build_plan_verify_payload(prepared, work_items, graph, validation_payload, plan_markdown, settings, on_log)
    artifacts["plan-verify.json"] = verify_payload
    if not bool(verify_payload.get("ok")):
        issues = verify_payload.get("issues") or []
        issue_text = "; ".join(str(item) for item in issues[:3]) if isinstance(issues, list) else "unknown"
        on_log(f"plan_verify_failed: {issue_text}")
        raise ValueError(f"plan verify failed: {issue_text}")
    on_log("plan_verify_ok: true")

    artifacts["plan-result.json"] = {
        "task_id": prepared.task_id,
        "status": STATUS_PLANNED,
        "work_item_count": len(work_items),
        "repo_count": len({item.repo_id for item in work_items}),
        "critical_path_length": len(graph.critical_path),
        "parallel_group_count": len(graph.parallel_groups),
        "selected_knowledge_ids": selected_ids,
        "artifacts": sorted(artifacts.keys()) + ["plan.md"],
    }
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        plan_markdown=plan_markdown,
        intermediate_artifacts=artifacts,
    )
