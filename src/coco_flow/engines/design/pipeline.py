from __future__ import annotations

from datetime import datetime
from pathlib import Path

from coco_flow.config import Settings
from coco_flow.engines.shared.diagnostics import enrich_verify_payload

from .adjudication import (
    apply_review_issues_to_decision,
    build_architect_adjudication,
    build_final_decision,
    build_skeptic_review,
    derive_repo_binding,
    derive_sections,
    normalize_decision_for_gate,
    review_payload_after_revision,
)
from .agent_io import DesignAgentSession, close_design_agent_session, new_design_agent_session
from .gate import build_design_diagnosis, run_semantic_gate
from .input_artifacts import build_design_input_markdown, build_design_input_payload
from .models import (
    EXECUTOR_NATIVE,
    GATE_DEGRADED,
    GATE_FAILED,
    PLAN_ALLOWED_GATE_STATUSES,
    STATUS_DESIGNED,
    DesignEngineResult,
)
from .research import build_research_plan, build_research_summary, run_parallel_repo_research, safe_artifact_name
from .search_hints import build_search_hints
from .skills import build_design_skills_bundle
from .source import prepare_design_input
from .utils import issues
from .writer import write_design_markdown


def run_design_engine(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log,
) -> DesignEngineResult:
    """执行 Design V3 的有限轮 agentic workflow。

    流程固定为 10 步：
    1. 准备输入 bundle，并落 `design-input.*`
    2. 检索 Design skills，并生成 SOP/repo role brief
    3. 将 refined PRD 转成结构化搜索线索
    4. 生成 repo research plan
    5. 并发做 repo evidence research
    6. Architect 做跨仓裁决
    7. Skeptic 做对抗审查
    8. 有界 revision 生成最终 decision，并派生兼容 artifact
    9. Writer 把 decision 写成 `design.md`
    10. Semantic gate 决定是否允许进入 Plan
    """
    artifacts: dict[str, str | dict[str, object]] = {}
    architect_session: DesignAgentSession | None = None

    try:
        prepared = _prepare(task_dir, task_meta, settings, artifacts, on_log)
        native_ok = settings.plan_executor.strip().lower() == EXECUTOR_NATIVE
        _skills(prepared, settings, artifacts, on_log)
        search_hints_payload = _search_hints(prepared, settings, native_ok, artifacts, on_log)
        research_plan_payload, research_summary_payload = _research(prepared, search_hints_payload, artifacts, on_log)
        if native_ok:
            architect_session = _start_architect_session(prepared, settings, on_log)
            native_ok = architect_session is not None
        adjudication_payload = _architect(prepared, research_plan_payload, research_summary_payload, settings, native_ok, architect_session, artifacts, on_log)
        review_payload = _skeptic(prepared, adjudication_payload, research_summary_payload, settings, native_ok, artifacts, on_log)
        decision_payload, debate_payload, repo_binding_payload, sections_payload = _decision(
            prepared,
            adjudication_payload,
            review_payload,
            research_summary_payload,
            settings,
            native_ok,
            architect_session,
            artifacts,
            on_log,
        )
        gate_review_payload = review_payload_after_revision(review_payload, debate_payload, decision_payload)

        design_markdown = _write_markdown(prepared, decision_payload, settings, native_ok and bool(adjudication_payload.get("native")), on_log)
        gate_status = _gate(prepared, decision_payload, design_markdown, settings, native_ok and bool(adjudication_payload.get("native")), gate_review_payload, artifacts, on_log)

        task_status = STATUS_DESIGNED if gate_status in PLAN_ALLOWED_GATE_STATUSES else GATE_FAILED
        artifacts["design-result.json"] = {
            "task_id": prepared.task_id,
            "status": task_status,
            "gate_status": gate_status,
            "agentic_version": "v3",
            "native": bool(adjudication_payload.get("native")) and gate_status != GATE_DEGRADED,
            "plan_allowed": gate_status in PLAN_ALLOWED_GATE_STATUSES,
            "artifacts": sorted(artifacts.keys()),
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        on_log(f"status: {task_status}")

        return DesignEngineResult(
            status=task_status,
            gate_status=gate_status,
            design_markdown=design_markdown,
            repo_binding_payload=repo_binding_payload,
            sections_payload=sections_payload,
            intermediate_artifacts=artifacts,
        )
    finally:
        if architect_session is not None:
            close_design_agent_session(architect_session, on_log)


def _prepare(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
):
    on_log("design_v3_prepare_start: true")
    prepared = prepare_design_input(task_dir, task_meta, settings)
    if not prepared.refined_markdown.strip():
        raise ValueError("prd-refined.md 为空，无法执行 design")
    if not prepared.repo_scopes:
        raise ValueError("design requires bound repos; please bind repos first")

    artifacts["design-input.json"] = build_design_input_payload(prepared)
    artifacts["design-input.md"] = build_design_input_markdown(prepared)
    on_log(f"design_v3_prepare_ok: repos={len(prepared.repo_scopes)} refined_chars={len(prepared.refined_markdown.strip())}")
    return prepared


def _skills(
    prepared,
    settings: Settings,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> None:
    on_log("design_v3_skills_start: true")
    brief_markdown, selection_payload, selected_skill_ids = build_design_skills_bundle(prepared, settings)
    prepared.design_skills_selection_payload = selection_payload
    prepared.design_skills_brief_markdown = brief_markdown
    prepared.design_selected_skill_ids = selected_skill_ids
    artifacts["design-skills-selection.json"] = selection_payload
    if brief_markdown.strip():
        artifacts["design-skills-brief.md"] = brief_markdown
    artifacts["design-input.json"] = build_design_input_payload(prepared)
    artifacts["design-input.md"] = build_design_input_markdown(prepared)
    on_log(f"design_v3_skills_ok: selected={len(selected_skill_ids)}")


def _search_hints(
    prepared,
    settings: Settings,
    native_ok: bool,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> dict[str, object]:
    on_log("design_v3_search_hints_start: true")
    search_hints_payload = build_search_hints(prepared, settings, native_ok=native_ok, on_log=on_log)
    artifacts["design-search-hints.json"] = search_hints_payload
    on_log(
        "design_v3_search_hints_ok: "
        f"source={search_hints_payload.get('source') or 'unknown'} "
        f"confidence={search_hints_payload.get('confidence') or 'unknown'} "
        f"terms={len(search_hints_payload.get('search_terms') or [])} "
        f"symbols={len(search_hints_payload.get('likely_symbols') or [])} "
        f"file_patterns={len(search_hints_payload.get('likely_file_patterns') or [])}"
    )
    return search_hints_payload


def _research(
    prepared,
    search_hints_payload: dict[str, object],
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> tuple[dict[str, object], dict[str, object]]:
    on_log("design_v3_research_plan_start: true")
    research_plan_payload = build_research_plan(prepared, search_hints_payload)
    artifacts["design-research-plan.json"] = research_plan_payload
    on_log(f"design_v3_research_plan_ok: repos={len(research_plan_payload.get('repos', []))}")

    on_log("design_v3_repo_research_start: true")
    repo_research_payloads = run_parallel_repo_research(prepared, research_plan_payload)
    for repo_payload in repo_research_payloads:
        repo_id = str(repo_payload.get("repo_id") or "repo")
        artifacts[f"design-research/{safe_artifact_name(repo_id)}.json"] = repo_payload
    research_summary_payload = build_research_summary(repo_research_payloads)
    artifacts["design-research-summary.json"] = research_summary_payload
    on_log(
        "design_v3_repo_research_ok: "
        f"mode=local_evidence_scan repos={len(repo_research_payloads)} "
        f"candidate_files={int(research_summary_payload.get('candidate_file_count') or 0)} "
        f"git_evidence={int(research_summary_payload.get('git_evidence_count') or 0)} "
        f"git_commands={int(research_summary_payload.get('git_command_count') or 0)}"
    )
    return research_plan_payload, research_summary_payload


def _architect(
    prepared,
    research_plan_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    settings: Settings,
    native_ok: bool,
    architect_session: DesignAgentSession | None,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> dict[str, object]:
    on_log("design_v3_architect_start: true")
    adjudication_payload = build_architect_adjudication(
        prepared,
        research_plan_payload,
        research_summary_payload,
        settings,
        native_ok=native_ok,
        agent_session=architect_session,
        on_log=on_log,
    )
    artifacts["design-adjudication.json"] = adjudication_payload
    on_log(f"design_v3_architect_ok: native={'true' if bool(adjudication_payload.get('native')) else 'false'}")
    return adjudication_payload


def _skeptic(
    prepared,
    adjudication_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    settings: Settings,
    native_ok: bool,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> dict[str, object]:
    on_log("design_v3_skeptic_start: true")
    review_payload = build_skeptic_review(
        prepared,
        adjudication_payload,
        research_summary_payload,
        settings,
        native_ok=native_ok and bool(adjudication_payload.get("native")),
        on_log=on_log,
    )
    artifacts["design-review.json"] = review_payload
    review_issues = issues(review_payload)
    blocking_count = _issue_count(review_issues, "blocking")
    warning_count = _issue_count(review_issues, "warning")
    info_count = _issue_count(review_issues, "info")
    on_log(
        "design_v3_skeptic_ok: "
        f"ok={'true' if bool(review_payload.get('ok')) else 'false'} "
        f"blocking={blocking_count} warnings={warning_count} info={info_count}"
    )
    return review_payload


def _decision(
    prepared,
    adjudication_payload: dict[str, object],
    review_payload: dict[str, object],
    research_summary_payload: dict[str, object],
    settings: Settings,
    native_ok: bool,
    architect_session: DesignAgentSession | None,
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    decision_payload, debate_payload = build_final_decision(
        prepared,
        adjudication_payload,
        review_payload,
        research_summary_payload,
        settings,
        native_ok=native_ok and bool(adjudication_payload.get("native")),
        agent_session=architect_session,
        on_log=on_log,
    )
    artifacts["design-debate.json"] = debate_payload
    artifacts["design-decision.json"] = decision_payload
    revision_payload = debate_payload.get("revision")
    revision = revision_payload if isinstance(revision_payload, dict) else {}
    revision_applied = bool(revision.get("applied"))
    revision_summary = str(revision.get("summary") or "")
    on_log(
        "design_v3_revision_ok: "
        f"applied={'true' if revision_applied else 'false'} "
        f"reason={revision_summary}"
    )

    repo_binding_payload = derive_repo_binding(prepared, decision_payload)
    sections_payload = derive_sections(prepared, decision_payload)
    artifacts["design-repo-binding.json"] = repo_binding_payload
    artifacts["design-sections.json"] = sections_payload
    return decision_payload, debate_payload, repo_binding_payload, sections_payload


def _write_markdown(prepared, decision_payload: dict[str, object], settings: Settings, native_ok: bool, on_log) -> str:
    on_log("design_v3_writer_start: true")
    design_markdown = write_design_markdown(
        prepared,
        decision_payload,
        settings,
        native_ok=native_ok,
        on_log=on_log,
    )
    on_log("design_v3_writer_ok: true")
    return design_markdown


def _gate(
    prepared,
    decision_payload: dict[str, object],
    design_markdown: str,
    settings: Settings,
    native_ok: bool,
    review_payload: dict[str, object],
    artifacts: dict[str, str | dict[str, object]],
    on_log,
) -> str:
    on_log("design_v3_gate_start: true")
    verify_payload = run_semantic_gate(
        prepared,
        decision_payload,
        design_markdown,
        settings,
        native_ok=native_ok,
        review_payload=review_payload,
        on_log=on_log,
    )
    gate_status = str(verify_payload.get("gate_status") or GATE_FAILED)
    verify_payload = enrich_verify_payload(stage="design", verify_payload=verify_payload, artifact="design.md")
    artifacts["design-verify.json"] = verify_payload
    artifacts["design-diagnosis.json"] = build_design_diagnosis(verify_payload)
    on_log(f"design_v3_gate_ok: gate_status={gate_status} ok={'true' if bool(verify_payload.get('ok')) else 'false'}")
    return gate_status


def _issue_count(review_issues: list[dict[str, object]], severity: str) -> int:
    return sum(1 for item in review_issues if str(item.get("severity") or "") == severity)


def _start_architect_session(prepared, settings: Settings, on_log) -> DesignAgentSession | None:
    try:
        return new_design_agent_session(
            prepared,
            settings,
            role="design_architect",
            on_log=on_log,
            bootstrap=True,
        )
    except Exception as error:
        on_log(f"design_v3_architect_session_degraded: {error}")
        return None


__all__ = [
    "apply_review_issues_to_decision",
    "normalize_decision_for_gate",
    "run_design_engine",
]
