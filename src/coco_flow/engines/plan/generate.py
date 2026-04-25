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


def generate_doc_only_plan_markdown(
    prepared: PlanPreparedInput,
    settings: Settings,
    on_log,
) -> tuple[str, str]:
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            raw = run_plan_agent_markdown_with_new_session(
                prepared,
                settings,
                build_plan_template_markdown(),
                lambda template_path: _build_doc_only_plan_prompt(prepared, template_path),
                ".plan-template-",
                role="plan_writer",
                stage="write_doc_only",
                on_log=on_log,
            )
            on_log("plan_writer_mode: native_doc_only")
            return _normalize_native_plan_markdown(raw), "native"
        except Exception as error:
            on_log(f"plan_writer_fallback: {error}")
    on_log("plan_writer_mode: local_doc_only")
    return generate_local_doc_only_plan_markdown(prepared), "local"


def generate_local_doc_only_plan_markdown(prepared: PlanPreparedInput) -> str:
    repos = [scope.repo_id for scope in prepared.repo_scopes if scope.repo_id]
    change_scope = prepared.refined_sections.change_scope or [prepared.title]
    acceptance = prepared.refined_sections.acceptance_criteria or ["完成与 Design 文档一致的最小验证。"]
    non_goals = prepared.refined_sections.non_goals
    lines = [
        "# Plan",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        "",
        "## 任务清单",
        "",
    ]
    for index, repo_id in enumerate(repos or ["未绑定仓库"], start=1):
        lines.extend(
            [
                f"### W{index} [{repo_id}] 执行 Design 方案",
                f"- 目标：在 {repo_id} 按 design.md 和 prd-refined.md 完成本次需求范围内的改动。",
                "- 输入：prd-refined.md、design.md、业务 Skills/SOP。",
                "- 具体做什么：",
            ]
        )
        lines.extend(f"  - {item}" for item in change_scope[:5])
        lines.extend(
            [
                "- 完成标准：",
                f"  - {repo_id} 的改动不超出 Design 文档确认范围。",
                "  - 关键链路完成最小验证。",
                "",
            ]
        )
    lines.extend(["## 执行顺序", ""])
    if len(repos) > 1:
        lines.append("- 按 design.md 中描述的仓库依赖和发布顺序执行；未声明硬依赖的仓库可并行推进。")
    else:
        lines.append("- 单仓执行，无额外跨仓排序要求。")
    lines.extend(["", "## 验证策略", ""])
    lines.extend(f"- {item}" for item in acceptance[:6])
    if non_goals:
        lines.append("- 回归边界：")
        lines.extend(f"  - 不引入非目标：{item}" for item in non_goals[:4])
    lines.extend(["", "## 风险与阻塞项", ""])
    lines.append("- 如果执行时发现 design.md 与真实代码职责不一致，先回到 Design 文档修正后再继续。")
    return "\n".join(lines).rstrip() + "\n"


def _build_doc_only_plan_prompt(prepared: PlanPreparedInput, template_path: str) -> str:
    skills = prepared.skills_brief_markdown.strip() or "当前没有额外 Skills/SOP 摘要。"
    return (
        "你在做 coco-flow Plan 阶段。当前第一版采用文档流，不使用结构化 Plan schema。\n\n"
        f"请直接编辑模板文件：{template_path}\n"
        "保留模板的一级标题与章节顺序，输出可交给研发执行的 plan.md。\n"
        "只允许依据 prd-refined.md、design.md、绑定仓库与 Skills/SOP；不要发明新仓库、新需求或新业务规则。\n\n"
        f"## 任务标题\n{prepared.title}\n\n"
        f"## 绑定仓库\n{', '.join(scope.repo_id for scope in prepared.repo_scopes if scope.repo_id) or '未绑定'}\n\n"
        f"## prd-refined.md\n{prepared.refined_markdown.strip()}\n\n"
        f"## design.md\n{prepared.design_markdown.strip()}\n\n"
        f"## Skills/SOP 摘要\n{skills}\n\n"
        "完成后只需简短回复已完成。"
    )


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
