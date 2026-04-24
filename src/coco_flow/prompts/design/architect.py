from __future__ import annotations

# Architect Agent：读取 refined PRD 和 repo evidence，完成第一轮跨仓设计裁决。
# 它负责判断范围、repo 工作类型、证据、边界和待确认项，但不能写 design.md。

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import DESIGN_OUTPUT_CONTRACT


def build_architect_template_json() -> str:
    return json.dumps(
        {
            "decision_summary": "__FILL__",
            "core_change_points": ["__FILL__"],
            "repo_decisions": [
                {
                    "repo_id": "__FILL__",
                    "work_type": "must_change",
                    "responsibility": "__FILL__",
                    "candidate_files": ["__FILL__"],
                    "candidate_dirs": ["__FILL__"],
                    "boundaries": ["__FILL__"],
                    "risks": ["__FILL__"],
                    "unresolved_questions": ["__FILL__"],
                    "confidence": "medium",
                    "evidence_refs": ["__FILL__"],
                }
            ],
            "system_boundaries": ["__FILL__"],
            "risks": ["__FILL__"],
            "unresolved_questions": ["__FILL__"],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_architect_prompt(
    *,
    title: str,
    refined_markdown: str,
    skills_brief_markdown: str,
    research_plan_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            goal="本次任务：基于 refined PRD 和 repo research evidence 生成跨仓设计裁决，只编辑指定 JSON 模板文件。",
            requirements=[
                "work_type 只使用 must_change / co_change / validate_only / reference_only。",
                "candidate_files 必须来自 repo research 的 candidate_files，且 evidence 必须能说明该文件承接本需求；不得只因为关键词命中就使用。",
                "validate_only / reference_only 仓库不要写 candidate_files；只写需要验证的问题、边界和 evidence_refs。",
                "如果涉及 producer / consumer 依赖（如公共实验字段被业务仓消费），必须写清提供方、消费方、证据和待确认项。",
            ],
            output_contract=DESIGN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                PromptSection("任务标题", title),
                PromptSection("Refined PRD", refined_markdown),
                PromptSection("Design Skills Brief", skills_brief_markdown.strip() or "- 当前没有 Design skills brief。"),
                PromptSection("Research Plan", json.dumps(research_plan_payload, ensure_ascii=False, indent=2)),
                PromptSection("Research Summary", json.dumps(research_summary_payload, ensure_ascii=False, indent=2)),
            ],
            closing="完成后只需简短回复已完成。",
        )
    )
