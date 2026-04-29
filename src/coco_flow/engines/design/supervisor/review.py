"""Supervisor Agent review for Design."""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.design.runtime import run_agent_json
from coco_flow.engines.design.support import as_str_list, dict_list
from coco_flow.engines.design.types import DesignInputBundle
from coco_flow.prompts.design import build_design_supervisor_review_prompt, build_design_supervisor_review_template_json

from .models import SUPERVISOR_DECISIONS, SUPERVISOR_NEXT_ACTIONS, SupervisorReview


def supervisor_review_design(
    prepared: DesignInputBundle,
    research_summary_payload: dict[str, object],
    design_markdown: str,
    quality_payload: dict[str, object],
    settings: Settings,
    *,
    native_ok: bool,
    on_log,
) -> SupervisorReview:
    if native_ok:
        try:
            payload = run_agent_json(
                prepared,
                settings,
                build_design_supervisor_review_template_json(),
                lambda template_path: build_design_supervisor_review_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    research_summary_payload=research_summary_payload,
                    design_markdown=design_markdown,
                    quality_payload=quality_payload,
                    template_path=template_path,
                ),
                ".design-supervisor-review-",
            )
            review = _normalize_supervisor_payload(payload, source="native")
            on_log(f"design_supervisor_review_ok: decision={review.decision} passed={str(review.passed).lower()}")
            return review
        except Exception as error:
            on_log(f"design_supervisor_review_fallback: {error}")
    review = _local_supervisor_review(quality_payload)
    on_log(f"design_supervisor_review_ok: decision={review.decision} passed={str(review.passed).lower()} source=local")
    return review


def _normalize_supervisor_payload(payload: dict[str, object], *, source: str) -> SupervisorReview:
    decision = str(payload.get("decision") or "").strip() or "needs_human"
    if decision not in SUPERVISOR_DECISIONS:
        decision = "needs_human"
    next_action = str(payload.get("next_action") or "").strip()
    if next_action not in SUPERVISOR_NEXT_ACTIONS:
        next_action = _default_next_action(decision)
    blocking_issues = dict_list(payload.get("blocking_issues"))
    repair_instructions = as_str_list(payload.get("repair_instructions"))
    passed = bool(payload.get("passed")) and decision == "pass" and not blocking_issues
    return SupervisorReview(
        passed=passed,
        decision="pass" if passed else decision,
        confidence=str(payload.get("confidence") or "medium"),
        blocking_issues=blocking_issues,
        repair_instructions=repair_instructions,
        next_action="accept_design" if passed else next_action,
        reason=str(payload.get("reason") or "").strip(),
        source=source,
    )


def _local_supervisor_review(quality_payload: dict[str, object]) -> SupervisorReview:
    actionability = quality_payload.get("actionability")
    if not isinstance(actionability, dict):
        actionability = {}
    passed = bool(actionability.get("passed"))
    issues = dict_list(actionability.get("issues"))
    if passed:
        return SupervisorReview(
            passed=True,
            decision="pass",
            next_action="accept_design",
            reason="Program quality gate passed.",
        )
    return SupervisorReview(
        passed=False,
        decision="repair_writer",
        confidence="medium",
        blocking_issues=[
            {
                "type": str(issue.get("type") or "quality_issue"),
                "summary": str(issue.get("summary") or "Design quality check failed."),
                "evidence": as_str_list(issue.get("evidence")),
            }
            for issue in issues
        ],
        repair_instructions=[str(issue.get("repair_suggestion") or "").strip() for issue in issues if str(issue.get("repair_suggestion") or "").strip()],
        next_action="rewrite_design",
        reason="Program quality gate found repairable structure issues.",
    )


def _default_next_action(decision: str) -> str:
    return {
        "pass": "accept_design",
        "repair_writer": "rewrite_design",
        "redo_research": "redo_research",
        "degrade_design": "write_degraded_design",
        "needs_human": "ask_human",
        "fail": "fail_design",
    }.get(decision, "ask_human")
