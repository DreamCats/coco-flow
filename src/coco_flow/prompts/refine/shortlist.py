from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_intent_json_section, build_knowledge_cards_section


def build_refine_shortlist_template_json() -> str:
    return (
        '{\n'
        '  "selected_ids": ["__FILL__"],\n'
        '  "rejected_ids": ["__FILL__"],\n'
        '  "reason": "__FILL__"\n'
        '}\n'
    )


def build_refine_shortlist_agent_prompt(
    *,
    intent_payload: dict[str, object],
    knowledge_cards: list[dict[str, object]],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的知识候选筛选。",
        goal="只基于候选知识卡片，编辑指定 JSON 文件，选出最适合当前 refine 使用的 0 到 4 篇知识文档。",
        requirements=[
            "只基于 frontmatter 卡片判断，不要假设正文内容。",
            "优先选择对术语消歧、稳定规则补充、冲突识别有帮助的文档。",
            "如果某篇文档看起来更像实现背景，而不是 refine 辅助知识，应剔除。",
            "如果没有明显相关的知识文档，selected_ids 必须返回空数组，不要为了凑数强行选择。",
            "只有在 title、desc、domain_name 与当前需求存在明显术语/领域/目标匹配时才允许选中。",
            "selected_ids 只保留当前候选卡片里的 id。",
            "必须直接编辑指定文件，不要只在回复里输出 JSON。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT
        + "\n\n"
        + "JSON 格式：\n"
        + '{\n  "selected_ids": ["..."],\n  "rejected_ids": ["..."],\n  "reason": "..."\n}',
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。",
            ),
            build_intent_json_section(intent_payload),
            build_knowledge_cards_section(knowledge_cards),
        ],
    )
    return render_prompt(document)
