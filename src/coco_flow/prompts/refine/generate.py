from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section, build_intent_json_section, build_skills_read_section


def build_refine_template_markdown() -> str:
    return (
        "# 需求确认书\n\n"
        "## 需求概述\n"
        "- 待补充\n\n"
        "## 具体变更点\n"
        "- 待补充\n\n"
        "## 验收标准\n"
        "- 待补充\n\n"
        "## 边界与非目标\n"
        "- 待补充\n\n"
        "## 待确认项\n"
        "- 问题：待补充；当前假设：待补充；影响范围：待补充\n"
    )


def build_refine_generate_agent_prompt(
    *,
    title: str,
    source_markdown: str,
    supplement: str,
    intent_payload: dict[str, object],
    skills_read_markdown: str,
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的文档生成。",
        goal="基于输入材料、Refine Intent 和 Skills 深读结果，编辑本地模板文件，产出最终需求确认书。",
        requirements=[
            "必须直接编辑指定模板文件，不要把结果只输出在回复文本里。",
            "保留模板的一级标题和五个二级标题，不要增删改章节名。",
            "所有章节都必须完成填写，最终文件里不能保留“待补充”或任何占位符。",
            "“需求概述”用研发视角总结为什么要做，不要复制 PRD 原文。",
            "“具体变更点”使用“场景：...；当前行为：...；期望行为：...”的单行结构。",
            "“验收标准”只写可验证条件，优先使用“当...时，应该...”语式。",
            "“边界与非目标”要明确不做什么，避免顺手扩大范围。",
            "“待确认项”必须使用“问题：...；当前假设：...；影响范围：...”结构。",
            "不要引入实现方案、repo 路径或代码层推断。",
            "完成后只需简短回复已完成。",
        ],
        output_contract=REFINE_OUTPUT_CONTRACT,
        sections=[
            PromptSection(
                title="需要编辑的模板文件",
                body=f"- file: {template_path}\n- 只修改这个文件，直接在文件内填充内容。",
            ),
            build_input_bundle_section(title=title, source_markdown=source_markdown, supplement=supplement),
            build_intent_json_section(intent_payload),
            build_skills_read_section(skills_read_markdown),
        ],
        closing="请现在开始编辑模板文件，确保最终文件可以直接作为需求确认书使用。",
    )
    return render_prompt(document)
