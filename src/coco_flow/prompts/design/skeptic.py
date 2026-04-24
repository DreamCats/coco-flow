from __future__ import annotations

# Skeptic Agent: adversarially reviews the architect adjudication. It reports
# evidence gaps, wrong repo/file choices, scope conflicts, and PRD coverage
# issues, but it must not rewrite the solution.

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_skeptic_template_json() -> str:
    return json.dumps(
        {
            "ok": False,
            "issues": [
                {
                    "severity": "blocking",
                    "failure_type": "__FILL__",
                    "target": "__FILL__",
                    "expected": "__FILL__",
                    "actual": "__FILL__",
                    "suggested_action": "__FILL__",
                }
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_skeptic_prompt(
    *,
    title: str,
    refined_markdown: str,
    adjudication_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Skeptic Agent。",
            goal="反向审查 Architect 裁决是否被 PRD 和 repo evidence 支撑，直接编辑指定 JSON 文件。",
            requirements=[
                "只输出结构化审查结果，不重写方案。",
                "重点找误选 repo、遗漏核心 repo、候选文件无证据、PRD 未覆盖。",
                "blocking issue 必须给出 target、expected、actual 和 suggested_action。",
                "无证据的反对只能标为 warning 或 info。",
                "如果没有 blocking 或 warning，ok=true 且 issues=[]。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Architect Adjudication", json.dumps(adjudication_payload, ensure_ascii=False, indent=2)),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )

