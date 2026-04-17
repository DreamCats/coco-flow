from __future__ import annotations

from pydantic import BaseModel


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
