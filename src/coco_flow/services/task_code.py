from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings, load_settings
from coco_flow.services.repo_state import (
    STATUS_CODING,
    STATUS_CODED,
    STATUS_FAILED,
    STATUS_PLANNED,
    clean_files_written,
    sanitize_repo_name,
    sync_task_status_from_repos,
    update_repo_binding,
    write_repo_code_log,
    write_repo_code_result,
    write_repo_diff_artifacts,
)
from coco_flow.services.task_detail import read_json_file
from coco_flow.services.task_refine import locate_task_dir

EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"


def code_task(
    task_id: str,
    settings: Settings | None = None,
    repo_id: str = "",
    all_repos: bool = False,
) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    repos_meta = read_json_file(task_dir / "repos.json")
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list) or not raw_repos:
        raise ValueError("task has no bound repos")

    targets = resolve_target_repos(raw_repos, repo_id, all_repos)
    if not targets:
        raise ValueError("当前没有可继续推进的仓库")

    if cfg.code_executor.strip().lower() == EXECUTOR_LOCAL:
        return code_task_local(task_id, task_dir, task_meta, targets)
    if cfg.code_executor.strip().lower() == EXECUTOR_NATIVE:
        return code_task_native(task_id, task_dir, task_meta, targets, cfg)
    raise ValueError(f"unknown code executor: {cfg.code_executor}")


def code_task_local(
    task_id: str,
    task_dir: Path,
    task_meta: dict[str, object],
    targets: list[dict[str, object]],
) -> str:
    started_at = datetime.now().astimezone().isoformat()
    reports: list[dict[str, object]] = []
    task_log_lines: list[str] = []

    for repo in targets:
        report, repo_log = prepare_local_repo(task_id, task_dir, repo, started_at)
        reports.append(report)
        task_log_lines.append(repo_log)
        update_repo_binding(
            task_dir,
            str(repo.get("id") or ""),
            lambda current, report=report: current.update(
                {
                    "status": STATUS_CODING,
                    "branch": report["branch"],
                    "worktree": report["worktree"],
                    "commit": "",
                }
            ),
        )

    if reports:
        write_task_outputs(task_dir, reports[0], task_log_lines)
    task_meta["status"] = sync_task_status_from_repos(task_dir)
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(task_dir / "task.json", task_meta)
    return str(task_meta["status"])


def code_task_native(
    task_id: str,
    task_dir: Path,
    task_meta: dict[str, object],
    targets: list[dict[str, object]],
    settings: Settings,
) -> str:
    started_at = datetime.now().astimezone().isoformat()
    reports: list[dict[str, object]] = []
    task_log_lines: list[str] = []
    repos_meta = read_json_file(task_dir / "repos.json")
    multi_repo = len(repos_meta.get("repos") or []) > 1

    for repo in targets:
        repo_name = str(repo.get("id") or "repo")
        try:
            report, repo_log = execute_native_repo(
                task_id=task_id,
                task_dir=task_dir,
                repo=repo,
                settings=settings,
                started_at=started_at,
                multi_repo=multi_repo,
            )
        except Exception as error:
            report = build_failed_report(task_id, task_dir, repo, started_at, error)
            repo_log = build_repo_log(repo_name, report, f"error:\n{error}\n")
            report["log"] = str(task_dir / "code.log")
            update_repo_binding(
                task_dir,
                repo_name,
                lambda current, report=report: current.update(
                    {
                        "status": STATUS_FAILED,
                        "branch": str(report.get("branch") or ""),
                        "worktree": str(report.get("worktree") or ""),
                        "commit": str(report.get("commit") or ""),
                    }
                ),
            )
            write_repo_code_result(task_dir, repo_name, report)
            write_repo_code_log(task_dir, repo_name, repo_log)
            task_log_lines.append(repo_log)
            reports.append(report)
            break

        update_repo_binding(
            task_dir,
            repo_name,
            lambda current, report=report: current.update(
                {
                    "status": derive_repo_status(report),
                    "branch": str(report.get("branch") or ""),
                    "worktree": str(report.get("worktree") or ""),
                    "commit": str(report.get("commit") or ""),
                }
            ),
        )
        write_repo_code_result(task_dir, repo_name, report)
        write_repo_code_log(task_dir, repo_name, repo_log)
        task_log_lines.append(repo_log)
        reports.append(report)

        if str(report.get("status") or "") == "failed":
            break

    if reports:
        write_task_outputs(task_dir, reports[-1], task_log_lines)
    task_meta["status"] = sync_task_status_from_repos(task_dir)
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(task_dir / "task.json", task_meta)
    return str(task_meta["status"])


def resolve_target_repos(raw_repos: list[object], repo_id: str, all_repos: bool) -> list[dict[str, object]]:
    repo_dicts = [repo for repo in raw_repos if isinstance(repo, dict)]
    if repo_id.strip():
        for repo in repo_dicts:
            if str(repo.get("id") or "") == repo_id.strip():
                if str(repo.get("status") or "") not in {STATUS_PLANNED, STATUS_FAILED}:
                    raise ValueError(f"repo {repo_id} 当前状态为 {repo.get('status') or ''}，不能开始 code")
                return [repo]
        options = ", ".join(sorted(str(repo.get("id") or "") for repo in repo_dicts))
        raise ValueError(f"task 未绑定 repo {repo_id}。可选 repo: {options}")
    if len(repo_dicts) == 1:
        repo = repo_dicts[0]
        if str(repo.get("status") or "") not in {STATUS_PLANNED, STATUS_FAILED}:
            raise ValueError(f"repo {repo.get('id') or ''} 当前状态为 {repo.get('status') or ''}，不能开始 code")
        return [repo]
    if all_repos:
        return [repo for repo in repo_dicts if str(repo.get("status") or "") in {STATUS_PLANNED, STATUS_FAILED}]
    options = ", ".join(sorted(str(repo.get("id") or "") for repo in repo_dicts))
    raise ValueError(f"该 task 关联多个 repo，请显式指定 repo。可选 repo: {options}")


def prepare_local_repo(
    task_id: str,
    task_dir: Path,
    repo: dict[str, object],
    started_at: str,
) -> tuple[dict[str, object], str]:
    repo_id = str(repo.get("id") or "").strip() or "repo"
    repo_path = str(repo.get("path") or "").strip()
    if not repo_path:
        raise ValueError(f"repo {repo_id} path missing")
    branch = build_branch_name(task_id, repo_id)
    worktree = build_worktree_path(repo_path, task_id)
    ensure_worktree(repo_path, worktree, branch)
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
        "summary": "已准备 worktree，等待后续实现。",
        "log": str(task_dir / "code.log"),
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    return report, build_repo_log(repo_id, report, "prepared worktree\n")


def execute_native_repo(
    *,
    task_id: str,
    task_dir: Path,
    repo: dict[str, object],
    settings: Settings,
    started_at: str,
    multi_repo: bool,
) -> tuple[dict[str, object], str]:
    repo_id = str(repo.get("id") or "").strip() or "repo"
    repo_path = str(repo.get("path") or "").strip()
    if not repo_path:
        raise ValueError(f"repo {repo_id} path missing")

    branch = build_branch_name(task_id, repo_id if multi_repo else "")
    worktree = build_worktree_path(repo_path, task_id)
    ensure_worktree(repo_path, worktree, branch)
    sync_native_workspace(task_dir, Path(repo_path), Path(worktree), task_id)

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
    clean_files = clean_files_written(changed_files, repo_path, worktree)
    commit_hash = ""
    patch = ""
    status = str(parsed["status"])

    if clean_files:
        patch = stage_and_read_patch(worktree, clean_files)
        commit_hash = commit_code_changes(worktree, task_id)
        write_repo_diff_artifacts(task_dir, repo_id, branch, commit_hash, clean_files, patch)
        repo_status = STATUS_CODED if status in {"success", "no_change"} else STATUS_FAILED
    else:
        repo_status = STATUS_CODED if status == "no_change" else STATUS_FAILED if status == "failed" else STATUS_CODED

    report = {
        "status": status,
        "task_id": task_id,
        "repo_id": repo_id,
        "repo_path": repo_path,
        "branch": branch,
        "worktree": worktree,
        "commit": commit_hash,
        "build_ok": bool(parsed["build_ok"]),
        "files_written": clean_files,
        "summary": str(parsed["summary"] or ""),
        "error": "" if repo_status != STATUS_FAILED else (str(parsed["summary"] or "") or "实现失败"),
        "log": str(task_dir / "code.log"),
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    if repo_status == STATUS_FAILED:
        report["status"] = "failed"
    repo_log = build_repo_log(repo_id, report, agent_reply)
    return report, repo_log


def build_failed_report(
    task_id: str,
    task_dir: Path,
    repo: dict[str, object],
    started_at: str,
    error: Exception,
) -> dict[str, object]:
    repo_id = str(repo.get("id") or "").strip() or "repo"
    repo_path = str(repo.get("path") or "").strip()
    branch = build_branch_name(task_id, repo_id)
    worktree = build_worktree_path(repo_path, task_id) if repo_path else ""
    return {
        "status": "failed",
        "task_id": task_id,
        "repo_id": repo_id,
        "repo_path": repo_path,
        "branch": branch,
        "worktree": worktree,
        "commit": "",
        "build_ok": False,
        "files_written": [],
        "summary": str(error),
        "error": str(error),
        "log": str(task_dir / "code.log"),
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
    }


def build_repo_log(repo_id: str, report: dict[str, object], body: str) -> str:
    lines = [
        f"[{repo_id}] native code executed",
        f"repo={report.get('repo_path') or ''}",
        f"branch={report.get('branch') or ''}",
        f"worktree={report.get('worktree') or ''}",
        f"status={report.get('status') or ''}",
        f"build_ok={report.get('build_ok')}",
        f"commit={report.get('commit') or '-'}",
        f"files_written={', '.join([str(item) for item in report.get('files_written') or []]) or '-'}",
        "reply:",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


def write_task_outputs(task_dir: Path, latest_report: dict[str, object], repo_logs: list[str]) -> None:
    write_json(task_dir / "code-result.json", latest_report)
    (task_dir / "code.log").write_text("\n".join(repo_logs))


def build_branch_name(task_id: str, repo_id: str) -> str:
    if repo_id.strip():
        return f"prd_{task_id}_{sanitize_repo_name(repo_id)}"
    return f"prd_{task_id}"


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
    block = reply.split(marker, 1)[1] if marker in reply else reply
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
        if path and not path.startswith(".coco-flow/") and not path.startswith(".livecoding/"):
            files.append(path)
    return files


def stage_and_read_patch(repo_root: str, files: list[str]) -> str:
    if not files:
        return ""
    subprocess.run(["git", "add", "--", *files], cwd=repo_root, check=True)
    result = subprocess.run(
        ["git", "diff", "--cached", "--no-ext-diff"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def commit_code_changes(repo_root: str, task_id: str) -> str:
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


def derive_repo_status(report: dict[str, object]) -> str:
    status = str(report.get("status") or "")
    commit = str(report.get("commit") or "")
    if status in {"success", "no_change"} and (commit or status == "no_change"):
        return STATUS_CODED
    if status == "failed":
        return STATUS_FAILED
    return STATUS_PLANNED


def sync_local_tree(source: Path, target: Path, replace: bool) -> None:
    if source.resolve() == target.resolve():
        return
    if not source.exists():
        raise ValueError(f"task directory missing: {source}")
    if replace and target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=not replace)
