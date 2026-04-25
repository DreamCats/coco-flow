from __future__ import annotations

from coco_flow.config import Settings

from .adjudication import apply_review_issues_to_decision, normalize_decision_for_gate
from .agent_io import DesignAgentSession
from .models import EXECUTOR_NATIVE, GATE_PASSED, STATUS_DESIGNED, DesignEngineResult
from .research import build_research_plan, build_research_summary, run_parallel_repo_research
from .search_hints import build_search_hints
from .skills import build_design_skills_bundle
from .source import prepare_design_input
from .writer import write_doc_only_design_markdown


def run_design_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> DesignEngineResult:
    on_log("design_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta, settings)
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")
    if not prepared.repo_scopes:
        raise ValueError("design requires bound repos; please bind repos first")
    on_log(f"design_prepare_ok: repos={len(prepared.repo_scopes)} refined_chars={len(prepared.refined_markdown.strip())}")

    on_log("design_skills_start: true")
    brief_markdown, selection_payload, selected_skill_ids = build_design_skills_bundle(prepared, settings)
    prepared.design_skills_selection_payload = selection_payload
    prepared.design_skills_brief_markdown = brief_markdown
    prepared.design_selected_skill_ids = selected_skill_ids
    on_log(f"design_skills_ok: selected={len(selected_skill_ids)}")

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
        gate_status=GATE_PASSED,
        design_markdown=design_markdown,
        repo_binding_payload={},
        sections_payload={},
        intermediate_artifacts={},
    )


__all__ = [
    "DesignAgentSession",
    "apply_review_issues_to_decision",
    "normalize_decision_for_gate",
    "run_design_engine",
]

