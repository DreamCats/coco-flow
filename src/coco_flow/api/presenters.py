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
        "sourceFetchError": detail.source_fetch_error or "",
        "sourceFetchErrorCode": detail.source_fetch_error_code or "",
        "updatedAt": format_timestamp(detail.updated_at or detail.created_at),
        "owner": "local",
        "complexity": read_task_complexity(Path(detail.task_dir)),
        "nextAction": detail.next_action,
        "diagnosis": (
            {
                "stage": detail.diagnosis.stage,
                "ok": detail.diagnosis.ok,
                "severity": detail.diagnosis.severity,
                "failureType": detail.diagnosis.failure_type,
                "nextAction": detail.diagnosis.next_action,
                "reason": detail.diagnosis.reason,
                "issueCount": detail.diagnosis.issue_count,
                "issues": detail.diagnosis.issues,
                "instructions": detail.diagnosis.instructions,
            }
            if detail.diagnosis
            else None
        ),
        "codeDispatch": (
            {
                "totalBatches": detail.code_dispatch.total_batches,
                "repoIds": detail.code_dispatch.repo_ids,
                "batchIds": detail.code_dispatch.batch_ids,
            }
            if detail.code_dispatch
            else None
        ),
        "codeProgress": (
            {
                "status": detail.code_progress.status or detail.status,
                "totalBatches": detail.code_progress.total_batches,
                "completedBatches": detail.code_progress.completed_batches,
                "runningBatches": detail.code_progress.running_batches,
                "blockedBatches": detail.code_progress.blocked_batches,
                "failedBatches": detail.code_progress.failed_batches,
                "totalWorkItems": detail.code_progress.total_work_items,
                "completedWorkItems": detail.code_progress.completed_work_items,
            }
            if detail.code_progress
            else None
        ),
        "repoNext": [
            repo.repo_id
            for repo in detail.repos
            if repo.repo_id
            and (repo.status or "") in {"planned", "failed", "initialized", "refined"}
            and (repo.failure_type or "") != "blocked_by_dependency"
        ],
        "repos": [
            {
                "id": repo.repo_id,
                "displayName": repo.repo_id,
                "path": repo.path,
                "status": repo.status or "pending",
                "scopeTier": repo.scope_tier,
                "confidence": repo.confidence,
                "executionMode": repo.execution_mode,
                "batchId": repo.batch_id,
                "batchStatus": repo.batch_status or repo.status or "pending",
                "workItemIds": repo.work_item_ids or [],
                "dependsOnBatchIds": repo.depends_on_batch_ids or [],
                "branch": repo.branch,
                "worktree": repo.worktree,
                "commit": repo.commit,
                "build": repo.build or infer_repo_build(repo.status, repo.commit),
                "failureType": repo.failure_type,
                "failureHint": repo.failure_hint,
                "failureAction": repo.failure_action,
                "filesWritten": repo.files_written or [],
                "diffSummary": repo.diff_summary,
                "verifyResult": repo.verify_result,
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
