from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import diagnosis_payload_from_verify
from coco_flow.prompts.design import build_semantic_gate_prompt, build_semantic_gate_template_json

from .agent_io import run_agent_json
from .models import (
    GATE_DEGRADED,
    GATE_FAILED,
    GATE_NEEDS_HUMAN,
    GATE_PASSED,
    GATE_PASSED_WITH_WARNINGS,
    DesignInputBundle,
)
from .utils import dict_list, issue, issues, normalize_issue


def run_semantic_gate(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    design_markdown: str,
    settings: Settings,
    *,
    native_ok: bool,
    review_payload: dict[str, object],
    on_log,
) -> dict[str, object]:
    if native_ok:
        try:
            payload = run_agent_json(
                prepared,
                settings,
                build_semantic_gate_template_json(),
                lambda template_path: build_semantic_gate_prompt(
                    title=prepared.title,
                    refined_markdown=prepared.refined_markdown,
                    decision_payload=decision_payload,
                    design_markdown=design_markdown,
                    template_path=template_path,
                ),
                ".design-gate-",
            )
            return normalize_gate_payload(payload, review_payload, design_markdown)
        except Exception as error:
            on_log(f"design_v3_gate_degraded: {error}")
    return local_gate_payload(prepared, decision_payload, design_markdown, review_payload, degraded=True)


def local_gate_payload(
    prepared: DesignInputBundle,
    decision_payload: dict[str, object],
    design_markdown: str,
    review_payload: dict[str, object],
    *,
    degraded: bool,
) -> dict[str, object]:
    gate_issues = list(issues(review_payload))
    if "# " not in design_markdown:
        gate_issues.append(issue("blocking", "design_markdown_invalid", "design.md", "design.md 必须是 Markdown 文档。", "缺少标题。", "重新生成 design.md。"))
    gate_issues.extend(_markdown_blocker_issues(design_markdown))
    if not dict_list(decision_payload.get("repo_decisions")):
        gate_issues.append(issue("blocking", "repo_decision_missing", "design-decision.json", "必须存在 repo_decisions。", "repo_decisions 为空。", "重跑 architect adjudication。"))
    blocking = [item for item in gate_issues if str(item.get("severity")) == "blocking"]
    if blocking:
        gate_status = GATE_NEEDS_HUMAN
    elif degraded:
        gate_status = GATE_DEGRADED
    elif gate_issues:
        gate_status = GATE_PASSED_WITH_WARNINGS
    else:
        gate_status = GATE_PASSED
    return {
        "ok": gate_status in {GATE_PASSED, GATE_PASSED_WITH_WARNINGS},
        "gate_status": gate_status,
        "issues": gate_issues,
        "reason": _normalized_gate_reason(gate_status, gate_issues, _gate_reason(gate_status, prepared)),
    }


def normalize_gate_payload(payload: dict[str, object], review_payload: dict[str, object], design_markdown: str) -> dict[str, object]:
    gate_issues = [normalize_issue(item) for item in dict_list(payload.get("issues"))] + issues(review_payload)
    gate_issues.extend(_markdown_blocker_issues(design_markdown))
    blocking = [item for item in gate_issues if str(item.get("severity")) == "blocking"]
    gate_status = str(payload.get("gate_status") or "").strip()
    if blocking:
        gate_status = GATE_NEEDS_HUMAN
    if gate_status not in {GATE_PASSED, GATE_PASSED_WITH_WARNINGS, GATE_NEEDS_HUMAN, GATE_DEGRADED, GATE_FAILED}:
        gate_status = GATE_PASSED if bool(payload.get("ok")) and not blocking else GATE_NEEDS_HUMAN
    return {
        "ok": gate_status in {GATE_PASSED, GATE_PASSED_WITH_WARNINGS},
        "gate_status": gate_status,
        "issues": gate_issues,
        "reason": _normalized_gate_reason(gate_status, gate_issues, str(payload.get("reason") or "")),
    }


def build_design_diagnosis(verify_payload: dict[str, object]) -> dict[str, object]:
    gate_status = str(verify_payload.get("gate_status") or GATE_FAILED)
    if gate_status == GATE_PASSED:
        return diagnosis_payload_from_verify(stage="design", verify_payload=verify_payload, artifact="design.md")
    severity = "warning" if gate_status == GATE_PASSED_WITH_WARNINGS else gate_status
    return {
        "ok": bool(verify_payload.get("ok")),
        "stage": "design",
        "severity": severity,
        "failure_type": gate_status,
        "next_action": "needs_human" if gate_status in {GATE_NEEDS_HUMAN, GATE_DEGRADED} else "retry",
        "retryable": gate_status == GATE_FAILED,
        "attempt": 0,
        "max_attempts": 0,
        "issues": issues(verify_payload),
        "reason": str(verify_payload.get("reason") or _gate_reason(gate_status, None)),
    }


def _gate_reason(gate_status: str, prepared: DesignInputBundle | None) -> str:
    if gate_status == GATE_PASSED:
        return "Design V3 semantic gate passed."
    if gate_status == GATE_PASSED_WITH_WARNINGS:
        return "Design V3 semantic gate passed with warnings."
    if gate_status == GATE_DEGRADED:
        return "Design V3 only produced a local or partial draft; human confirmation is required before Plan."
    if gate_status == GATE_NEEDS_HUMAN:
        title = prepared.title if prepared is not None else "当前任务"
        return f"{title} 的设计裁决存在证据不足或 blocking issue，需要人工确认。"
    return "Design V3 failed."


def _markdown_blocker_issues(design_markdown: str) -> list[dict[str, object]]:
    blocker_patterns = [
        "当前不能进入 Plan",
        "不能进入 Plan",
        "当前阻断",
        "阻断原因",
        "仍存在阻塞",
        "blocking issue 仍",
    ]
    if not any(pattern in design_markdown for pattern in blocker_patterns):
        return []
    return [
        issue(
            "blocking",
            "design_markdown_status_conflict",
            "design.md",
            "design.md 不应在 gate passed 时声明阻断或不能进入 Plan。",
            "design.md 含有阻断语义。",
            "修正 design-decision / review revision 后重写 design.md，或保持 needs_human。",
        )
    ]


def _normalized_gate_reason(gate_status: str, gate_issues: list[dict[str, object]], fallback: str) -> str:
    blocking = [item for item in gate_issues if str(item.get("severity") or "") == "blocking"]
    if gate_status in {GATE_NEEDS_HUMAN, GATE_FAILED, GATE_DEGRADED} and blocking:
        first = blocking[0]
        target = str(first.get("target") or "design decision")
        action = str(first.get("suggested_action") or first.get("actual") or "").strip()
        if action:
            return f"存在阻塞问题：{target}。{action}"
        return f"存在阻塞问题：{target}。"
    if gate_status == GATE_DEGRADED:
        return _gate_reason(gate_status, None)
    if gate_status == GATE_NEEDS_HUMAN and "能够支撑" in fallback:
        return _gate_reason(gate_status, None)
    return fallback or _gate_reason(gate_status, None)
