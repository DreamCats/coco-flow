from __future__ import annotations

# Architect Revision Agent: performs the one allowed bounded revision after
# skeptic review. It must explicitly accept or reject each issue and reflect
# accepted issues in a revised design decision.

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .architect import build_architect_template_json
from .shared import DESIGN_OUTPUT_CONTRACT


def build_revision_template_json() -> str:
    return json.dumps(
        {
            "issue_resolutions": [
                {
                    "failure_type": "__FILL__",
                    "target": "__FILL__",
                    "resolution": "accepted",
                    "reason": "__FILL__",
                    "decision_change": "__FILL__",
                }
            ],
            "decision": json.loads(build_architect_template_json()),
        },
        ensure_ascii=False,
        indent=2,
    )


def build_revision_prompt(
    *,
    title: str,
    refined_markdown: str,
    adjudication_payload: dict[str, object],
    review_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你是 coco-flow Design V3 的 Architect Revision Agent。",
            goal="根据 skeptic 的 blocking/warning issues 对架构裁决做一次有界修订，并直接编辑指定 JSON 文件。",
            requirements=[
                "必须逐条处理 review issues，在 issue_resolutions 中写 accepted / rejected。",
                "accepted 的 issue 必须实际修改 decision；不能只追加到 unresolved_questions。",
                "如果 issue 指出候选文件场景不符、字段不存在、与 non-goal 冲突，应删除该候选文件或降级仓库职责。",
                "rejected 必须引用 research evidence 证明原判断成立。",
                "不得扩大 refined PRD 范围，不得新增 research 中不存在的文件。",
                "validate_only / reference_only 仓库不要携带 candidate_files。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Original Adjudication", json.dumps(adjudication_payload, ensure_ascii=False, indent=2)),
                PromptSection("Skeptic Review", json.dumps(review_payload, ensure_ascii=False, indent=2)),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )

