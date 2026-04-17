from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class KnowledgeEvidence(BaseModel):
    inputTitle: str = ""
    inputDescription: str
    repoMatches: list[str]
    keywordMatches: list[str]
    pathMatches: list[str]
    candidateFiles: list[str]
    contextHits: list[str]
    retrievalNotes: list[str]
    openQuestions: list[str]


class KnowledgeDocument(BaseModel):
    id: str
    traceId: str = ""
    kind: str
    status: str
    title: str
    desc: str
    domainId: str
    domainName: str
    engines: list[str]
    repos: list[str]
    paths: list[str]
    keywords: list[str]
    priority: str
    confidence: str
    updatedAt: str
    owner: str
    body: str
    evidence: KnowledgeEvidence
    rawFrontmatter: str = ""
    rawContent: str = ""


class KnowledgeListResponse(BaseModel):
    documents: list[KnowledgeDocument]


class KnowledgeTraceResponse(BaseModel):
    trace_id: str
    files: list[str]
    intent: dict[str, object]
    term_mapping: dict[str, object]
    candidate_ranking: dict[str, object] = Field(default_factory=dict)
    term_family: dict[str, object] = Field(default_factory=dict)
    focus_boundary: dict[str, object] = Field(default_factory=dict)
    topic_adjudication: dict[str, object] = Field(default_factory=dict)
    anchor_selection: dict[str, object]
    repo_discovery: dict[str, object]
    repo_role_signals: dict[str, object] = Field(default_factory=dict)
    flow_slots: dict[str, object] = Field(default_factory=dict)
    storyline_outline: dict[str, object] = Field(default_factory=dict)
    flow_judge: dict[str, object] = Field(default_factory=dict)
    repo_research: dict[str, dict[str, object]]
    knowledge_draft: dict[str, object]
    validation: dict[str, object]


class KnowledgeGenerationJob(BaseModel):
    job_id: str
    status: str
    progress: int
    stage_label: str
    message: str
    created_at: str
    updated_at: str
    trace_id: str = ""
    document_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    error: str = ""


class CreateKnowledgeDraftsRequest(BaseModel):
    title: str
    description: str
    selected_paths: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=lambda: ["flow"])
    notes: str = ""

    @model_validator(mode="after")
    def normalize_paths(self) -> "CreateKnowledgeDraftsRequest":
        if not self.selected_paths and self.repos:
            self.selected_paths = list(self.repos)
        if not self.repos and self.selected_paths:
            self.repos = list(self.selected_paths)
        return self


class CreateKnowledgeDraftsResponse(BaseModel):
    job: KnowledgeGenerationJob


class CreateKnowledgeDocumentRequest(BaseModel):
    title: str
    content: str = ""


class UpdateKnowledgeDocumentContentRequest(BaseModel):
    content: str


class UpdateKnowledgeDocumentRequest(BaseModel):
    title: str
    desc: str
    status: str
    engines: list[str]
    repos: list[str]
    paths: list[str]
    keywords: list[str]
    priority: str
    confidence: str
    body: str
