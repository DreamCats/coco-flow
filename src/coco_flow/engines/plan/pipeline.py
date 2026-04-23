from __future__ import annotations

from coco_flow.config import Settings

from .generate import generate_native_plan_markdown, generate_plan_markdown
from .graph import build_plan_execution_graph
from .knowledge import build_plan_knowledge_bundle
from .models import PlanEngineResult, STATUS_PLANNED
from .source import prepare_plan_input
from .task_outline import build_plan_work_items
from .validation import build_plan_validation
from .verify import build_plan_verify_payload


def _collect_plan_verify_issues(verify_payload: dict[str, object]) -> list[str]:
    issues = [str(item) for item in (verify_payload.get("issues") or []) if str(item).strip()]
    if issues:
        return issues
    reason = str(verify_payload.get("reason") or "").strip()
    if reason:
        return [reason]
    return ["plan verify failed without actionable issues"]


def run_plan_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> PlanEngineResult:
    artifacts: dict[str, str | dict[str, object]] = {}

    on_log("plan_prepare_start: true")
    prepared = prepare_plan_input(task_dir, task_meta)
    on_log(f"plan_prepare_ok: repos={len(prepared.repo_scopes)}, title={prepared.title}")

    on_log("plan_skills_start: true")
    knowledge_brief_markdown, selection_payload, selected_ids = build_plan_knowledge_bundle(prepared, settings)
    prepared.knowledge_brief_markdown = knowledge_brief_markdown
    prepared.knowledge_selection_payload = selection_payload
    prepared.selected_skill_ids = selected_ids
    artifacts["plan-skills-selection.json"] = selection_payload
    if knowledge_brief_markdown.strip():
        artifacts["plan-skills-brief.md"] = knowledge_brief_markdown
    on_log(f"plan_skills_ok: selected={len(selected_ids)}")

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
    plan_markdown, plan_generate_mode = generate_plan_markdown(prepared, work_items, graph, validation_payload, settings, on_log)
    on_log(f"plan_generate_ok: mode={plan_generate_mode}")

    on_log("plan_verify_start: true")
    verify_payload = build_plan_verify_payload(prepared, work_items, graph, validation_payload, plan_markdown, settings, on_log)
    if not bool(verify_payload.get("ok")) and plan_generate_mode == "native" and settings.plan_executor.strip().lower() == "native":
        issues = _collect_plan_verify_issues(verify_payload)
        on_log(f"plan_regenerate_start: issue_count={len(issues)}")
        logged_regenerate_failure = False
        try:
            regenerated_plan_markdown = generate_native_plan_markdown(
                prepared,
                work_items,
                graph,
                validation_payload,
                settings,
                regeneration_issues=issues,
                previous_plan_markdown=plan_markdown,
            )
            regenerated_verify_payload = build_plan_verify_payload(
                prepared,
                work_items,
                graph,
                validation_payload,
                regenerated_plan_markdown,
                settings,
                on_log,
            )
            if not bool(regenerated_verify_payload.get("ok")):
                regenerated_issues = _collect_plan_verify_issues(regenerated_verify_payload)
                issue_text = "; ".join(regenerated_issues[:3])
                on_log(f"plan_regenerate_failed: {issue_text}")
                logged_regenerate_failure = True
                artifacts["plan-verify.json"] = regenerated_verify_payload
                raise ValueError(f"plan verify failed: {issue_text}")
            on_log("plan_regenerate_ok: true")
            plan_markdown = regenerated_plan_markdown
            verify_payload = regenerated_verify_payload
        except Exception as error:
            if not logged_regenerate_failure:
                on_log(f"plan_regenerate_failed: {error}")
            raise
    artifacts["plan-verify.json"] = verify_payload
    if not bool(verify_payload.get("ok")):
        issues = _collect_plan_verify_issues(verify_payload)
        issue_text = "; ".join(issues[:3])
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
        "selected_skill_ids": selected_ids,
        "artifacts": sorted(artifacts.keys()) + ["plan.md"],
    }
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        plan_markdown=plan_markdown,
        intermediate_artifacts=artifacts,
    )
