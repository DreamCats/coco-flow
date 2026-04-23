from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_design_sections_section,
    build_plan_input_section,
    build_plan_repo_binding_section,
)


def build_plan_task_outline_template_json() -> str:
    return (
        '{\n'
        '  "task_units": [\n'
        '    {\n'
        '      "id": "W1",\n'
        '      "title": "__FILL__",\n'
        '      "repo_id": "__FILL__",\n'
        '      "task_type": "__FILL__",\n'
        '      "serves_change_points": [1],\n'
        '      "goal": "__FILL__",\n'
        '      "specific_steps": ["__FILL__"],\n'
        '      "scope_summary": ["__FILL__"],\n'
        '      "inputs": ["__FILL__"],\n'
        '      "outputs": ["__FILL__"],\n'
        '      "done_definition": ["__FILL__"],\n'
        '      "validation_focus": ["__FILL__"],\n'
        '      "risk_notes": ["__FILL__"]\n'
        '    }\n'
        '  ]\n'
        '}\n'
    )


def build_plan_task_outline_agent_prompt(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    skills_brief_markdown: str,
    repo_binding_payload: dict[str, object],
    design_sections_payload: dict[str, object],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Plan V2 的任务骨架生成。",
        goal="基于已经完成 adjudication 的 Design artifacts，直接编辑指定 JSON 模板文件，产出 plan-task-outline.json。",
        requirements=[
            "必须直接编辑指定 JSON 文件，不要只在回复里输出结果。",
            "Plan 只负责执行拆分，不要重新判断 repo 是否 in scope，也不要改写 scope_tier。",
            "task_type 只使用 implementation / coordination / validation / preparation。",
            "优先覆盖所有 in-scope 且 scope_tier=must_change 的 repo；validate_only repo 只有在执行上确有必要时才单独成任务。",
            "每个任务必须是可执行单元，避免把多个 repo 的主改动混成一个模糊大任务。",
            "每个任务必须补充 2-5 条 specific_steps，格式优先使用“在 {模块/文件} 中 {动作} {对象}”。",
            "不要默认写伪代码；只需要明确 goal、specific_steps、done_definition、validation_focus 和风险边界。",
            "不得引入 Design artifacts 中不存在的仓库、模块、文件或额外需求。",
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
                skills_brief_markdown=skills_brief_markdown,
            ),
            build_plan_repo_binding_section(repo_binding_payload),
            build_plan_design_sections_section(design_sections_payload),
        ],
    )
    return render_prompt(document)
