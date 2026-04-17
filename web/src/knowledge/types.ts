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

export type KnowledgeTrace = {
  trace_id: string
  files: string[]
  intent: Record<string, unknown>
  term_mapping: Record<string, unknown>
  candidate_ranking: Record<string, unknown>
  term_family: Record<string, unknown>
  anchor_selection: Record<string, unknown>
  repo_discovery: {
    repos?: Array<{
      repo_id?: string
      requested_path?: string
      repo_path?: string
    }>
    [key: string]: unknown
  }
  repo_research: Record<string, unknown>
  knowledge_draft: Record<string, unknown>
  validation: Record<string, unknown>
}
