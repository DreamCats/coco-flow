from __future__ import annotations

from coco_flow.prompts.core import PromptSection
from coco_flow.prompts.sections import render_bullets, render_json_block


PLAN_OUTPUT_CONTRACT = render_bullets(
    [
        "输出使用中文。",
        "只基于当前 Design artifacts、继承知识和已有结构化 Plan artifacts 工作。",
        "不得重新做 repo discovery、repo binding adjudication 或 system design 结论改写。",
        "不得编造不存在的仓库、模块、文件、验证命令或依赖关系。",
        "章节和字段必须与模板保持一致。",
    ]
)


def build_plan_input_section(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    skills_brief_markdown: str,
) -> PromptSection:
    return PromptSection(
        title="Plan 输入",
        body="\n\n".join(
            [
                f"- 标题：{title}",
                "### Design Markdown\n\n" + design_markdown.strip(),
                "### PRD Refined\n\n" + (refined_markdown.strip() or "- 当前没有 refined markdown。"),
                "### Plan Skills Brief\n\n" + (skills_brief_markdown.strip() or "- 当前没有 skills brief。"),
            ]
        ),
    )


def build_plan_repo_binding_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Design Repo Binding", body=render_json_block(payload))


def build_plan_design_sections_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Design Sections", body=render_json_block(payload))


def build_plan_task_outline_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Plan Task Outline", body=render_json_block(payload))


def build_plan_work_items_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Plan Work Items", body=render_json_block(payload))


def build_plan_execution_graph_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Plan Execution Graph", body=render_json_block(payload))


def build_plan_validation_section(payload: dict[str, object]) -> PromptSection:
    return PromptSection(title="Plan Validation", body=render_json_block(payload))
