from __future__ import annotations

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_design_supervisor_review_template_json() -> str:
    return json.dumps(
        {
            "passed": False,
            "decision": "repair_writer",
            "confidence": "medium",
            "blocking_issues": [
                {
                    "type": "__FILL__",
                    "summary": "__FILL__",
                    "evidence": ["__FILL__"],
                }
            ],
            "repair_instructions": ["__FILL__"],
            "next_action": "rewrite_design",
            "reason": "__FILL__",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_design_supervisor_review_prompt(
    *,
    title: str,
    refined_markdown: str,
    research_summary_payload: dict[str, object],
    design_markdown: str,
    quality_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design 阶段的 Supervisor Agent，像 Tech Lead 一样审阅 design.md。",
            goal="基于 refined PRD、repo research、程序 quality report 审查 design.md 是否可信，并直接编辑指定 JSON 模板文件。",
            requirements=[
                "只做审阅和调度判断，不重写 design.md。",
                "decision 只使用 pass / repair_writer / redo_research / degrade_design / needs_human / fail。",
                "next_action 只使用 accept_design / rewrite_design / redo_research / write_degraded_design / ask_human / fail_design。",
                "重点检查：候选文件是否被证据支撑、弱相关 candidate 是否被写成精准落点、是否违背非目标、是否缺待确认项。",
                "如果只是章节缺失或表达不完整，优先 repair_writer，并给出明确修复指令。",
                "如果 repo research 不足以支撑精准落点，使用 degrade_design 或 needs_human，不要要求 writer 编造确定方案。",
                "blocking_issues 必须给出 type、summary 和 evidence；无阻断问题时 passed=true、decision=pass、blocking_issues=[]。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
                PromptSection("Program Quality Report", json.dumps(quality_payload, ensure_ascii=False, indent=2)),
                PromptSection("Draft Design Markdown", design_markdown),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )
