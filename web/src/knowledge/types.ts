export type KnowledgeKind = 'domain' | 'flow' | 'rule'
export type KnowledgeStatus = 'draft' | 'approved' | 'archived'
export type KnowledgeEngine = 'refine' | 'plan'
export type KnowledgePriority = 'low' | 'medium' | 'high'
export type KnowledgeConfidence = 'low' | 'medium' | 'high'

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
}

export type KnowledgeDraftInput = {
  title: string
  description: string
  selected_paths?: string[]
  repos: string[]
  kinds: KnowledgeKind[]
  notes: string
}

export type KnowledgeGenerationJob = {
  job_id: string
  status: string
  progress: number
  stage_label: string
  message: string
  created_at: string
  updated_at: string
  trace_id: string
  document_ids: string[]
  open_questions: string[]
  error: string
}
