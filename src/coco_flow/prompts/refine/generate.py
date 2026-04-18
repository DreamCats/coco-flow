from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import REFINE_OUTPUT_CONTRACT, build_input_bundle_section, build_intent_json_section, build_knowledge_read_section


def build_refine_template_markdown() -> str:
    return (
        "# PRD Refined\n\n"
        "## 核心诉求\n"
        "- 待补充\n\n"
        "## 改动范围\n"
        "- 待补充\n\n"
        "## 风险提示\n"
        "- 待补充\n\n"
        "## 讨论点\n"
        "- [待确认] 待补充\n"
        "- [建议补充] 待补充\n\n"
        "## 边界与非目标\n"
        "- 待补充\n"
    )


def build_refine_generate_agent_prompt(
    *,
    title: str,
    source_markdown: str,
    supplement: str,
    intent_payload: dict[str, object],
    knowledge_read_markdown: str,
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你在做 coco-flow Refine 的文档生成。",
        goal="基于输入材料、Refine Intent 和知识深读结果，编辑本地模板文件，产出最终 PRD Refined。",
        requirements=[
            "必须直接编辑指定模板文件，不要把结果只输出在回复文本里。",
            "保留模板的一级标题和五个二级标题，不要增删改章节名。",
            "讨论点中必须显式包含 [待确认] 或 [建议补充] 标签。",
            "风险提示只能写本次需求可能引入或暴露的风险，不能把背景问题伪装成风险。",
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
            build_knowledge_read_section(knowledge_read_markdown),
        ],
        closing="请现在开始编辑模板文件，确保最终文件可以直接作为 PRD Refined 使用。",
    )
    return render_prompt(document)
