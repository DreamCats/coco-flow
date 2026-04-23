from __future__ import annotations

from pathlib import Path
import os

from coco_flow.services import TaskStore
from coco_flow.services.queries.skills import skills_root_path


def workspace_summary(store: TaskStore) -> dict[str, object]:
    tasks = store.list_tasks(limit=1000)
    repos_involved: set[str] = set()
    for task in tasks:
        detail = store.get_task(task.task_id)
        if detail is None:
            continue
        for repo in detail.repos:
            if repo.repo_id:
                repos_involved.add(repo.repo_id)

    cwd = Path.cwd().resolve()
    return {
        "repoRoot": str(cwd),
        "tasksRoot": str(store.settings.task_root),
        "skillsRoot": str(skills_root_path(store.settings)),
        "worktreeRoot": str(cwd.parent / ".coco-flow-worktree"),
        "reposInvolved": sorted(repos_involved),
        "taskCount": len(tasks),
        "product_name": "coco-flow",
        "config_root": str(store.settings.config_root),
        "task_root": str(store.settings.task_root),
        "cwd": os.getcwd(),
    }
