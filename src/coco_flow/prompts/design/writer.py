from __future__ import annotations

# Writer Agent：把最终结构化 decision 转写成人可读的 design.md。
# 它可以改善表达和结构，但不能新增 repo、文件或范围裁决。

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_writer_prompt(
    *,
    title: str,
    decision_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Writer Agent。",
            goal="只把 design-decision.json 写成高质量 design.md，直接编辑指定 Markdown 文件。",
            requirements=[
                "不要新增 repo 裁决、候选文件或需求。",
                "结论先行，使用自然语言，不暴露 must_change/confidence 等内部标签。",
                "每个涉及仓库都说明主要做什么、候选文件或模块、边界是什么。",
                "只需检查的仓库不要写成本次代码改造项。",
                "待确认项只写会影响研发判断的问题。",
                "如果 finalized=false 或 review_blocking_count>0，必须在结论中明确写“当前不能进入 Plan”，并列出阻断原因。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 直接覆盖为最终 Markdown。"),
                PromptSection("任务标题", title),
                PromptSection("Design Decision", json.dumps(decision_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )
