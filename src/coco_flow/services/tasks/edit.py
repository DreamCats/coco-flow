from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil

from coco_flow.config import Settings, load_settings
from coco_flow.engines.shared.manual_extract import split_source_and_manual_extract, validate_manual_extract
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
    "plan-draft-work-items.json",
    "plan-draft-execution-graph.json",
    "plan-draft-validation.json",
    "plan-task-outline.json",
    "plan-work-items.json",
    "plan-execution-graph.json",
    "plan-validation.json",
    "plan-sync.json",
    "plan-review.json",
    "plan-debate.json",
    "plan-decision.json",
    "plan-dependency-notes.json",
    "plan-risk-check.json",
    "plan-verify.json",
    "plan-diagnosis.json",
    "plan-result.json",
]

PLAN_ARTIFACTS = [
    "plan-skills-selection.json",
    "plan-skills.json",
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
            "refine-manual-extract.json",
            "refine-brief.draft.json",
            "refine-source.excerpt.md",
            "refine-brief.json",
            "refine-intent.json",
            "refine-verify.json",
            "refine-diagnosis.json",
            "refine-result.json",
            "refine-scope.candidates.json",
            "refine-scope.json",
            "refine-query.json",
            "refine-skills-selection.json",
            "refine-skills-read.md",
            "design.md",
            "design.log",
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
            "design-skills-selection.json",
            "design-skills.json",
            "design-skills-brief.md",
            "design-search-hints.json",
            "design-repo-binding.json",
            "design-sections.json",
            "design-verify.json",
            "design-diagnosis.json",
            "design-result.json",
            "refine.log",
            *PLAN_ARTIFACTS,
            *CODE_ARTIFACTS,
        ],
        "invalidate_dirs": ["design-research", "code-results", "code-logs", "code-verify", "diffs"],
    },
    "prd-refined.md": {
        "allowed": {STATUS_REFINING, STATUS_REFINED, STATUS_DESIGNING, STATUS_DESIGNED, STATUS_PLANNED},
        "next_status": STATUS_REFINED,
        "invalidate": [
            "design.md",
            "design.log",
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
            "design-skills-selection.json",
            "design-skills.json",
            "design-skills-brief.md",
            "design-search-hints.json",
            "design-repo-binding.json",
            "design-sections.json",
            "design-verify.json",
            "design-diagnosis.json",
            "design-result.json",
            *PLAN_ARTIFACTS,
            *CODE_ARTIFACTS,
        ],
        "invalidate_dirs": ["design-research", "code-results", "code-logs", "code-verify", "diffs"],
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
    task_id: str, name: str, content: str, settings: Settings | None = None, repo_id: str | None = None
) -> tuple[str, str]:
    cfg = settings or load_settings()
    if repo_id:
        return update_repo_artifact(task_id, repo_id, name, content, cfg)
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
    if name == "prd.source.md":
        markdown_body = trimmed.split("\n---\n", 1)[1] if "\n---\n" in trimmed else trimmed
        _source, supplement = split_source_and_manual_extract(markdown_body)
        error = validate_manual_extract(supplement)
        if error:
            raise ValueError(error)

    (task_dir / name).write_text(trimmed + "\n")
    if name == "plan.md":
        mark_plan_unsynced(task_dir, changed_artifact=name)

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


def update_repo_artifact(task_id: str, repo_id: str, name: str, content: str, cfg: Settings) -> tuple[str, str]:
    if name not in {"plan.md", "repo-plan.md"}:
        raise ValueError(f"repo 级 artifact 暂不支持编辑 {name}")
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")
    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")
    status = str(task_meta.get("status") or "")
    if status != STATUS_PLANNED:
        raise ValueError(f"当前状态为 {status}，不能编辑 repo plan")
    trimmed = content.strip()
    if not trimmed:
        raise ValueError("repo plan 不能为空")
    repo_dir = task_dir / "plan-repos"
    repo_dir.mkdir(parents=True, exist_ok=True)
    target = repo_dir / f"{_sanitize_repo_id(repo_id)}.md"
    target.write_text(trimmed + "\n", encoding="utf-8")
    mark_plan_unsynced(task_dir, changed_artifact="plan.md", repo_id=repo_id)
    task_meta["updated_at"] = datetime.now().astimezone().isoformat()
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n")
    return status, target.read_text(encoding="utf-8")


def remove_path(path: Path) -> None:
    if path.exists() and path.is_file():
        path.unlink()


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _sanitize_repo_id(repo_id: str) -> str:
    chars = [char if char.isalnum() or char in {"-", "_", "."} else "_" for char in repo_id.strip()]
    return "".join(chars) or "repo"


def mark_plan_unsynced(task_dir: Path, *, changed_artifact: str, repo_id: str = "") -> None:
    payload = {
        "synced": False,
        "status": "markdown_changed",
        "reason": "Plan Markdown was edited after structured Plan artifacts were generated. Sync Plan before Code.",
        "changed_artifact": changed_artifact,
        "repo_id": repo_id,
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    (task_dir / "plan-sync.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
