export type KnowledgeKind = 'domain' | 'flow' | 'rule'
export type KnowledgeStatus = 'draft' | 'approved' | 'archived'
export type KnowledgeEngine = 'refine' | 'plan'
export type KnowledgePriority = 'low' | 'medium' | 'high'
export type KnowledgeConfidence = 'low' | 'medium' | 'high'

export type KnowledgeEvidence = {
  inputTitle: string
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
  traceId: string
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
  rawFrontmatter?: string
  rawContent?: string
}
