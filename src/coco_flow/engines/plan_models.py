from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlanAISections:
    summary: str = ""
    candidate_files: str = ""
    steps: str = ""
    risks: str = ""
    validation_extra: str = ""


@dataclass
class GlossaryEntry:
    business: str
    identifier: str
    module: str


@dataclass
class RefinedSections:
    summary: str
    features: list[str]
    boundaries: list[str]
    business_rules: list[str]
    open_questions: list[str]
    raw: str


@dataclass
class ContextSnapshot:
    available: bool
    glossary_excerpt: str = ""
    architecture_excerpt: str = ""
    patterns_excerpt: str = ""
    gotchas_excerpt: str = ""
    glossary_entries: list[GlossaryEntry] | None = None
    missing_files: list[str] | None = None


@dataclass
class ResearchFinding:
    matched_terms: list[GlossaryEntry]
    unmatched_terms: list[str]
    candidate_files: list[str]
    candidate_dirs: list[str]
    notes: list[str]


@dataclass
class ComplexityDimension:
    name: str
    score: int
    reason: str


@dataclass
class ComplexityAssessment:
    dimensions: list[ComplexityDimension]
    total: int
    level: str
    conclusion: str


@dataclass
class PlanTask:
    id: str
    title: str
    goal: str
    depends_on: list[str]
    files: list[str]
    input: list[str]
    output: list[str]
    actions: list[str]
    done: list[str]


@dataclass
class RepoScope:
    repo_id: str
    repo_path: str


@dataclass
class RepoResearch:
    repo_id: str
    repo_path: str
    context: ContextSnapshot
    finding: ResearchFinding


@dataclass
class PlanBuild:
    task_id: str
    title: str
    source_value: str
    source_markdown: str
    refined_markdown: str
    repo_lines: list[str]
    repo_scopes: list[RepoScope]
    repo_researches: list[RepoResearch]
    repo_ids: set[str]
    repo_root: str | None
    context: ContextSnapshot
    sections: RefinedSections
    finding: ResearchFinding
    assessment: ComplexityAssessment
    knowledge_brief_markdown: str = ""
    knowledge_selection_payload: dict[str, object] = field(default_factory=dict)
    selected_knowledge_ids: list[str] = field(default_factory=list)


@dataclass
class PlanEngineResult:
    status: str
    design_markdown: str
    plan_markdown: str
    intermediate_artifacts: dict[str, str | dict[str, object]] = field(default_factory=dict)


@dataclass
class KnowledgeDocumentLike:
    id: str
    kind: str
    status: str
    title: str
    desc: str
    domain_id: str
    domain_name: str
    engines: list[str]
    repos: list[str]
    paths: list[str]
    keywords: list[str]
    body: str
