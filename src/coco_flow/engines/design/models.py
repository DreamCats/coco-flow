from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from coco_flow.engines.plan_models import ComplexityAssessment, DesignResearchSignals, RefinedSections, RepoResearch, RepoScope

STATUS_DESIGNING = "designing"
STATUS_DESIGNED = "designed"
STATUS_FAILED = "failed"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"

LogHandler = Callable[[str], None]


@dataclass
class DesignPreparedInput:
    task_dir: Path
    task_id: str
    title: str
    refined_markdown: str
    input_meta: dict[str, object]
    refine_intent_payload: dict[str, object]
    refine_knowledge_selection_payload: dict[str, object]
    refine_knowledge_read_markdown: str
    repo_lines: list[str]
    repo_scopes: list[RepoScope]
    repo_researches: list[RepoResearch]
    repo_ids: set[str]
    repo_root: str | None
    sections: RefinedSections
    research_signals: DesignResearchSignals
    assessment: ComplexityAssessment
    research_payload: dict[str, object] = field(default_factory=dict)


@dataclass
class DesignRepoBindingEntry:
    repo_id: str
    repo_path: str
    decision: str
    role: str
    serves_change_points: list[int]
    system_name: str
    responsibility: str
    change_summary: list[str]
    boundaries: list[str]
    candidate_dirs: list[str]
    candidate_files: list[str]
    depends_on: list[str]
    parallelizable_with: list[str]
    confidence: str
    reason: str

    def to_payload(self) -> dict[str, object]:
        return {
            "repo_id": self.repo_id,
            "repo_path": self.repo_path,
            "decision": self.decision,
            "role": self.role,
            "serves_change_points": self.serves_change_points,
            "system_name": self.system_name,
            "responsibility": self.responsibility,
            "change_summary": self.change_summary,
            "boundaries": self.boundaries,
            "candidate_dirs": self.candidate_dirs,
            "candidate_files": self.candidate_files,
            "depends_on": self.depends_on,
            "parallelizable_with": self.parallelizable_with,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class DesignRepoBinding:
    repo_bindings: list[DesignRepoBindingEntry]
    missing_repos: list[str]
    decision_summary: str
    mode: str

    def to_payload(self) -> dict[str, object]:
        return {
            "repo_bindings": [entry.to_payload() for entry in self.repo_bindings],
            "missing_repos": self.missing_repos,
            "decision_summary": self.decision_summary,
            "mode": self.mode,
        }


@dataclass
class DesignEngineResult:
    status: str
    design_markdown: str
    repo_binding_payload: dict[str, object]
    sections_payload: dict[str, object]
    intermediate_artifacts: dict[str, str | dict[str, object]] = field(default_factory=dict)
