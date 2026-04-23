from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATUS_INITIALIZED = "initialized"
STATUS_REFINING = "refining"
STATUS_REFINED = "refined"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
SOURCE_TYPE_LARK_DOC = "lark_doc"
SUPPLEMENT_HEADING = "## 研发补充说明"

LogHandler = Callable[[str], None]


@dataclass
class RefinePreparedInput:
    task_dir: Path
    task_id: str
    title: str
    source_type: str
    source_meta: dict[str, object]
    source_markdown: str
    source_content: str
    supplement: str
    input_meta: dict[str, object]


@dataclass
class RefineIntent:
    goal: str
    change_points: list[str]
    acceptance_criteria: list[str]
    terms: list[str]
    risks_seed: list[str]
    discussion_seed: list[str]
    boundary_seed: list[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "goal": self.goal,
            "change_points": self.change_points,
            "acceptance_criteria": self.acceptance_criteria,
            "terms": self.terms,
            "risks_seed": self.risks_seed,
            "discussion_seed": self.discussion_seed,
            "boundary_seed": self.boundary_seed,
        }


@dataclass(frozen=True)
class KnowledgeCard:
    id: str
    title: str
    desc: str
    kind: str
    domain_name: str
    priority: str
    confidence: str

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "desc": self.desc,
            "kind": self.kind,
            "domain_name": self.domain_name,
            "priority": self.priority,
            "confidence": self.confidence,
        }


@dataclass
class RefineKnowledgeSelection:
    selected_skill_ids: list[str]
    rejected_skill_ids: list[str]
    reason: str
    candidates: list[dict[str, object]]
    mode: str

    def to_payload(self) -> dict[str, object]:
        return {
            "selected_skill_ids": self.selected_skill_ids,
            "rejected_skill_ids": self.rejected_skill_ids,
            "reason": self.reason,
            "candidates": self.candidates,
            "mode": self.mode,
        }


@dataclass
class RefineKnowledgeRead:
    markdown: str
    selected_skill_ids: list[str]
    selected_skill_titles: list[str]


@dataclass
class RefineEngineResult:
    status: str
    refined_markdown: str
    skills_used: bool
    selected_skill_ids: list[str]
    intermediate_artifacts: dict[str, str | dict[str, object]] = field(default_factory=dict)
