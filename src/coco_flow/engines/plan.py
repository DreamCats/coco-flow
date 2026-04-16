from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
from typing import Callable

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.engines.plan_generate import (
    build_plan_prompt,
    extract_plan_outputs,
    parse_ai_candidate_files,
    qualify_repo_path,
    validate_plan_outputs,
)
from coco_flow.engines.plan_knowledge import build_plan_knowledge_brief
from coco_flow.engines.plan_models import PlanBuild, PlanEngineResult
from coco_flow.engines.plan_render import build_design, build_plan
from coco_flow.engines.plan_research import (
    build_repo_researches,
    combine_context_snapshots,
    combine_research_findings,
    describe_repos,
    parse_refined_sections,
    parse_repo_scopes,
    read_text_if_exists,
    score_complexity,
    summarize_dirs,
)
from coco_flow.services.queries.task_detail import read_json_file

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
STATUS_PLANNING = "planning"
STATUS_PLANNED = "planned"
STATUS_FAILED = "failed"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"

LogHandler = Callable[[str], None]


def run_plan_engine(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler,
) -> PlanEngineResult:
    executor = settings.plan_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        return plan_task_native(task_dir, task_meta, settings, on_log=on_log)
    if executor == EXECUTOR_LOCAL:
        return plan_task_local(task_dir, task_meta, settings, on_log=on_log)
    raise ValueError(f"unknown plan executor: {settings.plan_executor}")


def plan_task_local(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler,
) -> PlanEngineResult:
    build = prepare_plan_build(task_dir, task_meta, settings)
    log_plan_research(build, on_log)
    on_log("fallback_local_plan: true")
    design = build_design(build, ai=None)
    plan = build_plan(build, ai=None)
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        design_markdown=design,
        plan_markdown=plan,
        intermediate_artifacts=build_plan_intermediate_artifacts(build),
    )


def plan_task_native(
    task_dir: Path,
    task_meta: dict[str, object],
    settings: Settings,
    on_log: LogHandler,
) -> PlanEngineResult:
    build = prepare_plan_build(task_dir, task_meta, settings)
    log_plan_research(build, on_log)
    on_log("generator_mode: explorer(readonly)")
    on_log(f"prompt_start: timeout={settings.native_query_timeout}")

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    try:
        raw = client.run_readonly_agent(
            build_plan_prompt(build),
            settings.native_query_timeout,
            build.repo_root or os.getcwd(),
        )
    except ValueError as error:
        on_log(f"generate_plan_with_native_error: {error}")
        return plan_task_local(task_dir, task_meta, settings, on_log=on_log)

    on_log(f"prompt_ok: {len(raw)} bytes")
    ai_sections, ok = extract_plan_outputs(raw)
    if not ok:
        on_log("parse_plan_output_error: missing required marker sections")
        return plan_task_local(task_dir, task_meta, settings, on_log=on_log)
    validate_plan_outputs(build, ai_sections)

    ai_files = parse_ai_candidate_files(raw=ai_sections.candidate_files, build=build)
    if ai_files:
        build.finding.candidate_files = ai_files
        build.finding.candidate_dirs = summarize_dirs(ai_files)
        build.assessment = score_complexity(build.sections, build.finding)
        on_log(f"candidate_files_override: {len(ai_files)}")
        on_log(f"complexity_after_ai: {build.assessment.level} ({build.assessment.total})")

    design = build_design(build, ai=ai_sections)
    plan = build_plan(build, ai=ai_sections)
    on_log(f"status: {STATUS_PLANNED}")
    return PlanEngineResult(
        status=STATUS_PLANNED,
        design_markdown=design,
        plan_markdown=plan,
        intermediate_artifacts=build_plan_intermediate_artifacts(build),
    )


def prepare_plan_build(task_dir: Path, task_meta: dict[str, object], settings: Settings) -> PlanBuild:
    task_id = task_dir.name
    title = str(task_meta.get("title") or task_id)
    source_value = str(task_meta.get("source_value") or "")
    source_markdown = read_text_if_exists(task_dir / "prd.source.md")
    refined_markdown = read_text_if_exists(task_dir / "prd-refined.md")
    repos_meta = read_json_file(task_dir / "repos.json")
    repo_lines = describe_repos(repos_meta)
    sections = parse_refined_sections(refined_markdown)
    repo_scopes = parse_repo_scopes(repos_meta)
    repo_researches = build_repo_researches(repo_scopes, title, sections)
    repo_root = repo_scopes[0].repo_path if repo_scopes else None
    context = combine_context_snapshots(repo_researches)
    finding = combine_research_findings(repo_researches, len(repo_scopes))
    assessment = score_complexity(sections, finding)
    knowledge_brief_markdown, knowledge_selection_payload, selected_knowledge_ids = build_plan_knowledge_brief(
        settings,
        title=title,
        sections=sections,
        repo_scopes=repo_scopes,
    )
    return PlanBuild(
        task_id=task_id,
        title=title,
        source_value=source_value,
        source_markdown=source_markdown,
        refined_markdown=refined_markdown,
        repo_lines=repo_lines,
        repo_scopes=repo_scopes,
        repo_researches=repo_researches,
        repo_ids={scope.repo_id for scope in repo_scopes},
        repo_root=repo_root,
        context=context,
        sections=sections,
        finding=finding,
        assessment=assessment,
        knowledge_brief_markdown=knowledge_brief_markdown,
        knowledge_selection_payload=knowledge_selection_payload,
        selected_knowledge_ids=selected_knowledge_ids,
    )


def log_plan_research(build: PlanBuild, on_log: LogHandler) -> None:
    on_log(f"repo_count: {len(build.repo_scopes)}")
    for repo in build.repo_researches:
        on_log(
            "repo_research: "
            f"{repo.repo_id} matched={len(repo.finding.matched_terms)} "
            f"files={len(repo.finding.candidate_files)} dirs={len(repo.finding.candidate_dirs)}"
        )
    if build.context.missing_files:
        on_log(f"context_missing: {', '.join(build.context.missing_files)}")
    on_log(f"context_available: {build.context.available}")
    on_log(f"glossary_matched_terms: {len(build.finding.matched_terms)}")
    if build.finding.matched_terms:
        matched = ", ".join(f"{item.business}->{item.identifier}" for item in build.finding.matched_terms[:6])
        on_log(f"glossary_hits: {matched}")
    on_log(f"unmatched_terms_count: {len(build.finding.unmatched_terms)}")
    if build.finding.unmatched_terms:
        on_log(f"unmatched_terms: {', '.join(build.finding.unmatched_terms[:6])}")
    on_log(f"candidate_files_count: {len(build.finding.candidate_files)}")
    if build.finding.candidate_files:
        on_log(f"candidate_files: {', '.join(build.finding.candidate_files[:6])}")
    on_log(f"candidate_dirs_count: {len(build.finding.candidate_dirs)}")
    if build.finding.notes:
        on_log(f"research_notes: {' | '.join(build.finding.notes)}")
    candidates = build.knowledge_selection_payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        on_log(f"knowledge_candidates: {len(candidates)}")
    if build.selected_knowledge_ids:
        on_log("selected_knowledge_ids: " + ", ".join(build.selected_knowledge_ids))
    if build.knowledge_brief_markdown.strip():
        on_log("knowledge_brief: true")
    on_log(f"complexity: {build.assessment.level} ({build.assessment.total})")


def build_plan_intermediate_artifacts(build: PlanBuild) -> dict[str, str | dict[str, object]]:
    artifacts: dict[str, str | dict[str, object]] = {}
    candidates = build.knowledge_selection_payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        artifacts["plan-knowledge-selection.json"] = build.knowledge_selection_payload
    if build.knowledge_brief_markdown.strip():
        artifacts["plan-knowledge-brief.md"] = build.knowledge_brief_markdown
    return artifacts


def sync_repo_statuses(task_dir: Path, status: str) -> None:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        return

    changed = False
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        current = str(repo.get("status") or "")
        if current in {"", STATUS_INITIALIZED, STATUS_REFINED, STATUS_PLANNING, STATUS_PLANNED}:
            repo["status"] = status
            changed = True

    if changed:
        repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")


def append_plan_log(task_dir: Path, message: str) -> None:
    log_path = task_dir / "plan.log"
    with log_path.open("a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        file.write(f"{timestamp} {message}\n")


def update_task_status(task_dir: Path, task_meta: dict[str, object], status: str) -> None:
    task_meta["status"] = status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
