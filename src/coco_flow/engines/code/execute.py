from __future__ import annotations

from datetime import datetime
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.code import build_code_execute_prompt, build_code_retry_prompt
from coco_flow.services.runtime.repo_state import (
    STATUS_ARCHIVED,
    STATUS_CODED,
    STATUS_FAILED,
    STATUS_PLANNED,
    clean_files_written,
)

from .models import (
    CodePreparedInput,
    CodeRepoBatch,
    CodeRepoRunResult,
    FAILURE_AGENT,
    FAILURE_BLOCKED,
    FAILURE_BUILD,
    FAILURE_GIT,
    FAILURE_RUNTIME,
    FAILURE_VERIFY,
    MAX_CODE_ATTEMPTS,
)
from .verify import verify_repo_changes

CODE_SHARED_CONTEXT_FILES = (
    "prd-refined.md",
    "design.md",
    "plan.md",
)


def execute_repo_batch(
    prepared: CodePreparedInput,
    batch: CodeRepoBatch,
    settings: Settings,
    *,
    on_log,
) -> CodeRepoRunResult:
    if batch.execution_mode == "verify_only":
        on_log(f"repo_verify_only: {batch.repo_id}")
        report = {
            "status": "no_change",
            "task_id": prepared.task_id,
            "repo_id": batch.repo_id,
            "repo_path": batch.repo_path,
            "branch": "",
            "worktree": "",
            "commit": "",
            "build_ok": True,
            "files_written": [],
            "summary": "verify-only repo 无需本地改码，已记录验证契约。",
            "failure_type": "",
            "failure_action": "",
            "execution_mode": batch.execution_mode,
            "error": "",
            "started_at": datetime.now().astimezone().isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(),
        }
        verify_payload = {
            "repo_id": batch.repo_id,
            "batch_id": batch.id,
            "mode": batch.execution_mode,
            "ok": True,
            "summary": "validate-only repo 无需本地改码，已记录验证契约。",
            "checks": batch.verify_rules,
            "failure_type": "",
            "failure_action": "",
            "verification_output": "verify-only repo: no local code changes required",
        }
        return CodeRepoRunResult(
            repo_id=batch.repo_id,
            batch_id=batch.id,
            execution_mode=batch.execution_mode,
            repo_status=STATUS_CODED,
            report=report,
            repo_log=_build_repo_log(batch, report, "verify-only batch completed\n", verify_payload["verification_output"]),
            verify_payload=verify_payload,
        )

    if settings.code_executor.strip().lower() == "local":
        return _execute_local_apply_batch(prepared, batch)
    return _execute_native_apply_batch(prepared, batch, settings, on_log=on_log)


def build_blocked_result(prepared: CodePreparedInput, batch: CodeRepoBatch, unmet_batch_ids: list[str]) -> CodeRepoRunResult:
    unmet_text = ", ".join(unmet_batch_ids)
    report = {
        "status": STATUS_PLANNED,
        "task_id": prepared.task_id,
        "repo_id": batch.repo_id,
        "repo_path": batch.repo_path,
        "branch": "",
        "worktree": "",
        "commit": "",
        "build_ok": False,
        "files_written": [],
        "summary": f"repo {batch.repo_id} 被依赖阻塞，需等待 {unmet_text}",
        "failure_type": FAILURE_BLOCKED,
        "failure_action": f"先推进上游 batch：{unmet_text}，完成后再继续当前 repo。",
        "execution_mode": batch.execution_mode,
        "error": f"blocked by dependencies: {unmet_text}",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    verify_payload = {
        "repo_id": batch.repo_id,
        "batch_id": batch.id,
        "mode": batch.execution_mode,
        "ok": False,
        "summary": report["summary"],
        "checks": batch.verify_rules,
        "failure_type": FAILURE_BLOCKED,
        "failure_action": report["failure_action"],
        "verification_output": report["error"],
    }
    return CodeRepoRunResult(
        repo_id=batch.repo_id,
        batch_id=batch.id,
        execution_mode=batch.execution_mode,
        repo_status=STATUS_PLANNED,
        report=report,
        repo_log=_build_repo_log(batch, report, "blocked before code execution\n", report["error"]),
        verify_payload=verify_payload,
    )


def _execute_local_apply_batch(prepared: CodePreparedInput, batch: CodeRepoBatch) -> CodeRepoRunResult:
    branch = build_branch_name(prepared.task_id, batch.repo_id)
    worktree = build_worktree_path(batch.repo_path, prepared.task_id)
    ensure_worktree(batch.repo_path, worktree, branch)
    sync_native_workspace(prepared, batch, Path(batch.repo_path), Path(worktree))
    report = {
        "status": "failed",
        "task_id": prepared.task_id,
        "repo_id": batch.repo_id,
        "repo_path": batch.repo_path,
        "branch": branch,
        "worktree": worktree,
        "commit": "",
        "build_ok": False,
        "files_written": [],
        "summary": "local code executor 当前仅准备 worktree，未实现自动改码。",
        "failure_type": FAILURE_RUNTIME,
        "failure_action": "请改用 native code executor，或手动在 worktree 中继续实现。",
        "execution_mode": batch.execution_mode,
        "error": "local code executor does not implement automatic apply batches",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    verify_payload = {
        "repo_id": batch.repo_id,
        "batch_id": batch.id,
        "mode": batch.execution_mode,
        "ok": False,
        "summary": report["summary"],
        "checks": batch.verify_rules,
        "failure_type": FAILURE_RUNTIME,
        "failure_action": report["failure_action"],
        "verification_output": report["error"],
    }
    return CodeRepoRunResult(
        repo_id=batch.repo_id,
        batch_id=batch.id,
        execution_mode=batch.execution_mode,
        repo_status=STATUS_FAILED,
        report=report,
        repo_log=_build_repo_log(batch, report, "local apply batch prepared only\n", report["error"]),
        verify_payload=verify_payload,
    )


def _execute_native_apply_batch(prepared: CodePreparedInput, batch: CodeRepoBatch, settings: Settings, *, on_log) -> CodeRepoRunResult:
    branch = build_branch_name(prepared.task_id, batch.repo_id)
    worktree = build_worktree_path(batch.repo_path, prepared.task_id)
    ensure_worktree(batch.repo_path, worktree, branch)
    sync_native_workspace(prepared, batch, Path(batch.repo_path), Path(worktree))

    client = CocoACPClient(
        settings.coco_bin,
        idle_timeout_seconds=settings.acp_idle_timeout_seconds,
        settings=settings,
    )
    agent_reply = ""
    clean_files: list[str] = []
    verification_ok = False
    verification_output = ""
    parsed: dict[str, object] = {"status": "failed", "build_ok": False, "summary": ""}

    work_item_brief = _render_work_item_brief(prepared.plan_work_items_payload, batch.work_item_ids)
    change_scope_brief = _render_list_block(batch.change_scope, fallback="- 当前 batch 未显式给出 change scope。")
    verify_brief = _render_list_block(batch.verify_rules, fallback="- 当前 batch 未显式给出 verify rules。")
    dependency_brief = _render_list_block(batch.depends_on_batch_ids, fallback="- 当前 batch 无 batch 级前置依赖。")

    prompt = build_code_execute_prompt(
        task_id=prepared.task_id,
        repo_id=batch.repo_id,
        execution_mode=batch.execution_mode,
        work_item_brief=work_item_brief,
        change_scope_brief=change_scope_brief,
        verify_brief=verify_brief,
        dependency_brief=dependency_brief,
    )

    for attempt in range(1, MAX_CODE_ATTEMPTS + 1):
        on_log(f"repo_attempt: {batch.repo_id} {attempt}/{MAX_CODE_ATTEMPTS}")
        agent_reply = client.run_agent(prompt, settings.native_code_timeout, worktree)
        parsed = parse_native_code_result(agent_reply)
        changed_files = collect_code_changes(worktree)
        clean_files = clean_files_written(changed_files, batch.repo_path, worktree)
        verification_ok, verification_output = verify_repo_changes(
            worktree,
            clean_files or batch.change_scope,
            verify_rules=batch.verify_rules,
            enable_go_test=settings.enable_go_test_verify,
        )
        for line in verification_output.splitlines():
            if line.strip():
                on_log(f"repo_verify_output: {line}")
        parsed["build_ok"] = verification_ok
        if verification_ok or str(parsed.get("status") or "") == "no_change":
            on_log(f"repo_verify_ok: {batch.repo_id}")
            break
        if attempt >= MAX_CODE_ATTEMPTS:
            on_log(f"repo_verify_failed: {batch.repo_id} giving up after {attempt} attempts")
            break
        on_log(f"repo_verify_failed: {batch.repo_id} attempt={attempt}")
        prompt = build_code_retry_prompt(
            task_id=prepared.task_id,
            repo_id=batch.repo_id,
            execution_mode=batch.execution_mode,
            work_item_brief=work_item_brief,
            change_scope_brief=change_scope_brief,
            verify_brief=verify_brief,
            dependency_brief=dependency_brief,
            changed_file_brief=_render_list_block(clean_files or batch.change_scope, fallback="- 当前未检测到稳定变更文件"),
            verification_output=verification_output,
        )

    commit_hash = ""
    patch = ""
    status = str(parsed.get("status") or "failed")
    if verification_ok and not clean_files and status == "success":
        status = "no_change"

    if clean_files and verification_ok:
        try:
            patch = stage_and_read_patch(worktree, clean_files)
            commit_hash = commit_code_changes(worktree, prepared.task_id)
            repo_status = STATUS_CODED
            failure_type = ""
            failure_action = ""
        except Exception as error:
            repo_status = STATUS_FAILED
            verification_ok = False
            verification_output = str(error)
            failure_type = FAILURE_GIT
            failure_action = suggest_failure_action(failure_type)
            on_log(f"repo_git_failed: {batch.repo_id} {error}")
    elif verification_ok:
        repo_status = STATUS_CODED
        failure_type = ""
        failure_action = ""
    else:
        repo_status = STATUS_FAILED
        failure_type = classify_failure_type(status, verification_output, bool(clean_files))
        failure_action = suggest_failure_action(failure_type)
        on_log(f"repo_failure_type: {batch.repo_id} {failure_type}")

    report = {
        "status": "failed" if repo_status == STATUS_FAILED else status,
        "task_id": prepared.task_id,
        "repo_id": batch.repo_id,
        "repo_path": batch.repo_path,
        "branch": branch,
        "worktree": worktree,
        "commit": commit_hash,
        "build_ok": verification_ok,
        "files_written": clean_files,
        "summary": str(parsed.get("summary") or ""),
        "failure_type": failure_type,
        "failure_action": failure_action,
        "execution_mode": batch.execution_mode,
        "error": "" if repo_status != STATUS_FAILED else verification_output.strip() or str(parsed.get("summary") or "") or "实现失败",
        "started_at": datetime.now().astimezone().isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    verify_payload = {
        "repo_id": batch.repo_id,
        "batch_id": batch.id,
        "mode": batch.execution_mode,
        "ok": verification_ok,
        "summary": "最小验证通过" if verification_ok else report["error"] or report["summary"],
        "checks": batch.verify_rules,
        "failure_type": failure_type,
        "failure_action": failure_action,
        "verification_output": verification_output,
    }
    return CodeRepoRunResult(
        repo_id=batch.repo_id,
        batch_id=batch.id,
        execution_mode=batch.execution_mode,
        repo_status=repo_status,
        report=report,
        repo_log=_build_repo_log(batch, report, agent_reply, verification_output),
        verify_payload=verify_payload,
        diff_patch=patch,
    )


def _build_repo_log(batch: CodeRepoBatch, report: dict[str, object], body: str, verification_output: str = "") -> str:
    lines = [
        f"[{batch.repo_id}] code v2 executed",
        f"batch_id={batch.id}",
        f"repo={report.get('repo_path') or ''}",
        f"branch={report.get('branch') or ''}",
        f"worktree={report.get('worktree') or ''}",
        f"execution_mode={report.get('execution_mode') or batch.execution_mode}",
        f"status={report.get('status') or ''}",
        f"failure_type={report.get('failure_type') or '-'}",
        f"build_ok={report.get('build_ok')}",
        f"commit={report.get('commit') or '-'}",
        f"files_written={', '.join([str(item) for item in report.get('files_written') or []]) or '-'}",
        "verification:",
        verification_output.strip() or "verification skipped or passed without output",
        "reply:",
        body.strip(),
        "",
    ]
    return "\n".join(lines)


def _render_work_item_brief(payload: dict[str, object], work_item_ids: list[str]) -> str:
    raw = payload.get("work_items")
    if not isinstance(raw, list):
        return "- 当前未提取到结构化 work items。"
    lines: list[str] = []
    selected = {item_id for item_id in work_item_ids}
    for item in raw:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id") or "").strip()
        if task_id not in selected:
            continue
        lines.append(f"- {task_id} {str(item.get('title') or '').strip()}")
        for key in ("goal",):
            value = str(item.get(key) or "").strip()
            if value:
                lines.append(f"  {key}: {value}")
        for key in ("change_scope", "done_definition", "verification_steps"):
            values = [str(value).strip() for value in (item.get(key) or []) if str(value).strip()]
            if values:
                lines.append(f"  {key}:")
                lines.extend(f"    - {value}" for value in values[:6])
    return "\n".join(lines) if lines else "- 当前未提取到结构化 work items。"


def _render_list_block(items: list[str], *, fallback: str) -> str:
    normalized = _dedupe(items)
    if not normalized:
        return fallback
    return "\n".join(f"- {item}" for item in normalized)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        current = str(item).strip()
        lowered = current.lower()
        if not current or lowered in seen:
            continue
        seen.add(lowered)
        result.append(current)
    return result


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


def sync_native_workspace(prepared: CodePreparedInput, batch: CodeRepoBatch, repo_root: Path, worktree_root: Path) -> None:
    task_dir = prepared.task_dir
    task_id = prepared.task_id
    task_target = worktree_root / ".coco-flow" / "tasks" / task_id
    if task_target.exists():
        shutil.rmtree(task_target)
    task_target.mkdir(parents=True, exist_ok=True)
    for name in CODE_SHARED_CONTEXT_FILES:
        copy_file_if_exists(task_dir / name, task_target / name)
    bundle_payload = build_code_batch_bundle(prepared, batch)
    (task_target / "code-batch.json").write_text(
        json.dumps(bundle_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_target / "code-batch.md").write_text(render_code_batch_markdown(bundle_payload), encoding="utf-8")
    context_source = repo_root / ".livecoding" / "context"
    if context_source.exists():
        sync_local_tree(context_source, worktree_root / ".livecoding" / "context", replace=True)


def copy_file_if_exists(source: Path, target: Path) -> None:
    if not source.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def sync_local_tree(source: Path, target: Path, replace: bool) -> None:
    if source.resolve() == target.resolve():
        return
    if not source.exists():
        raise ValueError(f"task directory missing: {source}")
    if replace and target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=not replace)


def build_code_batch_bundle(prepared: CodePreparedInput, batch: CodeRepoBatch) -> dict[str, object]:
    binding = _binding_for_repo(prepared.design_repo_binding_payload, batch.repo_id)
    work_items = _work_items_for_batch(prepared.plan_work_items_payload, batch.work_item_ids)
    validations = _validations_for_batch(prepared.plan_validation_payload, batch.work_item_ids, batch.repo_id)
    return {
        "task_id": prepared.task_id,
        "title": prepared.title,
        "repo_id": batch.repo_id,
        "repo_path": batch.repo_path,
        "batch_id": batch.id,
        "execution_mode": batch.execution_mode,
        "scope_tier": batch.scope_tier,
        "summary": batch.summary,
        "work_item_ids": batch.work_item_ids,
        "depends_on_batch_ids": batch.depends_on_batch_ids,
        "change_scope": batch.change_scope,
        "verify_rules": batch.verify_rules,
        "done_definition": batch.done_definition,
        "shared_context_files": [name for name in CODE_SHARED_CONTEXT_FILES if (prepared.task_dir / name).exists()],
        "repo_binding": {
            "reason": str(binding.get("reason") or "").strip(),
            "candidate_files": _string_list(binding.get("candidate_files")),
            "change_summary": _string_list(binding.get("change_summary")),
            "boundaries": _string_list(binding.get("boundaries")),
        },
        "work_items": work_items,
        "validations": validations,
        "global_validation_focus": _string_list(prepared.plan_validation_payload.get("global_validation_focus")),
    }


def render_code_batch_markdown(bundle: dict[str, object]) -> str:
    work_items = bundle.get("work_items")
    validations = bundle.get("validations")
    binding = bundle.get("repo_binding") if isinstance(bundle.get("repo_binding"), dict) else {}
    lines = [
        "# Code Batch",
        "",
        f"- task_id: {bundle.get('task_id') or ''}",
        f"- repo_id: {bundle.get('repo_id') or ''}",
        f"- batch_id: {bundle.get('batch_id') or ''}",
        f"- execution_mode: {bundle.get('execution_mode') or ''}",
        f"- scope_tier: {bundle.get('scope_tier') or ''}",
        "",
        "## Rules",
        "",
        "- 只实现本文件列出的 work items，不要实现其他 repo 或其他 batch 的任务。",
        "- 只在当前 worktree 内修改与当前 repo batch 相关的代码。",
        "- 如需参考全局背景，只读 shared_context_files 中列出的文件。",
        "",
        "## Repo Decision",
        "",
        str(binding.get("reason") or "当前没有额外的 repo decision 说明。"),
        "",
        "## Work Items",
        "",
    ]
    if isinstance(work_items, list) and work_items:
        for item in work_items:
            if not isinstance(item, dict):
                continue
            lines.append(f"### {item.get('id') or ''} {item.get('title') or ''}".strip())
            lines.append("")
            lines.append(f"- goal: {item.get('goal') or ''}")
            lines.append(f"- change_scope: {', '.join(_string_list(item.get('change_scope')) ) or '-'}")
            lines.append(f"- done_definition: {', '.join(_string_list(item.get('done_definition')) ) or '-'}")
            lines.append(f"- verification_steps: {', '.join(_string_list(item.get('verification_steps')) ) or '-'}")
            lines.append("")
    else:
        lines.append("- 当前没有结构化 work items。")
        lines.append("")
    lines.extend(["## Validation", ""])
    if isinstance(validations, list) and validations:
        for item in validations:
            if not isinstance(item, dict):
                continue
            lines.append(f"- {item.get('task_id') or ''}: {', '.join(_render_validation_reasons(item)) or '未提供'}")
    else:
        lines.append("- 当前没有结构化验证条目。")
    lines.append("")
    return "\n".join(lines)


def _binding_for_repo(payload: dict[str, object], repo_id: str) -> dict[str, object]:
    raw = payload.get("repo_bindings")
    if not isinstance(raw, list):
        return {}
    for item in raw:
        if isinstance(item, dict) and str(item.get("repo_id") or "").strip() == repo_id:
            return item
    return {}


def _work_items_for_batch(payload: dict[str, object], work_item_ids: list[str]) -> list[dict[str, object]]:
    raw = payload.get("work_items")
    if not isinstance(raw, list):
        return []
    allowed = set(work_item_ids)
    return [item for item in raw if isinstance(item, dict) and str(item.get("id") or "") in allowed]


def _validations_for_batch(payload: dict[str, object], work_item_ids: list[str], repo_id: str) -> list[dict[str, object]]:
    raw = payload.get("task_validations")
    if not isinstance(raw, list):
        return []
    allowed = set(work_item_ids)
    result: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        current_task_id = str(item.get("task_id") or "").strip()
        current_repo_id = str(item.get("repo_id") or "").strip()
        if current_task_id and current_task_id in allowed:
            result.append(item)
            continue
        if not current_task_id and current_repo_id == repo_id:
            result.append(item)
    return result


def _render_validation_reasons(item: dict[str, object]) -> list[str]:
    raw = item.get("checks")
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for check in raw:
        if not isinstance(check, dict):
            continue
        parts = [str(check.get("kind") or "").strip(), str(check.get("target") or "").strip(), str(check.get("reason") or "").strip()]
        text = " / ".join(part for part in parts if part)
        if text:
            result.append(text)
    return result


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def sanitize_repo_name(repo_id: str) -> str:
    sanitized = []
    for char in repo_id.strip():
        if char.isalnum():
            sanitized.append(char.lower())
        else:
            sanitized.append("_")
    value = "".join(sanitized).strip("_")
    return value or "repo"


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
