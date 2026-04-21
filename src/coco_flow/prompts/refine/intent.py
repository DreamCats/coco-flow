from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section


def build_refine_intent_template_json() -> str:
    return (
        '{\n'
        '  "goal": "__FILL__",\n'
        '  "change_points": ["__FILL__"],\n'
        '  "acceptance_criteria": ["__FILL__"],\n'
        '  "terms": ["__FILL__"],\n'
        '  "risks_seed": ["__FILL__"],\n'
        '  "discussion_seed": ["__FILL__"],\n'
        '  "boundary_seed": ["__FILL__"]\n'
        '}\n'
    )


def build_refine_intent_agent_prompt(*, title: str, source_markdown: str, supplement: str, template_path: str) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的意图提炼。",
        goal="根据 Input 阶段产物，直接编辑指定 JSON 文件，提炼核心诉求、改动点、验收标准、风险种子、待确认项种子与边界种子。",
        requirements=[
            "只能基于当前输入材料，不要引入外部事实。",
            "核心诉求必须聚焦，不要被冗长背景干扰。",
            "不明确的信息应进入 discussion_seed，不要擅自定结论。",
            "acceptance_criteria 只写可测试、可检查的结果，不写实现方案。",
            "必须直接编辑指定文件，不要只在回复里输出 JSON。",
            "terms 不要混入 PRD、背景、需求名称 这类无效词。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT
        + "\n\n"
        + "JSON 格式：\n"
        + '{\n  "goal": "...",\n  "change_points": ["..."],\n  "acceptance_criteria": ["..."],\n  "terms": ["..."],\n  "risks_seed": ["..."],\n  "discussion_seed": ["..."],\n  "boundary_seed": ["..."]\n}',
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。",
            ),
            build_input_bundle_section(
                title=title,
                source_markdown=source_markdown,
                supplement=supplement,
            )
        ],
    )
    return render_prompt(document)
