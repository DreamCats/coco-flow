from __future__ import annotations

from datetime import datetime
import json

from coco_flow.config import Settings
from coco_flow.services.runtime.repo_state import (
    STATUS_ARCHIVED,
    STATUS_CODED,
    STATUS_CODING,
    STATUS_FAILED,
    STATUS_PLANNED,
    aggregate_task_status,
    sync_task_status_from_repos,
    update_repo_binding,
)
from coco_flow.services.queries.task_detail import read_json_file

from .dispatch import build_code_runtime_state
from .execute import build_blocked_result, execute_repo_batch
from .models import CodePreparedInput, CodeRepoBatch, CodeRepoRunResult
from .persist import build_task_result_payload, write_code_runtime_artifacts, write_json_artifact, write_repo_runtime_artifacts
from .source import prepare_code_input


def start_code_engine(
    task_dir,
    task_meta: dict[str, object],
    *,
    repo_id: str,
    all_repos: bool,
    allow_coding_targets: bool,
) -> str:
    prepared = prepare_code_input(task_dir, task_meta)
    runtime = build_code_runtime_state(prepared)
    selected = _resolve_target_batches(
        prepared,
        runtime.batches,
        repo_id=repo_id,
        all_repos=all_repos,
        allow_coding_targets=allow_coding_targets,
    )
    if not selected:
        raise ValueError("当前没有可继续推进的仓库")
    write_code_runtime_artifacts(task_dir, runtime.dispatch_payload, runtime.progress_payload)

    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    raw_repos = repos_meta.get("repos")
    if isinstance(raw_repos, list):
        target_repo_ids = {batch.repo_id for batch in selected}
        changed = False
        for repo in raw_repos:
            if not isinstance(repo, dict):
                continue
            if str(repo.get("id") or "") not in target_repo_ids:
                continue
            if str(repo.get("status") or "") != STATUS_CODING:
                repo["status"] = STATUS_CODING
                changed = True
        if changed:
            repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    task_meta["status"] = aggregate_task_status(str(task_meta.get("status") or ""), repos_meta)
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(task_meta["status"])


def run_code_engine(
    task_dir,
    task_meta: dict[str, object],
    settings: Settings,
    *,
    repo_id: str,
    all_repos: bool,
    allow_coding_targets: bool,
    on_log,
) -> str:
    prepared = prepare_code_input(task_dir, task_meta)
    runtime = build_code_runtime_state(prepared)
    selected = _resolve_target_batches(
        prepared,
        runtime.batches,
        repo_id=repo_id,
        all_repos=all_repos,
        allow_coding_targets=allow_coding_targets,
    )
    if not selected:
        raise ValueError("当前没有可继续推进的仓库")

    write_code_runtime_artifacts(task_dir, runtime.dispatch_payload, runtime.progress_payload)

    completed_batch_ids = set(runtime.progress_payload.get("completed_batches") or [])
    repo_results: list[CodeRepoRunResult] = []

    for batch in selected:
        unmet = _unmet_batch_dependencies(batch, runtime.batches, completed_batch_ids)
        if unmet:
            on_log(f"repo_blocked: {batch.repo_id} unmet={', '.join(unmet)}")
            blocked_result = build_blocked_result(prepared, batch, unmet)
            batch.status = "blocked"
            batch.blocked_by_batch_ids = unmet
            write_repo_runtime_artifacts(task_dir, blocked_result)
            _update_repo_runtime_binding(task_dir, batch.repo_id, STATUS_PLANNED, blocked_result.report)
            repo_results.append(blocked_result)
            _sync_progress(task_dir, prepared, runtime.batches, current_batch_id="")
            break

        on_log(f"repo_start: {batch.repo_id}")
        batch.status = "running"
        _sync_progress(task_dir, prepared, runtime.batches, current_batch_id=batch.id)

        result = execute_repo_batch(prepared, batch, settings, on_log=on_log)
        write_repo_runtime_artifacts(task_dir, result)
        repo_results.append(result)

        batch.status = "completed" if result.repo_status == STATUS_CODED else "failed"
        if result.repo_status == STATUS_CODED:
            completed_batch_ids.add(batch.id)
        _update_repo_runtime_binding(task_dir, batch.repo_id, result.repo_status, result.report)
        _sync_progress(task_dir, prepared, runtime.batches, current_batch_id="" if batch.status != "running" else batch.id)
        on_log(
            "repo_done: "
            f"{batch.repo_id} batch={batch.id} mode={batch.execution_mode} "
            f"status={result.report.get('status') or ''} build_ok={result.report.get('build_ok')}"
        )

        if result.repo_status == STATUS_FAILED:
            break

    result_payload = build_task_result_payload(prepared.task_id, runtime.batches, repo_results)
    write_json_artifact(task_dir / "code-result.json", result_payload)
    status = sync_task_status_from_repos(task_dir)
    task_meta = read_json_file(task_dir / "task.json")
    task_meta["status"] = status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return status


def build_code_runtime_state_for_task(task_dir, task_meta: dict[str, object]) -> dict[str, object]:
    prepared = prepare_code_input(task_dir, task_meta)
    runtime = build_code_runtime_state(prepared)
    return {
        "dispatch": runtime.dispatch_payload,
        "progress": runtime.progress_payload,
    }


def _resolve_target_batches(
    prepared: CodePreparedInput,
    batches: list[CodeRepoBatch],
    *,
    repo_id: str,
    all_repos: bool,
    allow_coding_targets: bool,
) -> list[CodeRepoBatch]:
    repo_status_index = _repo_status_index(prepared.repos_meta)
    allowed_statuses = {STATUS_PLANNED, STATUS_FAILED}
    if allow_coding_targets:
        allowed_statuses.add(STATUS_CODING)

    runnable = [batch for batch in batches if batch.execution_mode in {"apply", "verify_only"}]
    if repo_id.strip():
        for batch in runnable:
            if batch.repo_id != repo_id.strip():
                continue
            if repo_status_index.get(batch.repo_id, "") not in allowed_statuses:
                raise ValueError(f"repo {repo_id} 当前状态为 {repo_status_index.get(batch.repo_id, '')}，不能开始 code")
            return [batch]
        options = ", ".join(sorted(batch.repo_id for batch in runnable))
        raise ValueError(f"task 未绑定 repo {repo_id}。可选 repo: {options}")

    eligible = [batch for batch in runnable if repo_status_index.get(batch.repo_id, "") in allowed_statuses]
    if len(eligible) == 1:
        return eligible
    if all_repos:
        return eligible
    if not eligible:
        return []
    options = ", ".join(sorted(batch.repo_id for batch in eligible))
    raise ValueError(f"该 task 关联多个 repo，请显式指定 repo。可选 repo: {options}")


def _repo_status_index(repos_meta: dict[str, object]) -> dict[str, str]:
    index: dict[str, str] = {}
    raw = repos_meta.get("repos")
    if not isinstance(raw, list):
        return index
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("id") or "").strip()
        if repo_id:
            index[repo_id] = str(item.get("status") or "").strip()
    return index


def _unmet_batch_dependencies(batch: CodeRepoBatch, batches: list[CodeRepoBatch], completed_batch_ids: set[str]) -> list[str]:
    batch_status_index = {current.id: current.status for current in batches}
    unmet: list[str] = []
    for dep_batch_id in batch.depends_on_batch_ids:
        if dep_batch_id in completed_batch_ids:
            continue
        if batch_status_index.get(dep_batch_id) == "completed":
            continue
        unmet.append(dep_batch_id)
    return unmet


def _sync_progress(task_dir, prepared: CodePreparedInput, batches: list[CodeRepoBatch], *, current_batch_id: str) -> None:
    completed = sum(1 for batch in batches if batch.status == "completed")
    running = sum(1 for batch in batches if batch.status == "running")
    blocked = sum(1 for batch in batches if batch.status == "blocked")
    failed = sum(1 for batch in batches if batch.status == "failed")
    payload = {
        "task_id": prepared.task_id,
        "status": "failed" if failed else "coding" if running else "ready",
        "current_batch_id": current_batch_id,
        "completed_batches": [batch.id for batch in batches if batch.status == "completed"],
        "failed_batches": [batch.id for batch in batches if batch.status == "failed"],
        "blocked_batches": [batch.id for batch in batches if batch.status == "blocked"],
        "repo_batches": [batch.to_payload() for batch in batches],
        "summary": {
            "total_batches": len(batches),
            "completed_batches": completed,
            "running_batches": running,
            "blocked_batches": blocked,
            "failed_batches": failed,
            "total_work_items": sum(len(batch.work_item_ids) for batch in batches),
            "completed_work_items": sum(len(batch.work_item_ids) for batch in batches if batch.status == "completed"),
        },
    }
    write_json_artifact(task_dir / "code-progress.json", payload)


def _update_repo_runtime_binding(task_dir, repo_id: str, repo_status: str, report: dict[str, object]) -> None:
    update_repo_binding(
        task_dir,
        repo_id,
        lambda current: current.update(
            {
                "status": repo_status,
                "branch": str(report.get("branch") or current.get("branch") or ""),
                "worktree": str(report.get("worktree") or current.get("worktree") or ""),
                "commit": str(report.get("commit") or current.get("commit") or ""),
            }
        ),
    )
