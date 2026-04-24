from __future__ import annotations

from pathlib import Path
import json

from coco_flow.models import ArtifactItem, DiagnosisSummary, RepoBinding, TaskDetail, TimelineItem
from coco_flow.models.task import CodeDispatchSummary, CodeProgressSummary
from coco_flow.services.runtime.repo_state import (
    clean_files_written,
    read_repo_code_result,
    read_repo_diff_patch,
    read_repo_diff_summary,
    summarize_repo_failure,
)

PLAN_V2_PRIMARY_ARTIFACTS = [
    "plan-work-items.json",
    "plan-execution-graph.json",
    "plan-validation.json",
    "plan-result.json",
    "plan.md",
]

PLAN_V2_INTERMEDIATE_ARTIFACTS = [
    "plan-task-outline.json",
    "plan-dependency-notes.json",
    "plan-risk-check.json",
]

TRACKED_ARTIFACTS = [
    "input.json",
    "input.log",
    "repos.json",
    "source.json",
    "prd.source.md",
    "prd-refined.md",
    "refine.notes.md",
    "design.notes.md",
    "refine-manual-extract.json",
    "refine-brief.draft.json",
    "refine-source.excerpt.md",
    "refine-brief.json",
    "refine-intent.json",
    "refine-verify.json",
    "refine-diagnosis.json",
    "refine-result.json",
    "design-input.json",
    "design-input.md",
    "design-research-plan.json",
    "design-research-summary.json",
    "design-adjudication.json",
    "design-review.json",
    "design-debate.json",
    "design-decision.json",
    "design-change-points.json",
    "design-repo-assignment.json",
    "design-research.json",
    "design-repo-responsibility-matrix.json",
    "design-skills-brief.md",
    "design-repo-binding.json",
    "design-sections.json",
    "design-verify.json",
    "design-diagnosis.json",
    "design-result.json",
    "plan-skills-selection.json",
    "plan-skills-brief.md",
    *PLAN_V2_INTERMEDIATE_ARTIFACTS,
    *PLAN_V2_PRIMARY_ARTIFACTS[:-1],
    "plan-scope.json",
    "plan-execution.json",
    "plan-verify.json",
    "plan-diagnosis.json",
    "design.md",
    "plan.md",
    "refine.log",
    "design.log",
    "plan.log",
    "code-dispatch.json",
    "code-progress.json",
    "code-result.json",
    "code.log",
    "diff.json",
    "diff.patch",
]


def build_task_detail(
    task_dir: Path,
    source_label: str,
    metadata: dict[str, object],
    source_meta: dict[str, object],
    repos_meta: dict[str, object],
) -> TaskDetail:
    task_id = str(metadata.get("task_id") or task_dir.name)
    status = str(metadata.get("status") or "unknown")
    code_dispatch = read_json_file(task_dir / "code-dispatch.json")
    code_progress = read_json_file(task_dir / "code-progress.json")
    design_repo_binding = read_json_file(task_dir / "design-repo-binding.json")
    repos = parse_repos(repos_meta, task_dir, code_dispatch, code_progress, design_repo_binding)
    diagnosis = build_latest_diagnosis(task_dir)

    return TaskDetail(
        task_id=task_id,
        title=str(metadata.get("title") or task_id),
        status=status,
        created_at=_optional_str(metadata.get("created_at")),
        updated_at=_optional_str(metadata.get("updated_at")),
        source_type=_optional_str(metadata.get("source_type") or source_meta.get("type")),
        source_value=_optional_str(metadata.get("source_value")),
        source_fetch_error=_optional_str(source_meta.get("fetch_error")),
        source_fetch_error_code=_optional_str(source_meta.get("fetch_error_code")),
        repo_count=int(metadata.get("repo_count") or len(repos)),
        task_dir=str(task_dir),
        source_label=source_label,
        next_action=build_next_action(task_id, status, task_dir, repos, diagnosis),
        repos=repos,
        code_dispatch=build_code_dispatch_summary(code_dispatch),
        code_progress=build_code_progress_summary(status, repos, code_dispatch, code_progress),
        diagnosis=diagnosis,
        timeline=build_timeline(status, task_dir),
        artifacts=build_artifacts(task_dir),
    )


def read_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def read_artifact_content(task_dir: Path, name: str) -> str:
    path = task_dir / name
    if not path.exists():
        return missing_artifact_placeholder(name)

    try:
        content = path.read_text()
    except OSError:
        return missing_artifact_placeholder(name)

    if not content.strip():
        return empty_artifact_placeholder(name)
    return content


def build_artifacts(task_dir: Path) -> list[ArtifactItem]:
    items: list[ArtifactItem] = []
    for name in TRACKED_ARTIFACTS:
        path = task_dir / name
        exists = path.exists()
        items.append(
            ArtifactItem(
                name=name,
                path=str(path),
                exists=exists,
                content=read_artifact_content(task_dir, name),
            )
        )
    return items


def build_latest_diagnosis(task_dir: Path) -> DiagnosisSummary | None:
    for name in ("plan-diagnosis.json", "design-diagnosis.json", "refine-diagnosis.json"):
        payload = read_json_file(task_dir / name)
        if not payload:
            continue
        issues = payload.get("issues")
        return DiagnosisSummary(
            stage=str(payload.get("stage") or name.split("-", 1)[0]),
            ok=bool(payload.get("ok")),
            severity=str(payload.get("severity") or ""),
            failure_type=str(payload.get("failure_type") or ""),
            next_action=str(payload.get("next_action") or ""),
            reason=str(payload.get("reason") or ""),
            issue_count=len(issues) if isinstance(issues, list) else 0,
        )
    return None


def parse_repos(
    repos_meta: dict[str, object],
    task_dir: Path | None = None,
    code_dispatch: dict[str, object] | None = None,
    code_progress: dict[str, object] | None = None,
    design_repo_binding: dict[str, object] | None = None,
) -> list[RepoBinding]:
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list):
        return []

    dispatch_by_repo = build_repo_batch_index(code_dispatch or {})
    progress_by_repo = build_repo_batch_index(code_progress or {})
    design_binding_by_repo = build_design_binding_index(design_repo_binding or {})

    repos: list[RepoBinding] = []
    for item in raw_repos:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("id") or "")
        repo_path = str(item.get("path") or "")
        status = _optional_str(item.get("status"))
        branch = _optional_str(item.get("branch"))
        worktree = _optional_str(item.get("worktree"))
        commit = _optional_str(item.get("commit"))
        scope_tier = _optional_str(item.get("scope_tier"))
        confidence: str | None = None
        build = "n/a"
        failure_hint: str | None = None
        failure_type: str | None = None
        failure_action: str | None = None
        files_written: list[str] | None = None
        diff_summary: dict[str, object] | None = None
        execution_mode: str | None = None
        batch_id: str | None = None
        batch_status: str | None = None
        work_item_ids: list[str] | None = None
        depends_on_batch_ids: list[str] | None = None
        verify_result: dict[str, object] | None = None

        dispatch_entry = dispatch_by_repo.get(repo_id, {})
        progress_entry = progress_by_repo.get(repo_id, {})
        design_binding_entry = design_binding_by_repo.get(repo_id, {})
        if dispatch_entry:
            scope_tier = scope_tier or _optional_str(dispatch_entry.get("scope_tier"))
            execution_mode = _optional_str(dispatch_entry.get("execution_mode") or dispatch_entry.get("mode"))
            batch_id = _optional_str(dispatch_entry.get("batch_id") or dispatch_entry.get("id"))
            work_item_ids = _string_list(
                dispatch_entry.get("work_item_ids") or dispatch_entry.get("work_items")
            ) or None
            depends_on_batch_ids = _string_list(
                dispatch_entry.get("depends_on_batch_ids") or dispatch_entry.get("depends_on_batches")
            ) or None
        if progress_entry:
            execution_mode = execution_mode or _optional_str(progress_entry.get("execution_mode") or progress_entry.get("mode"))
            batch_id = batch_id or _optional_str(progress_entry.get("batch_id") or progress_entry.get("id"))
            batch_status = _optional_str(progress_entry.get("status"))
            if not work_item_ids:
                work_item_ids = _string_list(
                    progress_entry.get("work_item_ids") or progress_entry.get("work_items")
                ) or None
            if not depends_on_batch_ids:
                depends_on_batch_ids = _string_list(
                    progress_entry.get("depends_on_batch_ids") or progress_entry.get("depends_on_batches")
                ) or None
        if design_binding_entry:
            scope_tier = scope_tier or _optional_str(design_binding_entry.get("scope_tier"))
            confidence = _optional_str(design_binding_entry.get("confidence"))
            execution_mode = execution_mode or infer_execution_mode(scope_tier)

        if task_dir is not None and repo_id:
            report = read_repo_code_result(task_dir, repo_id)
            if report:
                build = infer_repo_build_from_report(report)
                failure_type = _optional_str(report.get("failure_type"))
                failure_hint = summarize_repo_failure(task_dir, repo_id, report)
                failure_action = _optional_str(report.get("failure_action"))
                files_written = clean_files_written(
                    [str(path) for path in (report.get("files_written") or []) if isinstance(path, str)],
                    repo_path,
                    worktree or "",
                ) or None
                branch = branch or _optional_str(report.get("branch"))
                worktree = worktree or _optional_str(report.get("worktree"))
                commit = commit or _optional_str(report.get("commit"))
                status = status or _optional_str(report.get("status"))
                batch_status = batch_status or _optional_str(report.get("status"))
                execution_mode = execution_mode or _optional_str(report.get("execution_mode"))
            diff_meta = read_repo_diff_summary(task_dir, repo_id)
            if diff_meta:
                patch = ""
                try:
                    patch = read_repo_diff_patch(task_dir, repo_id)
                except OSError:
                    patch = ""
                diff_summary = {
                    "repoId": str(diff_meta.get("repo_id") or repo_id),
                    "commit": str(diff_meta.get("commit") or commit or ""),
                    "branch": str(diff_meta.get("branch") or branch or ""),
                    "files": [str(path) for path in (diff_meta.get("files") or []) if isinstance(path, str)],
                    "additions": int(diff_meta.get("additions") or 0),
                    "deletions": int(diff_meta.get("deletions") or 0),
                    "patch": patch,
                }
            verify_result = read_repo_verify_result(task_dir, repo_id)
            if verify_result:
                if failure_type is None and not _verify_result_ok(verify_result):
                    failure_type = _optional_str(verify_result.get("failure_type")) or "verify_failed"
                if failure_action is None:
                    failure_action = _optional_str(verify_result.get("failure_action"))
                if failure_hint is None and not _verify_result_ok(verify_result):
                    failure_hint = _optional_str(
                        verify_result.get("summary") or verify_result.get("error")
                    )

        repos.append(
            RepoBinding(
                repo_id=repo_id,
                path=repo_path,
                status=status,
                scope_tier=scope_tier,
                confidence=confidence,
                execution_mode=execution_mode,
                batch_id=batch_id,
                batch_status=batch_status,
                work_item_ids=work_item_ids,
                depends_on_batch_ids=depends_on_batch_ids,
                branch=branch,
                worktree=worktree,
                commit=commit,
                build=build,
                failure_type=failure_type,
                failure_hint=failure_hint,
                failure_action=failure_action,
                files_written=files_written,
                diff_summary=diff_summary,
                verify_result=verify_result,
            )
        )
    return repos


def build_repo_batch_index(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    entries = payload.get("batches") or payload.get("repo_batches") or payload.get("repos")
    if not isinstance(entries, list):
        return {}

    indexed: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        repo_id = _optional_str(entry.get("repo_id") or entry.get("repo"))
        if not repo_id:
            continue
        indexed[repo_id] = entry
    return indexed


def build_design_binding_index(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    raw = payload.get("repo_bindings") or payload.get("bindings")
    if not isinstance(raw, list):
        return {}
    indexed: dict[str, dict[str, object]] = {}
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        repo_id = _optional_str(entry.get("repo_id") or entry.get("repo"))
        if not repo_id:
            continue
        indexed[repo_id] = entry
    return indexed


def build_code_progress_summary(
    task_status: str,
    repos: list[RepoBinding],
    code_dispatch: dict[str, object],
    code_progress: dict[str, object],
) -> CodeProgressSummary | None:
    if not code_dispatch and not code_progress:
        return None

    batch_entries = code_progress.get("batches") or code_progress.get("repo_batches")
    summary = code_progress.get("summary")
    if isinstance(summary, dict):
        total_batches = _safe_int(summary.get("total_batches") or summary.get("batch_total"))
        completed_batches = _safe_int(summary.get("completed_batches") or summary.get("batch_completed"))
        running_batches = _safe_int(summary.get("running_batches") or summary.get("batch_running"))
        blocked_batches = _safe_int(summary.get("blocked_batches") or summary.get("batch_blocked"))
        failed_batches = _safe_int(summary.get("failed_batches") or summary.get("batch_failed"))
        total_work_items = _safe_int(summary.get("total_work_items") or summary.get("work_item_total"))
        completed_work_items = _safe_int(
            summary.get("completed_work_items") or summary.get("work_item_completed")
        )
    else:
        batch_list = [entry for entry in batch_entries if isinstance(entry, dict)] if isinstance(batch_entries, list) else []
        total_batches = len(batch_list)
        completed_batches = sum(1 for entry in batch_list if str(entry.get("status") or "") in {"done", "completed", "coded"})
        running_batches = sum(1 for entry in batch_list if str(entry.get("status") or "") in {"running", "coding", "in_progress"})
        blocked_batches = sum(1 for entry in batch_list if str(entry.get("status") or "") in {"blocked", "waiting_on_dependency"})
        failed_batches = sum(1 for entry in batch_list if str(entry.get("status") or "") in {"failed", "verify_failed"})
        total_work_items = sum(len(_string_list(entry.get("work_item_ids") or entry.get("work_items"))) for entry in batch_list)
        completed_work_items = sum(
            len(_string_list(entry.get("completed_work_item_ids") or entry.get("completed_work_items")))
            for entry in batch_list
        )
        if not batch_list and code_dispatch:
            dispatch_batches = code_dispatch.get("batches") or code_dispatch.get("repo_batches")
            if isinstance(dispatch_batches, list):
                dispatch_list = [entry for entry in dispatch_batches if isinstance(entry, dict)]
                total_batches = len(dispatch_list)
                total_work_items = sum(
                    len(_string_list(entry.get("work_item_ids") or entry.get("work_items")))
                    for entry in dispatch_list
                )

    return CodeProgressSummary(
        status=_optional_str(code_progress.get("status")) or task_status,
        total_batches=total_batches,
        completed_batches=completed_batches,
        running_batches=running_batches,
        blocked_batches=blocked_batches or sum(1 for repo in repos if is_blocked_repo(repo)),
        failed_batches=failed_batches or sum(
            1
            for repo in repos
            if (repo.status or "") == "failed" or (repo.failure_type or "") in {"verify_failed", "code_failed"}
        ),
        total_work_items=total_work_items,
        completed_work_items=completed_work_items,
    )


def build_code_dispatch_summary(code_dispatch: dict[str, object]) -> CodeDispatchSummary | None:
    if not code_dispatch:
        return None
    batch_entries = code_dispatch.get("batches") or code_dispatch.get("repo_batches")
    if not isinstance(batch_entries, list):
        batch_entries = []
    repo_ids: list[str] = []
    batch_ids: list[str] = []
    for entry in batch_entries:
        if not isinstance(entry, dict):
            continue
        repo_id = _optional_str(entry.get("repo_id") or entry.get("repo"))
        batch_id = _optional_str(entry.get("batch_id") or entry.get("id"))
        if repo_id and repo_id not in repo_ids:
            repo_ids.append(repo_id)
        if batch_id and batch_id not in batch_ids:
            batch_ids.append(batch_id)
    return CodeDispatchSummary(
        total_batches=len(batch_ids) or len(batch_entries),
        repo_ids=repo_ids,
        batch_ids=batch_ids,
    )


def infer_repo_build_from_report(report: dict[str, object]) -> str:
    if "build_ok" in report:
        return "passed" if bool(report.get("build_ok")) else "failed"
    verify_ok = report.get("verify_ok")
    if isinstance(verify_ok, bool):
        return "passed" if verify_ok else "failed"
    return "n/a"


def infer_execution_mode(scope_tier: str | None) -> str | None:
    if scope_tier == "validate_only":
        return "verify_only"
    if scope_tier == "reference_only":
        return "reference_only"
    if scope_tier:
        return "apply"
    return None


def read_repo_verify_result(task_dir: Path, repo_id: str) -> dict[str, object] | None:
    path = task_dir / "code-verify" / f"{sanitize_repo_id(repo_id)}.json"
    payload = read_json_file(path)
    return payload or None


def sanitize_repo_id(repo_id: str) -> str:
    sanitized = []
    for char in repo_id.strip():
        sanitized.append(char.lower() if char.isalnum() else "_")
    value = "".join(sanitized).strip("_")
    return value or "repo"


def _verify_result_ok(payload: dict[str, object]) -> bool | None:
    ok = payload.get("ok")
    if isinstance(ok, bool):
        return ok
    status = str(payload.get("status") or "").strip().lower()
    if status in {"passed", "ok", "success"}:
        return True
    if status in {"failed", "error"}:
        return False
    return None


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def build_next_action(
    task_id: str,
    status: str,
    task_dir: Path,
    repos: list[RepoBinding],
    diagnosis: DiagnosisSummary | None = None,
) -> str:
    has_refined = (task_dir / "prd-refined.md").exists()
    has_design = (task_dir / "design.md").exists()
    has_plan = has_plan_artifacts(task_dir)
    if diagnosis and diagnosis.severity in {"needs_human", "degraded"}:
        if diagnosis.failure_type == "missing_human_scope":
            return f"请先补齐 {task_dir / 'prd.source.md'} 中的人工提炼范围，然后重新执行 coco-flow tasks refine {task_id}"
        if diagnosis.failure_type == "repo_responsibility_uncertain":
            return f"请先确认 {task_dir / 'design-repo-binding.json'} 中的仓库执行职责，然后重新执行 coco-flow tasks design {task_id}"
        if diagnosis.stage == "design":
            return f"请先查看 {task_dir / 'design-diagnosis.json'} 和 {task_dir / 'design-decision.json'}，确认后重新执行 coco-flow tasks design {task_id}"
        return "当前阶段需要人工确认，请先查看 diagnosis artifact。"
    if diagnosis and diagnosis.stage == "design" and not diagnosis.ok:
        return f"请先查看 {task_dir / 'design-diagnosis.json'}，然后重新执行 coco-flow tasks design {task_id}"
    if status == "input_processing":
        return "Input 正在解析飞书正文，请稍候刷新任务详情。"
    if status == "input_failed":
        return f"请检查 {(task_dir / 'input.log')} 或手动编辑 {(task_dir / 'prd.source.md')}，确认正文后再执行 coco-flow tasks refine {task_id}"
    if status == "input_ready" and not has_refined:
        return f"coco-flow tasks refine {task_id}"
    if status == "refining":
        return "refine 正在执行，请稍候刷新任务详情。"
    if is_pending_refine_state(task_dir):
        return f"请先补充 {task_dir / 'prd.source.md'} 的正文，然后重新执行 coco-flow tasks refine {task_id}"

    if not has_refined:
        return f"coco-flow tasks refine {task_id}"
    if status == "designing":
        return "design 正在执行，请稍候刷新任务详情。"
    if status == "designed" and not has_plan:
        return f"coco-flow tasks plan {task_id}"
    if status == "planning":
        return "plan 正在执行，请稍候刷新任务详情。"
    if status == "failed" and not has_design:
        return f"coco-flow tasks design {task_id}"
    if status == "failed" and not has_plan:
        return f"coco-flow tasks plan {task_id}"
    if not has_design:
        return f"coco-flow tasks design {task_id}"
    if not has_design or not has_plan:
        return f"coco-flow tasks plan {task_id}"
    if status == "coding":
        return "code workspace 已准备，可继续接入自动实现或人工推进。"
    if status in {"partially_coded", "failed"}:
        next_repo = suggest_next_repo(repos)
        if next_repo:
            return f"coco-flow tasks code {task_id} --repo {next_repo}"
        blocked = summarize_blocked_repos(repos)
        if blocked:
            return f"当前可见 repo 受依赖阻塞：{blocked}。请先推进其依赖的上游 repo。"
    if status == "planned":
        next_repo = suggest_next_repo(repos)
        if next_repo:
            return f"coco-flow tasks code {task_id} --repo {next_repo}"
        blocked = summarize_blocked_repos(repos)
        if blocked:
            return f"当前可见 repo 受依赖阻塞：{blocked}。请先推进其依赖的上游 repo。"
        return f"coco-flow tasks code {task_id}"
    if status == "coded":
        return f"coco-flow tasks archive {task_id}"
    if status == "archived":
        return "task 已归档，无后续操作。"
    return "当前 task 无明确下一步，建议人工确认状态。"


def suggest_next_repo(repos: list[RepoBinding]) -> str | None:
    for repo in repos:
        if is_blocked_repo(repo):
            continue
        if repo.status in {
            None,
            "",
            "pending",
            "initialized",
            "refined",
            "planned",
            "failed",
        }:
            return repo.repo_id
    return None


def is_blocked_repo(repo: RepoBinding) -> bool:
    return (repo.failure_type or "") == "blocked_by_dependency"


def summarize_blocked_repos(repos: list[RepoBinding]) -> str:
    blocked = [repo.repo_id for repo in repos if repo.repo_id and is_blocked_repo(repo)]
    if not blocked:
        return ""
    return ", ".join(blocked)


def build_timeline(status: str, task_dir: Path) -> list[TimelineItem]:
    input_state, refine_state, design_state, plan_state, code_state, archive_state = (
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
        "pending",
    )
    input_detail, refine_detail, design_detail, plan_detail, code_detail, archive_detail = (
        "等待 Input",
        "等待 Refine",
        "等待 Design",
        "等待 Plan",
        "等待 Code",
        "等待 Archive",
    )
    has_design = (task_dir / "design.md").exists()
    has_plan = has_plan_artifacts(task_dir)
    repos = parse_repos(read_json_file(task_dir / "repos.json"), task_dir)
    blocked = summarize_blocked_repos(repos)
    next_repo = suggest_next_repo(repos)

    if status == "initialized":
        input_state = "current"
        input_detail = "已创建 task，等待整理输入内容"
        refine_detail = "等待 Input 就绪"
    elif status == "input_processing":
        input_state = "current"
        input_detail = "正在解析飞书正文并生成标准输入稿"
        refine_detail = "等待 Input 就绪"
    elif status == "input_failed":
        input_state = "current"
        input_detail = "飞书正文拉取失败，请查看 input.log 或手动补充 prd.source.md"
        refine_detail = "等待 Input 修复"
    elif status == "input_ready":
        input_state, refine_state = "done", "current"
        input_detail = "已完成输入整理"
        refine_detail = "等待生成 refined PRD"
    elif status == "refining":
        input_state, refine_state = "done", "current"
        input_detail = "已完成输入整理"
        refine_detail = "正在提炼核心诉求、风险、讨论点和边界"
    elif status == "refined":
        input_state, refine_state, design_state = "done", "done", "current"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "等待生成 design.md 与正式仓库绑定"
        plan_detail = "等待 Design 完成后生成 Plan 任务和验证契约"
    elif status == "designing":
        input_state, refine_state, design_state = "done", "done", "current"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "正在调研代码并生成 design.md"
        plan_detail = "等待 Design 产物就绪"
    elif status == "designed":
        input_state, refine_state, design_state, plan_state = "done", "done", "done", "current"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "已生成 design.md"
        plan_detail = "等待生成 Plan 结构化产物"
    elif status == "planning":
        input_state, refine_state = "done", "done"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        if has_design:
            design_state, plan_state = "done", "current"
            design_detail = "已生成 design.md"
            plan_detail = "正在生成 Plan 任务拆分、执行顺序和验证契约"
        else:
            design_state, plan_state = "current", "pending"
            design_detail = "正在调研代码并生成 design.md"
            plan_detail = "等待 Design 产物就绪"
    elif status == "planned":
        input_state, refine_state, design_state, plan_state = "done", "done", "done", "done"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "已生成 design.md"
        plan_detail = "已生成 Plan 结构化产物"
        if blocked and not next_repo:
            code_state = "blocked"
            code_detail = f"当前 code 受依赖阻塞：{blocked}"
        else:
            code_state = "current"
            code_detail = "可进入 code 阶段"
    elif status in {"coding", "partially_coded"}:
        input_state, refine_state, design_state, plan_state, code_state = "done", "done", "done", "done", "current"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "已生成 design.md"
        plan_detail = "已生成 Plan 结构化产物"
        if blocked:
            code_detail = f"至少一个 repo 正在执行 code；另有 repo 受依赖阻塞：{blocked}"
        else:
            code_detail = "至少一个 repo 正在执行 code"
    elif status == "coded":
        input_state, refine_state, design_state, plan_state, code_state, archive_state = (
            "done",
            "done",
            "done",
            "done",
            "done",
            "current",
        )
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "已生成 design.md"
        plan_detail = "已生成 Plan 结构化产物"
        code_detail = "所有关联 repo 已完成 code"
        archive_detail = "可归档收尾"
    elif status == "archived":
        input_state, refine_state, design_state, plan_state, code_state, archive_state = (
            "done",
            "done",
            "done",
            "done",
            "done",
            "done",
        )
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "已生成 design.md"
        plan_detail = "已生成 Plan 结构化产物"
        code_detail = "已完成 code"
        archive_detail = "已归档"
    elif status == "failed":
        input_state, refine_state = "done", "done"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        if not has_design:
            design_state = "failed"
            design_detail = "Design 执行失败，请查看 design.log"
            plan_detail = "等待 Design 修复后再生成 Plan 产物"
        elif not has_plan:
            design_state, plan_state = "done", "failed"
            design_detail = "已生成 design.md"
            plan_detail = "Plan 执行失败，请查看 plan.log"
        else:
            design_state, plan_state = "done", "done"
            design_detail = "已生成 design.md"
            plan_detail = "已生成 Plan 结构化产物"
            if blocked:
                code_state = "blocked"
                code_detail = f"存在失败或阻塞的 repo，当前阻塞：{blocked}"
            else:
                code_state = "failed"
                code_detail = "存在失败的 repo，需继续处理"

    return [
        TimelineItem(label="Input", state=input_state, detail=input_detail),
        TimelineItem(label="Refine", state=refine_state, detail=refine_detail),
        TimelineItem(label="Design", state=design_state, detail=design_detail),
        TimelineItem(label="Plan", state=plan_state, detail=plan_detail),
        TimelineItem(label="Code", state=code_state, detail=code_detail),
        TimelineItem(label="Archive", state=archive_state, detail=archive_detail),
    ]


def missing_artifact_placeholder(name: str) -> str:
    if name == "input.log":
        return "当前没有可用的 input.log。可能任务尚未进入 Input 处理，或日志写入失败。"
    if name == "refine.log":
        return "当前没有可用的 refine.log。可能任务尚未启动 refine，或日志写入失败。"
    if name == "design.log":
        return "当前没有可用的 design.log。可能任务尚未启动 design，或日志写入失败。"
    if name == "plan.log":
        return "当前没有可用的 plan.log。可能任务尚未启动 plan，或日志写入失败。"
    if name in {"diff.json", "diff.patch"}:
        return "该任务当前没有可用的 diff artifact。生成 code 结果后可按仓库查看 diff。"
    return f"该 task 当前没有 `{name}`。"


def empty_artifact_placeholder(name: str) -> str:
    if name == "input.log":
        return "input.log 当前为空。"
    if name == "refine.log":
        return "refine.log 当前为空。"
    if name == "design.log":
        return "design.log 当前为空。"
    if name == "plan.log":
        return "plan.log 当前为空。"
    if name in {"diff.json", "diff.patch"}:
        return f"`{name}` 当前为空。"
    return f"`{name}` 当前为空。"


def is_pending_refine_state(task_dir: Path) -> bool:
    refined_path = task_dir / "prd-refined.md"
    if not refined_path.exists():
        return False
    try:
        content = refined_path.read_text()
    except OSError:
        return False
    return "状态：待补充源内容" in content


def has_plan_artifacts(task_dir: Path) -> bool:
    return any((task_dir / name).exists() for name in PLAN_V2_PRIMARY_ARTIFACTS)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
