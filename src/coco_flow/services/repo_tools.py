from __future__ import annotations

from pathlib import Path
import subprocess

from coco_flow.services import TaskStore
from coco_flow.services.view_compat import format_timestamp


def list_recent_repos(store: TaskStore) -> list[dict[str, object]]:
    aggregates: dict[str, dict[str, object]] = {}
    for task in store.list_tasks(limit=1000):
        detail = store.get_task(task.task_id)
        if detail is None:
            continue
        for repo in detail.repos:
            key = repo.repo_id or Path(repo.path).name
            current = aggregates.get(key)
            if current is None:
                aggregates[key] = {
                    "id": key,
                    "displayName": key,
                    "path": repo.path,
                    "taskCount": 1,
                    "lastSeenAt": format_timestamp(detail.updated_at),
                    "_rawLastSeenAt": detail.updated_at or "",
                }
            else:
                current["taskCount"] = int(current["taskCount"]) + 1
                current_last_seen_raw = str(current.get("_rawLastSeenAt", ""))
                detail_updated_at = detail.updated_at or ""
                if detail_updated_at > current_last_seen_raw:
                    current["lastSeenAt"] = format_timestamp(detail_updated_at)
                    current["_rawLastSeenAt"] = detail_updated_at
    repos = list(aggregates.values())
    repos.sort(
        key=lambda item: (str(item.get("_rawLastSeenAt", "")), int(item.get("taskCount", 0))),
        reverse=True,
    )
    for repo in repos:
        repo.pop("_rawLastSeenAt", None)
    return repos


def validate_repo_path(path: str) -> dict[str, object]:
    repo_path = Path(path).expanduser().resolve()
    if not repo_path.exists():
        raise ValueError(f"repo 路径不存在: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"repo 路径不是目录: {repo_path}")
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise ValueError(f"目录不是 git 仓库: {repo_path}")
    return {
        "id": repo_path.name,
        "displayName": repo_path.name,
        "path": str(repo_path),
    }
