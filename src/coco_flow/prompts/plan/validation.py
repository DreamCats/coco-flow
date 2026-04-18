from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_execution_graph_section,
    build_plan_input_section,
    build_plan_work_items_section,
)


def build_plan_validation_template_json() -> str:
    return (
        '{\n'
        '  "global_validation_focus": ["__FILL__"],\n'
        '  "task_validations": [\n'
        '    {\n'
        '      "task_id": "W1",\n'
        '      "repo_id": "__FILL__",\n'
        '      "checks": [\n'
        '        {\n'
        '          "kind": "__FILL__",\n'
        '          "target": "__FILL__",\n'
        '          "reason": "__FILL__"\n'
        '        }\n'
        '      ],\n'
        '      "linked_design_flows": ["__FILL__"],\n'
        '      "non_goal_regressions": ["__FILL__"]\n'
        '    }\n'
        '  ]\n'
        '}\n'
    )


def build_plan_validation_agent_prompt(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    knowledge_brief_markdown: str,
    work_items_payload: dict[str, object],
    execution_graph_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Plan V2 的验证契约生成。",
        goal="基于 work items、execution graph 和 Design 重点，直接编辑指定 JSON 模板文件，产出 plan-validation.json。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "验证契约要服务执行，不要把大量泛化测试建议堆成 checklist。",
            "checks 优先写最小可执行验证动作或最小验证命令，不要发明项目里不存在的测试框架。",
            "每个 task_id 都必须有对应 task_validations 条目；不要遗漏 critical path 上的任务。",
            "如果某任务需要跨 repo 联动验证，要在 linked_design_flows 或 non_goal_regressions 里明确写出。",
            "不要把 validation scope 扩大成整仓全量回归，除非 Design 明确要求。",
            "不得引入 Design 或 work items 中不存在的任务、仓库或关键链路。",
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
            build_plan_work_items_section(work_items_payload),
            build_plan_execution_graph_section(execution_graph_payload),
        ],
    )
    return render_prompt(document)
