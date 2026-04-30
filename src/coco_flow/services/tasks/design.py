from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

from coco_flow.config import Settings, load_settings
from coco_flow.engines.design import (
    LogHandler,
    STATUS_DESIGNED,
    STATUS_DESIGNING,
    STATUS_FAILED,
    append_design_log,
    locate_task_dir,
    run_design_engine,
)
from coco_flow.services.queries.task_detail import read_json_file


def design_task(task_id: str, settings: Settings | None = None, on_log: LogHandler | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {"refined", STATUS_DESIGNING, STATUS_DESIGNED, "planned", STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow design")
    _ensure_bound_repos(task_dir)
    if status == "planned":
        _reset_plan_outputs(task_dir)

    logger = on_log or (lambda line: append_design_log(task_dir, line))
    owns_log_lifecycle = on_log is None
    started_at = datetime.now().astimezone()
    if owns_log_lifecycle:
        logger("=== DESIGN START ===")
        logger(f"task_id: {task_id}")
        logger(f"task_dir: {task_dir}")
        logger(f"executor: {cfg.plan_executor}")

    try:
        result = run_design_engine(task_dir, task_meta, cfg, logger)
        (task_dir / "design.md").write_text(result.design_markdown, encoding="utf-8")
        _write_json(task_dir / "design-skills.json", result.design_skills_payload)
        _write_json(task_dir / "design-contracts.json", result.design_contracts_payload)
        _write_json(task_dir / "design-research-summary.json", result.design_research_summary_payload)
        _write_json(task_dir / "design-quality.json", result.design_quality_payload)
        _write_json(task_dir / "design-supervisor-review.json", result.design_supervisor_review_payload)
        if result.rejected_design_markdown.strip():
            (task_dir / "design-writer-rejected.md").write_text(result.rejected_design_markdown.rstrip() + "\n", encoding="utf-8")
        _write_json(task_dir / "design-sync.json", build_design_sync_payload(result.design_markdown, status="synced"))
        task_meta["status"] = result.status
        task_meta["updated_at"] = datetime.now().astimezone().isoformat()
        (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _sync_repo_status(task_dir, result.status)
        return result.status
    except Exception as error:
        if owns_log_lifecycle:
            logger(f"error: {error}")
            logger(f"status: {STATUS_FAILED}")
        raise
    finally:
        if owns_log_lifecycle:
            duration = datetime.now().astimezone() - started_at
            logger(f"duration: {round(duration.total_seconds(), 3)}s")
            logger("=== DESIGN END ===")


def start_designing_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {"refined", STATUS_DESIGNED, "planned", STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow design")
    _ensure_bound_repos(task_dir)

    _reset_design_outputs(task_dir)
    if status == "planned":
        _reset_plan_outputs(task_dir)
    task_meta["status"] = STATUS_DESIGNING
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _sync_repo_status(task_dir, STATUS_DESIGNING)
    return STATUS_DESIGNING


def _ensure_bound_repos(task_dir: Path) -> None:
    repos_meta = read_json_file(task_dir / "repos.json")
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list) or not any(isinstance(item, dict) for item in raw_repos):
        raise ValueError("design requires bound repos; please bind repos first")


def _reset_design_outputs(task_dir: Path) -> None:
    for name in (
        "design.md",
        "design.log",
        "design-input.json",
        "design-input.md",
        "design-research-plan.json",
        "design-research-summary.json",
        "design-supervisor-review.json",
        "design-quality.json",
        "design-writer-rejected.md",
        "design-adjudication.json",
        "design-review.json",
        "design-debate.json",
        "design-decision.json",
        "design-change-points.json",
        "design-repo-assignment.json",
        "design-research.json",
        "design-repo-responsibility-matrix.json",
        "design-skills-selection.json",
        "design-skills.json",
        "design-skills-brief.md",
        "design-contracts.json",
        "design-sync.json",
        "design-search-hints.json",
        "design-repo-binding.json",
        "design-sections.json",
        "design-verify.json",
        "design-diagnosis.json",
        "design-result.json",
    ):
        path = task_dir / name
        if path.exists():
            path.unlink()
    research_dir = task_dir / "design-research"
    if research_dir.is_dir():
        for path in research_dir.glob("*.json"):
            path.unlink()
        try:
            research_dir.rmdir()
        except OSError:
            pass
    for pattern in (
        ".design-template-*.md",
        ".design-research-*.json",
        ".design-repo-binding-*.json",
        ".design-verify-*.json",
        ".design-architect-*.json",
        ".design-skeptic-*.json",
        ".design-search-hints-*.json",
        ".design-writer-*.md",
        ".design-writer-repair-*.md",
        ".design-supervisor-review-*.json",
        ".design-gate-*.json",
    ):
        for path in task_dir.glob(pattern):
            path.unlink()


def _reset_plan_outputs(task_dir: Path) -> None:
    for name in (
        "plan.md",
        "plan.log",
        "plan-skills-selection.json",
        "plan-skills.json",
        "plan-skills-brief.md",
        "plan-draft-work-items.json",
        "plan-draft-execution-graph.json",
        "plan-draft-validation.json",
        "plan-task-outline.json",
        "plan-work-items.json",
        "plan-execution-graph.json",
        "plan-validation.json",
        "plan-review.json",
        "plan-debate.json",
        "plan-decision.json",
        "plan-dependency-notes.json",
        "plan-risk-check.json",
        "plan-verify.json",
        "plan-diagnosis.json",
        "plan-result.json",
        "plan-scope.json",
        "plan-execution.json",
    ):
        path = task_dir / name
        if path.exists():
            path.unlink()
    for pattern in (
        ".plan-template-*.md",
        ".plan-task-outline-*.json",
        ".plan-planner-*.json",
        ".plan-scheduler-*.json",
        ".plan-validation-designer-*.json",
        ".plan-skeptic-*.json",
        ".plan-verify-*.json",
    ):
        for path in task_dir.glob(pattern):
            path.unlink()
    repo_dir = task_dir / "plan-repos"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)


def _sync_repo_status(task_dir: Path, status: str) -> None:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list):
        return
    changed = False
    for item in raw_repos:
        if not isinstance(item, dict):
            continue
        item["status"] = status
        changed = True
    if changed:
        repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_design_sync_payload(design_markdown: str, *, status: str) -> dict[str, object]:
    return {
        "synced": True,
        "status": status,
        "source_artifact": "design.md",
        "source_hash": hashlib.sha256(design_markdown.encode("utf-8")).hexdigest(),
        "synced_artifacts": ["design-contracts.json"],
        "reason": "Design contracts were generated from the current design.md.",
        "updated_at": datetime.now().astimezone().isoformat(),
    }
