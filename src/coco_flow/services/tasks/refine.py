from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil

from coco_flow.config import Settings, load_settings
from coco_flow.engines.input import STATUS_INPUT_READY
from coco_flow.engines.refine import (
    LogHandler,
    STATUS_INITIALIZED,
    STATUS_REFINED,
    STATUS_REFINING,
    append_refine_log,
    locate_task_dir,
    run_refine_engine,
)
from coco_flow.services.queries.task_detail import read_json_file


def refine_task(task_id: str, settings: Settings | None = None, on_log: LogHandler | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_INITIALIZED, STATUS_INPUT_READY, STATUS_REFINING, STATUS_REFINED}:
        raise ValueError(f"task status {status} does not allow refine")

    logger = on_log or (lambda line: append_refine_log(task_dir, line))
    owns_log_lifecycle = on_log is None
    started_at = datetime.now().astimezone()
    if owns_log_lifecycle:
        logger("=== REFINE START ===")
        logger(f"task_id: {task_id}")
        logger(f"task_dir: {task_dir}")
        logger(f"executor: {cfg.refine_executor}")

    try:
        result = run_refine_engine(task_dir, task_meta, cfg, logger)
        _write_markdown_artifact(task_dir / "prd-refined.md", result.refined_markdown)
        for name, payload in result.intermediate_artifacts.items():
            _write_intermediate_artifact(task_dir / name, payload)
        _write_json_artifact(
            task_dir / "refine-result.json",
            {
                "task_id": task_id,
                "status": result.status,
                "skills_used": result.skills_used,
                "selected_skill_ids": result.selected_skill_ids,
                "intermediate_artifacts": sorted(result.intermediate_artifacts.keys()),
                "updated_at": datetime.now().astimezone().isoformat(),
            },
        )
        task_meta["status"] = result.status
        task_meta["updated_at"] = datetime.now().astimezone().isoformat()
        (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
        return result.status
    except Exception as error:
        if owns_log_lifecycle:
            logger(f"error: {error}")
            logger(f"status: {status}")
        raise
    finally:
        if owns_log_lifecycle:
            duration = datetime.now().astimezone() - started_at
            logger(f"duration: {round(duration.total_seconds(), 3)}s")
            logger("=== REFINE END ===")


def start_refining_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {
        STATUS_INITIALIZED,
        STATUS_INPUT_READY,
        STATUS_REFINED,
        "designed",
        "planned",
        "partially_coded",
        "coded",
        "failed",
    }:
        raise ValueError(f"task status {status} does not allow refine")

    _reset_refine_outputs(task_dir)
    task_meta["status"] = STATUS_REFINING
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _sync_repo_status(task_dir, STATUS_INITIALIZED)
    return STATUS_REFINING


def _write_markdown_artifact(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _write_json_artifact(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_intermediate_artifact(path: Path, payload: str | dict[str, object]) -> None:
    if isinstance(payload, dict):
        _write_json_artifact(path, payload)
        return
    _write_markdown_artifact(path, payload)


def _reset_refine_outputs(task_dir: Path) -> None:
    for name in (
        "prd-refined.md",
        "refine-intent.json",
        "refine-query.json",
        "refine-skills-selection.json",
        "refine-skills-read.md",
        "refine-verify.json",
        "refine-result.json",
        "refine.log",
    ):
        path = task_dir / name
        if path.exists():
            path.unlink()
    for path in task_dir.glob(".refine-template-*.md"):
        path.unlink()
    for name in (
        "design.md",
        "design.log",
        "design-change-points.json",
        "design-repo-assignment.json",
        "design-research.json",
        "design-repo-responsibility-matrix.json",
        "design-skills-brief.md",
        "design-repo-binding.json",
        "design-sections.json",
        "design-verify.json",
        "design-result.json",
        "plan.md",
        "plan-skills-selection.json",
        "plan-skills-brief.md",
        "plan-task-outline.json",
        "plan-work-items.json",
        "plan-execution-graph.json",
        "plan-validation.json",
        "plan-dependency-notes.json",
        "plan-risk-check.json",
        "plan-verify.json",
        "plan-result.json",
        "plan-scope.json",
        "plan-execution.json",
        "plan.log",
        "code-dispatch.json",
        "code-progress.json",
        "code-result.json",
        "code.log",
    ):
        path = task_dir / name
        if path.exists():
            path.unlink()
    for directory in ("code-results", "code-logs", "code-verify", "diffs"):
        path = task_dir / directory
        if path.exists():
            shutil.rmtree(path)


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
