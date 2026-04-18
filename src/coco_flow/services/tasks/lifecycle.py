from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess

from coco_flow.config import Settings, load_settings
from coco_flow.services.runtime.repo_state import (
    STATUS_ARCHIVED,
    STATUS_CODED,
    STATUS_CODING,
    STATUS_FAILED,
    STATUS_PLANNED,
    remove_repo_runtime_artifacts,
    resolve_task_repo,
    sync_task_status_from_repos,
    update_repo_binding,
)
from coco_flow.services.queries.task_detail import read_json_file
from coco_flow.services.tasks.refine import locate_task_dir


def reset_task(task_id: str, settings: Settings | None = None, repo_id: str = "") -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    repo = resolve_task_repo(task_dir, repo_id)
    current_status = str(repo.get("status") or "")
    if current_status not in {STATUS_CODED, STATUS_FAILED}:
        raise ValueError(f"repo {repo.get('id') or ''} 当前状态为 {current_status}，不能执行 reset")

    repo_path = str(repo.get("path") or "").strip()
    worktree = str(repo.get("worktree") or "").strip()
    branch = str(repo.get("branch") or "").strip()
    cleanup_worktree(repo_path, worktree)
    delete_branch(repo_path, branch)
    remove_repo_runtime_artifacts(task_dir, str(repo.get("id") or ""), keep_results=False)

    status = update_repo_binding(
        task_dir,
        str(repo.get("id") or ""),
        lambda current: current.update(
            {
                "status": STATUS_PLANNED,
                "branch": "",
                "worktree": "",
                "commit": "",
            }
        ),
    )
    sync_task_meta(task_dir, status)
    refresh_task_level_code_artifacts(task_dir)
    return status


def archive_task(task_id: str, settings: Settings | None = None, repo_id: str = "") -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    repo = resolve_task_repo(task_dir, repo_id)
    current_status = str(repo.get("status") or "")
    if current_status != STATUS_CODED:
        raise ValueError(f"repo {repo.get('id') or ''} 当前状态为 {current_status}，不能执行 archive")

    repo_path = str(repo.get("path") or "").strip()
    worktree = str(repo.get("worktree") or "").strip()
    branch = str(repo.get("branch") or "").strip()
    cleanup_worktree(repo_path, worktree)
    delete_branch(repo_path, branch)

    status = update_repo_binding(
        task_dir,
        str(repo.get("id") or ""),
        lambda current: current.update(
            {
                "status": STATUS_ARCHIVED,
                "branch": branch,
                "worktree": "",
            }
        ),
    )
    sync_task_meta(task_dir, status)
    refresh_task_level_code_artifacts(task_dir)
    return status


def refresh_task_level_code_artifacts(task_dir: Path) -> None:
    code_results_dir = task_dir / "code-results"
    if not code_results_dir.is_dir():
        remove_file(task_dir / "code-dispatch.json")
        remove_file(task_dir / "code-progress.json")
        remove_file(task_dir / "code-result.json")
        remove_file(task_dir / "code.log")
        return

    result_paths = sorted(code_results_dir.glob("*.json"))
    if not result_paths:
        remove_file(task_dir / "code-dispatch.json")
        remove_file(task_dir / "code-progress.json")
        remove_file(task_dir / "code-result.json")
        remove_file(task_dir / "code.log")
        return

    latest_result = json.loads(result_paths[-1].read_text())
    (task_dir / "code-result.json").write_text(json.dumps(latest_result, ensure_ascii=False, indent=2) + "\n")

    code_logs_dir = task_dir / "code-logs"
    log_contents: list[str] = []
    if code_logs_dir.is_dir():
        for path in sorted(code_logs_dir.glob("*.log")):
            log_contents.append(path.read_text())
    if log_contents:
        (task_dir / "code.log").write_text("\n".join(log_contents))
    else:
        remove_file(task_dir / "code.log")


def sync_task_meta(task_dir: Path, status: str) -> None:
    task_meta = read_json_file(task_dir / "task.json")
    task_meta["status"] = status
    task_meta["updated_at"] = from_repo_status_timestamp()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")


def cleanup_worktree(repo_root: str, worktree: str) -> None:
    if not repo_root or not worktree:
        return
    if not Path(worktree).exists():
        return
    result = subprocess.run(
        ["git", "worktree", "remove", "--force", worktree],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        shutil.rmtree(worktree, ignore_errors=True)


def delete_branch(repo_root: str, branch: str) -> None:
    if not repo_root or not branch:
        return
    subprocess.run(
        ["git", "branch", "-D", branch],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )


def remove_file(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def from_repo_status_timestamp() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()
