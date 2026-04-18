from __future__ import annotations

from collections import defaultdict, deque

from .models import PlanExecutionEdge, PlanExecutionGraph, PlanWorkItem


def build_plan_execution_graph(work_items: list[PlanWorkItem]) -> tuple[PlanExecutionGraph, dict[str, object]]:
    edges: list[PlanExecutionEdge] = []
    items_by_id = {item.id: item for item in work_items}
    indegree = {item.id: 0 for item in work_items}
    outgoing: dict[str, list[str]] = defaultdict(list)

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
            outgoing[dependency].append(item.id)
            indegree[item.id] += 1

    levels = _topological_levels([item.id for item in work_items], outgoing, indegree)
    execution_order = [task_id for level in levels for task_id in level]
    parallel_groups = [level for level in levels if len(level) > 1]
    critical_path = _select_critical_path(levels)
    coordination_points = [
        f"{item.id}: {item.title}"
        for item in work_items
        if item.task_type in {"coordination", "validation"} or len(item.depends_on) > 1
    ]
    graph = PlanExecutionGraph(
        nodes=[item.id for item in work_items],
        edges=edges,
        execution_order=execution_order,
        parallel_groups=parallel_groups,
        critical_path=critical_path,
        coordination_points=coordination_points,
    )
    notes_payload = {
        "levels": [{"level": index + 1, "tasks": level} for index, level in enumerate(levels)],
        "coordination_points": coordination_points,
    }
    return graph, notes_payload


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
