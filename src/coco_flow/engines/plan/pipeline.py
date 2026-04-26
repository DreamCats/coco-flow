"""Plan 阶段主编排。"""

from __future__ import annotations

from coco_flow.config import Settings

from .compiler import (
    build_structured_plan_artifacts,
    render_plan_markdown,
    validate_plan_artifacts,
)
from .input import prepare_plan_input
from .knowledge import build_plan_skills_bundle
from .types import STATUS_PLANNED, PlanEngineResult
from .writer import generate_doc_only_plan_markdown


def run_plan_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> PlanEngineResult:
    # 1. 读取上游事实源。Plan 只消费 prd-refined.md、design.md 和 repos.json。
    on_log("plan_prepare_start: true")
    prepared = prepare_plan_input(task_dir, task_meta)
    on_log(f"plan_prepare_ok: repos={len(prepared.repo_scopes)}, title={prepared.title}")

    # 2. 选择 Plan 阶段需要的 Skills/SOP。业务规则放在知识层，不写进引擎。
    on_log("plan_skills_start: true")
    skills_index_markdown, skills_brief_markdown, skills_selection_payload, selected_skill_ids = build_plan_skills_bundle(prepared, settings)
    prepared.skills_index_markdown = skills_index_markdown
    prepared.skills_brief_markdown = skills_brief_markdown
    prepared.skills_selection_payload = skills_selection_payload
    prepared.selected_skill_ids = selected_skill_ids
    on_log(f"plan_skills_ok: selected={len(selected_skill_ids)}")

    # 3. 先构建 Code 阶段可消费的结构化 Plan sidecar。
    on_log("plan_structure_start: true")
    (
        plan_work_items_payload,
        plan_execution_graph_payload,
        plan_validation_payload,
        plan_result_payload,
        repo_task_markdowns,
    ) = build_structured_plan_artifacts(prepared)
    issues = validate_plan_artifacts(
        prepared,
        plan_work_items_payload,
        plan_execution_graph_payload,
        plan_validation_payload,
        repo_task_markdowns,
    )
    if issues:
        plan_result_payload["status"] = "failed"
        plan_result_payload["gate_status"] = "failed"
        plan_result_payload["code_allowed"] = False
        plan_result_payload["issues"] = issues
        on_log(f"plan_gate_failed: {len(issues)}")
        raise ValueError("plan gate failed: " + "; ".join(issues[:5]))
    on_log(
        "plan_structure_ok: "
        f"work_items={len(plan_work_items_payload.get('work_items') or [])} "
        f"edges={len(plan_execution_graph_payload.get('edges') or [])} "
        f"code_allowed={bool(plan_result_payload.get('code_allowed'))}"
    )

    # 4. 写 plan.md。native 只负责表达；不合格时使用结构化 sidecar 渲染的 Markdown。
    on_log("plan_writer_start: true")
    plan_markdown, mode = generate_doc_only_plan_markdown(prepared, settings, on_log)
    structured_markdown = render_plan_markdown(
        prepared,
        plan_work_items_payload,
        plan_execution_graph_payload,
        plan_validation_payload,
        plan_result_payload,
    )
    if mode != "native" or not _plan_markdown_matches_contract(plan_markdown):
        if mode == "native":
            on_log("plan_writer_replaced: contract_mismatch")
        plan_markdown = structured_markdown
    on_log(f"plan_writer_ok: mode={mode}")
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        plan_markdown=plan_markdown,
        plan_work_items_payload=plan_work_items_payload,
        plan_execution_graph_payload=plan_execution_graph_payload,
        plan_validation_payload=plan_validation_payload,
        plan_result_payload=plan_result_payload,
        repo_task_markdowns=repo_task_markdowns,
    )


def _plan_markdown_matches_contract(markdown: str) -> bool:
    required = (
        "depends_on",
        "hard_dependencies",
        "coordination_points",
        "acceptance_mapping",
        "blockers",
    )
    return all(item in markdown for item in required)
