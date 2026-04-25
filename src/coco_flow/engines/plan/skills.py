"""Plan Skills/SOP 适配层。

负责把通用 Plan skills 选择逻辑接入当前 doc-only Plan 输入，
产出 writer 可消费的知识摘要和 selected skill 信息。
"""

from __future__ import annotations

from coco_flow.config import Settings
from coco_flow.engines.plan_skills import build_plan_skills_brief as build_legacy_plan_skills_brief

from .models import PlanPreparedInput


def build_plan_skills_bundle(
    prepared: PlanPreparedInput,
    settings: Settings,
) -> tuple[str, dict[str, object], list[str]]:
    return build_legacy_plan_skills_brief(
        settings,
        title=prepared.title,
        sections=prepared.refined_sections,
        repo_scopes=prepared.repo_scopes,
    )
