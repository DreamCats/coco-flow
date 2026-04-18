from __future__ import annotations

from pathlib import Path
import json

from coco_flow.models import ArtifactItem, RepoBinding, TaskDetail, TimelineItem
from coco_flow.services.runtime.repo_state import (
    clean_files_written,
    read_repo_code_log,
    read_repo_code_result,
    read_repo_diff_patch,
    read_repo_diff_summary,
    summarize_repo_failure,
)

TRACKED_ARTIFACTS = [
    "input.json",
    "input.log",
    "repos.json",
    "source.json",
    "prd.source.md",
    "prd-refined.md",
    "refine.notes.md",
    "design.notes.md",
    "refine-intent.json",
    "refine-query.json",
    "refine-knowledge-selection.json",
    "refine-knowledge-read.md",
    "refine-verify.json",
    "refine-result.json",
    "design-change-points.json",
    "design-repo-assignment.json",
    "design-research.json",
    "design-knowledge-brief.md",
    "design-repo-binding.json",
    "design-sections.json",
    "design-verify.json",
    "design-result.json",
    "plan-knowledge-selection.json",
    "plan-knowledge-brief.md",
    "plan-scope.json",
    "plan-execution.json",
    "plan-verify.json",
    "design.md",
    "plan.md",
    "refine.log",
    "design.log",
    "plan.log",
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
    repos = parse_repos(repos_meta, task_dir)

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
        next_action=build_next_action(task_id, status, task_dir, repos),
        repos=repos,
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


def parse_repos(repos_meta: dict[str, object], task_dir: Path | None = None) -> list[RepoBinding]:
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list):
        return []

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
        build = "n/a"
        failure_hint: str | None = None
        failure_type: str | None = None
        failure_action: str | None = None
        files_written: list[str] | None = None
        diff_summary: dict[str, object] | None = None

        if task_dir is not None and repo_id:
            report = read_repo_code_result(task_dir, repo_id)
            if report:
                build = "passed" if bool(report.get("build_ok")) else "failed"
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

        repos.append(
            RepoBinding(
                repo_id=repo_id,
                path=repo_path,
                status=status,
                branch=branch,
                worktree=worktree,
                commit=commit,
                build=build,
                failure_type=failure_type,
                failure_hint=failure_hint,
                failure_action=failure_action,
                files_written=files_written,
                diff_summary=diff_summary,
            )
        )
    return repos


def build_next_action(
    task_id: str, status: str, task_dir: Path, repos: list[RepoBinding]
) -> str:
    has_refined = (task_dir / "prd-refined.md").exists()
    has_design = (task_dir / "design.md").exists()
    has_plan = (task_dir / "plan.md").exists()
    if status == "input_processing":
        return "Input 正在解析飞书正文，请稍候刷新任务详情。"
    if status == "input_failed":
        return f"请检查 {(task_dir / 'input.log')} 或手动编辑 {(task_dir / 'prd.source.md')}，确认正文后再执行 coco-flow prd refine --task {task_id}"
    if status == "input_ready" and not has_refined:
        return f"coco-flow prd refine --task {task_id}"
    if status == "refining":
        return "refine 正在执行，请稍候刷新任务详情。"
    if is_pending_refine_state(task_dir):
        return f"请先补充 {task_dir / 'prd.source.md'} 的正文，然后重新执行 coco-flow prd refine --task {task_id}"

    if not has_refined:
        return f"coco-flow prd refine --task {task_id}"
    if status == "designing":
        return "design 正在执行，请稍候刷新任务详情。"
    if status == "designed" and not has_plan:
        return f"coco-flow prd plan --task {task_id}"
    if status == "planning":
        return "plan 正在执行，请稍候刷新任务详情。"
    if status == "failed" and not has_design:
        return f"coco-flow prd design --task {task_id}"
    if status == "failed" and not has_plan:
        return f"coco-flow prd plan --task {task_id}"
    if not has_design:
        return f"coco-flow prd design --task {task_id}"
    if not has_design or not has_plan:
        return f"coco-flow prd plan --task {task_id}"
    if status == "coding":
        return "code workspace 已准备，可继续接入自动实现或人工推进。"
    if status in {"partially_coded", "failed"}:
        next_repo = suggest_next_repo(repos)
        if next_repo:
            return f"coco-flow prd code --task {task_id} --repo {next_repo}"
        blocked = summarize_blocked_repos(repos)
        if blocked:
            return f"当前可见 repo 受依赖阻塞：{blocked}。请先推进其依赖的上游 repo。"
    if status == "planned":
        next_repo = suggest_next_repo(repos)
        if next_repo:
            return f"coco-flow prd code --task {task_id} --repo {next_repo}"
        blocked = summarize_blocked_repos(repos)
        if blocked:
            return f"当前可见 repo 受依赖阻塞：{blocked}。请先推进其依赖的上游 repo。"
        return f"coco-flow prd code --task {task_id}"
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
    has_plan = (task_dir / "plan.md").exists()
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
        plan_detail = "等待 Design 完成后生成执行计划"
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
        plan_detail = "等待生成 plan.md"
    elif status == "planning":
        input_state, refine_state = "done", "done"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        if has_design:
            design_state, plan_state = "done", "current"
            design_detail = "已生成 design.md"
            plan_detail = "正在生成 plan.md、任务拆分和执行顺序"
        else:
            design_state, plan_state = "current", "pending"
            design_detail = "正在调研代码并生成 design.md"
            plan_detail = "等待 Design 产物就绪"
    elif status == "planned":
        input_state, refine_state, design_state, plan_state = "done", "done", "done", "done"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        design_detail = "已生成 design.md"
        plan_detail = "已生成 plan.md"
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
        plan_detail = "已生成 plan.md"
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
        plan_detail = "已生成 plan.md"
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
        plan_detail = "已生成 plan.md"
        code_detail = "已完成 code"
        archive_detail = "已归档"
    elif status == "failed":
        input_state, refine_state = "done", "done"
        input_detail = "已完成输入整理"
        refine_detail = "已生成 refined PRD"
        if not has_design:
            design_state = "failed"
            design_detail = "Design 执行失败，请查看 plan.log"
            plan_detail = "等待 Design 修复后再生成 plan.md"
        elif not has_plan:
            design_state, plan_state = "done", "failed"
            design_detail = "已生成 design.md"
            plan_detail = "Plan 执行失败，请查看 plan.log"
        else:
            design_state, plan_state = "done", "done"
            design_detail = "已生成 design.md"
            plan_detail = "已生成 plan.md"
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


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
