from __future__ import annotations

import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.plan import build_plan_generate_agent_prompt, build_plan_template_markdown

from .models import EXECUTOR_NATIVE, PlanExecutionGraph, PlanPreparedInput, PlanWorkItem


def generate_plan_markdown(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    settings: Settings,
    on_log,
) -> tuple[str, str]:
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            content = generate_native_plan_markdown(prepared, work_items, graph, validation_payload, settings)
            on_log("plan_generate_mode: native")
            return content, "native"
        except Exception as error:
            on_log(f"plan_generate_fallback: {error}")
    on_log("plan_generate_mode: local")
    return generate_local_plan_markdown(prepared, work_items, graph, validation_payload), "local"


def generate_local_plan_markdown(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
) -> str:
    lines = [
        "# Plan",
        "",
        f"- task_id: {prepared.task_id}",
        f"- title: {prepared.title}",
        "",
        "## 实施策略",
        "",
        f"- 基于 Design 已确认的 repo binding 进行执行拆分，不再重新 adjudicate repo scope。",
        f"- 当前共拆出 {len(work_items)} 个 work items。",
        "",
        "## 任务拆分",
        "",
    ]
    for item in work_items:
        lines.extend(
            [
                f"### {item.id} {item.title}",
                f"- repo_id: {item.repo_id}",
                f"- task_type: {item.task_type}",
                f"- goal: {item.goal}",
            ]
        )
        if item.depends_on:
            lines.append(f"- depends_on: {', '.join(item.depends_on)}")
        if item.change_scope:
            lines.append("- change_scope:")
            lines.extend(f"  - {entry}" for entry in item.change_scope[:6])
        if item.done_definition:
            lines.append("- done_definition:")
            lines.extend(f"  - {entry}" for entry in item.done_definition[:4])
        if item.verification_steps:
            lines.append("- verification:")
            lines.extend(f"  - {entry}" for entry in item.verification_steps[:4])
        lines.append("")
    lines.extend(["## 执行顺序", ""])
    lines.append("- " + " -> ".join(graph.execution_order) if graph.execution_order else "- 当前未形成稳定执行顺序。")
    lines.extend(["", "## 并发与协同", ""])
    if graph.parallel_groups:
        for index, group in enumerate(graph.parallel_groups, start=1):
            lines.append(f"- parallel_group_{index}: {', '.join(group)}")
    else:
        lines.append("- 当前未识别到明确并发组。")
    if graph.coordination_points:
        lines.append("- coordination_points:")
        lines.extend(f"  - {item}" for item in graph.coordination_points[:6])
    lines.extend(["", "## 验证计划", ""])
    global_focus = validation_payload.get("global_validation_focus")
    if isinstance(global_focus, list) and global_focus:
        lines.extend(f"- {str(item)}" for item in global_focus[:6] if str(item).strip())
    else:
        lines.append("- 优先覆盖关键链路和最小范围验证。")
    lines.extend(["", "## 阻塞项与风险", ""])
    risks = [risk for item in work_items for risk in item.risk_notes]
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
    lines.extend(["", "## 交付边界", ""])
    for item in prepared.refined_sections.non_goals[:4]:
        lines.append(f"- 非目标：{item}")
    if not prepared.refined_sections.non_goals:
        lines.append("- 保持最小执行范围，不扩大到 Design 未纳入的系统或 repo。")
    return "\n".join(lines).rstrip() + "\n"


def generate_native_plan_markdown(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    graph: PlanExecutionGraph,
    validation_payload: dict[str, object],
    settings: Settings,
    regeneration_issues: list[str] | None = None,
    previous_plan_markdown: str = "",
) -> str:
    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    template_path = _write_template(prepared.task_dir)
    try:
        client.run_agent(
            build_plan_generate_agent_prompt(
                title=prepared.title,
                design_markdown=prepared.design_markdown,
                refined_markdown=prepared.refined_markdown,
                knowledge_brief_markdown=prepared.knowledge_brief_markdown,
                work_items_payload={"work_items": [item.to_payload() for item in work_items]},
                execution_graph_payload=graph.to_payload(),
                validation_payload=validation_payload,
                template_path=str(template_path),
                regeneration_issues=regeneration_issues,
                previous_plan_markdown=previous_plan_markdown,
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()
    content = raw.strip()
    if not content or "待补充" in content or not content.startswith("# Plan"):
        raise ValueError("plan_template_unfilled")
    return content.rstrip() + "\n"


def _write_template(task_dir: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=task_dir,
        prefix=".plan-template-",
        suffix=".md",
        delete=False,
    ) as handle:
        handle.write(build_plan_template_markdown())
        handle.flush()
        return Path(handle.name)
