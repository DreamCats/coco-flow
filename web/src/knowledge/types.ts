export type KnowledgeKind = 'domain' | 'flow' | 'rule' | 'anchor'
export type KnowledgeStatus = 'draft' | 'approved' | 'archived'
export type KnowledgeEngine = 'refine' | 'plan'
export type KnowledgePriority = 'low' | 'medium' | 'high'
export type KnowledgeConfidence = 'low' | 'medium' | 'high'
export type KnowledgeGroupMode = 'domain' | 'file'

export type KnowledgeEvidence = {
  inputDescription: string
  repoMatches: string[]
  keywordMatches: string[]
  pathMatches: string[]
  candidateFiles: string[]
  contextHits: string[]
  retrievalNotes: string[]
  openQuestions: string[]
}

export type KnowledgeDocument = {
  id: string
  kind: KnowledgeKind
  status: KnowledgeStatus
  title: string
  desc: string
  domainId: string
  domainName: string
  engines: KnowledgeEngine[]
  repos: string[]
  paths: string[]
  keywords: string[]
  priority: KnowledgePriority
  confidence: KnowledgeConfidence
  updatedAt: string
  owner: string
  body: string
  evidence: KnowledgeEvidence
}

export type KnowledgeDraftInput = {
  description: string
  repos: string[]
  kinds: KnowledgeKind[]
  notes: string
}
