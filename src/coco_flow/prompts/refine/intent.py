from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section


def build_refine_intent_prompt(*, title: str, source_markdown: str, supplement: str) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的意图提炼。",
        goal="根据 Input 阶段产物，提炼核心诉求、改动点、风险种子、讨论点种子与边界种子。",
        requirements=[
            "只能基于当前输入材料，不要引入外部事实。",
            "核心诉求必须聚焦，不要被冗长背景干扰。",
            "不明确的信息应进入 discussion_seed，不要擅自定结论。",
            "输出必须是 JSON 对象，不要输出其它文字。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT
        + "\n\n"
        + "JSON 格式：\n"
        + '{\n  "goal": "...",\n  "change_points": ["..."],\n  "terms": ["..."],\n  "risks_seed": ["..."],\n  "discussion_seed": ["..."],\n  "boundary_seed": ["..."]\n}',
        sections=[
            build_input_bundle_section(
                title=title,
                source_markdown=source_markdown,
                supplement=supplement,
            )
        ],
    )
    return render_prompt(document)
