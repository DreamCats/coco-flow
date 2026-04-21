from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_execution_graph_section,
    build_plan_repo_binding_section,
    build_plan_validation_section,
    build_plan_work_items_section,
)


def build_plan_verify_template_json() -> str:
    return (
        '{\n'
        '  "ok": false,\n'
        '  "issues": ["__FILL__"],\n'
        '  "reason": "__FILL__"\n'
        '}\n'
    )


def build_plan_verify_agent_prompt(
    *,
    title: str,
    plan_markdown: str,
    design_markdown: str,
    repo_binding_payload: dict[str, object],
    work_items_payload: dict[str, object],
    execution_graph_payload: dict[str, object],
    validation_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Plan V2 的校验。",
        goal="检查 plan.md 是否与结构化 Plan artifacts 和上游 Design 结论一致，并直接编辑指定 JSON 模板文件写入结果。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "重点检查 must_change repo 是否都有对应任务，execution graph 是否存在明显缺边或冲突，validation 是否覆盖关键链路。",
            "重点检查 plan.md 是否包含任务清单、执行顺序、验证策略、风险与阻塞项四个章节，且任务段落体现 specific_steps。",
            "如果校验通过，ok=true，issues 使用空数组。",
            "不要因为 plan.md 写得更顺而反向覆盖结构化 artifact；发现矛盾时应报 issue。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=PLAN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。",
            ),
            PromptSection(title="任务标题", body=f"- title: {title}"),
            PromptSection(title="Design Markdown", body=design_markdown.strip()),
            PromptSection(title="Plan Markdown", body=plan_markdown.strip()),
            build_plan_repo_binding_section(repo_binding_payload),
            build_plan_work_items_section(work_items_payload),
            build_plan_execution_graph_section(execution_graph_payload),
            build_plan_validation_section(validation_payload),
        ],
    )
    return render_prompt(document)
