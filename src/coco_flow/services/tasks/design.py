from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

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
    if status not in {"refined", STATUS_DESIGNING, STATUS_DESIGNED, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow design")

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
        for name, payload in result.intermediate_artifacts.items():
            _write_intermediate_artifact(task_dir / name, payload)
        _write_intermediate_artifact(
            task_dir / "design-result.json",
            {
                "task_id": task_id,
                "status": result.status,
                "repo_binding": result.repo_binding_payload,
                "sections": result.sections_payload,
                "intermediate_artifacts": sorted(result.intermediate_artifacts.keys()),
                "updated_at": datetime.now().astimezone().isoformat(),
            },
        )
        task_meta["status"] = result.status
        task_meta["updated_at"] = datetime.now().astimezone().isoformat()
        (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    if status not in {"refined", STATUS_DESIGNED, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow design")

    _reset_design_outputs(task_dir)
    task_meta["status"] = STATUS_DESIGNING
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return STATUS_DESIGNING


def _write_intermediate_artifact(path: Path, payload: str | dict[str, object]) -> None:
    if isinstance(payload, dict):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    path.write_text(payload.rstrip() + "\n", encoding="utf-8")


def _reset_design_outputs(task_dir: Path) -> None:
    for name in (
        "design.md",
        "design.log",
        "design-change-points.json",
        "design-repo-assignment.json",
        "design-research.json",
        "design-knowledge-brief.md",
        "design-repo-binding.json",
        "design-sections.json",
        "design-verify.json",
        "design-result.json",
    ):
        path = task_dir / name
        if path.exists():
            path.unlink()
    for pattern in (".design-template-*.md", ".design-research-*.json", ".design-repo-binding-*.json", ".design-verify-*.json"):
        for path in task_dir.glob(pattern):
            path.unlink()
