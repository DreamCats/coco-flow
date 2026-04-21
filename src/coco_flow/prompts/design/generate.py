from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_input_section, build_design_sections_section, build_repo_binding_section


def build_design_template_markdown() -> str:
    return (
        "# Design\n\n"
        "## 系统改造点\n"
        "- 待补充\n\n"
        "## 方案设计\n\n"
        "### 总体方案\n"
        "- 待补充\n\n"
        "### 分系统改造\n"
        "- 待补充\n\n"
        "### 联动验证仓库\n"
        "- 待补充\n\n"
        "### 参考链路\n"
        "- 待补充\n\n"
        "### 系统依赖关系\n"
        "- 待补充\n\n"
        "### 关键链路说明\n"
        "- 待补充\n\n"
        "## 多端协议是否有变更\n"
        "- 待补充\n\n"
        "## 存储&&配置是否有变更\n"
        "- 待补充\n\n"
        "## 是否有实验，实验怎么涉及\n"
        "- 待补充\n\n"
        "## 给 QA 的输入\n"
        "- 待补充\n\n"
        "## 人力评估\n"
        "- 待补充\n"
    )


def build_design_generate_agent_prompt(
    *,
    title: str,
    refined_markdown: str,
    repo_binding_payload: dict[str, object],
    sections_payload: dict[str, object],
    knowledge_brief_markdown: str,
    template_path: str,
    regeneration_issues: list[str] | None = None,
    previous_design_markdown: str = "",
) -> str:
    regeneration_items = [str(item).strip() for item in (regeneration_issues or []) if str(item).strip()]
    requirements = [
        "必须直接编辑指定模板文件，不要只在回复里输出 Markdown。",
        "保留模板中的一级标题和章节顺序，不要擅自删改章节名。",
        "不得引入当前 repo binding 或 design sections 中没有出现的仓库、系统或文件。",
        "“分系统改造”只展开 scope_tier=must_change 的仓库。",
        "每个 in_scope 仓库都必须被明确提及，不能只写主仓。",
        "scope_tier=validate_only 的仓库必须写进“联动验证仓库”，并解释为什么不作为主改造仓。",
        "scope_tier=reference_only 的仓库只保留必要背景，不要展开成本次改造项。",
        "每个 must_change 仓库都必须写清：为什么选它、仓库现状、建议落点或候选文件。",
        "必须区分 closure_mode 和 selection_basis：single_repo 只表示单仓可闭合，不等于已经证明为什么必须选该仓。",
        "如果 selection_basis=heuristic_tiebreak，文档里必须明确写出“这是默认起始实现仓选择”，不能把它写成唯一正确仓库。",
        "避免在多个仓库段落里机械重复同一段 selection_note；总体方案说一次即可，分仓只保留和该仓直接相关的说明。",
        "优先消费 Design Sections 里的 repo_decisions；不要只复述 PRD Refined。",
        "内容要更像人写的设计文档，但不能偏离结构化结果。",
    ]
    if regeneration_items:
        requirements.append("这是修订模式：必须优先修正“需要修正的问题”里的每一项，再补充其他润色。")
    requirements.append("完成后只需简短回复已完成。")
    document = PromptDocument(
        intro="你在做 coco-flow Design 的文档生成。",
        goal="基于结构化的 repo binding 和 design sections，直接编辑指定 Markdown 模板文件，产出最终 design.md。",
        requirements=requirements,
        output_contract=DESIGN_OUTPUT_CONTRACT,
        sections=[
            PromptSection(title="需要编辑的模板文件", body=f"- file: {template_path}\n- 只修改这个 Markdown 文件。"),
            *(
                [PromptSection(title="需要修正的问题", body="\n".join(f"- {item}" for item in regeneration_items))]
                if regeneration_items else []
            ),
            *(
                [PromptSection(title="上一版 Design 草稿", body=previous_design_markdown.strip())]
                if previous_design_markdown.strip() else []
            ),
            build_design_input_section(title=title, refined_markdown=refined_markdown, knowledge_brief_markdown=knowledge_brief_markdown),
            build_repo_binding_section(repo_binding_payload),
            build_design_sections_section(sections_payload),
        ],
    )
    return render_prompt(document)
