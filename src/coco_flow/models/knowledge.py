from __future__ import annotations

from pydantic import BaseModel


class KnowledgeEvidence(BaseModel):
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


class KnowledgeListResponse(BaseModel):
    documents: list[KnowledgeDocument]


class CreateKnowledgeDraftsRequest(BaseModel):
    description: str
    repos: list[str]
    kinds: list[str]
    notes: str = ""


class CreateKnowledgeDraftsResponse(BaseModel):
    documents: list[KnowledgeDocument]


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

