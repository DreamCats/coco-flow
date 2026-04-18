from __future__ import annotations

from .models import PlanPreparedInput, PlanValidationCheck, PlanWorkItem


def build_plan_validation(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
) -> tuple[dict[str, object], dict[str, object]]:
    critical_flows = _critical_flows(prepared)
    task_validations: list[PlanValidationCheck] = []
    risk_summary: list[str] = []

    for item in work_items:
        checks = [{"kind": "review", "target": item.repo_id, "reason": step} for step in item.verification_steps[:4]]
        task_validations.append(
            PlanValidationCheck(
                task_id=item.id,
                repo_id=item.repo_id,
                checks=checks,
                linked_design_flows=critical_flows[:2],
                non_goal_regressions=prepared.refined_sections.non_goals[:3],
            )
        )
        risk_summary.extend(item.risk_notes[:2])

    payload = {
        "global_validation_focus": critical_flows + prepared.refined_sections.acceptance_criteria[:3],
        "task_validations": [item.to_payload() for item in task_validations],
    }
    risk_payload = {
        "task_risks": [{"task_id": item.id, "repo_id": item.repo_id, "risk_notes": item.risk_notes[:4]} for item in work_items],
        "global_risk_summary": _dedupe_terms(risk_summary)[:8],
    }
    return payload, risk_payload


def _critical_flows(prepared: PlanPreparedInput) -> list[str]:
    raw = prepared.design_sections_payload.get("critical_flows")
    if isinstance(raw, list):
        flows: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                trigger = str(item.get("trigger") or "").strip()
                summary = " / ".join(part for part in (name, trigger) if part)
                if summary:
                    flows.append(summary)
        if flows:
            return flows[:4]
    if prepared.refined_sections.change_scope:
        return prepared.refined_sections.change_scope[:3]
    return [prepared.title]


def _dedupe_terms(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        lowered = item.lower()
        if not item or lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result
