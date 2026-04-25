from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.prompts.plan import build_plan_template_markdown, build_plan_writer_agent_prompt

from .agent_io import PlanAgentSession, run_plan_agent_markdown_in_session, run_plan_agent_markdown_with_new_session
from .models import EXECUTOR_NATIVE, PlanPreparedInput


def generate_plan_markdown(
    prepared: PlanPreparedInput,
    decision_payload: dict[str, object],
    settings: Settings,
    on_log,
) -> tuple[str, str]:
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            content = generate_native_plan_markdown(prepared, decision_payload, settings, on_log=on_log)
            on_log("plan_writer_mode: native")
            return content, "native"
        except Exception as error:
            on_log(f"plan_writer_fallback: {error}")
    on_log("plan_writer_mode: local")
    return generate_local_plan_markdown(prepared, decision_payload), "local"


def generate_local_plan_markdown(
    prepared: PlanPreparedInput,
    decision_payload: dict[str, object],
) -> str:
    work_items = _dict_list(decision_payload.get("work_items"))
    graph = decision_payload.get("execution_graph")
    graph_payload = graph if isinstance(graph, dict) else {}
    validation = decision_payload.get("validation")
    validation_payload = validation if isinstance(validation, dict) else {}
    lines = [
        "# Plan",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        "",
        "## 任务清单",
        "",
    ]
    for item in work_items:
        item_id = str(item.get("id") or "")
        title = str(item.get("title") or "")
        goal = str(item.get("goal") or "")
        lines.extend(
            [
                f"### {item_id} {title}".rstrip(),
                f"- 目标：{goal}",
            ]
        )
        change_scope = _str_list(item.get("change_scope"))
        if change_scope:
            lines.append("- 改动范围：")
            lines.extend(f"  - {entry}" for entry in change_scope[:6])
        specific_steps = _str_list(item.get("specific_steps"))
        if specific_steps:
            lines.append("- 具体做什么：")
            lines.extend(f"  - {entry}" for entry in specific_steps[:5])
        done_definition = _str_list(item.get("done_definition"))
        if done_definition:
            lines.append("- 完成标准：")
            lines.extend(f"  - {entry}" for entry in done_definition[:4])
        depends_on = _str_list(item.get("depends_on"))
        if depends_on:
            lines.append(f"- 依赖：{', '.join(depends_on)}")
        else:
            lines.append("- 依赖：无前置任务约束。")
        lines.append("")
    lines.extend(["## 执行顺序", ""])
    execution_order = _str_list(graph_payload.get("execution_order"))
    lines.append("- " + " -> ".join(execution_order) if execution_order else "- 当前未形成稳定执行顺序。")
    parallel_groups = graph_payload.get("parallel_groups")
    if isinstance(parallel_groups, list):
        for index, group in enumerate(parallel_groups, start=1):
            if isinstance(group, list):
                lines.append(f"- 并行组 {index}：{', '.join(str(item) for item in group if str(item).strip())}")
    coordination_points = _str_list(graph_payload.get("coordination_points"))
    if coordination_points:
        lines.append("- 协同约束：")
        lines.extend(f"  - {item}" for item in coordination_points[:6])
    lines.extend(["", "## 验证策略", ""])
    global_focus = validation_payload.get("global_validation_focus")
    if isinstance(global_focus, list) and global_focus:
        lines.extend(f"- {str(item)}" for item in global_focus[:6] if str(item).strip())
    else:
        lines.append("- 优先覆盖关键链路和最小范围验证。")
    for item in work_items:
        item_id = str(item.get("id") or "")
        for verification in _str_list(item.get("verification_steps"))[:3]:
            lines.append(f"- {item_id}：{verification}")
    lines.extend(["", "## 风险与阻塞项", ""])
    if not bool(decision_payload.get("finalized", True)):
        lines.append("- 当前不能进入 Code，Plan review 仍存在 blocking issue。")
    risks = [risk for item in work_items for risk in _str_list(item.get("risk_notes"))]
    if risks:
        seen: set[str] = set()
        for risk in risks:
            lowered = risk.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            lines.append(f"- {risk}")
    else:
        lines.append("- 当前未沉淀出额外风险。")
    return "\n".join(lines).rstrip() + "\n"


def generate_native_plan_markdown(
    prepared: PlanPreparedInput,
    decision_payload: dict[str, object],
    settings: Settings,
    regeneration_issues: list[str] | None = None,
    previous_plan_markdown: str = "",
    on_log=None,
) -> str:
    raw = run_plan_agent_markdown_with_new_session(
        prepared,
        settings,
        build_plan_template_markdown(),
        lambda template_path: build_plan_writer_agent_prompt(
            title=prepared.title,
            decision_payload=decision_payload,
            template_path=template_path,
            regeneration_issues=regeneration_issues,
            previous_plan_markdown=previous_plan_markdown,
        ),
        ".plan-template-",
        role="plan_writer",
        stage="regenerate" if regeneration_issues else "write",
        on_log=on_log or (lambda _line: None),
    )
    return _normalize_native_plan_markdown(raw)


def generate_native_plan_markdown_in_session(
    prepared: PlanPreparedInput,
    decision_payload: dict[str, object],
    writer_session: PlanAgentSession,
    regeneration_issues: list[str] | None = None,
    previous_plan_markdown: str = "",
    on_log=None,
) -> str:
    raw = run_plan_agent_markdown_in_session(
        prepared,
        build_plan_template_markdown(),
        lambda template_path: build_plan_writer_agent_prompt(
            title=prepared.title,
            decision_payload=decision_payload,
            template_path=template_path,
            regeneration_issues=regeneration_issues,
            previous_plan_markdown=previous_plan_markdown,
        ),
        ".plan-template-",
        writer_session,
        stage="regenerate" if regeneration_issues else "write",
        inline_bootstrap=not regeneration_issues,
        on_log=on_log or (lambda _line: None),
    )
    return _normalize_native_plan_markdown(raw)


def _normalize_native_plan_markdown(raw: str) -> str:
    content = raw.strip()
    if not content or "待补充" in content or not content.startswith("# Plan"):
        raise ValueError("plan_template_unfilled")
    return content.rstrip() + "\n"


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
