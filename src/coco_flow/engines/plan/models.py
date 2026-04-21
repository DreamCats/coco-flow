from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from coco_flow.engines.plan_models import RefinedSections, RepoScope

STATUS_PLANNING = "planning"
STATUS_PLANNED = "planned"
STATUS_FAILED = "failed"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"

LogHandler = Callable[[str], None]


@dataclass
class PlanPreparedInput:
    task_dir: Path
    task_id: str
    title: str
    design_markdown: str
    refined_markdown: str
    input_meta: dict[str, object]
    task_meta: dict[str, object]
    design_repo_binding_payload: dict[str, object]
    design_sections_payload: dict[str, object]
    design_result_payload: dict[str, object]
    repos_meta: dict[str, object]
    repo_scopes: list[RepoScope]
    repo_ids: set[str]
    refined_sections: RefinedSections
    knowledge_brief_markdown: str = ""
    knowledge_selection_payload: dict[str, object] = field(default_factory=dict)
    selected_knowledge_ids: list[str] = field(default_factory=list)


@dataclass
class PlanWorkItem:
    id: str
    title: str
    repo_id: str
    task_type: str
    serves_change_points: list[int]
    goal: str
    specific_steps: list[str]
    change_scope: list[str]
    inputs: list[str]
    outputs: list[str]
    done_definition: list[str]
    verification_steps: list[str]
    risk_notes: list[str]
    handoff_notes: list[str]
    depends_on: list[str] = field(default_factory=list)
    parallelizable_with: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "repo_id": self.repo_id,
            "task_type": self.task_type,
            "serves_change_points": self.serves_change_points,
            "goal": self.goal,
            "specific_steps": self.specific_steps,
            "change_scope": self.change_scope,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "done_definition": self.done_definition,
            "verification_steps": self.verification_steps,
            "risk_notes": self.risk_notes,
            "handoff_notes": self.handoff_notes,
            "depends_on": self.depends_on,
            "parallelizable_with": self.parallelizable_with,
        }


@dataclass
class PlanExecutionEdge:
    from_task_id: str
    to_task_id: str
    type: str
    reason: str

    def to_payload(self) -> dict[str, object]:
        return {
            "from": self.from_task_id,
            "to": self.to_task_id,
            "type": self.type,
            "reason": self.reason,
        }


@dataclass
class PlanExecutionGraph:
    nodes: list[str]
    edges: list[PlanExecutionEdge]
    execution_order: list[str]
    parallel_groups: list[list[str]]
    critical_path: list[str]
    coordination_points: list[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "nodes": self.nodes,
            "edges": [edge.to_payload() for edge in self.edges],
            "execution_order": self.execution_order,
            "parallel_groups": self.parallel_groups,
            "critical_path": self.critical_path,
            "coordination_points": self.coordination_points,
        }


@dataclass
class PlanValidationCheck:
    task_id: str
    repo_id: str
    checks: list[dict[str, str]]
    linked_design_flows: list[str]
    non_goal_regressions: list[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "repo_id": self.repo_id,
            "checks": self.checks,
            "linked_design_flows": self.linked_design_flows,
            "non_goal_regressions": self.non_goal_regressions,
        }


@dataclass
class PlanEngineResult:
    status: str
    plan_markdown: str
    intermediate_artifacts: dict[str, str | dict[str, object]] = field(default_factory=dict)
