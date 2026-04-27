from __future__ import annotations

# Semantic Gate Agent：执行最终通过 / 阻断裁决。
# 它同时检查结构化 decision 和 design.md 是否被 refined PRD 与 evidence 支撑；
# 对无证据设计必须阻断，而不是润色成看似可执行的方案。

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_semantic_gate_template_json() -> str:
    return json.dumps(
        {
            "ok": False,
            "gate_status": "needs_human",
            "issues": [],
            "reason": "__FILL__",
        },
        ensure_ascii=False,
        indent=2,
    )


def build_semantic_gate_prompt(
    *,
    title: str,
    refined_markdown: str,
    decision_payload: dict[str, object],
    design_markdown: str,
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            goal="本次任务：检查 design.md 是否真实表达 design-decision.json 且能支撑 refined PRD，只编辑指定 JSON 模板文件。",
            requirements=[
                "同时检查 contract gate 和 semantic gate。",
                "gate_status 只使用 passed / passed_with_warnings / needs_human / degraded / failed。",
                "仅有非阻塞风险时使用 passed_with_warnings。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Design Decision", json.dumps(decision_payload, ensure_ascii=False, indent=2)),
                PromptSection("Design Markdown", design_markdown),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )
