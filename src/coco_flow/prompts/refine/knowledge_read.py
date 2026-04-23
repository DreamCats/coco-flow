from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt
from coco_flow.prompts.sections import render_yaml_cards

from .shared import REFINE_OUTPUT_CONTRACT, build_intent_json_section


def build_refine_knowledge_read_template_markdown() -> str:
    return (
        "# Refine Skills Read\n\n"
        "## 术语解释\n"
        "- 待补充\n\n"
        "## 稳定规则\n"
        "- 待补充\n\n"
        "## 冲突提醒\n"
        "- 待补充\n\n"
        "## 边界提示\n"
        "- 待补充\n"
    )


def build_refine_knowledge_read_agent_prompt(
    *,
    intent_payload: dict[str, object],
    knowledge_documents: list[dict[str, str]],
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的 skills 深读。",
        goal="读取已选 skills 材料的本地文件，编辑指定 Markdown 模板文件，提取术语解释、稳定规则、冲突提醒和边界提示，供后续 refined 文档生成使用。",
        requirements=[
            "必须逐个读取给出的本地文件，不要只看卡片信息。",
            "只提取对当前需求有帮助的信息，不要重写整篇文档。",
            "历史 skills 材料只能作为辅助判断，不能覆盖当前 PRD。",
            "如发现材料与需求明显冲突，应显式标出冲突点。",
            "必须直接编辑指定模板文件，不要只在回复里输出 Markdown。",
            "如果当前没有明显冲突，也要写明“当前未识别到明确冲突”。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT,
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 Markdown 文件，替换所有“待补充”占位内容。",
            ),
            build_intent_json_section(intent_payload),
            PromptSection(
                title="已选 Skills 文件",
                body="```yaml\n" + render_yaml_cards(knowledge_documents) + "\n```",
            ),
        ],
        closing="输出应尽量收敛为：术语解释、稳定规则、冲突提醒、边界提示 四部分。",
    )
    return render_prompt(document)
