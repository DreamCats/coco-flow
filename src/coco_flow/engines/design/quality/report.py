"""Build persisted Design quality reports."""

from __future__ import annotations

from datetime import datetime

from .actionability import evaluate_design_actionability


def build_design_quality_payload(
    markdown: str,
    *,
    source: str,
    quality_status: str = "",
    supervisor_decision: str = "",
) -> dict[str, object]:
    actionability = evaluate_design_actionability(markdown)
    status = quality_status or ("passed" if actionability.passed else "failed")
    return {
        "quality_status": status,
        "source": source,
        "actionability": actionability.to_payload(),
        "supervisor_decision": supervisor_decision,
        "updated_at": datetime.now().astimezone().isoformat(),
    }
