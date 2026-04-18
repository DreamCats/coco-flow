from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section, build_intent_json_section, build_knowledge_read_section


def build_refine_generate_prompt(
    *,
    title: str,
    source_markdown: str,
    supplement: str,
    intent_payload: dict[str, object],
    knowledge_read_markdown: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的 refined 文档生成。",
        goal="输出一份对用户友好、能支撑后续推进的 PRD Refined。",
        requirements=[
            "输出必须直接从 # PRD Refined 开始。",
            "结构必须包含：核心诉求、改动范围、风险提示、讨论点、边界与非目标。",
            "讨论点中必须显式记录待确认项和建议补充的信息。",
            "不要引入实现方案、repo 路径或代码层推断。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT,
        sections=[
            build_input_bundle_section(title=title, source_markdown=source_markdown, supplement=supplement),
            build_intent_json_section(intent_payload),
            build_knowledge_read_section(knowledge_read_markdown),
        ],
        closing="输出结构示例：\n# PRD Refined\n\n## 核心诉求\n- ...\n\n## 改动范围\n- ...\n\n## 风险提示\n- ...\n\n## 讨论点\n- [待确认] ...\n- [建议补充] ...\n\n## 边界与非目标\n- ...",
    )
    return render_prompt(document)
