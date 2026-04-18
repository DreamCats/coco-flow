from __future__ import annotations

from datetime import datetime

from coco_flow.config import Settings, load_settings
from coco_flow.engines.code import (
    EXECUTOR_LOCAL,
    EXECUTOR_NATIVE,
    LogHandler,
    STATUS_FAILED,
    append_code_log,
    build_code_runtime_state_for_task,
    locate_task_dir,
    run_code_engine,
    start_code_engine,
)
from coco_flow.services.queries.task_detail import read_json_file


def code_task(
    task_id: str,
    settings: Settings | None = None,
    repo_id: str = "",
    all_repos: bool = False,
    on_log: LogHandler | None = None,
    allow_coding_targets: bool = False,
) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    executor = cfg.code_executor.strip().lower()
    if executor not in {EXECUTOR_NATIVE, EXECUTOR_LOCAL}:
        raise ValueError(f"unknown code executor: {cfg.code_executor}")
    logger = on_log or (lambda line: append_code_log(task_dir, line))
    owns_log_lifecycle = on_log is None
    started_at = datetime.now().astimezone()
    if owns_log_lifecycle:
        logger("=== CODE START ===")
        logger(f"task_id: {task_id}")
        logger(f"task_dir: {task_dir}")
        logger(f"executor: {cfg.code_executor}")
        if repo_id:
            logger(f"repo_id: {repo_id}")
        if all_repos:
            logger("all_repos: true")
    try:
        status = run_code_engine(
            task_dir,
            task_meta,
            cfg,
            repo_id=repo_id,
            all_repos=all_repos,
            allow_coding_targets=allow_coding_targets,
            on_log=logger,
        )
        if owns_log_lifecycle:
            logger(f"status: {status}")
        return status
    except Exception as error:
        if owns_log_lifecycle:
            logger(f"error: {error}")
            logger(f"status: {STATUS_FAILED}")
        raise
    finally:
        if owns_log_lifecycle:
            duration = datetime.now().astimezone() - started_at
            logger(f"duration: {round(duration.total_seconds(), 3)}s")
            logger("=== CODE END ===")


def start_coding_task(
    task_id: str,
    settings: Settings | None = None,
    repo_id: str = "",
    all_repos: bool = False,
) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    return start_code_engine(
        task_dir,
        task_meta,
        repo_id=repo_id,
        all_repos=all_repos,
        allow_coding_targets=False,
    )


def build_code_runtime(task_id: str, settings: Settings | None = None) -> dict[str, object]:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    return build_code_runtime_state_for_task(task_dir, task_meta)
