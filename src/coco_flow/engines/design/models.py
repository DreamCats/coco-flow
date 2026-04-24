from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from coco_flow.engines.shared.models import RefinedSections, RepoScope

STATUS_DESIGNING = "designing"
STATUS_DESIGNED = "designed"
STATUS_FAILED = "failed"

EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"

GATE_PASSED = "passed"
GATE_PASSED_WITH_WARNINGS = "passed_with_warnings"
GATE_NEEDS_HUMAN = "needs_human"
GATE_DEGRADED = "degraded"
GATE_FAILED = "failed"

PLAN_ALLOWED_GATE_STATUSES = {GATE_PASSED, GATE_PASSED_WITH_WARNINGS}

LogHandler = Callable[[str], None]


@dataclass
class DesignInputBundle:
    task_dir: Path
    task_id: str
    title: str
    refined_markdown: str
    input_meta: dict[str, object]
    refine_brief_payload: dict[str, object]
    refine_intent_payload: dict[str, object]
    refine_skills_selection_payload: dict[str, object]
    refine_skills_read_markdown: str
    repos_meta: dict[str, object]
    repo_scopes: list[RepoScope]
    sections: RefinedSections
    selected_skill_ids: list[str] = field(default_factory=list)
    design_skills_selection_payload: dict[str, object] = field(default_factory=dict)
    design_skills_brief_markdown: str = ""
    design_selected_skill_ids: list[str] = field(default_factory=list)


@dataclass
class DesignEngineResult:
    status: str
    gate_status: str
    design_markdown: str
    repo_binding_payload: dict[str, object]
    sections_payload: dict[str, object]
    intermediate_artifacts: dict[str, str | dict[str, object]] = field(default_factory=dict)
