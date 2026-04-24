from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import shutil

from coco_flow.config import Settings, load_settings
from coco_flow.engines.input.persist import derive_repo_id
from coco_flow.engines.input.sources import normalize_repo_paths
from coco_flow.services.queries.repos import validate_repo_path
from coco_flow.services.queries.task_detail import read_json_file
from coco_flow.services.tasks.refine import locate_task_dir

_ALLOWED_STATUSES = {
    "initialized",
    "input_processing",
    "input_ready",
    "input_failed",
    "refined",
    "designed",
    "planned",
    "failed",
}


def update_task_repos(task_id: str, repos: list[str], settings: Settings | None = None) -> str:
    cfg = settings or load_settings()
    task_dir = locate_task_dir(task_id, cfg)
    if task_dir is None:
        raise ValueError(f"task not found: {task_id}")

    task_meta = read_json_file(task_dir / "task.json")
    if not task_meta:
        raise ValueError(f"task metadata missing: {task_id}")

    status = str(task_meta.get("status") or "")
    if status not in _ALLOWED_STATUSES:
        raise ValueError(f"task status {status} does not allow repo update")

    normalized_repos = normalize_repo_paths(repos)
    validated = [validate_repo_path(path) for path in normalized_repos]

    next_status = _next_status(task_dir, status)
    _invalidate_downstream_outputs(task_dir)
    _write_repos(task_dir / "repos.json", validated, next_status)

    now = datetime.now().astimezone().isoformat()
    task_meta["repo_count"] = len(validated)
    task_meta["updated_at"] = now
    task_meta["status"] = next_status
    (task_dir / "task.json").write_text(json.dumps(task_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    input_meta = read_json_file(task_dir / "input.json")
    if input_meta:
        input_meta["updated_at"] = now
        (task_dir / "input.json").write_text(json.dumps(input_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return next_status


def _next_status(task_dir: Path, status: str) -> str:
    if (task_dir / "prd-refined.md").exists():
        return "refined"
    if status in {"initialized", "input_processing", "input_failed", "input_ready"}:
        return status
    return "input_ready"


def _write_repos(path: Path, repos: list[dict[str, object]], status: str) -> None:
    payload = {
        "repos": [
            {
                "id": str(repo.get("id") or derive_repo_id(str(repo.get("path") or ""))),
                "path": str(repo.get("path") or ""),
                "status": status,
                "branch": "",
                "worktree": "",
                "commit": "",
            }
            for repo in repos
        ]
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _invalidate_downstream_outputs(task_dir: Path) -> None:
    for name in (
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
        "design-skills-brief.md",
        "design-search-hints.json",
        "design-repo-binding.json",
        "design-sections.json",
        "design-verify.json",
        "design-diagnosis.json",
        "design-result.json",
        "plan.md",
        "plan-skills-selection.json",
        "plan-skills-brief.md",
        "plan-task-outline.json",
        "plan-work-items.json",
        "plan-execution-graph.json",
        "plan-validation.json",
        "plan-dependency-notes.json",
        "plan-risk-check.json",
        "plan-verify.json",
        "plan-diagnosis.json",
        "plan-result.json",
        "plan-scope.json",
        "plan-execution.json",
        "plan.log",
        "code-dispatch.json",
        "code-progress.json",
        "code-result.json",
        "code.log",
    ):
        artifact = task_dir / name
        if artifact.exists():
            artifact.unlink()
    research_dir = task_dir / "design-research"
    if research_dir.exists():
        shutil.rmtree(research_dir)
    for pattern in (
        ".design-template-*.md",
        ".design-research-*.json",
        ".design-repo-binding-*.json",
        ".design-verify-*.json",
        ".design-architect-*.json",
        ".design-skeptic-*.json",
        ".design-writer-*.md",
        ".design-gate-*.json",
    ):
        for path in task_dir.glob(pattern):
            path.unlink()
    for directory in ("code-results", "code-logs", "code-verify", "diffs"):
        path = task_dir / directory
        if path.exists():
            shutil.rmtree(path)
