from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil
import subprocess

from coco_flow.config import Settings, load_settings
from coco_flow.services.task_detail import read_json_file
from coco_flow.services.task_refine import locate_task_dir

STATUS_PLANNED = "planned"
STATUS_CODING = "coding"
STATUS_CODED = "coded"
STATUS_FAILED = "failed"
STATUS_ARCHIVED = "archived"
EXECUTOR_LOCAL = "local"
EXECUTOR_NATIVE = "native"


def reset_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_CODING, STATUS_CODED, STATUS_FAILED}:
        raise ValueError(f"task status {status} does not allow reset")

    if cfg.code_executor.strip().lower() in {EXECUTOR_LOCAL, EXECUTOR_NATIVE}:
        return _local_reset(task_dir)
    raise ValueError(f"unknown code executor: {cfg.code_executor}")


def archive_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_CODED, STATUS_ARCHIVED}:
        raise ValueError(f"task status {status} does not allow archive")

    if cfg.code_executor.strip().lower() in {EXECUTOR_LOCAL, EXECUTOR_NATIVE}:
        return _local_archive(task_dir)
    raise ValueError(f"unknown code executor: {cfg.code_executor}")


def _local_reset(task_dir: Path) -> str:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if isinstance(repos, list):
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            worktree = str(repo.get("worktree") or "").strip()
            branch = str(repo.get("branch") or "").strip()
            repo_path = str(repo.get("path") or "").strip()
            cleanup_worktree(repo_path, worktree)
            delete_branch(repo_path, branch)
            repo["status"] = STATUS_PLANNED
            repo["branch"] = ""
            repo["worktree"] = ""
            repo["commit"] = ""
        repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")

    remove_path(task_dir / "code-result.json")
    remove_path(task_dir / "code.log")
    remove_tree(task_dir / "code-results")
    update_task_status(task_dir, STATUS_PLANNED)
    return STATUS_PLANNED


def _local_archive(task_dir: Path) -> str:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if isinstance(repos, list):
        for repo in repos:
            if not isinstance(repo, dict):
                continue
            worktree = str(repo.get("worktree") or "").strip()
            branch = str(repo.get("branch") or "").strip()
            repo_path = str(repo.get("path") or "").strip()
            cleanup_worktree(repo_path, worktree)
            delete_branch(repo_path, branch)
            repo["status"] = STATUS_ARCHIVED
        repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")

    update_task_status(task_dir, STATUS_ARCHIVED)
    return STATUS_ARCHIVED


def update_task_status(task_dir: Path, status: str) -> None:
    task_meta = read_json_file(task_dir / "task.json")
    task_meta["status"] = status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
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


def remove_path(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
