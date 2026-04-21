from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT, build_design_input_section, build_design_sections_section, build_repo_binding_section


def build_design_template_markdown() -> str:
    return (
        "# Design\n\n"
        "## 改造点总览\n"
        "- 待补充\n\n"
        "## 总体方案\n"
        "- 待补充\n\n"
        "## 分仓库方案\n"
        "- 待补充\n\n"
        "## 仓库依赖关系\n"
        "- 待补充\n\n"
        "## 接口协议变更\n"
        "- 待补充\n\n"
        "## 风险与待确认项\n"
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
        "“分仓库方案”要覆盖所有 in_scope 仓库，但最终文档必须用自然语言表达角色定位，不要直接输出 scope_tier / must_change / co_change / validate_only / reference_only。",
        "reference_only 的仓库不要展开成本次改造项。",
        "主改仓和协同仓必须写清：职责、主要改动、核心改点、联动检查项、改动理由。",
        "联动验证仓要写清验证要点，不能伪装成主改仓。",
        "必须区分 closure_mode 和 selection_basis：single_repo 只表示单仓可闭合，不等于已经证明为什么必须选该仓。",
        "如果 selection_basis=heuristic_tiebreak，文档里必须明确写出“这是默认起始实现仓选择”，不能把它写成唯一正确仓库。",
        "“总体方案”要同时覆盖核心判断、主链路和关键约束，不要只复述 PRD Refined。",
        "候选文件需要分层表达：优先给出核心改点，再给出联动检查项，最后才是参考上下文。",
        "不要直接输出 change point、state_definition=high 这类内部分析标签，要翻译成用户能读懂的设计判断。",
        "“接口协议变更”只写对外接口新增或修改；如果没有，明确写“不涉及”。",
        "“风险与待确认项”只写技术风险和未锁定项，不要重复业务背景。",
        "优先消费 Design Sections 里的 repo_decisions、critical_flows、risk_boundaries；不要只复述 refined 需求。",
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
