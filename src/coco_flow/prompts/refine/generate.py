from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, render_prompt

from .shared import build_refine_constraints_section, build_refine_file_section


def build_refine_generate_agent_prompt(
    *,
    manual_extract_path: str,
    brief_draft_path: str,
    source_excerpt_path: str,
    template_path: str,
) -> str:
    document = PromptDocument(
        intro="你正在使用 AGENT_MODE。",
        goal=(
            "你是 staff-level backend product requirements editor，也是服务端需求收敛与验收设计专家。"
            "你的能力：稳定保持 scope、不被原始 PRD 噪音带偏、把人工提炼结果整理成高质量需求确认书、"
            "补边界与待确认项、把验收标准改写成可验证句子。"
        ),
        requirements=[],
        output_contract="完成后只需简短回复已完成。",
        sections=[
            build_refine_file_section(
                title="请先阅读以下文件",
                paths=[manual_extract_path, brief_draft_path, source_excerpt_path],
            ),
            build_refine_file_section(
                title="然后只编辑这个模板文件",
                paths=[template_path],
            ),
            build_refine_constraints_section(
                [
                    "人工提炼范围优先级最高，不得推翻它。",
                    "只能补洞和润色，不能扩大 in_scope。",
                    "不得把 out_of_scope 或原始 PRD 中无关的 UI/交互需求写进主变更点。",
                    "不得把模板提示语、占位语、链接清单、Figma/Legal/Starling 信息写进最终结果。",
                    "必须保留模板中的标题结构，不新增章节。",
                    "具体变更点应尽量保留叶子改动点，不要把纯标题行单独写成改动点。",
                    "如果 brief draft 有 gating_conditions，必须在“具体变更点”开头写一条“适用条件：...”。",
                    "如果模板中的具体变更点已是表格，只能润色表格前后的文字，不得拆散或改写表格内容。",
                    "验收标准要改写成“当...时，应该...”的可验证句子。",
                ]
            ),
        ],
    )
    return render_prompt(document)
