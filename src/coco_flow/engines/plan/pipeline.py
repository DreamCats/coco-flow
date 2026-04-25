from __future__ import annotations

import json

from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import diagnosis_payload_from_verify

from .generate import generate_native_plan_markdown, generate_plan_markdown
from .graph import build_plan_execution_graph
from .skills import build_plan_skills_bundle
from .models import (
    CODE_ALLOWED_GATE_STATUSES,
    GATE_NEEDS_DESIGN_REVISION,
    GATE_NEEDS_HUMAN,
    GATE_PASSED,
    PLAN_HARNESS_VERSION,
    STATUS_FAILED,
    STATUS_PLANNED,
    PlanEngineResult,
)
from .review import build_plan_review_and_decision
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
    skills_brief_markdown, skills_selection_payload, selected_skill_ids = build_plan_skills_bundle(prepared, settings)
    prepared.skills_brief_markdown = skills_brief_markdown
    prepared.skills_selection_payload = skills_selection_payload
    prepared.selected_skill_ids = selected_skill_ids
    artifacts["plan-skills-selection.json"] = skills_selection_payload
    if skills_brief_markdown.strip():
        artifacts["plan-skills-brief.md"] = skills_brief_markdown
    on_log(f"plan_skills_ok: selected={len(selected_skill_ids)}")

    on_log("plan_planner_start: true")
    work_items, outline_payload, draft_work_items_payload = build_plan_work_items(
        prepared,
        settings,
        skills_brief_markdown,
        on_log,
    )
    if not work_items:
        raise ValueError("plan 未生成任何 work item")
    artifacts["plan-draft-work-items.json"] = draft_work_items_payload
    artifacts["plan-task-outline.json"] = outline_payload
    artifacts["plan-work-items.json"] = {"work_items": [item.to_payload() for item in work_items]}
    planner_meta = draft_work_items_payload.get("planner")
    planner_degraded = bool(planner_meta.get("degraded")) if isinstance(planner_meta, dict) else False
    on_log(f"plan_planner_ok: work_items={len(work_items)} degraded={'true' if planner_degraded else 'false'}")

    on_log("plan_graph_start: true")
    graph, dependency_notes, draft_graph_payload = build_plan_execution_graph(prepared, work_items, settings, on_log)
    artifacts["plan-draft-execution-graph.json"] = draft_graph_payload
    artifacts["plan-execution-graph.json"] = graph.to_payload()
    artifacts["plan-dependency-notes.json"] = dependency_notes
    on_log(f"plan_graph_ok: edges={len(graph.edges)}, parallel_groups={len(graph.parallel_groups)}")

    on_log("plan_validation_start: true")
    validation_payload, risk_payload, draft_validation_payload = build_plan_validation(prepared, work_items, graph, settings, on_log)
    artifacts["plan-draft-validation.json"] = draft_validation_payload
    artifacts["plan-validation.json"] = validation_payload
    artifacts["plan-risk-check.json"] = risk_payload
    on_log(f"plan_validation_ok: task_validations={len(validation_payload.get('task_validations', []))}")

    on_log("plan_skeptic_start: true")
    review_payload, debate_payload, decision_payload = build_plan_review_and_decision(
        prepared,
        work_items,
        graph,
        validation_payload,
        settings,
        on_log,
    )
    artifacts["plan-review.json"] = review_payload
    artifacts["plan-debate.json"] = debate_payload
    artifacts["plan-decision.json"] = decision_payload
    review_issues = review_payload.get("issues")
    review_issue_count = len(review_issues) if isinstance(review_issues, list) else 0
    decision_finalized = bool(decision_payload.get("finalized"))
    review_degraded = bool(review_payload.get("degraded"))
    on_log(
        "plan_skeptic_ok: "
        f"issues={review_issue_count} "
        f"blocking={int(decision_payload.get('review_blocking_count') or 0)} "
        f"finalized={'true' if decision_finalized else 'false'}"
    )

    on_log("plan_writer_start: true")
    plan_markdown, plan_generate_mode = generate_plan_markdown(prepared, decision_payload, settings, on_log)
    on_log(f"plan_writer_ok: mode={plan_generate_mode}")

    on_log("plan_verify_start: true")
    verify_payload = build_plan_verify_payload(prepared, work_items, graph, validation_payload, plan_markdown, settings, on_log)
    artifacts["plan-verify.json"] = verify_payload
    artifacts["plan-diagnosis.json"] = diagnosis_payload_from_verify(
        stage="plan",
        verify_payload=verify_payload,
        artifact="plan.md",
    )
    _log_plan_diagnosis(artifacts["plan-diagnosis.json"], on_log)
    if not bool(verify_payload.get("ok")) and plan_generate_mode == "native" and settings.plan_executor.strip().lower() == "native":
        issues = _collect_plan_verify_issues(verify_payload)
        on_log(f"plan_regenerate_start: issue_count={len(issues)}")
        logged_regenerate_failure = False
        try:
            regenerated_plan_markdown = generate_native_plan_markdown(
                prepared,
                decision_payload,
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
                artifacts["plan-diagnosis.json"] = diagnosis_payload_from_verify(
                    stage="plan",
                    verify_payload=regenerated_verify_payload,
                    artifact="plan.md",
                )
                _write_failure_diagnosis_artifacts(prepared.task_dir, artifacts)
                raise ValueError(f"plan verify failed: {issue_text}")
            on_log("plan_regenerate_ok: true")
            plan_markdown = regenerated_plan_markdown
            verify_payload = regenerated_verify_payload
            artifacts["plan-verify.json"] = verify_payload
            artifacts["plan-diagnosis.json"] = diagnosis_payload_from_verify(
                stage="plan",
                verify_payload=verify_payload,
                artifact="plan.md",
            )
            _log_plan_diagnosis(artifacts["plan-diagnosis.json"], on_log)
        except Exception as error:
            if not logged_regenerate_failure:
                on_log(f"plan_regenerate_failed: {error}")
            raise
    if not bool(verify_payload.get("ok")):
        issues = _collect_plan_verify_issues(verify_payload)
        issue_text = "; ".join(issues[:3])
        on_log(f"plan_verify_failed: {issue_text}")
        _write_failure_diagnosis_artifacts(prepared.task_dir, artifacts)
        raise ValueError(f"plan verify failed: {issue_text}")
    gate_payload = _build_plan_gate_payload(verify_payload, review_payload, decision_payload)
    verify_payload = gate_payload
    artifacts["plan-verify.json"] = verify_payload
    artifacts["plan-diagnosis.json"] = diagnosis_payload_from_verify(
        stage="plan",
        verify_payload=verify_payload,
        artifact="plan.md",
    )
    _log_plan_diagnosis(artifacts["plan-diagnosis.json"], on_log)
    on_log(
        "plan_gate_ok: "
        f"gate_status={verify_payload.get('gate_status') or ''} "
        f"code_allowed={'true' if bool(verify_payload.get('ok')) else 'false'}"
    )

    gate_status = str(verify_payload.get("gate_status") or GATE_NEEDS_HUMAN)
    code_allowed = gate_status in CODE_ALLOWED_GATE_STATUSES
    result_status = STATUS_PLANNED if code_allowed else STATUS_FAILED
    artifacts["plan-result.json"] = {
        "task_id": prepared.task_id,
        "status": result_status,
        "harness_version": PLAN_HARNESS_VERSION,
        "gate_status": gate_status,
        "code_allowed": code_allowed,
        "planner_degraded": planner_degraded,
        "review_degraded": review_degraded,
        "fallback_stage": "planner" if planner_degraded else "skeptic" if review_degraded else "",
        "degraded_reason": (
            str(planner_meta.get("degraded_reason") or "")
            if isinstance(planner_meta, dict) and planner_degraded
            else str(review_payload.get("degraded_reason") or "")
        ),
        "review_issue_count": review_issue_count,
        "review_blocking_count": int(decision_payload.get("review_blocking_count") or 0),
        "decision_finalized": decision_finalized,
        "work_item_count": len(work_items),
        "repo_count": len({item.repo_id for item in work_items}),
        "critical_path_length": len(graph.critical_path),
        "parallel_group_count": len(graph.parallel_groups),
        "selected_skill_ids": selected_skill_ids,
        "artifacts": sorted(artifacts.keys()) + ["plan.md"],
    }
    on_log(f"status: {result_status}")
    return PlanEngineResult(
        status=result_status,
        plan_markdown=plan_markdown,
        intermediate_artifacts=artifacts,
    )


def _build_plan_gate_payload(
    verify_payload: dict[str, object],
    review_payload: dict[str, object],
    decision_payload: dict[str, object],
) -> dict[str, object]:
    blocking_issues = [
        item
        for item in _dict_list(review_payload.get("issues"))
        if str(item.get("severity") or "") == "blocking"
    ]
    if not blocking_issues and bool(verify_payload.get("ok")) and bool(decision_payload.get("finalized", True)):
        payload = dict(verify_payload)
        payload["ok"] = True
        payload["gate_status"] = GATE_PASSED
        payload.setdefault("reason", "Plan gate passed.")
        return payload

    gate_status = (
        GATE_NEEDS_DESIGN_REVISION
        if any(str(item.get("failure_type") or "") in {"needs_design_revision", "design_artifact_conflict"} for item in blocking_issues)
        else GATE_NEEDS_HUMAN
    )
    reason = "Plan review has blocking issues."
    if blocking_issues:
        first = blocking_issues[0]
        action = str(first.get("suggested_action") or first.get("actual") or "").strip()
        target = str(first.get("target") or "plan").strip()
        reason = f"Plan gate blocked by {target}."
        if action:
            reason += f" {action}"
    payload = dict(verify_payload)
    payload["ok"] = False
    payload["gate_status"] = gate_status
    payload["severity"] = gate_status
    payload["failure_type"] = gate_status
    payload["next_action"] = gate_status
    payload["retryable"] = False
    payload["issues"] = blocking_issues
    payload["reason"] = reason
    return payload


def _write_failure_diagnosis_artifacts(task_dir, artifacts: dict[str, str | dict[str, object]]) -> None:
    for name in ("plan-verify.json", "plan-diagnosis.json"):
        payload = artifacts.get(name)
        if isinstance(payload, dict):
            (task_dir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _log_plan_diagnosis(payload: object, on_log) -> None:
    if not isinstance(payload, dict):
        return
    on_log(
        "diagnosis: "
        f"severity={payload.get('severity') or ''} "
        f"failure_type={payload.get('failure_type') or '-'} "
        f"next_action={payload.get('next_action') or ''}"
    )
