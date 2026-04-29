"""Design quality data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DesignQualityIssue:
    issue_type: str
    severity: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    repair_suggestion: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "type": self.issue_type,
            "severity": self.severity,
            "summary": self.summary,
            "evidence": self.evidence,
            "repair_suggestion": self.repair_suggestion,
        }


@dataclass
class DesignActionabilityResult:
    passed: bool
    issues: list[DesignQualityIssue] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "issues": [issue.to_payload() for issue in self.issues],
        }
