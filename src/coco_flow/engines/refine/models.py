from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATUS_INITIALIZED = "initialized"
STATUS_REFINED = "refined"
EXECUTOR_NATIVE = "native"
EXECUTOR_LOCAL = "local"
SOURCE_TYPE_LARK_DOC = "lark_doc"

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
    repos_meta: dict[str, object]
    repo_root: str | None


@dataclass
class RefineIntent:
    title: str
    source_type: str
    goal: str
    key_terms: list[str]
    potential_features: list[str]
    constraints: list[str]
    open_questions: list[str]
    source_length: int

    def to_payload(self) -> dict[str, object]:
        return {
            "title": self.title,
            "source_type": self.source_type,
            "goal": self.goal,
            "key_terms": self.key_terms,
            "potential_features": self.potential_features,
            "constraints": self.constraints,
            "open_questions": self.open_questions,
            "source_length": self.source_length,
        }


@dataclass
class RefineKnowledgeBrief:
    markdown: str
    matched_documents: list[str]
    matched_terms: list[str]
    selected_knowledge_ids: list[str]
    selection_payload: dict[str, object]


@dataclass
class RefineEngineResult:
    status: str
    refined_markdown: str
    context_mode: str
    business_memory_used: bool
    business_memory_provider: str
    business_memory_documents: list[dict[str, str]]
    risk_flags: list[str]
    intermediate_artifacts: dict[str, str | dict[str, object]] = field(default_factory=dict)
