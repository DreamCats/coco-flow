from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.sections import render_yaml_cards

from .shared import REFINE_OUTPUT_CONTRACT, build_intent_json_section


def build_refine_knowledge_read_prompt(*, intent_payload: dict[str, object], knowledge_documents: list[dict[str, str]]) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的知识深读。",
        goal="读取已选知识文档的本地文件，提取术语解释、稳定规则、冲突提醒和边界提示，供后续 refined 文档生成使用。",
        requirements=[
            "必须逐个读取给出的本地文件，不要只看卡片信息。",
            "只提取对当前需求有帮助的信息，不要重写整篇知识文档。",
            "历史知识只能作为辅助判断，不能覆盖当前 PRD。",
            "如发现知识与需求明显冲突，应显式标出冲突点。",
            "输出使用 Markdown，不要输出多余前言。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT,
        sections=[
            build_intent_json_section(intent_payload),
            PromptSection(
                title="已选知识文件",
                body="```yaml\n" + render_yaml_cards(knowledge_documents) + "\n```",
            ),
        ],
        closing="输出应尽量收敛为：术语解释、稳定规则、冲突提醒、边界提示 四部分。",
    )
    return render_prompt(document)
