from __future__ import annotations

from pathlib import Path
import json
import subprocess
from typing import Callable

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
STATUS_PLANNING = "planning"
STATUS_PLANNED = "planned"
STATUS_CODING = "coding"
STATUS_PARTIALLY_CODED = "partially_coded"
STATUS_CODED = "coded"
STATUS_ARCHIVED = "archived"
STATUS_FAILED = "failed"


def sanitize_repo_name(repo_id: str) -> str:
    sanitized = []
    for char in repo_id.strip():
        if char.isalnum():
            sanitized.append(char.lower())
        else:
            sanitized.append("_")
    value = "".join(sanitized).strip("_")
    return value or "repo"


def repo_code_result_path(task_dir: Path, repo_id: str) -> Path:
    return task_dir / "code-results" / f"{sanitize_repo_name(repo_id)}.json"


def repo_code_log_path(task_dir: Path, repo_id: str) -> Path:
    return task_dir / "code-logs" / f"{sanitize_repo_name(repo_id)}.log"


def repo_diff_patch_path(task_dir: Path, repo_id: str) -> Path:
    return task_dir / "diffs" / f"{sanitize_repo_name(repo_id)}.patch"


def repo_diff_summary_path(task_dir: Path, repo_id: str) -> Path:
    return task_dir / "diffs" / f"{sanitize_repo_name(repo_id)}.json"


def repo_code_verify_path(task_dir: Path, repo_id: str) -> Path:
    return task_dir / "code-verify" / f"{sanitize_repo_name(repo_id)}.json"


def read_repo_code_result(task_dir: Path, repo_id: str) -> dict[str, object]:
    return read_json_file(repo_code_result_path(task_dir, repo_id))


def read_repo_code_result_raw(task_dir: Path, repo_id: str) -> str:
    return repo_code_result_path(task_dir, repo_id).read_text()


def read_repo_code_log(task_dir: Path, repo_id: str) -> str:
    return repo_code_log_path(task_dir, repo_id).read_text()


def read_repo_diff_summary(task_dir: Path, repo_id: str) -> dict[str, object]:
    return read_json_file(repo_diff_summary_path(task_dir, repo_id))


def read_repo_diff_patch(task_dir: Path, repo_id: str) -> str:
    return repo_diff_patch_path(task_dir, repo_id).read_text()


def read_repo_code_verify(task_dir: Path, repo_id: str) -> dict[str, object]:
    return read_json_file(repo_code_verify_path(task_dir, repo_id))


def write_repo_code_result(task_dir: Path, repo_id: str, payload: dict[str, object]) -> None:
    path = repo_code_result_path(task_dir, repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_repo_code_log(task_dir: Path, repo_id: str, content: str) -> None:
    path = repo_code_log_path(task_dir, repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def write_repo_code_verify(task_dir: Path, repo_id: str, payload: dict[str, object]) -> None:
    path = repo_code_verify_path(task_dir, repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def write_repo_diff_artifacts(
    task_dir: Path,
    repo_id: str,
    branch: str,
    commit: str,
    files: list[str],
    patch: str,
) -> None:
    if not repo_id.strip() or not commit.strip():
        return
    patch_path = repo_diff_patch_path(task_dir, repo_id)
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch)
    additions, deletions = parse_unified_diff_stats(patch)
    summary = {
        "repo_id": repo_id,
        "commit": commit,
        "branch": branch,
        "files": files,
        "additions": additions,
        "deletions": deletions,
    }
    repo_diff_summary_path(task_dir, repo_id).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


def remove_repo_runtime_artifacts(task_dir: Path, repo_id: str, keep_results: bool) -> None:
    if not keep_results:
        _remove_path(repo_code_result_path(task_dir, repo_id))
        _remove_path(repo_code_log_path(task_dir, repo_id))
        _remove_path(repo_code_verify_path(task_dir, repo_id))
        _remove_path(repo_diff_patch_path(task_dir, repo_id))
        _remove_path(repo_diff_summary_path(task_dir, repo_id))


def clean_files_written(files: list[str], repo_path: str, worktree: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    prefixes = [
        (worktree.strip() + "/") if worktree.strip() else "",
        (str(Path(worktree).resolve()) + "/") if worktree.strip() else "",
        (repo_path.strip() + "/") if repo_path.strip() else "",
        (str(Path(repo_path).resolve()) + "/") if repo_path.strip() else "",
    ]
    for file in files:
        current = file.strip()
        if not current:
            continue
        for prefix in prefixes:
            if prefix and current.startswith(prefix):
                current = current[len(prefix):]
        current = current.strip()
        if not current or current in {".", Path(repo_path).name}:
            continue
        if current in seen:
            continue
        seen.add(current)
        cleaned.append(current)
    return cleaned


def summarize_repo_failure(task_dir: Path, repo_id: str, report: dict[str, object]) -> str:
    error = str(report.get("error") or "").strip()
    if error:
        return trim_failure_log_line(error)
    summary = str(report.get("summary") or "").strip()
    if str(report.get("status") or "") == STATUS_FAILED and summary:
        return trim_failure_log_line(summary)
    try:
        content = read_repo_code_log(task_dir, repo_id)
    except OSError:
        return ""
    for line in reversed(content.splitlines()):
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            continue
        if "error" in lower or "failed" in lower:
            return trim_failure_log_line(stripped)
    return ""


def trim_failure_log_line(line: str) -> str:
    value = line.strip()
    if len(value) > 140:
        return value[:140] + "..."
    return value


def aggregate_task_status(current: str, repos_meta: dict[str, object]) -> str:
    repos = repos_meta.get("repos")
    if not isinstance(repos, list) or not repos:
        return current

    all_archived = True
    all_planned_like = True
    has_coding = False
    has_coded = False
    has_completed = False
    has_failed = False

    for item in repos:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status == STATUS_ARCHIVED:
            has_completed = True
            all_planned_like = False
            continue
        if status == STATUS_CODED:
            has_coded = True
            has_completed = True
            all_archived = False
            all_planned_like = False
            continue
        if status == STATUS_CODING:
            has_coding = True
            all_archived = False
            all_planned_like = False
            continue
        if status == STATUS_FAILED:
            has_failed = True
            all_archived = False
            all_planned_like = False
            continue
        if status in {STATUS_INITIALIZED, STATUS_REFINED, STATUS_PLANNING, STATUS_PLANNED, "", "pending"}:
            all_archived = False
            continue
        all_archived = False
        all_planned_like = False

    if all_archived:
        return STATUS_ARCHIVED
    if has_failed:
        return STATUS_FAILED
    if has_coding:
        return STATUS_CODING
    if has_completed and not all_coded_or_archived(repos):
        return STATUS_PARTIALLY_CODED
    if has_coded and all_coded_or_archived(repos):
        return STATUS_CODED
    if all_planned_like:
        if current in {STATUS_INITIALIZED, STATUS_REFINED, STATUS_PLANNING, STATUS_PLANNED}:
            return current
        return STATUS_PLANNED
    return current


def all_coded_or_archived(repos: list[object]) -> bool:
    matched = False
    for item in repos:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status not in {STATUS_CODED, STATUS_ARCHIVED}:
            return False
        matched = True
    return matched


def sync_task_status_from_repos(task_dir: Path) -> str:
    repos_path = task_dir / "repos.json"
    task_path = task_dir / "task.json"
    repos_meta = read_json_file(repos_path)
    task_meta = read_json_file(task_path)
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_dir.name}")
    current = str(task_meta.get("status") or "")
    task_meta["repo_count"] = len(repos_meta.get("repos") or [])
    task_meta["updated_at"] = datetime_now_iso()
    task_meta["status"] = aggregate_task_status(current, repos_meta)
    task_path.write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    return str(task_meta["status"])


def update_repo_binding(
    task_dir: Path,
    repo_id: str,
    mutator: Callable[[dict[str, object]], None],
) -> str:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        raise ValueError(f"repos metadata missing: {task_dir.name}")
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        if str(repo.get("id") or "") == repo_id:
            mutator(repo)
            repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")
            return sync_task_status_from_repos(task_dir)
    raise ValueError(f"task 未绑定 repo {repo_id}")


def resolve_task_repo(task_dir: Path, requested_repo_id: str) -> dict[str, object]:
    repos_meta = read_json_file(task_dir / "repos.json")
    repos = repos_meta.get("repos")
    if not isinstance(repos, list) or not repos:
        raise ValueError("task 未绑定 repo")
    repo_id = requested_repo_id.strip()
    if not repo_id:
        if len(repos) == 1:
            repo = repos[0]
            if isinstance(repo, dict):
                return repo
        options = sorted(str(repo.get("id") or "") for repo in repos if isinstance(repo, dict))
        raise ValueError(f"该 task 关联多个 repo，请显式指定 repo。可选 repo: {', '.join(options)}")
    for repo in repos:
        if isinstance(repo, dict) and str(repo.get("id") or "") == repo_id:
            return repo
    options = sorted(str(repo.get("id") or "") for repo in repos if isinstance(repo, dict))
    raise ValueError(f"task 未绑定 repo {repo_id}。可选 repo: {', '.join(options)}")


def parse_unified_diff_stats(patch: str) -> tuple[int, int]:
    additions = 0
    deletions = 0
    for line in patch.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions


def read_commit_patch(repo_root: str, commit: str) -> str:
    result = subprocess.run(
        ["git", "show", "--format=medium", "--patch", "--stat=0", "--no-ext-diff", commit],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "读取 commit patch 失败")
    return result.stdout


def datetime_now_iso() -> str:
    from datetime import datetime

    return datetime.now().astimezone().isoformat()


def _remove_path(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
