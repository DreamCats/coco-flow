from __future__ import annotations

from coco_flow.prompts.core import PromptDocument, render_prompt

from .shared import build_refine_constraints_section, build_refine_file_section


def build_refine_verify_agent_prompt(
    *,
    brief_draft_path: str,
    refined_markdown_path: str,
    template_path: str,
) -> str:
    document = PromptDocument(
        goal="本次任务：独立校验需求确认书是否偏离 brief draft，只编辑指定 JSON 模板文件。",
        requirements=[],
        output_contract="完成后只需简短回复已完成。",
        sections=[
            build_refine_file_section(
                title="请先阅读以下文件",
                paths=[brief_draft_path, refined_markdown_path],
            ),
            build_refine_file_section(
                title="然后只编辑这个 JSON 模板文件",
                paths=[template_path],
            ),
            build_refine_constraints_section(
                [
                    "只以本次读取的 artifact 为准，不采信生成阶段的口头解释或聊天历史。",
                    "检查是否遗漏 brief draft 的 in_scope 叶子改动点。",
                    "检查是否把模板提示语或无关链接信息写进结果。",
                    "检查是否把标题行当成改动点，导致叶子点缺失。",
                    "如果 brief draft 有 gating_conditions，检查它是否出现在“具体变更点”的适用条件中，不能只出现在验收标准。",
                    "如果“具体变更点”使用表格，按表格中的分组、状态和展示内容还原检查叶子改动点。",
                    "检查是否把 out_of_scope 写进主变更点或验收标准。",
                    "只有问题为空时才允许 ok=true。",
                ]
            ),
        ],
    )
    return render_prompt(document)
