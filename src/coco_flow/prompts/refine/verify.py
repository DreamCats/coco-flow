from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section


def build_refine_verify_prompt(*, title: str, source_markdown: str, supplement: str, refined_markdown: str) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的校验与批注。",
        goal="检查生成结果是否真正抓住核心诉求，并覆盖风险、讨论点和边界。",
        requirements=[
            "只输出 JSON 对象，不要输出其它文字。",
            "重点检查是否遗漏风险提示、讨论点、边界与非目标。",
            "重点检查是否被知识或背景信息带偏，偏离当前 PRD。",
            "如果信息缺失但没有进入讨论点，应明确指出。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT
        + "\n\n"
        + "JSON 格式：\n"
        + '{\n  "ok": true,\n  "issues": ["..."],\n  "missing_sections": ["..."],\n  "reason": "..."\n}',
        sections=[
            build_input_bundle_section(title=title, source_markdown=source_markdown, supplement=supplement),
            PromptSection(title="待校验结果", body=refined_markdown.strip()),
        ],
    )
    return render_prompt(document)
