from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil

from coco_flow.config import Settings, load_settings
from coco_flow.services.queries.task_detail import read_artifact_content, read_json_file
from coco_flow.services.tasks.refine import locate_task_dir

STATUS_INITIALIZED = "initialized"
STATUS_INPUT_PROCESSING = "input_processing"
STATUS_INPUT_READY = "input_ready"
STATUS_INPUT_FAILED = "input_failed"
STATUS_REFINING = "refining"
STATUS_REFINED = "refined"
STATUS_DESIGNING = "designing"
STATUS_DESIGNED = "designed"
STATUS_PLANNED = "planned"
STATUS_FAILED = "failed"

PLAN_V2_ARTIFACTS = [
    "plan-task-outline.json",
    "plan-work-items.json",
    "plan-execution-graph.json",
    "plan-validation.json",
    "plan-dependency-notes.json",
    "plan-risk-check.json",
    "plan-verify.json",
    "plan-result.json",
]

PLAN_ARTIFACTS = [
    "plan-skills-selection.json",
    "plan-skills-brief.md",
    *PLAN_V2_ARTIFACTS,
    "plan-scope.json",
    "plan-execution.json",
    "plan.md",
    "plan.log",
]

CODE_ARTIFACTS = [
    "code-dispatch.json",
    "code-progress.json",
    "code-result.json",
    "code.log",
]

EDIT_RULES = {
    "prd.source.md": {
        "allowed": {STATUS_INITIALIZED, STATUS_INPUT_PROCESSING, STATUS_INPUT_READY, STATUS_INPUT_FAILED, STATUS_REFINED, STATUS_DESIGNED, STATUS_PLANNED},
        "next_status": STATUS_INPUT_READY,
        "invalidate": [
            "input.log",
            "prd-refined.md",
            "refine-intent.json",
            "refine-query.json",
            "refine-skills-selection.json",
            "refine-skills-read.md",
            "refine-verify.json",
            "refine-result.json",
            "design.md",
            "design.log",
            "design-change-points.json",
            "design-repo-assignment.json",
            "design-research.json",
            "design-repo-responsibility-matrix.json",
            "design-skills-brief.md",
            "design-repo-binding.json",
            "design-sections.json",
            "design-verify.json",
            "design-result.json",
            "refine.log",
            *PLAN_ARTIFACTS,
            *CODE_ARTIFACTS,
        ],
        "invalidate_dirs": ["code-results", "code-logs", "code-verify", "diffs"],
    },
    "prd-refined.md": {
        "allowed": {STATUS_REFINING, STATUS_REFINED, STATUS_DESIGNING, STATUS_DESIGNED, STATUS_PLANNED},
        "next_status": STATUS_REFINED,
        "invalidate": [
            "design.md",
            "design.log",
            "design-change-points.json",
            "design-repo-assignment.json",
            "design-research.json",
            "design-repo-responsibility-matrix.json",
            "design-skills-brief.md",
            "design-repo-binding.json",
            "design-sections.json",
            "design-verify.json",
            "design-result.json",
            *PLAN_ARTIFACTS,
            *CODE_ARTIFACTS,
        ],
        "invalidate_dirs": ["code-results", "code-logs", "code-verify", "diffs"],
    },
    "refine.notes.md": {
        "allowed": {STATUS_INPUT_READY, STATUS_REFINING, STATUS_REFINED, STATUS_DESIGNING, STATUS_DESIGNED, STATUS_PLANNED, STATUS_FAILED},
        "next_status": "__keep__",
        "invalidate": [],
        "invalidate_dirs": [],
    },
    "design.notes.md": {
        "allowed": {STATUS_REFINED, STATUS_DESIGNING, STATUS_DESIGNED, STATUS_PLANNED, STATUS_FAILED},
        "next_status": "__keep__",
        "invalidate": [],
        "invalidate_dirs": [],
    },
    "design.md": {
        "allowed": {STATUS_DESIGNED, STATUS_PLANNED},
        "next_status": STATUS_DESIGNED,
        "invalidate": [*PLAN_ARTIFACTS],
        "invalidate_dirs": [],
    },
    "plan.md": {
        "allowed": {STATUS_PLANNED},
        "next_status": STATUS_PLANNED,
        "invalidate": [],
        "invalidate_dirs": [],
    },
}


def update_artifact(
    task_id: str, name: str, content: str, settings: Settings | None = None
) -> tuple[str, str]:
    cfg = settings or load_settings()
    rule = EDIT_RULES.get(name)
    if rule is None:
        raise ValueError(f"artifact {name} 不支持编辑")

    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in rule["allowed"]:
        raise ValueError(f"当前状态为 {status}，不能编辑 {name}")

    trimmed = content.strip()
    if not trimmed:
        raise ValueError(f"{name} 不能为空")

    (task_dir / name).write_text(trimmed + "\n")

    for artifact_name in rule["invalidate"]:
        remove_path(task_dir / artifact_name)
    for dir_name in rule["invalidate_dirs"]:
        remove_tree(task_dir / dir_name)

    next_status = status if str(rule["next_status"]) == "__keep__" else str(rule["next_status"])
    task_meta["status"] = next_status
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    input_meta = read_json_file(task_dir / "input.json")
    if input_meta:
        input_meta["status"] = next_status
        (task_dir / "input.json").write_text(json.dumps(input_meta, ensure_ascii=False, indent=2) + "\n")
    source_meta = read_json_file(task_dir / "source.json")
    if source_meta and name == "prd.source.md":
        source_meta["fetch_error"] = ""
        source_meta["fetch_error_code"] = ""
        source_meta["captured_at"] = datetime.now().astimezone().isoformat()
        (task_dir / "source.json").write_text(json.dumps(source_meta, ensure_ascii=False, indent=2) + "\n")
    sync_repo_statuses(task_dir, next_status)
    return next_status, read_artifact_content(task_dir, name)


def remove_path(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def sync_repo_statuses(task_dir: Path, status: str) -> None:
    repos_path = task_dir / "repos.json"
    repos_meta = read_json_file(repos_path)
    repos = repos_meta.get("repos")
    if not isinstance(repos, list):
        return
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo["status"] = status
        repo["branch"] = ""
        repo["worktree"] = ""
        repo["commit"] = ""
    repos_path.write_text(json.dumps(repos_meta, ensure_ascii=False, indent=2) + "\n")
