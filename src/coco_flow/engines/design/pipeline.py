"""Design 阶段主编排。

当前 Design 第一版只生成 design.md：读取 refined PRD 和绑定仓库，
补充 Skills/SOP 与代码调研证据，然后交给 writer 形成可人工评审的 Markdown 技术方案。
"""

from __future__ import annotations

from coco_flow.config import Settings

from .discovery import build_search_hints
from .evidence import build_research_plan, build_research_summary, run_parallel_repo_research
from .input import prepare_design_input
from .knowledge import build_design_skills_bundle
from .runtime import DesignAgentSession
from .types import EXECUTOR_NATIVE, STATUS_DESIGNED, DesignEngineResult
from .writer import write_doc_only_design_markdown


def run_design_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> DesignEngineResult:
    # 1. 读取上游输入。Design 的事实源是 prd-refined.md、input 元数据和已绑定仓库。
    on_log("design_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta, settings)
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")
    if not prepared.repo_scopes:
        raise ValueError("design requires bound repos; please bind repos first")
    on_log(f"design_prepare_ok: repos={len(prepared.repo_scopes)} refined_chars={len(prepared.refined_markdown.strip())}")

    # 2. 选择业务 Skills/SOP。业务定制只进入 knowledge layer，不写进引擎规则。
    on_log("design_skills_start: true")
    index_markdown, brief_markdown, selection_payload, selected_skill_ids = build_design_skills_bundle(prepared, settings)
    prepared.design_skills_selection_payload = selection_payload
    prepared.design_skills_index_markdown = index_markdown
    prepared.design_skills_brief_markdown = brief_markdown
    prepared.design_selected_skill_ids = selected_skill_ids
    on_log(f"design_skills_ok: selected={len(selected_skill_ids)}")

    # 3. 做轻量代码调研。native 只负责给搜索线索，真正证据仍来自本地 repo research。
    native_ok = settings.plan_executor.strip().lower() == EXECUTOR_NATIVE
    on_log("design_research_start: true")
    search_hints_payload = build_search_hints(prepared, settings, native_ok=native_ok, on_log=on_log)
    research_plan_payload = build_research_plan(prepared, search_hints_payload)
    repo_research_payloads = run_parallel_repo_research(prepared, research_plan_payload)
    research_summary_payload = build_research_summary(repo_research_payloads)
    on_log(
        "design_research_ok: "
        f"repos={len(repo_research_payloads)} "
        f"candidate_files={int(research_summary_payload.get('candidate_file_count') or 0)}"
    )

    # 4. 写 Markdown 方案。最终只返回 design.md，不再派生旧 schema 中间产物。
    on_log("design_writer_start: true")
    design_markdown = write_doc_only_design_markdown(
        prepared,
        research_summary_payload,
        settings,
        native_ok=native_ok,
        on_log=on_log,
    )
    on_log("design_writer_ok: true")
    on_log(f"status: {STATUS_DESIGNED}")
    return DesignEngineResult(
        status=STATUS_DESIGNED,
        design_markdown=design_markdown,
    )


__all__ = [
    "DesignAgentSession",
    "run_design_engine",
]
