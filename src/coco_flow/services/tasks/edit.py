from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil

from coco_flow.config import Settings, load_settings
from coco_flow.services.queries.task_detail import read_artifact_content, read_json_file
from coco_flow.services.tasks.refine import locate_task_dir

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
STATUS_PLANNED = "planned"

EDIT_RULES = {
    "prd.source.md": {
        "allowed": {STATUS_INITIALIZED, STATUS_REFINED, STATUS_PLANNED},
        "next_status": STATUS_INITIALIZED,
        "invalidate": [
            "prd-refined.md",
            "refine-intent.json",
            "refine-knowledge-selection.json",
            "refine-knowledge-brief.md",
            "refine-result.json",
            "plan-knowledge-selection.json",
            "plan-knowledge-brief.md",
            "design.md",
            "plan.md",
            "refine.log",
            "plan.log",
            "code-result.json",
            "code.log",
        ],
        "invalidate_dirs": ["code-results", "code-logs", "diffs"],
    },
    "prd-refined.md": {
        "allowed": {STATUS_REFINED, STATUS_PLANNED},
        "next_status": STATUS_REFINED,
        "invalidate": [
            "design.md",
            "plan.md",
            "plan-knowledge-selection.json",
            "plan-knowledge-brief.md",
            "plan.log",
            "code-result.json",
            "code.log",
        ],
        "invalidate_dirs": ["code-results", "code-logs", "diffs"],
    },
    "design.md": {
        "allowed": {STATUS_PLANNED},
        "next_status": STATUS_PLANNED,
        "invalidate": [],
        "invalidate_dirs": [],
    },
    "plan.md": {
        "allowed": {STATUS_PLANNED},
        "next_status": STATUS_PLANNED,
        "invalidate": [],
        "invalidate_dirs": [],
    },
}


def update_artifact(
    task_id: str, name: str, content: str, settings: Settings | None = None
) -> tuple[str, str]:
    cfg = settings or load_settings()
    rule = EDIT_RULES.get(name)
    if rule is None:
        raise ValueError(f"artifact {name} 不支持编辑")

    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in rule["allowed"]:
        raise ValueError(f"当前状态为 {status}，不能编辑 {name}")

    trimmed = content.strip()
    if not trimmed:
        raise ValueError(f"{name} 不能为空")

    (task_dir / name).write_text(trimmed + "\n")

    for artifact_name in rule["invalidate"]:
        remove_path(task_dir / artifact_name)
    for dir_name in rule["invalidate_dirs"]:
        remove_tree(task_dir / dir_name)

    next_status = str(rule["next_status"])
    task_meta["status"] = next_status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    sync_repo_statuses(task_dir, next_status)
    return next_status, read_artifact_content(task_dir, name)


def remove_path(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def sync_repo_statuses(task_dir: Path, status: str) -> None:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        return
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo["status"] = status
        repo["branch"] = ""
        repo["worktree"] = ""
        repo["commit"] = ""
    repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")
