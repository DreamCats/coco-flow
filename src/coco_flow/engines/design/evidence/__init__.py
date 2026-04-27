"""Design local repository evidence collection."""

from .research import (
    build_research_plan,
    build_research_summary,
    candidate_paths,
    research_single_repo,
    run_parallel_repo_research,
    safe_artifact_name,
)

__all__ = [
    "build_research_plan",
    "build_research_summary",
    "candidate_paths",
    "research_single_repo",
    "run_parallel_repo_research",
    "safe_artifact_name",
]
