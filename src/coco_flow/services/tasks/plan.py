from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from coco_flow.config import Settings, load_settings
from coco_flow.engines.plan import (
    LogHandler,
    STATUS_FAILED,
    STATUS_PLANNED,
    STATUS_PLANNING,
    append_plan_log,
    locate_task_dir,
    run_plan_engine,
)
from coco_flow.services.queries.task_detail import read_json_file


def plan_task(task_id: str, settings: Settings | None = None, on_log: LogHandler | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    if not (task_dir / "design.md").exists():
        raise ValueError(f"task {task_id} 尚未生成 design.md，不能执行 plan")

    status = str(task_meta.get("status") or "")
    if status not in {"designed", STATUS_PLANNED, STATUS_PLANNING, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow plan")

    logger = on_log or (lambda line: append_plan_log(task_dir, line))
    owns_log_lifecycle = on_log is None
    started_at = datetime.now().astimezone()
    if owns_log_lifecycle:
        logger("=== PLAN START ===")
        logger(f"task_id: {task_id}")
        logger(f"task_dir: {task_dir}")
        logger(f"executor: {cfg.plan_executor}")

    try:
        result = run_plan_engine(task_dir, task_meta, cfg, logger)
        (task_dir / "plan.md").write_text(result.plan_markdown, encoding="utf-8")
        for name, payload in result.intermediate_artifacts.items():
            _write_intermediate_artifact(task_dir / name, payload)
        _update_task_status(task_dir, task_meta, result.status)
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
            logger("=== PLAN END ===")


def start_planning_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    if not (task_dir / "design.md").exists():
        raise ValueError(f"task {task_id} 尚未生成 design.md，不能执行 plan")

    status = str(task_meta.get("status") or "")
    if status not in {"designed", STATUS_PLANNED, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow plan")

    _reset_plan_outputs(task_dir)
    _update_task_status(task_dir, task_meta, STATUS_PLANNING)
    return STATUS_PLANNING


def mark_task_failed(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    _update_task_status(task_dir, task_meta, STATUS_FAILED)
    return STATUS_FAILED


def _write_intermediate_artifact(path: Path, payload: str | dict[str, object]) -> None:
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(payload.rstrip() + "\n", encoding="utf-8")


def _update_task_status(task_dir: Path, task_meta: dict[str, object], status: str) -> None:
    task_meta["status"] = status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    repos_meta = read_json_file(task_dir / "repos.json")
    raw_repos = repos_meta.get("repos")
    if isinstance(raw_repos, list):
        for item in raw_repos:
            if isinstance(item, dict):
                item["status"] = status
        (task_dir / "repos.json").write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reset_plan_outputs(task_dir: Path) -> None:
    for name in (
        "plan.md",
        "plan.log",
        "plan-skills-selection.json",
        "plan-skills-brief.md",
        "plan-knowledge-selection.json",
        "plan-knowledge-brief.md",
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
    ):
        path = task_dir / name
        if path.exists():
            path.unlink()
    for pattern in (".plan-template-*.md", ".plan-task-outline-*.json", ".plan-verify-*.json"):
        for path in task_dir.glob(pattern):
            path.unlink()
