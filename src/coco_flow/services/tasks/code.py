from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
from typing import Callable

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings, load_settings
from coco_flow.services.runtime.repo_state import (
    STATUS_ARCHIVED,
    STATUS_CODING,
    STATUS_CODED,
    STATUS_FAILED,
    STATUS_PLANNED,
    aggregate_task_status,
    clean_files_written,
    sanitize_repo_name,
    sync_task_status_from_repos,
    update_repo_binding,
    write_repo_code_log,
    write_repo_code_result,
    write_repo_diff_artifacts,
)
from coco_flow.services.queries.task_detail import read_json_file
from coco_flow.services.tasks.refine import locate_task_dir

EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
MAX_CODE_ATTEMPTS = 3
MAX_GO_TEST_PACKAGES = 3
MAX_GO_TEST_DISCOVERY_PACKAGES = 8
FAILURE_AGENT = "agent_failed"
FAILURE_BUILD = "build_failed"
FAILURE_VERIFY = "verify_failed"
FAILURE_GIT = "git_failed"
FAILURE_RUNTIME = "runtime_failed"
FAILURE_BLOCKED = "blocked_by_dependency"
LogHandler = Callable[[str], None]


def code_task(
    task_id: str,
    settings: Settings | None = None,
    repo_id: str = "",
    all_repos: bool = False,
    on_log: LogHandler | None = None,
    allow_coding_targets: bool = False,
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

    plan_execution = load_plan_execution_artifact(task_dir)
    targets = resolve_target_repos(raw_repos, repo_id, all_repos, allow_coding_targets=allow_coding_targets)
    targets = reorder_target_repos_by_plan(targets, plan_execution)
    targets, blocked = split_ready_and_blocked_target_repos(targets, raw_repos, plan_execution, all_repos=all_repos)
    persist_blocked_repos(task_dir, blocked)
    if not targets:
        if blocked:
            blocked_repo = blocked[0][0]
            unmet = ", ".join(blocked[0][1])
            raise ValueError(f"repo {blocked_repo} 依赖 {unmet}，当前没有可继续推进的 repo")
        raise ValueError("当前没有可继续推进的仓库")

    if cfg.code_executor.strip().lower() == EXECUTOR_LOCAL:
        return code_task_local(task_id, task_dir, task_meta, targets, on_log=on_log)
    if cfg.code_executor.strip().lower() == EXECUTOR_NATIVE:
        return code_task_native(task_id, task_dir, task_meta, targets, cfg, on_log=on_log)
    raise ValueError(f"unknown code executor: {cfg.code_executor}")


def start_coding_task(
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

    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list) or not raw_repos:
        raise ValueError("task has no bound repos")

    plan_execution = load_plan_execution_artifact(task_dir)
    targets = resolve_target_repos(raw_repos, repo_id, all_repos)
    targets = reorder_target_repos_by_plan(targets, plan_execution)
    targets, blocked = split_ready_and_blocked_target_repos(targets, raw_repos, plan_execution, all_repos=all_repos)
    persist_blocked_repos(task_dir, blocked)
    if not targets:
        if blocked:
            blocked_repo = blocked[0][0]
            unmet = ", ".join(blocked[0][1])
            raise ValueError(f"repo {blocked_repo} 依赖 {unmet}，当前没有可继续推进的 repo")
        raise ValueError("当前没有可继续推进的仓库")

    target_ids = {str(repo.get("id") or "") for repo in targets}
    changed = False
    for repo in raw_repos:
        if not isinstance(repo, dict):
            continue
        if str(repo.get("id") or "") not in target_ids:
            continue
        if str(repo.get("status") or "") != STATUS_CODING:
            repo["status"] = STATUS_CODING
            changed = True
    if changed:
        repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")

    task_meta["status"] = aggregate_task_status(str(task_meta.get("status") or ""), repos_meta)
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(task_dir / "task.json", task_meta)
    return str(task_meta["status"])


def code_task_local(
    task_id: str,
    task_dir: Path,
    task_meta: dict[str, object],
    targets: list[dict[str, object]],
    on_log: LogHandler | None = None,
) -> str:
    started_at = datetime.now().astimezone().isoformat()
    reports: list[dict[str, object]] = []
    task_log_lines: list[str] = []
    event_lines: list[str] = []
    log = on_log or event_lines.append

    for repo in targets:
        repo_name = str(repo.get("id") or "repo")
        log(f"repo_start: {repo_name}")
        report, repo_log = prepare_local_repo(task_id, task_dir, repo, started_at)
        reports.append(report)
        task_log_lines.append(repo_log)
        update_repo_binding(
            task_dir,
            repo_name,
            lambda current, report=report: current.update(
                {
                    "status": STATUS_CODING,
                    "branch": report["branch"],
                    "worktree": report["worktree"],
                    "commit": "",
                }
            ),
        )
        log(f"repo_worktree: {repo_name} branch={report['branch']} worktree={report['worktree']}")
        log(f"repo_status: {repo_name} prepared")

    if reports:
        write_task_outputs(task_dir, reports[0], task_log_lines, event_lines)
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
    on_log: LogHandler | None = None,
) -> str:
    started_at = datetime.now().astimezone().isoformat()
    reports: list[dict[str, object]] = []
    task_log_lines: list[str] = []
    event_lines: list[str] = []
    log = on_log or event_lines.append
    repos_meta = read_json_file(task_dir / "repos.json")
    multi_repo = len(repos_meta.get("repos") or []) > 1

    for repo in targets:
        repo_name = str(repo.get("id") or "repo")
        log(f"repo_start: {repo_name}")
        try:
            report, repo_log = execute_native_repo(
                task_id=task_id,
                task_dir=task_dir,
                repo=repo,
                settings=settings,
                started_at=started_at,
                multi_repo=multi_repo,
                on_log=log,
            )
        except Exception as error:
            log(f"repo_error: {repo_name} {error}")
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
        log(
            "repo_done: "
            f"{repo_name} status={report.get('status') or ''} "
            f"build_ok={report.get('build_ok')} commit={report.get('commit') or '-'}"
        )

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
        write_task_outputs(task_dir, reports[-1], task_log_lines, event_lines)
    task_meta["status"] = sync_task_status_from_repos(task_dir)
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    write_json(task_dir / "task.json", task_meta)
    return str(task_meta["status"])


def resolve_target_repos(
    raw_repos: list[object],
    repo_id: str,
    all_repos: bool,
    allow_coding_targets: bool = False,
) -> list[dict[str, object]]:
    repo_dicts = [repo for repo in raw_repos if isinstance(repo, dict)]
    allowed_statuses = {STATUS_PLANNED, STATUS_FAILED}
    if allow_coding_targets:
        allowed_statuses.add(STATUS_CODING)
    if repo_id.strip():
        for repo in repo_dicts:
            if str(repo.get("id") or "") == repo_id.strip():
                if str(repo.get("status") or "") not in allowed_statuses:
                    raise ValueError(f"repo {repo_id} 当前状态为 {repo.get('status') or ''}，不能开始 code")
                return [repo]
        options = ", ".join(sorted(str(repo.get("id") or "") for repo in repo_dicts))
        raise ValueError(f"task 未绑定 repo {repo_id}。可选 repo: {options}")
    if len(repo_dicts) == 1:
        repo = repo_dicts[0]
        if str(repo.get("status") or "") not in allowed_statuses:
            raise ValueError(f"repo {repo.get('id') or ''} 当前状态为 {repo.get('status') or ''}，不能开始 code")
        return [repo]
    if all_repos:
        return [repo for repo in repo_dicts if str(repo.get("status") or "") in allowed_statuses]
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
    on_log: LogHandler | None = None,
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
    log = on_log or (lambda line: None)
    plan_execution = load_plan_execution_artifact(task_dir)
    repo_tasks = select_repo_tasks(plan_execution, repo_id)
    task_scope = collect_repo_task_change_scope(repo_id, repo_tasks)
    verify_rules = collect_repo_verify_rules(repo_tasks)
    prompt = build_native_code_prompt(task_id, repo_id, plan_execution)
    agent_reply = ""
    parsed: dict[str, object] = {"status": "failed", "build_ok": False, "summary": ""}
    clean_files: list[str] = []
    verification_ok = False
    verification_output = ""

    for attempt in range(1, MAX_CODE_ATTEMPTS + 1):
        log(f"repo_attempt: {repo_id} {attempt}/{MAX_CODE_ATTEMPTS}")
        agent_reply = client.run_agent(
            prompt,
            settings.native_code_timeout,
            worktree,
        )
        parsed = parse_native_code_result(agent_reply)
        changed_files = collect_code_changes(worktree)
        clean_files = clean_files_written(changed_files, repo_path, worktree)
        verification_ok, verification_output = verify_repo_changes(
            worktree,
            clean_files,
            task_scope=task_scope,
            verify_rules=verify_rules,
            enable_go_test=settings.enable_go_test_verify,
        )
        for line in verification_output.splitlines():
            if line.strip():
                log(f"repo_verify_output: {line}")
        parsed["build_ok"] = verification_ok
        if verification_ok or str(parsed.get("status") or "") == "no_change":
            log(f"repo_verify_ok: {repo_id}")
            break
        if attempt >= MAX_CODE_ATTEMPTS:
            log(f"repo_verify_failed: {repo_id} giving up after {attempt} attempts")
            break
        log(f"repo_verify_failed: {repo_id} attempt={attempt}")
        prompt = build_code_retry_prompt(
            task_id=task_id,
            repo_id=repo_id,
            plan_execution=plan_execution,
            changed_files=select_retry_target_files(clean_files, task_scope),
            verification_output=verification_output,
        )

    commit_hash = ""
    patch = ""
    status = str(parsed["status"])
    if verification_ok and not clean_files and status == "success":
        status = "no_change"

    failure_type = ""
    failure_action = ""
    if clean_files and verification_ok:
        try:
            patch = stage_and_read_patch(worktree, clean_files)
            commit_hash = commit_code_changes(worktree, task_id)
            write_repo_diff_artifacts(task_dir, repo_id, branch, commit_hash, clean_files, patch)
        except Exception as error:
            verification_ok = False
            repo_status = STATUS_FAILED
            failure_type = FAILURE_GIT
            verification_output = str(error)
            log(f"repo_git_failed: {repo_id} {error}")
        else:
            repo_status = STATUS_CODED if status in {"success", "no_change"} else STATUS_FAILED
    elif clean_files and not verification_ok:
        repo_status = STATUS_FAILED
    else:
        repo_status = STATUS_CODED if status == "no_change" else STATUS_FAILED if status == "failed" else STATUS_CODED

    if repo_status == STATUS_FAILED and not failure_type:
        failure_type = classify_failure_type(status, verification_output, bool(clean_files))
        failure_action = suggest_failure_action(failure_type)
        log(f"repo_failure_type: {repo_id} {failure_type}")
    elif repo_status == STATUS_FAILED:
        failure_action = suggest_failure_action(failure_type)

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
        "failure_type": failure_type,
        "failure_action": failure_action,
        "error": (
            ""
            if repo_status != STATUS_FAILED
            else (
                verification_output.strip()
                or str(parsed["summary"] or "")
                or "实现失败"
            )
        ),
        "log": str(task_dir / "code.log"),
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    if repo_status == STATUS_FAILED:
        report["status"] = "failed"
    repo_log = build_repo_log(repo_id, report, agent_reply, verification_output=verification_output)
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
        "failure_type": classify_exception_failure_type(error),
        "failure_action": suggest_failure_action(classify_exception_failure_type(error)),
        "error": str(error),
        "log": str(task_dir / "code.log"),
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
    }


def build_repo_log(repo_id: str, report: dict[str, object], body: str, verification_output: str = "") -> str:
    lines = [
        f"[{repo_id}] native code executed",
        f"repo={report.get('repo_path') or ''}",
        f"branch={report.get('branch') or ''}",
        f"worktree={report.get('worktree') or ''}",
        f"status={report.get('status') or ''}",
        f"failure_type={report.get('failure_type') or '-'}",
        f"build_ok={report.get('build_ok')}",
        f"commit={report.get('commit') or '-'}",
        f"files_written={', '.join([str(item) for item in report.get('files_written') or []]) or '-'}",
        f"failure_action={report.get('failure_action') or '-'}",
        "verification:",
        verification_output.strip() or "verification skipped or passed without output",
        "reply:",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


def write_task_outputs(
    task_dir: Path,
    latest_report: dict[str, object],
    repo_logs: list[str],
    event_lines: list[str] | None = None,
) -> None:
    write_json(task_dir / "code-result.json", latest_report)
    content_parts: list[str] = []
    if event_lines:
        content_parts.append("\n".join(event_lines).strip())
    if repo_logs:
        content_parts.append("\n".join(repo_logs).strip())
    (task_dir / "code.log").write_text("\n\n".join(part for part in content_parts if part).strip() + "\n")


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


def load_plan_execution_artifact(task_dir: Path) -> dict[str, object]:
    payload = read_json_file(task_dir / "plan-execution.json")
    return payload if isinstance(payload, dict) else {}


def select_repo_tasks(plan_execution: dict[str, object], repo_id: str) -> list[dict[str, object]]:
    raw_tasks = plan_execution.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    tasks: list[dict[str, object]] = []
    for item in raw_tasks:
        if not isinstance(item, dict):
            continue
        target = str(item.get("target_system_or_repo") or "")
        if target not in {repo_id, "current-repo", ""}:
            continue
        tasks.append(item)
    return tasks


def reorder_target_repos_by_plan(targets: list[dict[str, object]], plan_execution: dict[str, object]) -> list[dict[str, object]]:
    if len(targets) <= 1:
        return targets
    raw_tasks = plan_execution.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return targets

    repo_rank: dict[str, int] = {}
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("target_system_or_repo") or "")
        if not repo_id or repo_id in repo_rank:
            continue
        repo_rank[repo_id] = index

    def sort_key(repo: dict[str, object]) -> tuple[int, str]:
        repo_id = str(repo.get("id") or "")
        return (repo_rank.get(repo_id, len(raw_tasks) + 1000), repo_id)

    return sorted(targets, key=sort_key)


def build_task_repo_index(plan_execution: dict[str, object]) -> dict[str, str]:
    raw_tasks = plan_execution.get("tasks")
    if not isinstance(raw_tasks, list):
        return {}
    index: dict[str, str] = {}
    for item in raw_tasks:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id") or "").strip()
        repo_id = str(item.get("target_system_or_repo") or "").strip()
        if task_id and repo_id:
            index[task_id] = repo_id
    return index


def collect_repo_dependency_repos(plan_execution: dict[str, object], repo_id: str) -> list[str]:
    task_repo_index = build_task_repo_index(plan_execution)
    repo_tasks = select_repo_tasks(plan_execution, repo_id)
    dependency_repos: list[str] = []
    seen: set[str] = set()
    for task in repo_tasks:
        depends_on = task.get("depends_on")
        if not isinstance(depends_on, list):
            continue
        for item in depends_on:
            dep_repo = task_repo_index.get(str(item).strip(), "")
            if not dep_repo or dep_repo == repo_id or dep_repo in seen:
                continue
            seen.add(dep_repo)
            dependency_repos.append(dep_repo)
    return dependency_repos


def find_unmet_repo_dependencies(raw_repos: list[object], plan_execution: dict[str, object], repo_id: str) -> list[str]:
    dependency_repos = collect_repo_dependency_repos(plan_execution, repo_id)
    if not dependency_repos:
        return []
    status_by_repo: dict[str, str] = {}
    for repo in raw_repos:
        if not isinstance(repo, dict):
            continue
        status_by_repo[str(repo.get("id") or "")] = str(repo.get("status") or "")
    unmet: list[str] = []
    for dep_repo in dependency_repos:
        if status_by_repo.get(dep_repo, "") not in {STATUS_CODED, STATUS_ARCHIVED}:
            unmet.append(dep_repo)
    return unmet


def split_ready_and_blocked_target_repos(
    targets: list[dict[str, object]],
    raw_repos: list[object],
    plan_execution: dict[str, object],
    *,
    all_repos: bool,
) -> tuple[list[dict[str, object]], list[tuple[str, list[str]]]]:
    ready: list[dict[str, object]] = []
    blocked: list[tuple[str, list[str]]] = []
    for repo in targets:
        repo_id = str(repo.get("id") or "")
        unmet = find_unmet_repo_dependencies(raw_repos, plan_execution, repo_id)
        if not unmet:
            ready.append(repo)
            continue
        blocked.append((repo_id, unmet))
        if not all_repos:
            return ready, blocked
        if ready:
            break
    return ready, blocked


def persist_blocked_repos(task_dir: Path, blocked: list[tuple[str, list[str]]]) -> None:
    for repo_id, unmet in blocked:
        report = build_blocked_report(task_dir, repo_id, unmet)
        write_repo_code_result(task_dir, repo_id, report)
        write_repo_code_log(task_dir, repo_id, build_repo_log(repo_id, report, "blocked before code execution\n"))


def build_blocked_report(task_dir: Path, repo_id: str, unmet: list[str]) -> dict[str, object]:
    unmet_text = ", ".join(unmet)
    return {
        "status": STATUS_PLANNED,
        "task_id": task_dir.name,
        "repo_id": repo_id,
        "repo_path": "",
        "branch": "",
        "worktree": "",
        "commit": "",
        "build_ok": False,
        "files_written": [],
        "summary": f"repo {repo_id} 被依赖阻塞，需等待 {unmet_text}",
        "failure_type": FAILURE_BLOCKED,
        "failure_action": f"先推进上游 repo：{unmet_text}，完成 code 后再继续当前 repo。",
        "error": f"blocked by dependencies: {unmet_text}",
        "log": str(task_dir / "code.log"),
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
    }


def normalize_repo_task_file(repo_id: str, file_path: str) -> str:
    normalized = str(file_path).strip().lstrip("./")
    if not normalized:
        return ""
    prefix = f"{repo_id}/"
    if repo_id and normalized.startswith(prefix):
        return normalized[len(prefix) :]
    return normalized


def collect_repo_task_change_scope(repo_id: str, tasks: list[dict[str, object]]) -> list[str]:
    seen: set[str] = set()
    files: list[str] = []
    for task in tasks:
        change_scope = task.get("change_scope")
        if not isinstance(change_scope, list):
            continue
        for item in change_scope:
            normalized = normalize_repo_task_file(repo_id, str(item))
            lowered = normalized.lower()
            if not normalized or lowered in seen:
                continue
            seen.add(lowered)
            files.append(normalized)
    return files


def collect_repo_verify_rules(tasks: list[dict[str, object]]) -> list[str]:
    seen: set[str] = set()
    rules: list[str] = []
    for task in tasks:
        verify_rule = task.get("verify_rule")
        if not isinstance(verify_rule, list):
            continue
        for item in verify_rule:
            current = str(item).strip()
            lowered = current.lower()
            if not current or lowered in seen:
                continue
            seen.add(lowered)
            rules.append(current)
    return rules


def select_verification_target_files(changed_files: list[str], task_scope: list[str]) -> list[str]:
    if not task_scope:
        return changed_files
    normalized_changed = dedupe_relative_files(changed_files)
    normalized_scope = dedupe_relative_files(task_scope)
    if not normalized_changed:
        return normalized_scope
    scope_set = {item.lower() for item in normalized_scope}
    overlapped = [item for item in normalized_changed if item.lower() in scope_set]
    return overlapped or normalized_changed


def select_retry_target_files(changed_files: list[str], task_scope: list[str]) -> list[str]:
    targets = select_verification_target_files(changed_files, task_scope)
    if targets:
        return targets
    return dedupe_relative_files(task_scope)


def dedupe_relative_files(files: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in files:
        current = str(item).strip().lstrip("./")
        lowered = current.lower()
        if not current or lowered in seen:
            continue
        seen.add(lowered)
        result.append(current)
    return result


def render_plan_task_brief(tasks: list[dict[str, object]]) -> str:
    if not tasks:
        return "- 当前未提取到 repo 对应的结构化任务，回退到 design.md / plan.md 语义。"
    lines: list[str] = []
    for task in tasks[:6]:
        title = str(task.get("title") or "")
        task_id = str(task.get("id") or "")
        goal = str(task.get("goal") or "")
        depends_on = task.get("depends_on")
        change_scope = task.get("change_scope")
        actions = task.get("actions")
        verify_rule = task.get("verify_rule")
        lines.append(f"- {task_id} {title}".strip())
        if goal:
            lines.append(f"  goal: {goal}")
        if isinstance(depends_on, list) and depends_on:
            lines.append(f"  depends_on: {', '.join(str(item) for item in depends_on)}")
        if isinstance(change_scope, list) and change_scope:
            lines.append("  change_scope:")
            lines.extend(f"    - {item}" for item in change_scope[:6])
        if isinstance(actions, list) and actions:
            lines.append("  actions:")
            lines.extend(f"    - {item}" for item in actions[:6])
        if isinstance(verify_rule, list) and verify_rule:
            lines.append("  verify_rule:")
            lines.extend(f"    - {item}" for item in verify_rule[:4])
    return "\n".join(lines)


def render_repo_task_execution_order(tasks: list[dict[str, object]]) -> str:
    if not tasks:
        return "- 当前 repo 未提取到结构化任务顺序。"
    lines: list[str] = []
    ordered_ids = [str(task.get("id") or "") for task in tasks if str(task.get("id") or "").strip()]
    if ordered_ids:
        lines.append(f"- task_order: {' -> '.join(ordered_ids)}")
    for task in tasks:
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            continue
        depends_on = task.get("depends_on")
        if isinstance(depends_on, list) and depends_on:
            lines.append(f"- {task_id} depends_on: {', '.join(str(item) for item in depends_on)}")
        else:
            lines.append(f"- {task_id} depends_on: none")
    return "\n".join(lines)


def render_repo_scope_summary(repo_id: str, plan_execution: dict[str, object]) -> str:
    tasks = select_repo_tasks(plan_execution, repo_id)
    scope = collect_repo_task_change_scope(repo_id, tasks)
    rules = collect_repo_verify_rules(tasks)
    lines: list[str] = []
    if scope:
        lines.append("- change_scope:")
        lines.extend(f"  - {item}" for item in scope[:8])
    if rules:
        lines.append("- verify_rule:")
        lines.extend(f"  - {item}" for item in rules[:6])
    return "\n".join(lines) if lines else "- 当前 repo 未提取到额外的结构化范围约束。"


def build_native_code_prompt(task_id: str, repo_id: str, plan_execution: dict[str, object]) -> str:
    repo_tasks = select_repo_tasks(plan_execution, repo_id)
    return f"""你正在一个代码仓库的隔离 worktree 中执行实现任务。

任务要求：
1. 读取 `.coco-flow/tasks/{task_id}/prd-refined.md`、`design.md`、`plan.md`、`plan-execution.json`。
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

当前 repo 对应的结构化任务：
{render_plan_task_brief(repo_tasks)}

当前 repo 本轮优先范围与验证规则：
{render_repo_scope_summary(repo_id, plan_execution)}

当前 repo 任务顺序与依赖：
{render_repo_task_execution_order(repo_tasks)}
"""


def build_code_retry_prompt(
    task_id: str,
    repo_id: str,
    plan_execution: dict[str, object],
    changed_files: list[str],
    verification_output: str,
) -> str:
    file_block = "\n".join(f"- {item}" for item in changed_files) or "- 当前未检测到稳定变更文件，可优先围绕结构化任务 change_scope 收敛修复范围"
    repo_tasks = select_repo_tasks(plan_execution, repo_id)
    return f"""刚才的实现未通过最小验证，请继续在当前 worktree 中直接修复，不要重置已有改动。

任务要求：
1. 继续围绕 `.coco-flow/tasks/{task_id}/prd-refined.md`、`design.md`、`plan.md`、`plan-execution.json` 修复问题。
2. 仅修改当前 worktree 内与本次任务相关的代码，不要改 `.coco-flow/` 和 `.livecoding/`。
3. 优先修复下面这些已经变更过的文件：
{file_block}
4. 修复后请再次做最小范围验证。
4.1 如果是 Go 代码，至少重新执行相关 package 的 go build；若存在测试或验证脚本，也一并确认。
5. 最后仍然必须输出：

=== CODE RESULT ===
status: success|no_change|failed
build: passed|failed|unknown
summary: 一句话总结
files:
- relative/path

最近一次验证失败输出：
{verification_output.strip() or '无'}

当前 repo_id: {repo_id}
当前 task_id: {task_id}

当前 repo 对应的结构化任务：
{render_plan_task_brief(repo_tasks)}

当前 repo 本轮优先范围与验证规则：
{render_repo_scope_summary(repo_id, plan_execution)}

当前 repo 任务顺序与依赖：
{render_repo_task_execution_order(repo_tasks)}
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


def verify_repo_changes(
    repo_root: str,
    files: list[str],
    *,
    task_scope: list[str] | None = None,
    verify_rules: list[str] | None = None,
    enable_go_test: bool = False,
) -> tuple[bool, str]:
    target_files = select_verification_target_files(files, task_scope or [])
    if not target_files:
        return True, "no changed files"

    go_files = [item for item in target_files if item.endswith(".go")]
    if go_files:
        ok, output = verify_go_build(repo_root, go_files, enable_go_test=enable_go_test)
        if verify_rules:
            output = (output + "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)).strip()
        return ok, output

    py_files = [item for item in target_files if item.endswith(".py")]
    if py_files:
        ok, output = verify_python_files(repo_root, py_files)
        if verify_rules:
            output = (output + "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)).strip()
        return ok, output

    output = "no language-specific verification for current changed files"
    if verify_rules:
        output += "\n\nverify rules:\n" + "\n".join(f"- {item}" for item in verify_rules)
    return True, output


def verify_go_build(repo_root: str, files: list[str], enable_go_test: bool = False) -> tuple[bool, str]:
    packages = sorted({go_package_pattern(file_path) for file_path in files if file_path.endswith(".go")})
    if not packages:
        return True, "no go packages to build"

    outputs: list[str] = []
    all_ok = True
    test_candidates = discover_go_test_packages(repo_root, files) if enable_go_test else []
    for package in packages:
        result = subprocess.run(
            ["go", "build", package],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            all_ok = False
            outputs.append(
                f"go build {package} 失败:\n{result.stdout}{result.stderr}".strip()
            )
        elif result.stdout.strip() or result.stderr.strip():
            outputs.append(f"go build {package} 成功:\n{result.stdout}{result.stderr}".strip())
    if all_ok and test_candidates:
        for package in test_candidates[:MAX_GO_TEST_PACKAGES]:
            result = subprocess.run(
                ["go", "test", package],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                all_ok = False
                outputs.append(f"go test {package} 失败:\n{result.stdout}{result.stderr}".strip())
            elif result.stdout.strip() or result.stderr.strip():
                outputs.append(f"go test {package} 成功:\n{result.stdout}{result.stderr}".strip())
    elif all_ok and enable_go_test:
        outputs.append("go test skipped: no *_test.go files in affected packages")
    if all_ok and not outputs:
        outputs.append("go build passed")
    return all_ok, "\n\n".join(outputs).strip()


def go_package_pattern(file_path: str) -> str:
    directory = str(Path(file_path).parent)
    if directory in {"", "."}:
        return "./..."
    return f"./{directory}/..."


def go_test_package_pattern(file_path: str) -> str:
    directory = str(Path(file_path).parent)
    if directory in {"", "."}:
        return "."
    return f"./{directory}"


def should_run_go_test(file_path: str) -> bool:
    name = Path(file_path).name
    return name.endswith(".go")


def discover_go_test_packages(repo_root: str, files: list[str]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        if not should_run_go_test(file_path):
            continue
        package = go_test_package_pattern(file_path)
        if package in seen:
            continue
        seen.add(package)
        candidates.append(package)
        if len(candidates) >= MAX_GO_TEST_DISCOVERY_PACKAGES:
            break
    return [package for package in candidates if package_has_go_tests(repo_root, package)]


def package_has_go_tests(repo_root: str, package_pattern: str) -> bool:
    directory = package_pattern.removeprefix("./")
    package_dir = Path(repo_root) / directory
    if directory in {"", "."}:
        package_dir = Path(repo_root)
    if not package_dir.is_dir():
        return False
    return any(path.is_file() for path in package_dir.glob("*_test.go"))


def classify_failure_type(status: str, verification_output: str, has_changed_files: bool) -> str:
    output = verification_output.strip().lower()
    if "git" in output and ("commit" in output or "index.lock" in output or "worktree" in output):
        return FAILURE_GIT
    if "go build " in output or "python py_compile failed" in output:
        return FAILURE_BUILD
    if "go test " in output:
        return FAILURE_VERIFY
    if status == "failed" and not has_changed_files:
        return FAILURE_AGENT
    if status == "failed":
        return FAILURE_VERIFY
    return FAILURE_RUNTIME


def classify_exception_failure_type(error: Exception) -> str:
    message = str(error).lower()
    if "git" in message or "worktree" in message or "index.lock" in message:
        return FAILURE_GIT
    return FAILURE_RUNTIME


def suggest_failure_action(failure_type: str) -> str:
    if failure_type == FAILURE_BLOCKED:
        return "先推进依赖的上游 repo，再继续当前 repo。"
    if failure_type == FAILURE_BUILD:
        return "先修复编译错误，再重试实现。"
    if failure_type == FAILURE_VERIFY:
        return "先查看验证输出，确认测试或校验失败点，再决定重试还是调整方案。"
    if failure_type == FAILURE_GIT:
        return "先检查 worktree、分支或 git 锁冲突，再重试实现。"
    if failure_type == FAILURE_AGENT:
        return "先查看 agent 输出和方案上下文，确认提示词或实现边界后再重试。"
    return "先查看日志定位失败点，再决定重试还是回退。"


def verify_python_files(repo_root: str, files: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        ["python3", "-m", "py_compile", *files],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}{result.stderr}".strip()
    if result.returncode == 0:
        return True, output or "python py_compile passed"
    return False, output or "python py_compile failed"


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
