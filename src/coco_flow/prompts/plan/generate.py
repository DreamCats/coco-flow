from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_execution_graph_section,
    build_plan_input_section,
    build_plan_validation_section,
    build_plan_work_items_section,
)


def build_plan_template_markdown() -> str:
    return (
        "# Plan\n\n"
        "## 实施策略\n"
        "- 待补充\n\n"
        "## 任务拆分\n"
        "- 待补充\n\n"
        "## 执行顺序\n"
        "- 待补充\n\n"
        "## 并发与协同\n"
        "- 待补充\n\n"
        "## 验证计划\n"
        "- 待补充\n\n"
        "## 阻塞项与风险\n"
        "- 待补充\n\n"
        "## 交付边界\n"
        "- 待补充\n"
    )


def build_plan_generate_agent_prompt(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    work_items_payload: dict[str, object],
    execution_graph_payload: dict[str, object],
    validation_payload: dict[str, object],
    template_path: str,
    regeneration_issues: list[str] | None = None,
    previous_plan_markdown: str = "",
) -> str:
    regeneration_items = [str(item).strip() for item in (regeneration_issues or []) if str(item).strip()]
    requirements = [
        "必须直接编辑指定模板文件，不要只在回复里输出 Markdown。",
        "保留模板中的一级标题和章节顺序，不要擅自删改章节名。",
        "plan.md 必须是结构化 artifacts 的可读派生结果，不能反向发明新的 repo、任务、依赖或验证方案。",
        "“任务拆分”只展开 work items 中已有任务，不要把 supporting 背景写成新的主任务。",
        "“执行顺序”和“并发与协同”必须与 execution graph 保持一致。",
        "“验证计划”必须与 validation contract 保持一致，优先写最小验证链路。",
        "内容要像人写的执行方案，但不能偏离结构化结果。",
    ]
    if regeneration_items:
        requirements.append("这是修订模式：必须优先修正“需要修正的问题”中的每一项，再做其他润色。")
    requirements.append("完成后只需简短回复已完成。")
    document = PromptDocument(
        intro="你在做 coco-flow Plan V2 的文档生成。",
        goal="基于结构化的 Plan artifacts，直接编辑指定 Markdown 模板文件，产出最终 plan.md。",
        requirements=requirements,
        output_contract=PLAN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 只修改这个 Markdown 文件。"),
            *(
                [PromptSection(title="需要修正的问题", body="\n".join(f"- {item}" for item in regeneration_items))]
                if regeneration_items else []
            ),
            *(
                [PromptSection(title="上一版 Plan 草稿", body=previous_plan_markdown.strip())]
                if previous_plan_markdown.strip() else []
            ),
            build_plan_input_section(
                title=title,
                design_markdown=design_markdown,
                refined_markdown=refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
            ),
            build_plan_work_items_section(work_items_payload),
            build_plan_execution_graph_section(execution_graph_payload),
            build_plan_validation_section(validation_payload),
        ],
    )
    return render_prompt(document)
