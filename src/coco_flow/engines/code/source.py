from __future__ import annotations

from pathlib import Path

from coco_flow.config import Settings
from coco_flow.services.queries.task_detail import read_json_file

from .models import CodePreparedInput


def locate_task_dir(task_id: str, settings: Settings) -> Path | None:
    candidate = settings.task_root / task_id
    if candidate.is_dir():
        return candidate
    return None


def prepare_code_input(task_dir: Path, task_meta: dict[str, object]) -> CodePreparedInput:
    task_id = task_dir.name
    input_meta = read_json_file(task_dir / "input.json")
    repos_meta = read_json_file(task_dir / "repos.json")
    design_repo_binding_payload = read_json_file(task_dir / "design-repo-binding.json")
    plan_work_items_payload = read_json_file(task_dir / "plan-work-items.json")
    plan_execution_graph_payload = read_json_file(task_dir / "plan-execution-graph.json")
    plan_validation_payload = read_json_file(task_dir / "plan-validation.json")
    plan_result_payload = read_json_file(task_dir / "plan-result.json")

    refined_markdown = _read_text_if_exists(task_dir / "prd-refined.md")
    design_markdown = _read_text_if_exists(task_dir / "design.md")
    plan_markdown = _read_text_if_exists(task_dir / "plan.md")
    title = str(task_meta.get("title") or input_meta.get("title") or task_id)

    _require_payload(design_repo_binding_payload, "design-repo-binding.json 缺失，无法执行 code")
    _require_payload(plan_work_items_payload, "plan-work-items.json 缺失，无法执行 code")
    _require_payload(plan_execution_graph_payload, "plan-execution-graph.json 缺失，无法执行 code")
    _require_payload(plan_validation_payload, "plan-validation.json 缺失，无法执行 code")
    _require_payload(plan_result_payload, "plan-result.json 缺失，无法执行 code")
    _require_payload(repos_meta, "repos.json 缺失，无法执行 code")
    _ensure_plan_allows_code(plan_result_payload)

    return CodePreparedInput(
        task_dir=task_dir,
        task_id=task_id,
        title=title,
        task_meta=task_meta,
        repos_meta=repos_meta,
        design_repo_binding_payload=design_repo_binding_payload,
        plan_work_items_payload=plan_work_items_payload,
        plan_execution_graph_payload=plan_execution_graph_payload,
        plan_validation_payload=plan_validation_payload,
        plan_result_payload=plan_result_payload,
        refined_markdown=refined_markdown,
        design_markdown=design_markdown,
        plan_markdown=plan_markdown,
    )


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _require_payload(payload: dict[str, object], message: str) -> None:
    if not payload:
        raise ValueError(message)


def _ensure_plan_allows_code(plan_result_payload: dict[str, object]) -> None:
    gate_status = str(plan_result_payload.get("gate_status") or "").strip()
    code_allowed = plan_result_payload.get("code_allowed")
    if code_allowed is False:
        raise ValueError(f"plan gate status {gate_status or 'blocked'} does not allow code")
    if gate_status and gate_status not in {"passed", "passed_with_warnings"}:
        raise ValueError(f"plan gate status {gate_status} does not allow code")
