from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.plan import (
    build_plan_review_template_json,
    build_plan_revision_prompt,
    build_plan_revision_template_json,
    build_plan_skeptic_prompt,
)

from .agent_io import close_plan_agent_session, new_plan_agent_session, run_plan_agent_json_in_session, run_plan_agent_json_with_new_session
from .models import EXECUTOR_NATIVE, PlanExecutionGraph, PlanPreparedInput, PlanWorkItem

_SEVERITIES = {"blocking", "warning", "info"}
_GENERIC_VALIDATION_TEXTS = {
    "最小范围验证通过",
    "优先覆盖关键链路和核心约束",
}


def build_plan_review_and_decision(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    settings: Settings,
    on_log,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            return _build_native_plan_review_and_revision_payloads(
                prepared,
                work_items,
                graph,
                validation_payload,
                settings,
                on_log,
            )
        except Exception as error:
            on_log(f"plan_skeptic_fallback: {error}")
            review_payload = build_local_plan_review_payload(prepared, work_items, graph, validation_payload)
            review_payload["source"] = "local_fallback"
            review_payload["degraded"] = True
            review_payload["degraded_reason"] = str(error)
            review_payload["fallback_stage"] = "skeptic"
            debate_payload, decision_payload = build_plan_decision_payload(
                prepared,
                work_items,
                graph,
                validation_payload,
                review_payload,
            )
            return review_payload, debate_payload, decision_payload

    review_payload = build_plan_review_payload(prepared, work_items, graph, validation_payload, settings, on_log)
    debate_payload, decision_payload = build_plan_decision_payload(
        prepared,
        work_items,
        graph,
        validation_payload,
        review_payload,
    )
    return review_payload, debate_payload, decision_payload


def build_plan_review_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    settings: Settings,
    on_log,
) -> dict[str, object]:
    fallback = build_local_plan_review_payload(prepared, work_items, graph, validation_payload)
    if settings.plan_executor.strip().lower() != EXECUTOR_NATIVE:
        return fallback
    try:
        payload = _build_native_plan_review_payload(prepared, work_items, graph, validation_payload, settings, on_log)
        on_log("plan_skeptic_mode: native")
        return normalize_plan_review_payload(payload)
    except Exception as error:
        on_log(f"plan_skeptic_fallback: {error}")
        degraded = dict(fallback)
        degraded["source"] = "local_fallback"
        degraded["degraded"] = True
        degraded["degraded_reason"] = str(error)
        degraded["fallback_stage"] = "skeptic"
        return degraded


def build_local_plan_review_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
) -> dict[str, object]:
    issues: list[dict[str, object]] = []
    binding_items = _in_scope_binding_items(prepared)
    scope_by_repo = {str(item.get("repo_id") or ""): str(item.get("scope_tier") or "") for item in binding_items}
    in_scope_repos = {repo_id for repo_id in scope_by_repo if repo_id}
    must_change_repos = {repo_id for repo_id, scope_tier in scope_by_repo.items() if scope_tier == "must_change"}
    work_item_repos = {item.repo_id for item in work_items}

    missing_must_change = sorted(must_change_repos - work_item_repos)
    if missing_must_change:
        issues.append(
            _issue(
                "blocking",
                "missing_must_change_repo",
                "plan-work-items.json",
                "每个 must_change repo 必须至少有一个 work item。",
                "缺少 must_change repo: " + ", ".join(missing_must_change),
                "回到 Planner draft 补齐对应 repo 的 implementation work item。",
            )
        )

    extra_repos = sorted(work_item_repos - in_scope_repos)
    if extra_repos:
        issues.append(
            _issue(
                "blocking",
                "scope_tier_rewritten",
                "plan-work-items.json",
                "Plan 不得新增 Design artifacts 之外的 repo。",
                "出现 Design 未认可的 repo: " + ", ".join(extra_repos),
                "删除越界 repo 的 work item，或回到 Design 修订 repo binding。",
            )
        )

    for item in work_items:
        scope_tier = scope_by_repo.get(item.repo_id, "")
        if scope_tier == "validate_only" and item.task_type == "implementation":
            issues.append(
                _issue(
                    "blocking",
                    "scope_tier_rewritten",
                    item.id,
                    "validate_only repo 只能生成 validation / coordination 类任务。",
                    f"{item.id} 把 validate_only repo {item.repo_id} 生成为 implementation。",
                    "将任务降级为 validation，或回到 Design 修订 scope_tier。",
                )
            )
        if not item.specific_steps:
            issues.append(
                _issue(
                    "blocking",
                    "code_input_missing",
                    item.id,
                    "每个 work item 必须有可执行 specific_steps。",
                    f"{item.id} 缺少 specific_steps。",
                    "补充 2-5 条面向文件或模块的执行步骤。",
                )
            )
        if not item.inputs or not item.outputs or not item.done_definition:
            issues.append(
                _issue(
                    "blocking",
                    "code_input_missing",
                    item.id,
                    "每个 work item 必须有 inputs、outputs 和 done_definition。",
                    f"{item.id} 缺少 Code 可消费字段。",
                    "补齐 inputs、outputs 和 done_definition。",
                )
            )
        if len(item.change_scope) > 8 or len(item.specific_steps) > 6:
            issues.append(
                _issue(
                    "warning",
                    "work_item_too_broad",
                    item.id,
                    "work item 应保持小而可执行。",
                    f"{item.id} 的 change_scope 或 specific_steps 过多。",
                    "考虑拆分为更小的 work item。",
                )
            )
        if _validation_is_too_vague(item.verification_steps):
            issues.append(
                _issue(
                    "warning",
                    "validation_too_vague",
                    item.id,
                    "每个 work item 应至少有一条具体到链路、模块或验收点的验证说明。",
                    f"{item.id} 的验证说明偏泛。",
                    "补充与 Design critical flows 或 refined acceptance criteria 对齐的验证项。",
                )
            )

    graph_nodes = set(graph.nodes)
    item_ids = {item.id for item in work_items}
    if graph_nodes != item_ids:
        issues.append(
            _issue(
                "blocking",
                "dependency_cycle_or_gap",
                "plan-execution-graph.json",
                "execution graph 必须完整覆盖 work items。",
                f"graph nodes={sorted(graph_nodes)} work_items={sorted(item_ids)}",
                "重建 execution graph，确保节点与 work item 一一对应。",
            )
        )
    if len(graph.execution_order) != len(work_items):
        issues.append(
            _issue(
                "blocking",
                "dependency_cycle_or_gap",
                "plan-execution-graph.json",
                "execution_order 必须覆盖全部 work items。",
                "execution_order 数量与 work items 不一致。",
                "修复依赖图，避免循环或漏节点。",
            )
        )

    validation_task_ids = {
        str(item.get("task_id") or "")
        for item in _dict_list(validation_payload.get("task_validations"))
    }
    missing_validations = sorted(item_ids - validation_task_ids)
    if missing_validations:
        issues.append(
            _issue(
                "blocking",
                "validation_too_vague",
                "plan-validation.json",
                "validation contract 必须覆盖全部 work items。",
                "缺少 task validation: " + ", ".join(missing_validations),
                "为缺失任务补齐 task_validations。",
            )
        )

    normalized = normalize_plan_review_payload({"issues": issues})
    normalized["source"] = "local"
    normalized["degraded"] = False
    return normalized


def build_plan_decision_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    review_payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    issues = _issues(review_payload)
    blocking = [item for item in issues if str(item.get("severity") or "") == "blocking"]
    issue_resolutions = [_resolution_for_issue(item) for item in blocking]
    finalized = not blocking
    debate_payload = {
        "rounds": [
            {"role": "planner", "artifact": "plan-draft-work-items.json"},
            {"role": "scheduler", "artifact": "plan-execution-graph.json"},
            {"role": "validation_designer", "artifact": "plan-validation.json"},
            {"role": "skeptic", "artifact": "plan-review.json", "blocking_count": len(blocking)},
        ],
        "revision": {
            "applied": bool(blocking),
            "summary": (
                "Plan Skeptic 未发现 blocking issue，无需修订。"
                if not blocking
                else "Plan Skeptic 发现 blocking issue；当前 Phase 3 仅记录有界修订决议，未自动改写 Design artifacts。"
            ),
            "issue_resolutions": issue_resolutions,
        },
        "task_id": prepared.task_id,
    }
    decision_payload = {
        "task_id": prepared.task_id,
        "finalized": finalized,
        "review_blocking_count": len(blocking),
        "review_warning_count": len([item for item in issues if str(item.get("severity") or "") == "warning"]),
        "issue_resolutions": issue_resolutions,
        "work_items": [item.to_payload() for item in work_items],
        "execution_graph": graph.to_payload(),
        "validation": validation_payload,
        "unresolved_questions": [
            str(item.get("suggested_action") or item.get("actual") or "")
            for item in blocking
            if str(item.get("suggested_action") or item.get("actual") or "").strip()
        ],
        "artifacts": [
            "plan-work-items.json",
            "plan-execution-graph.json",
            "plan-validation.json",
        ],
    }
    return debate_payload, decision_payload


def normalize_plan_review_payload(payload: dict[str, object]) -> dict[str, object]:
    issues = [_normalize_issue(item) for item in _dict_list(payload.get("issues"))]
    blocking = [item for item in issues if item["severity"] == "blocking"]
    return {
        "ok": not blocking and bool(payload.get("ok", not issues or not blocking)),
        "issues": issues,
        "source": str(payload.get("source") or "native"),
        "degraded": bool(payload.get("degraded", False)),
        "degraded_reason": str(payload.get("degraded_reason") or ""),
        "fallback_stage": str(payload.get("fallback_stage") or ""),
    }


def normalize_plan_revision_payload(
    payload: dict[str, object],
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    review_payload: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    fallback_debate, fallback_decision = build_plan_decision_payload(
        prepared,
        work_items,
        graph,
        validation_payload,
        review_payload,
    )
    debate_raw = payload.get("debate")
    debate_payload = dict(debate_raw) if isinstance(debate_raw, dict) else {}
    revision_raw = debate_payload.get("revision")
    revision_payload = dict(revision_raw) if isinstance(revision_raw, dict) else {}
    raw_resolutions = _dict_list(revision_payload.get("issue_resolutions"))
    if not raw_resolutions:
        raw_resolutions = _dict_list(payload.get("issue_resolutions"))
    if not raw_resolutions:
        decision_raw = payload.get("decision")
        if isinstance(decision_raw, dict):
            raw_resolutions = _dict_list(decision_raw.get("issue_resolutions"))
    issue_resolutions = _normalize_issue_resolutions(raw_resolutions, _issues(review_payload))

    blocking = [item for item in _issues(review_payload) if str(item.get("severity") or "") == "blocking"]
    unresolved_blocking = _unresolved_blocking_issues(blocking, issue_resolutions)
    decision_raw = payload.get("decision")
    decision_input = decision_raw if isinstance(decision_raw, dict) else {}
    finalized = not unresolved_blocking and bool(decision_input.get("finalized", True))

    revision_payload.update(
        {
            "applied": bool(blocking),
            "source": "native",
            "summary": str(revision_payload.get("summary") or fallback_debate.get("revision", {}).get("summary") or "").strip(),
            "issue_resolutions": issue_resolutions,
        }
    )
    debate_payload.update(
        {
            "rounds": [
                {"role": "planner", "artifact": "plan-draft-work-items.json"},
                {"role": "scheduler", "artifact": "plan-execution-graph.json"},
                {"role": "validation_designer", "artifact": "plan-validation.json"},
                {"role": "skeptic", "artifact": "plan-review.json", "blocking_count": len(blocking)},
                {"role": "revision", "artifact": "plan-decision.json", "unresolved_blocking_count": len(unresolved_blocking)},
            ],
            "revision": revision_payload,
            "task_id": prepared.task_id,
        }
    )

    decision_payload = dict(fallback_decision)
    decision_payload.update(
        {
            "finalized": finalized,
            "review_blocking_count": len(blocking),
            "review_warning_count": len([item for item in _issues(review_payload) if str(item.get("severity") or "") == "warning"]),
            "issue_resolutions": issue_resolutions,
            "unresolved_questions": [
                str(item.get("suggested_action") or item.get("actual") or "")
                for item in unresolved_blocking
                if str(item.get("suggested_action") or item.get("actual") or "").strip()
            ],
            "revision_source": "native",
        }
    )
    return debate_payload, decision_payload


def _build_native_plan_review_payload(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    settings: Settings,
    on_log,
) -> dict[str, object]:
    return run_plan_agent_json_with_new_session(
        prepared,
        settings,
        build_plan_review_template_json(),
        lambda template_path: build_plan_skeptic_prompt(
            title=prepared.title,
            design_markdown=prepared.design_markdown,
            refined_markdown=prepared.refined_markdown,
            skills_brief_markdown=prepared.skills_brief_markdown,
            repo_binding_payload=prepared.design_repo_binding_payload,
            work_items_payload={"work_items": [item.to_payload() for item in work_items]},
            execution_graph_payload=graph.to_payload(),
            validation_payload=validation_payload,
            template_path=template_path,
        ),
        ".plan-skeptic-",
        role="plan_skeptic",
        stage="review",
        on_log=on_log,
    )


def _build_native_plan_review_and_revision_payloads(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    settings: Settings,
    on_log,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    session = new_plan_agent_session(prepared, settings, role="plan_skeptic", on_log=on_log, bootstrap=False)
    try:
        review_payload = run_plan_agent_json_in_session(
            prepared,
            build_plan_review_template_json(),
            lambda template_path: build_plan_skeptic_prompt(
                title=prepared.title,
                design_markdown=prepared.design_markdown,
                refined_markdown=prepared.refined_markdown,
                skills_brief_markdown=prepared.skills_brief_markdown,
                repo_binding_payload=prepared.design_repo_binding_payload,
                work_items_payload={"work_items": [item.to_payload() for item in work_items]},
                execution_graph_payload=graph.to_payload(),
                validation_payload=validation_payload,
                template_path=template_path,
            ),
            ".plan-skeptic-",
            session,
            stage="review",
            inline_bootstrap=True,
            on_log=on_log,
        )
        review_payload = normalize_plan_review_payload(review_payload)
        on_log("plan_skeptic_mode: native")

        revision_payload = run_plan_agent_json_in_session(
            prepared,
            build_plan_revision_template_json(),
            lambda template_path: build_plan_revision_prompt(
                title=prepared.title,
                review_payload=review_payload,
                work_items_payload={"work_items": [item.to_payload() for item in work_items]},
                execution_graph_payload=graph.to_payload(),
                validation_payload=validation_payload,
                template_path=template_path,
            ),
            ".plan-revision-",
            session,
            stage="revision",
            inline_bootstrap=False,
            on_log=on_log,
        )
        on_log("plan_revision_mode: native")
        debate_payload, decision_payload = normalize_plan_revision_payload(
            revision_payload,
            prepared,
            work_items,
            graph,
            validation_payload,
            review_payload,
        )
        return review_payload, debate_payload, decision_payload
    finally:
        close_plan_agent_session(session, on_log)


def _issue(
    severity: str,
    failure_type: str,
    target: str,
    expected: str,
    actual: str,
    suggested_action: str,
) -> dict[str, object]:
    return {
        "severity": severity,
        "failure_type": failure_type,
        "target": target,
        "expected": expected,
        "actual": actual,
        "suggested_action": suggested_action,
    }


def _normalize_issue(item: dict[str, object]) -> dict[str, object]:
    severity = str(item.get("severity") or "warning").strip()
    if severity not in _SEVERITIES:
        severity = "warning"
    return {
        "severity": severity,
        "failure_type": str(item.get("failure_type") or "plan_review_issue").strip(),
        "target": str(item.get("target") or "").strip(),
        "expected": str(item.get("expected") or "").strip(),
        "actual": str(item.get("actual") or "").strip(),
        "suggested_action": str(item.get("suggested_action") or "").strip(),
    }


def _resolution_for_issue(item: dict[str, object]) -> dict[str, object]:
    return {
        "failure_type": item.get("failure_type"),
        "target": item.get("target"),
        "resolution": "needs_design_revision" if item.get("failure_type") == "needs_design_revision" else "needs_human",
        "reason": "Phase 3 只记录结构化 review 和 revision 决议；需要后续 Planner 或 Design rerun 处理。",
        "decision_change": "none",
    }


def _issues(payload: dict[str, object]) -> list[dict[str, object]]:
    return [_normalize_issue(item) for item in _dict_list(payload.get("issues"))]


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_issue_resolutions(
    raw_resolutions: list[dict[str, object]],
    issues: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key = {
        _issue_key(item): item
        for item in raw_resolutions
        if str(item.get("failure_type") or "").strip() or str(item.get("target") or "").strip()
    }
    result: list[dict[str, object]] = []
    for issue in issues:
        raw = by_key.get(_issue_key(issue), {})
        resolution = str(raw.get("resolution") or "").strip()
        if resolution not in {"resolved", "rejected", "needs_human", "needs_design_revision", "deferred"}:
            resolution = (
                "needs_design_revision"
                if str(issue.get("failure_type") or "") in {"needs_design_revision", "design_artifact_conflict"}
                else "needs_human"
                if str(issue.get("severity") or "") == "blocking"
                else "deferred"
            )
        result.append(
            {
                "failure_type": issue.get("failure_type"),
                "target": issue.get("target"),
                "resolution": resolution,
                "reason": str(raw.get("reason") or issue.get("suggested_action") or issue.get("actual") or "").strip(),
                "decision_change": str(raw.get("decision_change") or "none").strip(),
            }
        )
    return result


def _unresolved_blocking_issues(
    blocking_issues: list[dict[str, object]],
    issue_resolutions: list[dict[str, object]],
) -> list[dict[str, object]]:
    resolved_keys = {
        _issue_key(item)
        for item in issue_resolutions
        if str(item.get("resolution") or "") in {"resolved", "rejected"}
    }
    return [item for item in blocking_issues if _issue_key(item) not in resolved_keys]


def _issue_key(item: dict[str, object]) -> tuple[str, str]:
    return (str(item.get("failure_type") or "").strip(), str(item.get("target") or "").strip())


def _in_scope_binding_items(prepared: PlanPreparedInput) -> list[dict[str, object]]:
    raw = prepared.design_repo_binding_payload.get("repo_bindings")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"]


def _validation_is_too_vague(verification_steps: list[str]) -> bool:
    if not verification_steps:
        return True
    concrete = [step for step in verification_steps if step.strip() and step.strip() not in _GENERIC_VALIDATION_TEXTS]
    return not concrete
