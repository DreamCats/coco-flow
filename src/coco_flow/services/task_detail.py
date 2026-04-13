from __future__ import annotations

from pathlib import Path
import json

from coco_flow.models import ArtifactItem, RepoBinding, TaskDetail, TimelineItem

TRACKED_ARTIFACTS = [
    "repos.json",
    "source.json",
    "prd.source.md",
    "prd-refined.md",
    "design.md",
    "plan.md",
    "refine.log",
    "plan.log",
    "code-result.json",
    "code.log",
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
    repos = parse_repos(repos_meta)

    return TaskDetail(
        task_id=task_id,
        title=str(metadata.get("title") or task_id),
        status=status,
        created_at=_optional_str(metadata.get("created_at")),
        updated_at=_optional_str(metadata.get("updated_at")),
        source_type=_optional_str(metadata.get("source_type") or source_meta.get("type")),
        source_value=_optional_str(metadata.get("source_value")),
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


def parse_repos(repos_meta: dict[str, object]) -> list[RepoBinding]:
    raw_repos = repos_meta.get("repos")
    if not isinstance(raw_repos, list):
        return []

    repos: list[RepoBinding] = []
    for item in raw_repos:
        if not isinstance(item, dict):
            continue
        repos.append(
            RepoBinding(
                repo_id=str(item.get("id") or ""),
                path=str(item.get("path") or ""),
                status=_optional_str(item.get("status")),
                branch=_optional_str(item.get("branch")),
                worktree=_optional_str(item.get("worktree")),
                commit=_optional_str(item.get("commit")),
            )
        )
    return repos


def build_next_action(
    task_id: str, status: str, task_dir: Path, repos: list[RepoBinding]
) -> str:
    has_refined = (task_dir / "prd-refined.md").exists()
    has_design = (task_dir / "design.md").exists()
    has_plan = (task_dir / "plan.md").exists()

    if not has_refined:
        return f"coco-flow tasks refine {task_id}"
    if status == "planning":
        return "plan 正在执行，请稍候刷新任务详情。"
    if status == "failed" and (not has_design or not has_plan):
        return f"coco-flow tasks plan {task_id}"
    if not has_design or not has_plan:
        return f"coco-flow prd plan --task {task_id}"
    if status == "coding":
        return "code workspace 已准备，可继续接入自动实现或人工推进。"
    if status in {"partially_coded", "failed"}:
        next_repo = suggest_next_repo(repos)
        if next_repo:
            return f"coco-flow tasks code {task_id}"
    if status == "planned":
        return f"coco-flow tasks code {task_id}"
    if status == "coded":
        return f"coco-flow prd archive --task {task_id}"
    if status == "archived":
        return "task 已归档，无后续操作。"
    return "当前 task 无明确下一步，建议人工确认状态。"


def suggest_next_repo(repos: list[RepoBinding]) -> str | None:
    for repo in repos:
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


def build_timeline(status: str, task_dir: Path) -> list[TimelineItem]:
    refine_state, plan_state, code_state, archive_state = (
        "pending",
        "pending",
        "pending",
        "pending",
    )
    refine_detail, plan_detail, code_detail, archive_detail = (
        "等待 refine",
        "等待 plan",
        "等待 code",
        "等待 archive",
    )

    if status == "initialized":
        refine_state = "current"
        refine_detail = "已初始化 task，等待生成 refined PRD"
    elif status == "refined":
        refine_state, plan_state = "done", "current"
        refine_detail = "已生成 refined PRD"
        plan_detail = "等待生成 design.md 与 plan.md"
    elif status == "planning":
        refine_state, plan_state = "done", "current"
        refine_detail = "已生成 refined PRD"
        plan_detail = "正在调研代码并生成 design.md / plan.md"
    elif status == "planned":
        refine_state, plan_state, code_state = "done", "done", "current"
        refine_detail = "已生成 refined PRD"
        plan_detail = "已完成 plan"
        code_detail = "可进入 code 阶段"
    elif status in {"coding", "partially_coded"}:
        refine_state, plan_state, code_state = "done", "done", "current"
        refine_detail = "已生成 refined PRD"
        plan_detail = "已完成 plan"
        code_detail = "至少一个 repo 正在执行 code"
    elif status == "coded":
        refine_state, plan_state, code_state, archive_state = (
            "done",
            "done",
            "done",
            "current",
        )
        refine_detail = "已生成 refined PRD"
        plan_detail = "已完成 plan"
        code_detail = "所有关联 repo 已完成 code"
        archive_detail = "可归档收尾"
    elif status == "archived":
        refine_state, plan_state, code_state, archive_state = (
            "done",
            "done",
            "done",
            "done",
        )
        refine_detail = "已生成 refined PRD"
        plan_detail = "已完成 plan"
        code_detail = "已完成 code"
        archive_detail = "已归档"
    elif status == "failed":
        has_design = (task_dir / "design.md").exists()
        has_plan = (task_dir / "plan.md").exists()
        if not has_design or not has_plan:
            refine_state, plan_state = "done", "current"
            refine_detail = "已生成 refined PRD"
            plan_detail = "plan 执行失败，请查看 plan.log"
        else:
            refine_state, plan_state, code_state = "done", "done", "current"
            refine_detail = "已生成 refined PRD"
            plan_detail = "已完成 plan"
            code_detail = "存在失败的 repo，需继续处理"

    return [
        TimelineItem(label="Refine", state=refine_state, detail=refine_detail),
        TimelineItem(label="Plan", state=plan_state, detail=plan_detail),
        TimelineItem(label="Code", state=code_state, detail=code_detail),
        TimelineItem(label="Archive", state=archive_state, detail=archive_detail),
    ]


def missing_artifact_placeholder(name: str) -> str:
    if name == "refine.log":
        return "当前没有可用的 refine.log。可能任务尚未启动 refine，或日志写入失败。"
    if name == "plan.log":
        return "当前没有可用的 plan.log。可能任务尚未启动 plan，或日志写入失败。"
    return f"该 task 当前没有 `{name}`。"


def empty_artifact_placeholder(name: str) -> str:
    if name == "refine.log":
        return "refine.log 当前为空。"
    if name == "plan.log":
        return "plan.log 当前为空。"
    return f"`{name}` 当前为空。"


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
