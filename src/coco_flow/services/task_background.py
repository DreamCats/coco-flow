from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import threading

from coco_flow.config import Settings
from coco_flow.services.task_detail import read_json_file
from coco_flow.services.task_plan import mark_task_failed, plan_task
from coco_flow.services.task_refine import refine_task

STATUS_FAILED = "failed"
REFINE_LOG_NAME = "refine.log"


def start_background_refine(task_id: str, settings: Settings) -> None:
    worker = threading.Thread(
        target=_run_background_refine,
        args=(task_id, settings),
        name=f"coco-flow-refine-{task_id}",
        daemon=True,
    )
    worker.start()


def start_background_plan(task_id: str, settings: Settings) -> None:
    worker = threading.Thread(
        target=_run_background_plan,
        args=(task_id, settings),
        name=f"coco-flow-plan-{task_id}",
        daemon=True,
    )
    worker.start()


def _run_background_refine(task_id: str, settings: Settings) -> None:
    task_dir = settings.task_root / task_id
    started_at = datetime.now().astimezone()
    _append_log_line(task_dir, "=== REFINE START ===")
    _append_log_line(task_dir, f"task_id: {task_id}")
    _append_log_line(task_dir, f"executor: {settings.refine_executor}")

    try:
        status = refine_task(task_id, settings=settings)
        _append_log_line(task_dir, f"status: {status}")
    except Exception as error:
        _append_log_line(task_dir, f"error: {error}")
        _mark_task_failed(task_dir)
        _append_log_line(task_dir, f"status: {STATUS_FAILED}")
    finally:
        duration = datetime.now().astimezone() - started_at
        _append_log_line(task_dir, f"duration: {round(duration.total_seconds(), 3)}s")
        _append_log_line(task_dir, "=== REFINE END ===")


def _run_background_plan(task_id: str, settings: Settings) -> None:
    task_dir = settings.task_root / task_id
    started_at = datetime.now().astimezone()
    _append_named_log_line(task_dir, "plan.log", "=== PLAN START ===")
    _append_named_log_line(task_dir, "plan.log", f"task_id: {task_id}")
    _append_named_log_line(task_dir, "plan.log", f"task_dir: {task_dir}")
    _append_named_log_line(task_dir, "plan.log", f"executor: {settings.plan_executor}")

    try:
        status = plan_task(
            task_id,
            settings=settings,
            on_log=lambda line: _append_named_log_line(task_dir, "plan.log", line),
        )
        _append_named_log_line(task_dir, "plan.log", f"status: {status}")
    except Exception as error:
        _append_named_log_line(task_dir, "plan.log", f"error: {error}")
        mark_task_failed(task_id, settings=settings)
        _append_named_log_line(task_dir, "plan.log", f"status: {STATUS_FAILED}")
    finally:
        duration = datetime.now().astimezone() - started_at
        _append_named_log_line(task_dir, "plan.log", f"duration: {round(duration.total_seconds(), 3)}s")
        _append_named_log_line(task_dir, "plan.log", "=== PLAN END ===")


def _append_log_line(task_dir: Path, line: str) -> None:
    _append_named_log_line(task_dir, REFINE_LOG_NAME, line)


def _append_named_log_line(task_dir: Path, file_name: str, line: str) -> None:
    task_dir.mkdir(parents=True, exist_ok=True)
    log_path = task_dir / file_name
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{timestamp} {line}\n")


def _mark_task_failed(task_dir: Path) -> None:
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        return
    task_meta["status"] = STATUS_FAILED
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
