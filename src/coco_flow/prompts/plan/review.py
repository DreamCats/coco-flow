from __future__ import annotations

import json

from coco_flow.prompts.core import PromptDocument, PromptSection, render_prompt

from .shared import (
    PLAN_OUTPUT_CONTRACT,
    build_plan_execution_graph_section,
    build_plan_input_section,
    build_plan_repo_binding_section,
    build_plan_validation_section,
    build_plan_work_items_section,
)


def build_plan_review_template_json() -> str:
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


def build_plan_skeptic_prompt(
    *,
    title: str,
    design_markdown: str,
    refined_markdown: str,
    skills_brief_markdown: str,
    repo_binding_payload: dict[str, object],
    work_items_payload: dict[str, object],
    execution_graph_payload: dict[str, object],
    validation_payload: dict[str, object],
    template_path: str,
) -> str:
    return render_prompt(
        PromptDocument(
            intro="你在做 coco-flow Plan Open Harness 的 Skeptic 角色。",
            goal="本次任务：独立审查 Plan 结构化 artifacts 是否可交给 Code 阶段执行，只编辑指定 JSON 模板文件。",
            requirements=[
                "只输出结构化审查结果，不重写 plan。",
                "重点检查 must_change repo 是否遗漏、scope_tier 是否被改写、任务是否过大、依赖是否缺口、验证是否空泛、Code 输入是否缺失。",
                "不得重新做 Design repo adjudication；如果上游 Design artifact 自相矛盾，输出 needs_design_revision。",
                "blocking issue 必须给出 target、expected、actual 和 suggested_action。",
                "无证据的反对只能标为 warning 或 info。",
                "如果没有 blocking 或 warning，ok=true 且 issues=[]。",
                "完成后只需简短回复已完成。",
            ],
            output_contract=PLAN_OUTPUT_CONTRACT,
            sections=[
                PromptSection("需要编辑的模板文件", f"- file: {template_path}\n- 替换所有 __FILL__ 占位符。"),
                build_plan_input_section(
                    title=title,
                    design_markdown=design_markdown,
                    refined_markdown=refined_markdown,
                    skills_brief_markdown=skills_brief_markdown,
                ),
                build_plan_repo_binding_section(repo_binding_payload),
                build_plan_work_items_section(work_items_payload),
                build_plan_execution_graph_section(execution_graph_payload),
                build_plan_validation_section(validation_payload),
            ],
        )
    )
