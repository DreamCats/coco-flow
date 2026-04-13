from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings, load_settings
from coco_flow.services.task_detail import read_json_file
from coco_flow.services.task_refine import locate_task_dir

STATUS_PLANNED = "planned"
STATUS_CODING = "coding"
STATUS_CODED = "coded"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"


def code_task(task_id: str, settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in {STATUS_PLANNED, STATUS_CODING}:
        raise ValueError(f"task status {status} does not allow code")

    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if not isinstance(repos, list) or not repos:
        raise ValueError("task has no bound repos")

    executor = cfg.code_executor.strip().lower()
    if executor == EXECUTOR_NATIVE:
        return code_task_native(task_id, task_dir, task_meta, repos_path, repos_meta, repos, cfg)
    if executor == EXECUTOR_LOCAL:
        return code_task_local(task_id, task_dir, task_meta, repos_path, repos_meta, repos)
    raise ValueError(f"unknown code executor: {cfg.code_executor}")


def code_task_local(
    task_id: str,
    task_dir: Path,
    task_meta: dict[str, object],
    repos_path: Path,
    repos_meta: dict[str, object],
    repos: list[object],
) -> str:
    repo_dicts = [repo for repo in repos if isinstance(repo, dict)]

    started_at = datetime.now().astimezone()
    code_logs: list[str] = []
    first_report: dict[str, object] | None = None

    for repo in repo_dicts:
        repo_id = str(repo.get("id") or "").strip() or "repo"
        repo_path = str(repo.get("path") or "").strip()
        if not repo_path:
            raise ValueError(f"repo {repo_id} path missing")
        branch = f"prd_{task_id}"
        worktree = build_worktree_path(repo_path, task_id)
        ensure_worktree(repo_path, worktree, branch)

        repo["status"] = STATUS_CODING
        repo["branch"] = branch
        repo["worktree"] = worktree

        finished_at = datetime.now().astimezone()
        report = {
            "status": "prepared",
            "task_id": task_id,
            "repo_id": repo_id,
            "repo_path": repo_path,
            "branch": branch,
            "worktree": worktree,
            "commit": "",
            "build_ok": False,
            "files_written": [],
            "log": str(task_dir / "code.log"),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
        }
        if first_report is None:
            first_report = report
        write_json(task_dir / "code-results" / f"{sanitize_name(repo_id)}.json", report)
        code_logs.append(
            f"[{repo_id}] prepared worktree\nrepo={repo_path}\nbranch={branch}\nworktree={worktree}\n"
        )

    if first_report is None:
        raise ValueError("no valid repos found")

    task_meta["status"] = STATUS_CODING
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(task_dir / "task.json", task_meta)
    write_json(repos_path, repos_meta)
    write_json(task_dir / "code-result.json", first_report)
    (task_dir / "code.log").write_text("\n".join(code_logs))
    return STATUS_CODING


def code_task_native(
    task_id: str,
    task_dir: Path,
    task_meta: dict[str, object],
    repos_path: Path,
    repos_meta: dict[str, object],
    repos: list[object],
    settings: Settings,
) -> str:
    repo_dicts = [repo for repo in repos if isinstance(repo, dict)]
    if not repo_dicts:
        raise ValueError("no valid repos found")

    started_at = datetime.now().astimezone().isoformat()
    first_report: dict[str, object] | None = None
    code_logs: list[str] = []
    overall_status = STATUS_CODING

    for repo in repo_dicts:
        repo_id = str(repo.get("id") or "").strip() or "repo"
        repo_path = str(repo.get("path") or "").strip()
        if not repo_path:
            raise ValueError(f"repo {repo_id} path missing")

        branch = f"prd_{task_id}"
        worktree = build_worktree_path(repo_path, task_id)
        ensure_worktree(repo_path, worktree, branch)
        sync_native_workspace(task_dir, Path(repo_path), Path(worktree), task_id)

        repo["status"] = STATUS_CODING
        repo["branch"] = branch
        repo["worktree"] = worktree

        client = CocoACPClient(
            settings.coco_bin,
            idle_timeout_seconds=settings.acp_idle_timeout_seconds,
            settings=settings,
        )
        agent_reply = client.run_agent(
            build_native_code_prompt(task_id, repo_id),
            settings.native_code_timeout,
            worktree,
        )
        parsed = parse_native_code_result(agent_reply)
        changed_files = collect_code_changes(worktree)
        commit_hash = ""
        build_ok = parsed["build_ok"]
        result_status = parsed["status"]

        if changed_files:
            commit_hash = commit_code_changes(worktree, task_id)
            repo["commit"] = commit_hash
            if result_status == "success":
                repo["status"] = STATUS_CODED
                overall_status = STATUS_CODED
            else:
                repo["status"] = STATUS_CODING
                overall_status = STATUS_CODING
        else:
            repo["status"] = STATUS_CODING
            overall_status = STATUS_CODING

        finished_at = datetime.now().astimezone().isoformat()
        report = {
            "status": result_status,
            "task_id": task_id,
            "repo_id": repo_id,
            "repo_path": repo_path,
            "branch": branch,
            "worktree": worktree,
            "commit": commit_hash,
            "build_ok": build_ok,
            "files_written": changed_files,
            "log": str(task_dir / "code.log"),
            "started_at": started_at,
            "finished_at": finished_at,
        }
        write_json(task_dir / "code-results" / f"{sanitize_name(repo_id)}.json", report)
        if first_report is None:
            first_report = report
        code_logs.append(
            "\n".join(
                [
                    f"[{repo_id}] native code executed",
                    f"repo={repo_path}",
                    f"branch={branch}",
                    f"worktree={worktree}",
                    f"status={result_status}",
                    f"build_ok={build_ok}",
                    f"commit={commit_hash or '-'}",
                    "reply:",
                    agent_reply,
                    "",
                ]
            )
        )

    task_meta["status"] = overall_status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(task_dir / "task.json", task_meta)
    write_json(repos_path, repos_meta)
    if first_report is not None:
        write_json(task_dir / "code-result.json", first_report)
    (task_dir / "code.log").write_text("\n".join(code_logs))
    return overall_status


def build_worktree_path(repo_root: str, task_id: str) -> str:
    repo_path = Path(repo_root).resolve()
    repo_hash = hashlib.sha1(str(repo_path).encode("utf-8")).hexdigest()[:8]
    parent = repo_path.parent
    repo_name = repo_path.name or "repo"
    return str(parent / ".coco-flow-worktree" / f"{repo_name}-{repo_hash}" / task_id)


def ensure_worktree(repo_root: str, worktree_dir: str, branch: str) -> None:
    worktree_path = Path(worktree_dir)
    if worktree_path.exists():
        if is_git_worktree(worktree_dir):
            return
        raise ValueError(f"worktree path exists but is not a git worktree: {worktree_dir}")

    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    args = ["git", "worktree", "add"]
    if branch_exists(repo_root, branch):
        args.extend([worktree_dir, branch])
    else:
        args.extend(["-b", branch, worktree_dir])
    run_git(repo_root, args)


def branch_exists(repo_root: str, branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=repo_root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def is_git_worktree(path: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def run_git(repo_root: str, args: list[str]) -> None:
    result = subprocess.run(
        args,
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or result.stdout.strip() or "git command failed")


def sanitize_name(value: str) -> str:
    return value.replace("/", "_")


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def sync_native_workspace(task_dir: Path, repo_root: Path, worktree_root: Path, task_id: str) -> None:
    task_target = worktree_root / ".coco-flow" / "tasks" / task_id
    sync_local_tree(task_dir, task_target, replace=True)
    context_source = repo_root / ".livecoding" / "context"
    if context_source.exists():
        sync_local_tree(context_source, worktree_root / ".livecoding" / "context", replace=True)


def build_native_code_prompt(task_id: str, repo_id: str) -> str:
    return f"""你正在一个代码仓库的隔离 worktree 中执行实现任务。

任务要求：
1. 读取 `.coco-flow/tasks/{task_id}/prd-refined.md`、`design.md`、`plan.md`。
2. 在当前 worktree 内完成最小实现，不要修改 `.coco-flow/` 下的任务产物。
3. 优先做最小范围验证；如果仓库是 Go 项目，优先验证受影响包或最小构建。
4. 如果不需要改动，请明确说明 no_change。
5. 最后必须输出如下结构，且不要省略字段：

=== CODE RESULT ===
status: success|no_change|failed
build: passed|failed|unknown
summary: 一句话总结
files:
- relative/path

当前 repo_id: {repo_id}
当前 task_id: {task_id}
"""


def parse_native_code_result(reply: str) -> dict[str, object]:
    status = "success"
    build_ok = False
    summary = ""

    marker = "=== CODE RESULT ==="
    if marker in reply:
        block = reply.split(marker, 1)[1]
    else:
        block = reply
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("status:"):
            status = stripped.split(":", 1)[1].strip() or status
        elif stripped.startswith("build:"):
            build_value = stripped.split(":", 1)[1].strip().lower()
            build_ok = build_value in {"passed", "ok", "true"}
        elif stripped.startswith("summary:"):
            summary = stripped.split(":", 1)[1].strip()
    return {"status": status, "build_ok": build_ok, "summary": summary}


def collect_code_changes(repo_root: str) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if path and not path.startswith(".coco-flow/"):
            files.append(path)
    return files


def commit_code_changes(repo_root: str, task_id: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=coco-flow",
            "-c",
            "user.email=coco-flow@local",
            "commit",
            "-m",
            f"feat: apply coco-flow task {task_id}",
        ],
        cwd=repo_root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def sync_local_tree(source: Path, target: Path, replace: bool) -> None:
    if source.resolve() == target.resolve():
        return
    if not source.exists():
        raise ValueError(f"task directory missing: {source}")
    if replace and target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=not replace)
