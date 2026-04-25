"""Plan 阶段主编排。

当前第一版采用 Markdown 文档流：准备上游输入，选择 Plan Skills/SOP，
再生成可执行的 plan.md。旧 work-items / graph / validation / review schema 已移除。
"""

from __future__ import annotations

from coco_flow.config import Settings

from .generate import generate_doc_only_plan_markdown
from .models import STATUS_PLANNED, PlanEngineResult
from .skills import build_plan_skills_bundle
from .source import prepare_plan_input


def run_plan_engine(task_dir, task_meta: dict[str, object], settings: Settings, on_log) -> PlanEngineResult:
    # 1. 读取上游事实源。Plan 只消费 prd-refined.md、design.md 和 repos.json。
    on_log("plan_prepare_start: true")
    prepared = prepare_plan_input(task_dir, task_meta)
    on_log(f"plan_prepare_ok: repos={len(prepared.repo_scopes)}, title={prepared.title}")

    # 2. 选择 Plan 阶段需要的 Skills/SOP。业务规则放在知识层，不写进引擎。
    on_log("plan_skills_start: true")
    skills_brief_markdown, skills_selection_payload, selected_skill_ids = build_plan_skills_bundle(prepared, settings)
    prepared.skills_brief_markdown = skills_brief_markdown
    prepared.skills_selection_payload = skills_selection_payload
    prepared.selected_skill_ids = selected_skill_ids
    on_log(f"plan_skills_ok: selected={len(selected_skill_ids)}")

    # 3. 写 plan.md。native 失败时回退到本地 Markdown 草稿，不再生成结构化中间产物。
    on_log("plan_writer_start: true")
    plan_markdown, mode = generate_doc_only_plan_markdown(prepared, settings, on_log)
    on_log(f"plan_writer_ok: mode={mode}")
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        plan_markdown=plan_markdown,
    )
