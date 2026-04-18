from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.plan_knowledge import build_plan_knowledge_brief as build_legacy_plan_knowledge_brief

from .models import PlanPreparedInput


def build_plan_knowledge_bundle(
    prepared: PlanPreparedInput,
    settings: Settings,
) -> tuple[str, dict[str, object], list[str]]:
    return build_legacy_plan_knowledge_brief(
        settings,
        title=prepared.title,
        sections=prepared.refined_sections,
        repo_scopes=prepared.repo_scopes,
    )
