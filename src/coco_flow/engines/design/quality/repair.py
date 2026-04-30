"""Low-risk deterministic Design repairs."""

from __future__ import annotations

from coco_flow.engines.shared.models import RefinedSections

from .open_questions import ensure_inferred_open_questions


def repair_low_risk_design_quality(markdown: str, sections: RefinedSections, on_log) -> str:
    repaired, added_count = ensure_inferred_open_questions(markdown, sections)
    if added_count:
        on_log(f"design_quality_repair: inferred_open_questions_added={added_count}")
    return repaired
