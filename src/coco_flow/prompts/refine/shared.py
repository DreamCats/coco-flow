from __future__ import annotations

from coco_flow.prompts.core import PromptSection
from coco_flow.prompts.sections import render_bullets, render_json_block, render_yaml_cards


REFINE_OUTPUT_CONTRACT = render_bullets(
    [
        "输出使用中文 Markdown。",
        "不得引入代码实现方案、repo 细节或外部事实。",
        "不得把知识文档中的历史信息伪装成当前 PRD 已确认事实。",
        "信息不明确时，必须落入“待确认项”，不能自行脑补结论。",
    ]
)


def build_input_bundle_section(*, title: str, source_markdown: str, supplement: str) -> PromptSection:
    supplement_body = supplement.strip() or "无"
    body = "\n\n".join(
        [
            f"- 标题：{title}",
            "### PRD 原文\n\n" + source_markdown.strip(),
            "### 补充说明\n\n" + supplement_body,
        ]
    )
    return PromptSection(title="输入材料", body=body)


def build_intent_json_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Refine Intent", body=render_json_block(payload))


def build_skill_cards_section(cards: list[dict[str, object]]) -> PromptSection:
    return PromptSection(title="候选 Skills 卡片", body="```yaml\n" + render_yaml_cards(cards) + "\n```")


def build_skills_read_section(markdown: str) -> PromptSection:
    return PromptSection(title="Skills 深读结果", body=markdown.strip() or "- 当前无 skills 深读结果。")
