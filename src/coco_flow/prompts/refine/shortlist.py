from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_intent_json_section, build_knowledge_cards_section


def build_refine_shortlist_prompt(*, intent_payload: dict[str, object], knowledge_cards: list[dict[str, object]]) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的知识候选筛选。",
        goal="只基于候选知识卡片，选出最适合当前 refine 使用的 1 到 4 篇知识文档。",
        requirements=[
            "只基于 frontmatter 卡片判断，不要假设正文内容。",
            "优先选择对术语消歧、稳定规则补充、冲突识别有帮助的文档。",
            "如果某篇文档看起来更像实现背景，而不是 refine 辅助知识，应剔除。",
            "输出必须是 JSON 对象，不要输出其它文字。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT
        + "\n\n"
        + "JSON 格式：\n"
        + '{\n  "selected_ids": ["..."],\n  "rejected_ids": ["..."],\n  "reason": "..."\n}',
        sections=[
            build_intent_json_section(intent_payload),
            build_knowledge_cards_section(knowledge_cards),
        ],
    )
    return render_prompt(document)
