from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from coco_flow.models import TaskDetail, TaskSummary

_complexity_line = re.compile(r"(?m)^- complexity:\s*([^\s]+)\s*\((\d+)\)\s*$")


def format_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def task_list_item(summary: TaskSummary, detail: TaskDetail | None) -> dict[str, object]:
    repo_ids = [repo.repo_id for repo in detail.repos] if detail else []
    return {
        "id": summary.task_id,
        "title": summary.title,
        "status": summary.status,
        "sourceType": summary.source_type or "text",
        "updatedAt": format_timestamp(summary.updated_at or summary.created_at),
        "repoCount": detail.repo_count if detail else 0,
        "repoIds": repo_ids,
    }


def task_detail_item(detail: TaskDetail) -> dict[str, object]:
    return {
        "id": detail.task_id,
        "title": detail.title,
        "status": detail.status,
        "sourceType": detail.source_type or "text",
        "updatedAt": format_timestamp(detail.updated_at or detail.created_at),
        "owner": "local",
        "complexity": read_task_complexity(Path(detail.task_dir)),
        "nextAction": detail.next_action,
        "repoNext": [
            repo.repo_id
            for repo in detail.repos
            if repo.repo_id and (repo.status or "") in {"planned", "failed", "initialized", "refined"}
        ],
        "repos": [
            {
                "id": repo.repo_id,
                "displayName": repo.repo_id,
                "path": repo.path,
                "status": repo.status or "pending",
                "branch": repo.branch,
                "worktree": repo.worktree,
                "commit": repo.commit,
                "build": repo.build or infer_repo_build(repo.status, repo.commit),
                "failureHint": repo.failure_hint,
                "filesWritten": repo.files_written or [],
                "diffSummary": repo.diff_summary,
            }
            for repo in detail.repos
        ],
        "timeline": [
            {"label": item.label, "state": item.state, "detail": item.detail}
            for item in detail.timeline
        ],
        "artifacts": {
            artifact.name: artifact.content or ""
            for artifact in detail.artifacts
        },
    }


def read_task_complexity(task_dir: Path) -> str:
    plan_path = task_dir / "plan.md"
    if not plan_path.exists():
        return "未评估"
    try:
        content = plan_path.read_text()
    except OSError:
        return "未评估"
    match = _complexity_line.search(content)
    if match:
        return f"{match.group(1)} ({match.group(2)})"
    return "未评估"


def infer_repo_build(status: str | None, commit: str | None) -> str:
    if status == "coded" and commit:
        return "passed"
    if status == "failed":
        return "failed"
    return "n/a"
