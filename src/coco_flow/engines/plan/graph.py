from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import tempfile

from coco_flow.clients import CocoACPClient
from coco_flow.config import Settings
from coco_flow.prompts.plan import build_plan_scheduler_agent_prompt, build_plan_scheduler_template_json

from .models import EXECUTOR_NATIVE, PlanExecutionEdge, PlanExecutionGraph, PlanPreparedInput, PlanWorkItem

_ALLOWED_EDGE_TYPES = {"hard_dependency", "soft_dependency", "parallel", "coordination"}


def build_plan_execution_graph(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    settings: Settings,
    on_log,
) -> tuple[PlanExecutionGraph, dict[str, object], dict[str, object]]:
    fallback_graph, fallback_notes = build_local_plan_execution_graph(work_items)
    graph = fallback_graph
    dependency_notes = fallback_notes
    draft_payload = _with_scheduler_metadata(fallback_graph.to_payload(), source="local", degraded=False)
    if settings.plan_executor.strip().lower() == EXECUTOR_NATIVE:
        try:
            native_payload = _build_plan_execution_graph_with_scheduler(prepared, work_items, settings)
            graph = normalize_plan_execution_graph(native_payload, work_items)
            dependency_notes = _dependency_notes_from_graph(graph)
            draft_payload = _with_scheduler_metadata(native_payload, source="native", degraded=False)
            on_log(f"plan_scheduler_mode: native edges={len(graph.edges)}")
        except Exception as error:
            on_log(f"plan_scheduler_fallback: {error}")
            draft_payload = _with_scheduler_metadata(
                fallback_graph.to_payload(),
                source="local_fallback",
                degraded=True,
                degraded_reason=str(error),
            )
    else:
        on_log("plan_scheduler_mode: local")
    return graph, dependency_notes, draft_payload


def build_local_plan_execution_graph(work_items: list[PlanWorkItem]) -> tuple[PlanExecutionGraph, dict[str, object]]:
    return _build_graph_from_dependencies(work_items)


def normalize_plan_execution_graph(payload: dict[str, object], work_items: list[PlanWorkItem]) -> PlanExecutionGraph:
    item_ids = [item.id for item in work_items]
    item_id_set = set(item_ids)
    edges: list[PlanExecutionEdge] = []
    for raw in _dict_list(payload.get("edges")):
        from_task_id = str(raw.get("from") or raw.get("from_task_id") or "").strip()
        to_task_id = str(raw.get("to") or raw.get("to_task_id") or "").strip()
        if from_task_id not in item_id_set or to_task_id not in item_id_set or from_task_id == to_task_id:
            continue
        edge_type = str(raw.get("type") or "hard_dependency").strip()
        if edge_type not in _ALLOWED_EDGE_TYPES:
            edge_type = "hard_dependency"
        edges.append(
            PlanExecutionEdge(
                from_task_id=from_task_id,
                to_task_id=to_task_id,
                type=edge_type,
                reason=str(raw.get("reason") or f"{to_task_id} 依赖 {from_task_id} 的前置结果。").strip(),
            )
        )
    graph = _build_graph_from_edges(work_items, edges)
    payload_order = _valid_id_list(payload.get("execution_order"), item_id_set)
    if set(payload_order) == item_id_set:
        graph.execution_order = payload_order
    payload_parallel_groups = _valid_parallel_groups(payload.get("parallel_groups"), item_id_set, graph.edges)
    if payload_parallel_groups:
        graph.parallel_groups = payload_parallel_groups
    payload_critical_path = _valid_id_list(payload.get("critical_path"), item_id_set)
    if payload_critical_path:
        graph.critical_path = payload_critical_path
    payload_coordination = _coordination_points(payload.get("coordination_points"))
    if payload_coordination:
        graph.coordination_points = payload_coordination
    return graph


def _build_plan_execution_graph_with_scheduler(
    prepared: PlanPreparedInput,
    work_items: list[PlanWorkItem],
    settings: Settings,
) -> dict[str, object]:
    client = CocoACPClient(settings.coco_bin, idle_timeout_seconds=settings.acp_idle_timeout_seconds, settings=settings)
    template_path = _write_template(prepared.task_dir, ".plan-scheduler-", ".json", build_plan_scheduler_template_json())
    try:
        client.run_agent(
            build_plan_scheduler_agent_prompt(
                title=prepared.title,
                design_markdown=prepared.design_markdown,
                refined_markdown=prepared.refined_markdown,
                skills_brief_markdown=prepared.skills_brief_markdown,
                repo_binding_payload=prepared.design_repo_binding_payload,
                work_items_payload={"work_items": [item.to_payload() for item in work_items]},
                template_path=str(template_path),
            ),
            settings.native_query_timeout,
            cwd=str(prepared.task_dir),
            fresh_session=True,
        )
        raw = template_path.read_text(encoding="utf-8") if template_path.exists() else ""
    finally:
        if template_path.exists():
            template_path.unlink()
    if "__FILL__" in raw or not raw.strip():
        raise ValueError("plan_scheduler_template_unfilled")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("plan_scheduler_output_invalid")
    return payload


def _build_graph_from_dependencies(work_items: list[PlanWorkItem]) -> tuple[PlanExecutionGraph, dict[str, object]]:
    edges: list[PlanExecutionEdge] = []
    items_by_id = {item.id: item for item in work_items}
    for item in work_items:
        for dependency in item.depends_on:
            if dependency not in items_by_id:
                continue
            edges.append(
                PlanExecutionEdge(
                    from_task_id=dependency,
                    to_task_id=item.id,
                    type="hard_dependency",
                    reason=f"{item.id} 依赖 {dependency} 的前置结果。",
                )
            )
    graph = _build_graph_from_edges(work_items, edges)
    return graph, _dependency_notes_from_graph(graph)


def _build_graph_from_edges(work_items: list[PlanWorkItem], edges: list[PlanExecutionEdge]) -> PlanExecutionGraph:
    item_ids = [item.id for item in work_items]
    indegree = {item.id: 0 for item in work_items}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        if edge.type != "hard_dependency":
            continue
        outgoing[edge.from_task_id].append(edge.to_task_id)
        indegree[edge.to_task_id] = indegree.get(edge.to_task_id, 0) + 1
    levels = _topological_levels(item_ids, outgoing, indegree)
    return PlanExecutionGraph(
        nodes=item_ids,
        edges=edges,
        execution_order=[task_id for level in levels for task_id in level],
        parallel_groups=[level for level in levels if len(level) > 1],
        critical_path=_select_critical_path(levels),
        coordination_points=[
            f"{item.id}: {item.title}"
            for item in work_items
            if item.task_type in {"coordination", "validation"} or len(item.depends_on) > 1
        ],
    )


def _dependency_notes_from_graph(graph: PlanExecutionGraph) -> dict[str, object]:
    levels = _levels_from_order(graph.execution_order, graph.parallel_groups)
    return {
        "levels": [{"level": index + 1, "tasks": level} for index, level in enumerate(levels)],
        "coordination_points": graph.coordination_points,
    }


def _levels_from_order(order: list[str], parallel_groups: list[list[str]]) -> list[list[str]]:
    grouped = {task_id for group in parallel_groups for task_id in group}
    levels = [group for group in parallel_groups if group]
    levels.extend([task_id] for task_id in order if task_id not in grouped)
    return levels


def _topological_levels(nodes: list[str], outgoing: dict[str, list[str]], indegree: dict[str, int]) -> list[list[str]]:
    pending = dict(indegree)
    queue = deque(sorted(node for node in nodes if pending.get(node, 0) == 0))
    visited: set[str] = set()
    levels: list[list[str]] = []

    while queue:
        level_size = len(queue)
        current_level: list[str] = []
        for _ in range(level_size):
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            current_level.append(node)
        for node in current_level:
            for target in sorted(outgoing.get(node, [])):
                pending[target] = pending.get(target, 0) - 1
        ready_targets = sorted(node for node in nodes if node not in visited and pending.get(node, 0) <= 0 and node not in queue)
        for node in ready_targets:
            queue.append(node)
        if current_level:
            levels.append(current_level)

    for node in nodes:
        if node not in visited:
            levels.append([node])
    return levels


def _select_critical_path(levels: list[list[str]]) -> list[str]:
    return [level[0] for level in levels if level]


def _with_scheduler_metadata(
    payload: dict[str, object],
    *,
    source: str,
    degraded: bool,
    degraded_reason: str = "",
) -> dict[str, object]:
    result = dict(payload)
    scheduler = result.get("scheduler")
    scheduler_payload = dict(scheduler) if isinstance(scheduler, dict) else {}
    scheduler_payload.update({"role": "scheduler", "source": source, "degraded": degraded})
    if degraded_reason:
        scheduler_payload["degraded_reason"] = degraded_reason
        scheduler_payload["fallback_stage"] = "scheduler"
    result["scheduler"] = scheduler_payload
    return result


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _valid_id_list(value: object, valid_ids: set[str]) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        task_id = str(item).strip()
        if task_id in valid_ids and task_id not in result:
            result.append(task_id)
    return result


def _valid_parallel_groups(value: object, valid_ids: set[str], edges: list[PlanExecutionEdge]) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    hard_pairs = {(edge.from_task_id, edge.to_task_id) for edge in edges if edge.type == "hard_dependency"}
    groups: list[list[str]] = []
    for raw_group in value:
        if not isinstance(raw_group, list):
            continue
        group = _valid_id_list(raw_group, valid_ids)
        if len(group) < 2:
            continue
        if any((left, right) in hard_pairs or (right, left) in hard_pairs for left in group for right in group if left != right):
            continue
        groups.append(group)
    return groups


def _coordination_points(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = " / ".join(str(item.get(key) or "").strip() for key in ("id", "title", "reason") if str(item.get(key) or "").strip())
        else:
            text = str(item).strip()
        if text:
            result.append(text)
    return result[:8]


def _write_template(task_dir: Path, prefix: str, suffix: str, content: str) -> Path:
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=task_dir, prefix=prefix, suffix=suffix, delete=False) as handle:
        handle.write(content)
        handle.flush()
        return Path(handle.name)
