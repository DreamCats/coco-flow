from __future__ import annotations

from dataclasses import dataclass, field


SEVERITY_BLOCKING = "blocking"
SEVERITY_INFO = "info"
SEVERITY_NEEDS_HUMAN = "needs_human"
SEVERITY_WARNING = "warning"

NEXT_ACTION_CONTINUE = "continue"
NEXT_ACTION_CONTINUE_WITH_WARNINGS = "continue_with_warnings"
NEXT_ACTION_FAIL = "fail"
NEXT_ACTION_NEEDS_HUMAN = "needs_human"
NEXT_ACTION_REPAIR = "repair"


@dataclass
class DiagnosticIssue:
    id: str
    artifact: str
    path: str
    expected: str
    actual: str
    repair_hint: str
    auto_repairable: bool
    repo_id: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "artifact": self.artifact,
            "path": self.path,
            "expected": self.expected,
            "actual": self.actual,
            "repair_hint": self.repair_hint,
            "auto_repairable": self.auto_repairable,
        }
        if self.repo_id:
            payload["repo_id"] = self.repo_id
        return payload


@dataclass
class GateDecision:
    severity: str
    next_action: str
    retryable: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "next_action": self.next_action,
            "retryable": self.retryable,
        }


@dataclass
class StageDiagnosis:
    ok: bool
    stage: str
    severity: str
    failure_type: str
    next_action: str
    retryable: bool
    attempt: int
    max_attempts: int
    issues: list[DiagnosticIssue] = field(default_factory=list)
    reason: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "stage": self.stage,
            "severity": self.severity,
            "failure_type": self.failure_type,
            "next_action": self.next_action,
            "retryable": self.retryable,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "issues": [issue.to_payload() for issue in self.issues],
            "reason": self.reason,
        }


def build_stage_diagnosis(
    *,
    stage: str,
    verify_payload: dict[str, object],
    artifact: str | None = None,
    attempt: int = 0,
    max_attempts: int = 0,
) -> StageDiagnosis:
    ok = bool(verify_payload.get("ok"))
    issues = _normalize_issues(stage, verify_payload.get("issues"), artifact or _default_artifact(stage))
    reason = str(verify_payload.get("reason") or "")
    failure_type = str(verify_payload.get("failure_type") or "").strip()
    if not failure_type:
        failure_type = "" if ok else infer_failure_type(stage, issues, reason)

    decision = _build_gate_decision(ok=ok, issues=issues, failure_type=failure_type)
    return StageDiagnosis(
        ok=ok,
        stage=stage,
        severity=str(verify_payload.get("severity") or decision.severity),
        failure_type=failure_type,
        next_action=str(verify_payload.get("next_action") or decision.next_action),
        retryable=bool(verify_payload.get("retryable", decision.retryable)),
        attempt=int(verify_payload.get("attempt") or attempt),
        max_attempts=int(verify_payload.get("max_attempts") or max_attempts),
        issues=issues,
        reason=reason,
    )


def enrich_verify_payload(
    *,
    stage: str,
    verify_payload: dict[str, object],
    artifact: str | None = None,
    attempt: int = 0,
    max_attempts: int = 0,
) -> dict[str, object]:
    diagnosis = build_stage_diagnosis(
        stage=stage,
        verify_payload=verify_payload,
        artifact=artifact,
        attempt=attempt,
        max_attempts=max_attempts,
    )
    payload = dict(verify_payload)
    payload.setdefault("stage", stage)
    payload.setdefault("severity", diagnosis.severity)
    payload.setdefault("failure_type", diagnosis.failure_type)
    payload.setdefault("next_action", diagnosis.next_action)
    payload.setdefault("retryable", diagnosis.retryable)
    payload.setdefault("attempt", diagnosis.attempt)
    payload.setdefault("max_attempts", diagnosis.max_attempts)
    return payload


def diagnosis_payload_from_verify(
    *,
    stage: str,
    verify_payload: dict[str, object],
    artifact: str | None = None,
    attempt: int = 0,
    max_attempts: int = 0,
) -> dict[str, object]:
    return build_stage_diagnosis(
        stage=stage,
        verify_payload=verify_payload,
        artifact=artifact,
        attempt=attempt,
        max_attempts=max_attempts,
    ).to_payload()


def infer_failure_type(stage: str, issues: list[DiagnosticIssue], reason: str = "") -> str:
    if not issues and not reason:
        return ""
    text = " ".join([issue.actual for issue in issues] + [reason]).lower()
    if "占位" in text or "placeholder" in text or "__fill__" in text:
        return "template_placeholder"
    if "缺少必要章节" in text or "缺少必填章节" in text or "missing section" in text:
        return "missing_required_section"
    if "must_change repo" in text or "work item" in text or "执行任务覆盖" in text:
        return "missing_work_item_coverage"
    if "contract" in text or "契约" in text:
        return "contract_failed"
    if "in_scope" in text or "acceptance" in text or "specific_steps" in text:
        return "missing_required_content"
    return f"{stage}_verify_failed"


def _build_gate_decision(*, ok: bool, issues: list[DiagnosticIssue], failure_type: str) -> GateDecision:
    if ok:
        return GateDecision(severity=SEVERITY_INFO, next_action=NEXT_ACTION_CONTINUE, retryable=False)
    if failure_type in {"repo_responsibility_uncertain", "source_conflict", "missing_human_scope"}:
        return GateDecision(severity=SEVERITY_NEEDS_HUMAN, next_action=NEXT_ACTION_NEEDS_HUMAN, retryable=False)
    if issues and all(issue.auto_repairable for issue in issues):
        return GateDecision(severity=SEVERITY_BLOCKING, next_action=NEXT_ACTION_REPAIR, retryable=True)
    return GateDecision(severity=SEVERITY_BLOCKING, next_action=NEXT_ACTION_FAIL, retryable=False)


def _normalize_issues(stage: str, raw_issues: object, default_artifact: str) -> list[DiagnosticIssue]:
    if not isinstance(raw_issues, list):
        return []
    issues: list[DiagnosticIssue] = []
    prefix = stage[:1].upper() or "S"
    for index, item in enumerate(raw_issues, start=1):
        if isinstance(item, dict):
            actual = str(item.get("actual") or item.get("message") or item.get("reason") or item)
            artifact = str(item.get("artifact") or default_artifact)
            path = str(item.get("path") or "")
            expected = str(item.get("expected") or "满足阶段 verify 契约")
            repair_hint = str(item.get("repair_hint") or _repair_hint(stage, actual))
            auto_repairable = bool(item.get("auto_repairable", _is_auto_repairable(actual)))
            repo_id = str(item.get("repo_id") or "").strip() or None
            issue_id = str(item.get("id") or f"{prefix}{index:03d}")
        else:
            actual = str(item)
            artifact = _infer_issue_artifact(stage, actual, default_artifact)
            path = _infer_issue_path(actual)
            expected = _expected_for_issue(stage, actual)
            repair_hint = _repair_hint(stage, actual)
            auto_repairable = _is_auto_repairable(actual)
            repo_id = None
            issue_id = f"{prefix}{index:03d}"
        if not actual.strip():
            continue
        issues.append(
            DiagnosticIssue(
                id=issue_id,
                artifact=artifact,
                path=path,
                expected=expected,
                actual=actual,
                repair_hint=repair_hint,
                auto_repairable=auto_repairable,
                repo_id=repo_id,
            )
        )
    return issues


def _default_artifact(stage: str) -> str:
    return {
        "refine": "prd-refined.md",
        "design": "design.md",
        "plan": "plan.md",
    }.get(stage, f"{stage}.md")


def _infer_issue_artifact(stage: str, actual: str, default_artifact: str) -> str:
    if "work item" in actual or "执行任务覆盖" in actual:
        return "plan-work-items.json"
    if "execution graph" in actual:
        return "plan-execution-graph.json"
    if "validation contract" in actual:
        return "plan-validation.json"
    if "brief" in actual:
        return "refine-brief.json"
    if stage == "design" and ("候选文件" in actual or "candidate" in actual):
        return "design-repo-binding.json"
    return default_artifact


def _infer_issue_path(actual: str) -> str:
    if "缺少必要章节" in actual or "缺少必填章节" in actual:
        return "sections"
    if "work item" in actual or "执行任务覆盖" in actual:
        return "work_items"
    if "execution graph" in actual:
        return "execution_graph"
    if "validation contract" in actual:
        return "task_validations"
    return ""


def _expected_for_issue(stage: str, actual: str) -> str:
    if "缺少必要章节" in actual or "缺少必填章节" in actual:
        return "markdown 必须包含阶段必填章节"
    if "work item" in actual or "执行任务覆盖" in actual:
        return "必须为进入执行范围的 repo 生成可执行 work item"
    if "validation contract" in actual:
        return "每个 work item 都应有对应验证契约"
    if stage == "refine":
        return "需求确认书必须覆盖人工提炼范围、边界和验收标准"
    if stage == "design":
        return "design 必须解释仓库执行职责、候选文件和风险"
    if stage == "plan":
        return "plan 必须能被 code 阶段直接消费"
    return "满足阶段 verify 契约"


def _repair_hint(stage: str, actual: str) -> str:
    if "占位" in actual or "placeholder" in actual:
        return "移除模板占位语，并用已知上下文补齐对应内容。"
    if "缺少必要章节" in actual or "缺少必填章节" in actual:
        return "只补齐缺失章节，保持已有内容和范围不变。"
    if "work item" in actual or "执行任务覆盖" in actual:
        return "基于 design-repo-binding.json 为缺失 repo 补充 implementation work item。"
    if stage == "refine":
        return "基于 manual extract 和 refine brief 定点补齐缺失内容。"
    if stage == "design":
        return "基于 repo binding、research 和 sections 定点补齐缺失证据。"
    if stage == "plan":
        return "基于 work items、execution graph 和 validation 定点修复 plan。"
    return "根据 verify issue 定点修复对应 artifact。"


def _is_auto_repairable(actual: str) -> bool:
    text = actual.lower()
    if "needs_human" in text or "人工" in text or "冲突" in text:
        return False
    return True
