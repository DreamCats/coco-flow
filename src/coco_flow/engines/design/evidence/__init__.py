"""Design local repository evidence collection."""

from .agent_research import normalize_agent_research_payload, run_agent_repo_research
from .repo_index import build_repo_context_package, load_or_build_repo_index
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
    "build_repo_context_package",
    "build_research_summary",
    "candidate_paths",
    "normalize_agent_research_payload",
    "research_single_repo",
    "load_or_build_repo_index",
    "run_agent_repo_research",
    "run_parallel_repo_research",
    "safe_artifact_name",
]
