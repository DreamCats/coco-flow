"""Plan deterministic compiler.

This layer turns prepared inputs or edited repo Markdown into Code-consumable
JSON contracts. It should stay mostly rule-based and avoid calling agents.
"""

from .structure import (
    build_structured_plan_artifacts,
    build_structured_plan_artifacts_from_repo_markdowns,
    render_plan_markdown,
    validate_plan_artifacts,
)

__all__ = [
    "build_structured_plan_artifacts",
    "build_structured_plan_artifacts_from_repo_markdowns",
    "render_plan_markdown",
    "validate_plan_artifacts",
]
