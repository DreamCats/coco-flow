from __future__ import annotations

import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.plan import (
    build_plan_validation_designer_agent_prompt,
    build_plan_validation_designer_template_json,
)

from .models import EXECUTOR_NATIVE, PlanExecutionGraph, PlanPreparedInput, PlanValidationCheck, PlanWorkItem


def build_plan_validation(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    settings: Settings,
    on_log,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    fallback_payload, fallback_risk = build_local_plan_validation(prepared, work_items)
    validation_payload = fallback_payload
    risk_payload = fallback_risk
    draft_payload = _with_validation_metadata(fallback_payload, source="local", degraded=False)
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            native_payload = _build_plan_validation_with_designer(prepared, work_items, graph, settings)
            validation_payload = normalize_plan_validation_payload(native_payload, prepared, work_items)
            risk_payload = build_plan_risk_payload(work_items)
            draft_payload = _with_validation_metadata(native_payload, source="native", degraded=False)
            on_log(f"plan_validation_designer_mode: native task_validations={len(validation_payload.get('task_validations', []))}")
        except Exception as error:
            on_log(f"plan_validation_designer_fallback: {error}")
            draft_payload = _with_validation_metadata(
                fallback_payload,
                source="local_fallback",
                degraded=True,
                degraded_reason=str(error),
            )
    else:
        on_log("plan_validation_designer_mode: local")
    return validation_payload, risk_payload, draft_payload


def build_local_plan_validation(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
) -> tuple[dict[str, object], dict[str, object]]:
    critical_flows = _critical_flows(prepared)
    task_validations: list[PlanValidationCheck] = []

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

    payload = {
        "global_validation_focus": critical_flows + prepared.refined_sections.acceptance_criteria[:3],
        "task_validations": [item.to_payload() for item in task_validations],
    }
    return payload, build_plan_risk_payload(work_items)


def normalize_plan_validation_payload(
    payload: dict[str, object],
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
) -> dict[str, object]:
    fallback_payload, _risk = build_local_plan_validation(prepared, work_items)
    fallback_by_task = {
        str(item.get("task_id") or ""): item
        for item in _dict_list(fallback_payload.get("task_validations"))
    }
    raw_by_task = {
        str(item.get("task_id") or ""): item
        for item in _dict_list(payload.get("task_validations"))
    }
    task_validations: list[dict[str, object]] = []
    for item in work_items:
        raw = raw_by_task.get(item.id, {})
        fallback = fallback_by_task.get(item.id, {})
        checks = _normalize_checks(raw.get("checks"), item.repo_id)
        if not checks:
            checks = _dict_list(fallback.get("checks"))
        task_validations.append(
            {
                "task_id": item.id,
                "repo_id": item.repo_id,
                "checks": checks,
                "linked_design_flows": _str_list(raw.get("linked_design_flows")) or _str_list(fallback.get("linked_design_flows")),
                "non_goal_regressions": _str_list(raw.get("non_goal_regressions")) or _str_list(fallback.get("non_goal_regressions")),
            }
        )
    global_focus = _str_list(payload.get("global_validation_focus")) or _str_list(fallback_payload.get("global_validation_focus"))
    return {
        "global_validation_focus": global_focus,
        "task_validations": task_validations,
    }


def build_plan_risk_payload(work_items: list[PlanWorkItem]) -> dict[str, object]:
    risk_summary: list[str] = []
    for item in work_items:
        risk_summary.extend(item.risk_notes[:2])
    return {
        "task_risks": [{"task_id": item.id, "repo_id": item.repo_id, "risk_notes": item.risk_notes[:4]} for item in work_items],
        "global_risk_summary": _dedupe_terms(risk_summary)[:8],
    }


def _build_plan_validation_with_designer(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    template_path = _write_template(prepared.task_dir, ".plan-validation-designer-", ".json", build_plan_validation_designer_template_json())
    try:
        client.run_agent(
            build_plan_validation_designer_agent_prompt(
                title=prepared.title,
                design_markdown=prepared.design_markdown,
                refined_markdown=prepared.refined_markdown,
                skills_brief_markdown=prepared.skills_brief_markdown,
                work_items_payload={"work_items": [item.to_payload() for item in work_items]},
                execution_graph_payload=graph.to_payload(),
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()
    if "__FILL__" in raw or not raw.strip():
        raise ValueError("plan_validation_designer_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("plan_validation_designer_output_invalid")
    return payload


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


def _normalize_checks(value: object, repo_id: str) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for raw in _dict_list(value):
        kind = str(raw.get("kind") or "review").strip()
        if kind not in {"review", "build", "test", "smoke", "manual-check"}:
            kind = "review"
        target = str(raw.get("target") or repo_id).strip()
        reason = str(raw.get("reason") or "").strip()
        if not reason:
            continue
        checks.append({"kind": kind, "target": target, "reason": reason})
    return checks[:6]


def _with_validation_metadata(
    payload: dict[str, object],
    *,
    source: str,
    degraded: bool,
    degraded_reason: str = "",
) -> dict[str, object]:
    result = dict(payload)
    validation_designer = result.get("validation_designer")
    validation_payload = dict(validation_designer) if isinstance(validation_designer, dict) else {}
    validation_payload.update({"role": "validation_designer", "source": source, "degraded": degraded})
    if degraded_reason:
        validation_payload["degraded_reason"] = degraded_reason
        validation_payload["fallback_stage"] = "validation_designer"
    result["validation_designer"] = validation_payload
    return result


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)
