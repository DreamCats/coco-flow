from __future__ import annotations

# 本文件定义 Refine 阶段内部使用的数据模型和状态常量。模型用于内存编排
# 和函数传参，不代表阶段目录中需要持久化的 schema artifact。

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATUS_INITIALIZED = "initialized"
STATUS_REFINING = "refining"
STATUS_REFINED = "refined"
EXECUTOR_NATIVE = "native"

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
class ManualExtract:
    scope: list[str]
    change_points: list[str]
    out_of_scope: list[str]
    notes: list[str]
    gating_conditions: list[str]
    open_questions: list[str]
    raw_sections: dict[str, str] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "change_points": self.change_points,
            "out_of_scope": self.out_of_scope,
            "notes": self.notes,
            "gating_conditions": self.gating_conditions,
            "open_questions": self.open_questions,
            "raw_sections": self.raw_sections,
        }


@dataclass
class RefineBrief:
    target_surface: str
    goal: str
    in_scope: list[str]
    out_of_scope: list[str]
    gating_conditions: list[str]
    acceptance_criteria: list[str]
    edge_cases: list[str]
    open_questions: list[str]

    def to_payload(self) -> dict[str, object]:
        return {
            "target_surface": self.target_surface,
            "goal": self.goal,
            "in_scope": self.in_scope,
            "out_of_scope": self.out_of_scope,
            "gating_conditions": self.gating_conditions,
            "acceptance_criteria": self.acceptance_criteria,
            "edge_cases": self.edge_cases,
            "open_questions": self.open_questions,
        }


@dataclass
class RefineVerifyResult:
    ok: bool
    issues: list[str]
    missing_sections: list[str]
    reason: str
    failure_type: str = ""
    repair_attempts: int = 0


@dataclass
class RefineEngineResult:
    status: str
    refined_markdown: str
