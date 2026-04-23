from __future__ import annotations

from coco_flow.prompts.core import PromptSection
from coco_flow.prompts.sections import render_json_block


DESIGN_OUTPUT_CONTRACT = "\n".join(
    [
        "- 输出使用中文。",
        "- 只基于当前 refined、repo binding、repo research 和 inherited knowledge 工作。",
        "- 不得编造不存在的仓库、模块或文件。",
        "- 章节和字段必须与模板保持一致。",
    ]
)


def build_design_input_section(*, title: str, refined_markdown: str, knowledge_brief_markdown: str) -> PromptSection:
    return PromptSection(
        title="Design 输入",
        body="\n\n".join(
            [
                f"- 标题：{title}",
                "### PRD Refined\n\n" + refined_markdown.strip(),
                "### Design Skills Brief\n\n" + (knowledge_brief_markdown.strip() or "- 当前没有 skills brief。"),
            ]
        ),
    )


def build_repo_binding_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Repo Binding", body=render_json_block(payload))


def build_design_sections_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Design Sections", body=render_json_block(payload))
