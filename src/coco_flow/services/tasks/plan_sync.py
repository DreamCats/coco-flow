from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from coco_flow.config import Settings, load_settings
from coco_flow.engines.plan.compiler import build_structured_plan_artifacts_from_repo_markdowns, validate_plan_artifacts
from coco_flow.engines.plan.input import locate_task_dir, prepare_plan_input
from coco_flow.services.queries.task_detail import read_json_file


def sync_plan_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    if str(task_meta.get("status") or "") != "planned":
        raise ValueError("只有 planned 状态可以同步 Plan 执行契约")

    prepared = prepare_plan_input(task_dir, task_meta)
    repo_markdowns = _read_repo_markdowns(task_dir, [scope.repo_id for scope in prepared.repo_scopes])
    if not repo_markdowns:
        raise ValueError("当前没有可同步的 plan-repos markdown")

    work_items_payload, graph_payload, validation_payload, result_payload = build_structured_plan_artifacts_from_repo_markdowns(
        prepared,
        repo_markdowns,
        read_json_file(task_dir / "plan-work-items.json"),
    )
    issues = validate_plan_artifacts(prepared, work_items_payload, graph_payload, validation_payload, repo_markdowns)
    if issues:
        raise ValueError("plan sync failed: " + "; ".join(issues[:5]))

    _write_json(task_dir / "plan-work-items.json", work_items_payload)
    _write_json(task_dir / "plan-execution-graph.json", graph_payload)
    _write_json(task_dir / "plan-validation.json", validation_payload)
    _write_json(task_dir / "plan-result.json", result_payload)
    _write_json(
        task_dir / "plan-sync.json",
        {
            "synced": True,
            "status": "synced_from_markdown",
            "reason": "Structured Plan artifacts were synced from edited repo plan Markdown.",
            "updated_at": datetime.now().astimezone().isoformat(),
        },
    )
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "planned"


def _read_repo_markdowns(task_dir: Path, repo_ids: list[str]) -> dict[str, str]:
    repo_dir = task_dir / "plan-repos"
    if not repo_dir.is_dir():
        return {}
    result: dict[str, str] = {}
    for repo_id in repo_ids:
        path = repo_dir / f"{_sanitize_repo_id(repo_id)}.md"
        if path.exists():
            result[repo_id] = path.read_text(encoding="utf-8")
    return result


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sanitize_repo_id(repo_id: str) -> str:
    chars = [char if char.isalnum() or char in {"-", "_", "."} else "_" for char in repo_id.strip()]
    return "".join(chars) or "repo"
