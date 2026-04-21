from __future__ import annotations

from coco_flow.services.runtime.repo_state import STATUS_ARCHIVED, STATUS_CODED

from .models import CodePreparedInput, CodeRepoBatch, CodeRunState, CodeWorkItem


def build_code_runtime_state(prepared: CodePreparedInput) -> CodeRunState:
    work_items = _parse_work_items(prepared)
    task_repo_index = {item.id: item.repo_id for item in work_items}
    validation_index = _build_validation_index(prepared.plan_validation_payload)
    repo_path_index, repo_status_index = _build_repo_runtime_indexes(prepared.repos_meta)

    batches: list[CodeRepoBatch] = []
    batch_id_by_repo: dict[str, str] = {}

    for binding in _in_scope_repo_bindings(prepared.design_repo_binding_payload):
        repo_id = str(binding.get("repo_id") or "").strip()
        scope_tier = str(binding.get("scope_tier") or "").strip()
        if not repo_id or scope_tier == "reference_only":
            continue
        execution_mode = "verify_only" if scope_tier == "validate_only" else "apply"
        repo_items = [item for item in work_items if item.repo_id == repo_id]
        if execution_mode == "apply" and not repo_items:
            continue
        batch_id = f"B{len(batches) + 1}"
        batch_id_by_repo[repo_id] = batch_id
        change_scope = _dedupe(
            [path for item in repo_items for path in item.change_scope]
        )[:10]
        verify_rules = _dedupe(
            [rule for item in repo_items for rule in item.verification_steps]
            + [
                _render_validation_check(check)
                for item in repo_items
                for check in validation_index.get(item.id, [])
            ]
        )[:10]
        done_definition = _dedupe(
            [text for item in repo_items for text in item.done_definition]
            + _string_list(binding.get("change_summary"))
        )[:10]
        batches.append(
            CodeRepoBatch(
                id=batch_id,
                repo_id=repo_id,
                repo_path=repo_path_index.get(repo_id, str(binding.get("repo_path") or "")),
                scope_tier=scope_tier,
                execution_mode=execution_mode,
                work_item_ids=[item.id for item in repo_items],
                depends_on_batch_ids=[],
                blocked_by_batch_ids=[],
                change_scope=change_scope,
                verify_rules=verify_rules,
                done_definition=done_definition,
                status=_initial_batch_status(repo_status_index.get(repo_id, "")),
                summary=str(binding.get("reason") or "").strip(),
            )
        )

    for batch in batches:
        dependency_repos = _dependency_repos_for_batch(batch, prepared.plan_execution_graph_payload, task_repo_index)
        batch.depends_on_batch_ids = [batch_id_by_repo[repo_id] for repo_id in dependency_repos if repo_id in batch_id_by_repo]
        batch.blocked_by_batch_ids = [
            dep_batch_id
            for dep_batch_id in batch.depends_on_batch_ids
            if repo_status_index.get(_repo_for_batch_id(dep_batch_id, batches), "") not in {STATUS_CODED, STATUS_ARCHIVED}
        ]
        if batch.status not in {"completed", "failed"}:
            batch.status = "blocked" if batch.blocked_by_batch_ids else "ready"

    dispatch_payload = {
        "task_id": prepared.task_id,
        "batches": [batch.to_payload() for batch in batches],
    }
    progress_payload = _build_progress_payload(prepared.task_id, batches)
    return CodeRunState(dispatch_payload=dispatch_payload, progress_payload=progress_payload, batches=batches)


def _parse_work_items(prepared: CodePreparedInput) -> list[CodeWorkItem]:
    raw = prepared.plan_work_items_payload.get("work_items")
    if not isinstance(raw, list):
        return []
    items: list[CodeWorkItem] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("id") or "").strip()
        repo_id = str(item.get("repo_id") or "").strip()
        if not task_id or not repo_id:
            continue
        items.append(
            CodeWorkItem(
                id=task_id,
                repo_id=repo_id,
                title=str(item.get("title") or "").strip(),
                goal=str(item.get("goal") or "；".join(_string_list(item.get("specific_steps"))[:2])).strip(),
                change_scope=_string_list(item.get("change_scope")),
                done_definition=_string_list(item.get("done_definition")),
                verification_steps=_string_list(item.get("verification_steps")),
                depends_on=_string_list(item.get("depends_on")),
            )
        )
    return items


def _build_validation_index(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    index: dict[str, list[dict[str, object]]] = {}
    raw = payload.get("task_validations")
    if not isinstance(raw, list):
        return index
    for item in raw:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or "").strip()
        checks = item.get("checks")
        if not task_id or not isinstance(checks, list):
            continue
        index[task_id] = [check for check in checks if isinstance(check, dict)]
    return index


def _build_repo_runtime_indexes(repos_meta: dict[str, object]) -> tuple[dict[str, str], dict[str, str]]:
    repo_path_index: dict[str, str] = {}
    repo_status_index: dict[str, str] = {}
    raw = repos_meta.get("repos")
    if not isinstance(raw, list):
        return repo_path_index, repo_status_index
    for item in raw:
        if not isinstance(item, dict):
            continue
        repo_id = str(item.get("id") or "").strip()
        if not repo_id:
            continue
        repo_path_index[repo_id] = str(item.get("path") or "").strip()
        repo_status_index[repo_id] = str(item.get("status") or "").strip()
    return repo_path_index, repo_status_index


def _in_scope_repo_bindings(payload: dict[str, object]) -> list[dict[str, object]]:
    raw = payload.get("repo_bindings")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict) and str(item.get("decision") or "") == "in_scope"]


def _dependency_repos_for_batch(
    batch: CodeRepoBatch,
    graph_payload: dict[str, object],
    task_repo_index: dict[str, str],
) -> list[str]:
    raw = graph_payload.get("edges")
    if not isinstance(raw, list):
        return []
    dependency_repos: list[str] = []
    seen: set[str] = set()
    work_item_ids = set(batch.work_item_ids)
    for edge in raw:
        if not isinstance(edge, dict):
            continue
        to_task = str(edge.get("to") or "").strip()
        from_task = str(edge.get("from") or "").strip()
        if to_task not in work_item_ids:
            continue
        dep_repo = task_repo_index.get(from_task, "")
        if not dep_repo or dep_repo == batch.repo_id or dep_repo in seen:
            continue
        seen.add(dep_repo)
        dependency_repos.append(dep_repo)
    return dependency_repos


def _repo_for_batch_id(batch_id: str, batches: list[CodeRepoBatch]) -> str:
    for batch in batches:
        if batch.id == batch_id:
            return batch.repo_id
    return ""


def _initial_batch_status(repo_status: str) -> str:
    if repo_status in {STATUS_CODED, STATUS_ARCHIVED}:
        return "completed"
    if repo_status == "failed":
        return "failed"
    if repo_status == "coding":
        return "running"
    return "ready"


def _build_progress_payload(task_id: str, batches: list[CodeRepoBatch]) -> dict[str, object]:
    completed = sum(1 for batch in batches if batch.status == "completed")
    running = sum(1 for batch in batches if batch.status == "running")
    blocked = sum(1 for batch in batches if batch.status == "blocked")
    failed = sum(1 for batch in batches if batch.status == "failed")
    return {
        "task_id": task_id,
        "status": "coding" if running else "ready",
        "current_batch_id": "",
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


def _render_validation_check(check: dict[str, object]) -> str:
    kind = str(check.get("kind") or "").strip()
    target = str(check.get("target") or "").strip()
    reason = str(check.get("reason") or "").strip()
    parts = [part for part in (kind, target, reason) if part]
    return " / ".join(parts)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        lowered = item.lower()
        if not item or lowered in seen:
            continue
        seen.add(lowered)
        result.append(item)
    return result
