"""Supervisor review models."""

from __future__ import annotations

from dataclasses import dataclass, field


SUPERVISOR_DECISIONS = {"pass", "repair_writer", "redo_research", "degrade_design", "needs_human", "fail"}
SUPERVISOR_NEXT_ACTIONS = {
    "accept_design",
    "rewrite_design",
    "redo_research",
    "write_degraded_design",
    "ask_human",
    "fail_design",
}


@dataclass
class SupervisorReview:
    passed: bool
    decision: str
    confidence: str = "medium"
    blocking_issues: list[dict[str, object]] = field(default_factory=list)
    repair_instructions: list[str] = field(default_factory=list)
    next_action: str = "accept_design"
    reason: str = ""
    source: str = "local"

    def to_payload(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "decision": self.decision,
            "confidence": self.confidence,
            "blocking_issues": self.blocking_issues,
            "repair_instructions": self.repair_instructions,
            "next_action": self.next_action,
            "reason": self.reason,
            "source": self.source,
        }
