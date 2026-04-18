from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_input_section,
    build_plan_repo_binding_section,
    build_plan_work_items_section,
)


def build_plan_execution_graph_template_json() -> str:
    return (
        '{\n'
        '  "nodes": [\n'
        '    {"task_id": "W1", "repo_id": "__FILL__", "title": "__FILL__"}\n'
        '  ],\n'
        '  "edges": [\n'
        '    {\n'
        '      "from": "W1",\n'
        '      "to": "W2",\n'
        '      "type": "__FILL__",\n'
        '      "reason": "__FILL__"\n'
        '    }\n'
        '  ],\n'
        '  "execution_order": ["W1", "W2"],\n'
        '  "parallel_groups": [\n'
        '    ["W3", "W4"]\n'
        '  ],\n'
        '  "critical_path": ["W1", "W2"],\n'
        '  "coordination_points": [\n'
        '    {\n'
        '      "id": "C1",\n'
        '      "title": "__FILL__",\n'
        '      "tasks": ["W1", "W2"],\n'
        '      "reason": "__FILL__"\n'
        '    }\n'
        '  ]\n'
        '}\n'
    )


def build_plan_execution_graph_agent_prompt(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    repo_binding_payload: dict[str, object],
    work_items_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Plan V2 的执行图构建。",
        goal="基于已归一化的 work items 和 Design 结论，直接编辑指定 JSON 模板文件，产出 plan-execution-graph.json。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "只使用 hard_dependency / soft_dependency / parallel / coordination 作为 edge type。",
            "不要把 repo exploration 顺序、文档章节顺序或叙述顺序误写成任务依赖。",
            "execution_order、critical_path、parallel_groups 只能引用已经存在的 task id。",
            "只有在任务之间确有独立推进空间时才写 parallel_groups；共享同一落地前置条件的任务不要强行并发。",
            "如果存在跨 repo 联调、协议对齐或共同发布窗口，优先用 coordination_points 表达，而不是伪造 hard dependency。",
            "不要重新做 repo binding adjudication，也不要新增 Design 没有认可的 repo。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=PLAN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。",
            ),
            build_plan_input_section(
                title=title,
                design_markdown=design_markdown,
                refined_markdown=refined_markdown,
                knowledge_brief_markdown=knowledge_brief_markdown,
            ),
            build_plan_repo_binding_section(repo_binding_payload),
            build_plan_work_items_section(work_items_payload),
        ],
    )
    return render_prompt(document)
