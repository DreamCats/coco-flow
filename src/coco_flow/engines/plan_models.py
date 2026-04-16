from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DesignAISections:
    system_change_points: str = ""
    solution_overview: str = ""
    system_dependencies: str = ""
    critical_flows: str = ""
    protocol_changes: str = ""
    storage_config_changes: str = ""
    experiment_changes: str = ""
    qa_inputs: str = ""
    staffing_estimate: str = ""


@dataclass
class ExecutionAISections:
    execution_strategy: str = ""
    candidate_files: str = ""
    steps: str = ""
    blockers_and_risks: str = ""
    validation_plan: str = ""


@dataclass
class PlanAISections:
    design: DesignAISections = field(default_factory=DesignAISections)
    execution: ExecutionAISections = field(default_factory=ExecutionAISections)


@dataclass
class PlanScope:
    summary: str = ""
    boundaries: list[str] = field(default_factory=list)
    priorities: list[str] = field(default_factory=list)
    risk_focus: list[str] = field(default_factory=list)
    validation_focus: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "boundaries": self.boundaries,
            "priorities": self.priorities,
            "risk_focus": self.risk_focus,
            "validation_focus": self.validation_focus,
        }


@dataclass
class GlossaryEntry:
    business: str
    identifier: str
    module: str


@dataclass
class RefinedSections:
    change_scope: list[str]
    non_goals: list[str]
    key_constraints: list[str]
    acceptance_criteria: list[str]
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
class DesignResearchSignals:
    system_summaries: list[str] = field(default_factory=list)
    system_dependencies: list[str] = field(default_factory=list)
    critical_flows: list[str] = field(default_factory=list)
    protocol_changes: list[str] = field(default_factory=list)
    storage_config_changes: list[str] = field(default_factory=list)
    experiment_changes: list[str] = field(default_factory=list)
    qa_inputs: list[str] = field(default_factory=list)


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
class SystemChange:
    system_id: str
    system_name: str
    serves_change_points: list[int]
    responsibility: str
    planned_changes: list[str]
    upstream_inputs: list[str]
    downstream_outputs: list[str]
    touched_repos: list[str]


@dataclass
class SystemDependency:
    upstream_system_id: str
    downstream_system_id: str
    dependency_type: str
    reason: str


@dataclass
class CriticalFlow:
    name: str
    trigger: str
    steps: list[str]
    state_changes: list[str]
    fallback_or_error_handling: list[str]


@dataclass
class ProtocolChange:
    boundary_name: str
    changed: bool
    summary: str
    impacted_systems: list[str]
    compatibility_notes: list[str]


@dataclass
class StorageConfigChange:
    category: str
    changed: bool
    summary: str
    affected_items: list[str]
    rollout_notes: list[str]


@dataclass
class ExperimentChange:
    changed: bool
    experiment_name: str
    traffic_scope: str
    affected_flows: list[str]
    rollout_notes: list[str]
    rollback_notes: list[str]


@dataclass
class StaffingEstimate:
    summary: str
    frontend: str
    backend: str
    qa: str
    coordination_notes: list[str]


@dataclass
class DesignSections:
    system_change_points: list[str] = field(default_factory=list)
    solution_overview: str = ""
    system_changes: list[SystemChange] = field(default_factory=list)
    system_dependencies: list[SystemDependency] = field(default_factory=list)
    critical_flows: list[CriticalFlow] = field(default_factory=list)
    protocol_changes: list[ProtocolChange] = field(default_factory=list)
    storage_config_changes: list[StorageConfigChange] = field(default_factory=list)
    experiment_changes: list[ExperimentChange] = field(default_factory=list)
    qa_inputs: list[str] = field(default_factory=list)
    staffing_estimate: StaffingEstimate | None = None


@dataclass
class PlanTaskSpec:
    id: str
    title: str
    target_system_or_repo: str
    serves_change_points: list[int]
    goal: str
    depends_on: list[str]
    parallelizable_with: list[str]
    change_scope: list[str]
    actions: list[str]
    done_definition: list[str]
    verify_rule: list[str]


PlanTask = PlanTaskSpec


@dataclass
class PlanExecutionSections:
    execution_strategy: list[str] = field(default_factory=list)
    tasks: list[PlanTaskSpec] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    verification_plan: list[str] = field(default_factory=list)
    blockers_and_risks: list[str] = field(default_factory=list)


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
    research_signals: DesignResearchSignals
    assessment: ComplexityAssessment
    knowledge_brief_markdown: str = ""
    knowledge_selection_payload: dict[str, object] = field(default_factory=dict)
    selected_knowledge_ids: list[str] = field(default_factory=list)
    llm_scope: PlanScope = field(default_factory=PlanScope)


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
