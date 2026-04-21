from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section


def build_refine_verify_template_json() -> str:
    return (
        '{\n'
        '  "ok": false,\n'
        '  "issues": ["__FILL__"],\n'
        '  "missing_sections": ["__FILL__"],\n'
        '  "reason": "__FILL__"\n'
        '}\n'
    )


def build_refine_verify_agent_prompt(
    *,
    title: str,
    source_markdown: str,
    supplement: str,
    refined_markdown: str,
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的校验与批注。",
        goal="检查生成结果是否真正抓住需求边界、验收标准和待确认项，并编辑指定 JSON 文件写入校验结果。",
        requirements=[
            "重点检查是否遗漏验收标准、边界与非目标、待确认项。",
            "重点检查是否被知识或背景信息带偏，偏离当前 PRD。",
            "如果信息缺失但没有进入待确认项，应明确指出。",
            "如果“具体变更点”没有使用场景/当前行为/期望行为结构，应明确指出。",
            "必须直接编辑指定文件，不要只在回复里输出 JSON。",
            "如果检查通过，ok=true，issues/missing_sections 使用空数组。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT
        + "\n\n"
        + "JSON 格式：\n"
        + '{\n  "ok": true,\n  "issues": ["..."],\n  "missing_sections": ["..."],\n  "reason": "..."\n}',
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 直接编辑这个 JSON 文件，替换所有 __FILL__ 占位符。",
            ),
            build_input_bundle_section(title=title, source_markdown=source_markdown, supplement=supplement),
            PromptSection(title="待校验结果", body=refined_markdown.strip()),
        ],
    )
    return render_prompt(document)
