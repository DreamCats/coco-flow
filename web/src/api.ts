import type { KnowledgeDocument } from './knowledge/types'

export type TaskStatus =
  | 'initialized'
  | 'input_processing'
  | 'input_ready'
  | 'input_failed'
  | 'refining'
  | 'refined'
  | 'designing'
  | 'designed'
  | 'planning'
  | 'planned'
  | 'coding'
  | 'partially_coded'
  | 'coded'
  | 'archived'
  | 'failed'

export type RepoTaskStatus = 'pending' | 'planned' | 'coding' | 'coded' | 'failed' | 'archived' | 'initialized' | 'refined'
export type SourceType = 'text' | 'file' | 'lark_doc'
export type CodeRepoScopeTier = 'must_change' | 'co_change' | 'validate_only' | 'reference_only' | 'unknown'
export type CodeRepoExecutionMode = 'apply' | 'verify_only' | 'reference_only'
export type CodeRepoQueueState = 'ready' | 'running' | 'blocked' | 'done' | 'failed' | 'reference' | 'waiting'
export type CodeProgressStepState = 'done' | 'current' | 'pending'

export type TaskArtifactName =
  | 'prd.source.md'
  | 'prd-refined.md'
  | 'refine.notes.md'
  | 'design.notes.md'
  | 'refine.log'
  | 'design.log'
  | 'design.md'
  | 'plan.md'
  | 'plan.log'
  | 'code-result.json'
  | 'code.log'
  | 'diff.json'
  | 'diff.patch'

export type CodeWorkItem = {
  id: string
  title: string
  repoId: string
  taskType: string
  goal: string
  changeScope: string[]
  dependsOn: string[]
  doneDefinition: string[]
  verificationSteps: string[]
  riskNotes: string[]
  handoffNotes: string[]
}

export type CodeValidationCheck = {
  label: string
  expectation: string
}

export type RepoResult = {
  id: string
  displayName: string
  path: string
  status: RepoTaskStatus
  branch?: string
  worktree?: string
  commit?: string
  build?: 'passed' | 'failed' | 'n/a'
  failureType?: string
  failureHint?: string
  failureAction?: string
  filesWritten?: string[]
  scopeTier?: CodeRepoScopeTier
  executionMode?: CodeRepoExecutionMode
  queueState?: CodeRepoQueueState
  blockedBy?: string[]
  workItems?: CodeWorkItem[]
  verificationChecks?: CodeValidationCheck[]
  changeScope?: string[]
  doneDefinition?: string[]
  verificationSteps?: string[]
  riskNotes?: string[]
  handoffNotes?: string[]
  rationale?: string
  candidateFiles?: string[]
  executionIndex?: number
  diffSummary?: {
    repoId: string
    commit: string
    branch: string
    files: string[]
    additions: number
    deletions: number
    patch: string
  }
}

export type TaskTimelineItem = {
  label: string
  state: 'done' | 'current' | 'pending' | 'blocked' | 'failed'
  detail: string
}

export type TaskListItem = {
  id: string
  title: string
  status: TaskStatus
  sourceType: SourceType
  updatedAt: string
  repoCount: number
  repoIds: string[]
}

export type TaskRecord = {
  id: string
  title: string
  status: TaskStatus
  sourceType: SourceType
  sourceFetchError: string
  sourceFetchErrorCode: string
  updatedAt: string
  owner: string
  complexity: string
  nextAction: string
  repoNext: string[]
  repos: RepoResult[]
  timeline: TaskTimelineItem[]
  artifacts: Record<string, string>
  codeProgress: {
    available: boolean
    source: 'typed' | 'derived' | 'none'
    summary: string
    activeLabel: string
    progressPercent: number
    activeRepoId: string
    repoExecutionOrder: string[]
    runnableRepoIds: string[]
    blockedRepoIds: string[]
    failedRepoIds: string[]
    completedRepoIds: string[]
    referenceRepoIds: string[]
    counts: {
      ready: number
      running: number
      blocked: number
      failed: number
      done: number
      reference: number
    }
    steps: Array<{
      key: string
      label: string
      state: CodeProgressStepState
    }>
  }
}

export type WorkspaceSummary = {
  repoRoot: string
  tasksRoot: string
  knowledgeRoot: string
  worktreeRoot: string
  reposInvolved: string[]
  taskCount: number
}

export type RepoCandidate = {
  id: string
  displayName: string
  path: string
  taskCount?: number
  lastSeenAt?: string
}

export type ArtifactResponse = {
  task_id: string
  repo_id?: string
  name: string
  content: string
}

export type UpdateArtifactResponse = {
  task_id: string
  name: string
  status: TaskStatus
  content: string
}

export type RemoteRoot = {
  label: string
  path: string
}

export type RemoteDirEntry = {
  name: string
  path: string
  isGitRepo: boolean
}

export type CreateTaskRequest = {
  input: string
  title?: string
  supplement?: string
  repos?: string[]
}

async function fetchJSON<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export async function listTasks() {
  const response = await fetchJSON<{ tasks: TaskListItem[] }>('/api/tasks')
  return response.tasks
}

export async function getTask(taskId: string) {
  const detail = await fetchJSON<unknown>(`/api/tasks/${taskId}`)
  return normalizeTaskRecord(detail)
}

export async function getWorkspace() {
  return fetchJSON<WorkspaceSummary>('/api/workspace')
}

export async function listKnowledge() {
  const response = await fetchJSON<{ documents: KnowledgeDocument[] }>('/api/knowledge')
  return response.documents
}

export async function getKnowledge(documentId: string) {
  return fetchJSON<KnowledgeDocument>(`/api/knowledge/${documentId}`)
}

export async function createKnowledgeDocument(input: { title: string; content: string }) {
  const response = await fetch('/api/knowledge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<KnowledgeDocument>
}

export async function updateKnowledgeDocument(documentId: string, input: Partial<KnowledgeDocument>) {
  const response = await fetch(`/api/knowledge/${documentId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: input.title,
      desc: input.desc,
      status: input.status,
      engines: input.engines,
      repos: input.repos,
      priority: input.priority,
      confidence: input.confidence,
      body: input.body,
    }),
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<KnowledgeDocument>
}

export async function updateKnowledgeDocumentContent(documentId: string, content: string) {
  const response = await fetch(`/api/knowledge/${documentId}/content`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<KnowledgeDocument>
}

export async function deleteKnowledgeDocument(documentId: string) {
  const response = await fetch(`/api/knowledge/${documentId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function createTask(input: CreateTaskRequest) {
  const response = await fetch('/api/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function deleteTask(taskId: string) {
  const response = await fetch(`/api/tasks/${taskId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function startRefine(taskId: string) {
  const response = await fetch(`/api/tasks/${taskId}/refine`, {
    method: 'POST',
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string; error?: string } | null
    throw new Error(body?.detail || body?.error || '启动 refine 失败')
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function startDesign(taskId: string) {
  const response = await fetch(`/api/tasks/${taskId}/design`, {
    method: 'POST',
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string; error?: string } | null
    throw new Error(body?.detail || body?.error || '启动 design 失败')
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function startPlan(taskId: string) {
  const response = await fetch(`/api/tasks/${taskId}/plan`, {
    method: 'POST',
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error || '启动 plan 失败')
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function startCode(taskId: string, repoId?: string) {
  const response = await fetch(buildTaskActionPath(taskId, 'code', repoId), {
    method: 'POST',
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error || '启动实现失败')
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function startRemainingCode(taskId: string) {
  const response = await fetch(`/api/tasks/${taskId}/code-all`, {
    method: 'POST',
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error || '启动批量实现失败')
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function resetCode(taskId: string, repoId?: string) {
	const response = await fetch(buildTaskActionPath(taskId, 'reset', repoId), {
		method: 'POST',
	})
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error || '回退实现失败')
	}
	return response.json() as Promise<{ task_id: string; status: string }>
}

export async function archiveCode(taskId: string, repoId?: string) {
	const response = await fetch(buildTaskActionPath(taskId, 'archive', repoId), {
		method: 'POST',
	})
	if (!response.ok) {
		const body = (await response.json().catch(() => null)) as { error?: string } | null
		throw new Error(body?.error || '归档失败')
	}
	return response.json() as Promise<{ task_id: string; status: string }>
}

function buildTaskActionPath(taskId: string, action: 'code' | 'reset' | 'archive', repoId?: string) {
  const path = `/api/tasks/${taskId}/${action}`
  if (!repoId) {
    return path
  }
  return `${path}?repo=${encodeURIComponent(repoId)}`
}

export async function getTaskArtifact(taskId: string, name: TaskArtifactName, repoId?: string) {
  const params = new URLSearchParams({ name })
  if (repoId) {
    params.set('repo', repoId)
  }
  return fetchJSON<ArtifactResponse>(`/api/tasks/${taskId}/artifact?${params.toString()}`)
}

export async function updateTaskArtifact(taskId: string, name: TaskArtifactName, content: string) {
  const params = new URLSearchParams({ name })
  const response = await fetch(`/api/tasks/${taskId}/artifact?${params.toString()}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error || '保存文档失败')
  }
  return response.json() as Promise<UpdateArtifactResponse>
}

export async function updateTaskRepos(taskId: string, repos: string[]) {
  const response = await fetch(`/api/tasks/${taskId}/repos`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repos }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string; error?: string } | null
    throw new Error(body?.detail || body?.error || '更新仓库失败')
  }
  return response.json() as Promise<{ task_id: string; status: string }>
}

export async function listRecentRepos() {
  const response = await fetchJSON<{ repos: RepoCandidate[] }>('/api/repos/recent')
  return response.repos
}

export async function validateRepo(path: string) {
  const response = await fetch('/api/repos/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null
    throw new Error(body?.error || '校验 repo 失败')
  }
  return response.json() as Promise<RepoCandidate>
}

export async function listRemoteRoots() {
  const response = await fetchJSON<{ roots: RemoteRoot[] }>('/api/fs/roots')
  return response.roots
}

export async function listRemoteDirs(path: string) {
  const response = await fetchJSON<{
    path: string
    parentPath: string
    entries: RemoteDirEntry[]
  }>(`/api/fs/list?path=${encodeURIComponent(path)}`)
  return response
}

function normalizeTaskRecord(raw: unknown): TaskRecord {
  const current = asRecord(raw)
  const artifacts = normalizeArtifacts(current.artifacts)
  const repos = normalizeRepos(current.repos)
  const timeline = normalizeTimeline(current.timeline)
  const baseTask: TaskRecord = {
    id: asString(current.id) || asString(current.task_id),
    title: asString(current.title) || asString(current.task_id),
    status: normalizeTaskStatus(asString(current.status)),
    sourceType: normalizeSourceType(asString(current.sourceType) || asString(current.source_type)),
    sourceFetchError: asString(current.sourceFetchError) || asString(current.source_fetch_error),
    sourceFetchErrorCode: asString(current.sourceFetchErrorCode) || asString(current.source_fetch_error_code),
    updatedAt: asString(current.updatedAt) || asString(current.updated_at),
    owner: asString(current.owner),
    complexity: asString(current.complexity),
    nextAction: asString(current.nextAction) || asString(current.next_action),
    repoNext: normalizeStringList(current.repoNext ?? current.repo_next),
    repos,
    timeline,
    artifacts,
    codeProgress: emptyCodeProgress(),
  }

  const enriched = deriveCodeContract(baseTask, current)
  return {
    ...baseTask,
    repos: enriched.repos,
    repoNext: enriched.repoNext,
    codeProgress: enriched.codeProgress,
  }
}

function deriveCodeContract(
  task: TaskRecord,
  raw: Record<string, unknown>,
): Pick<TaskRecord, 'repos' | 'repoNext' | 'codeProgress'> {
  const bindingPayload = parseJSONArtifact(task.artifacts['design-repo-binding.json'])
  const workItemsPayload = parseJSONArtifact(task.artifacts['plan-work-items.json'])
  const graphPayload = parseJSONArtifact(task.artifacts['plan-execution-graph.json'])
  const validationPayload = parseJSONArtifact(task.artifacts['plan-validation.json'])
  const typedProgress = normalizeTypedCodeProgress(raw.codeProgress ?? raw.code_progress)
  const bindings = normalizeBindingEntries(bindingPayload.repo_bindings ?? bindingPayload.bindings)
  const workItems = normalizeWorkItems(workItemsPayload.work_items)
  const validations = normalizeTaskValidations(validationPayload.task_validations)
  const dependencyMap = buildRepoDependencyMap(workItems, bindings)
  const executionOrder = buildRepoExecutionOrder(workItems, graphPayload.execution_order)
  const executionIndex = new Map(executionOrder.map((repoId, index) => [repoId, index]))
  const repoNextFallback = task.repoNext.length > 0 ? task.repoNext : executionOrder

  const repos = task.repos.map((repo) => {
    const binding = bindings.get(repo.id)
    const repoWorkItems = workItems.filter((item) => item.repoId === repo.id)
    const validationEntry = validations.get(repo.id)
    const scopeTier = binding?.scopeTier ?? 'unknown'
    const executionMode = resolveExecutionMode(scopeTier)
    const blockedBy = dependencyMap
      .get(repo.id)
      ?.filter((dependencyRepo) => {
        const dependency = task.repos.find((item) => item.id === dependencyRepo)
        return Boolean(dependency) && dependency?.status !== 'coded' && dependency?.status !== 'archived'
      }) ?? []

    const queueState = resolveRepoQueueState(repo, executionMode, blockedBy, repoNextFallback)
    return {
      ...repo,
      scopeTier,
      executionMode,
      queueState,
      blockedBy,
      workItems: repoWorkItems,
      verificationChecks: validationEntry?.checks ?? [],
      changeScope: uniqueStrings(repoWorkItems.flatMap((item) => item.changeScope)),
      doneDefinition: uniqueStrings(repoWorkItems.flatMap((item) => item.doneDefinition)),
      verificationSteps: uniqueStrings([
        ...repoWorkItems.flatMap((item) => item.verificationSteps),
        ...(validationEntry?.checks ?? []).map((item) => `${item.label}：${item.expectation}`),
      ]),
      riskNotes: uniqueStrings(repoWorkItems.flatMap((item) => item.riskNotes)),
      handoffNotes: uniqueStrings(repoWorkItems.flatMap((item) => item.handoffNotes)),
      rationale: binding?.reason,
      candidateFiles: binding?.candidateFiles ?? [],
      executionIndex: executionIndex.get(repo.id) ?? Number.MAX_SAFE_INTEGER,
    }
  })

  repos.sort((left, right) => {
    const gap = (left.executionIndex ?? Number.MAX_SAFE_INTEGER) - (right.executionIndex ?? Number.MAX_SAFE_INTEGER)
    if (gap !== 0) {
      return gap
    }
    return left.id.localeCompare(right.id)
  })

  const codeProgress = typedProgress ?? buildDerivedCodeProgress(task, repos, executionOrder)
  const repoNext = codeProgress.runnableRepoIds.length > 0 ? codeProgress.runnableRepoIds : task.repoNext
  return { repos, repoNext, codeProgress }
}

function normalizeArtifacts(raw: unknown) {
  if (Array.isArray(raw)) {
    return raw.reduce<Record<string, string>>((acc, item) => {
      const current = asRecord(item)
      const name = asString(current.name)
      if (!name) {
        return acc
      }
      acc[name] = asString(current.content)
      return acc
    }, {})
  }
  const current = asRecord(raw)
  const artifacts: Record<string, string> = {}
  for (const [name, value] of Object.entries(current)) {
    if (typeof value === 'string') {
      artifacts[name] = value
      continue
    }
    const content = asString(asRecord(value).content)
    if (content) {
      artifacts[name] = content
    }
  }
  return artifacts
}

function normalizeRepos(raw: unknown): RepoResult[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.reduce<RepoResult[]>((acc, item) => {
    const current = asRecord(item)
    const id = asString(current.id) || asString(current.repo_id)
    if (!id) {
      return acc
    }
    const diff = asRecord(current.diffSummary ?? current.diff_summary)
    acc.push({
      id,
      displayName: asString(current.displayName) || asString(current.display_name) || id,
      path: asString(current.path),
      status: normalizeRepoStatus(asString(current.status)),
      branch: asString(current.branch) || undefined,
      worktree: asString(current.worktree) || undefined,
      commit: asString(current.commit) || undefined,
      build: normalizeBuildStatus(asString(current.build)),
      failureType: asString(current.failureType) || asString(current.failure_type) || undefined,
      failureHint: asString(current.failureHint) || asString(current.failure_hint) || undefined,
      failureAction: asString(current.failureAction) || asString(current.failure_action) || undefined,
      filesWritten: normalizeStringList(current.filesWritten ?? current.files_written),
      diffSummary: Object.keys(diff).length
        ? {
            repoId: asString(diff.repoId) || asString(diff.repo_id) || id,
            commit: asString(diff.commit),
            branch: asString(diff.branch),
            files: normalizeStringList(diff.files),
            additions: asNumber(diff.additions),
            deletions: asNumber(diff.deletions),
            patch: asString(diff.patch),
          }
        : undefined,
    })
    return acc
  }, [])
}

function normalizeTimeline(raw: unknown): TaskTimelineItem[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map((item) => {
    const current = asRecord(item)
    return {
      label: asString(current.label),
      state: normalizeTimelineState(asString(current.state)),
      detail: asString(current.detail),
    }
  })
}

function normalizeBindingEntries(raw: unknown) {
  const byRepo = new Map<
    string,
    {
      scopeTier: CodeRepoScopeTier
      reason: string
      candidateFiles: string[]
      dependsOn: string[]
    }
  >()
  if (!Array.isArray(raw)) {
    return byRepo
  }
  for (const item of raw) {
    const current = asRecord(item)
    const repoId = asString(current.repo_id) || asString(current.repoId)
    if (!repoId) {
      continue
    }
    byRepo.set(repoId, {
      scopeTier: normalizeScopeTier(asString(current.scope_tier) || asString(current.scopeTier)),
      reason: asString(current.reason),
      candidateFiles: normalizeStringList(current.candidate_files ?? current.candidateFiles),
      dependsOn: normalizeStringList(current.depends_on ?? current.dependsOn),
    })
  }
  return byRepo
}

function normalizeWorkItems(raw: unknown): CodeWorkItem[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .map((item) => {
      const current = asRecord(item)
      const id = asString(current.id)
      const repoId = asString(current.repo_id) || asString(current.repoId)
      if (!id || !repoId) {
        return null
      }
      return {
        id,
        title: asString(current.title),
        repoId,
        taskType: asString(current.task_type) || asString(current.taskType),
        goal: asString(current.goal),
        changeScope: normalizeStringList(current.change_scope ?? current.changeScope),
        dependsOn: normalizeStringList(current.depends_on ?? current.dependsOn),
        doneDefinition: normalizeStringList(current.done_definition ?? current.doneDefinition),
        verificationSteps: normalizeStringList(current.verification_steps ?? current.verificationSteps),
        riskNotes: normalizeStringList(current.risk_notes ?? current.riskNotes),
        handoffNotes: normalizeStringList(current.handoff_notes ?? current.handoffNotes),
      } satisfies CodeWorkItem
    })
    .filter((item): item is CodeWorkItem => Boolean(item))
}

function normalizeTaskValidations(raw: unknown) {
  const byRepo = new Map<string, { checks: CodeValidationCheck[] }>()
  if (!Array.isArray(raw)) {
    return byRepo
  }
  for (const item of raw) {
    const current = asRecord(item)
    const repoId = asString(current.repo_id) || asString(current.repoId)
    if (!repoId) {
      continue
    }
    const checks = Array.isArray(current.checks)
      ? current.checks
          .map((entry) => {
            const check = asRecord(entry)
            const label = asString(check.label) || asString(check.name) || asString(check.type)
            const expectation = asString(check.expectation) || asString(check.detail) || asString(check.rule)
            if (!label && !expectation) {
              return null
            }
            return { label: label || '检查项', expectation: expectation || '已定义' } satisfies CodeValidationCheck
          })
          .filter((entry): entry is CodeValidationCheck => Boolean(entry))
      : []
    byRepo.set(repoId, { checks })
  }
  return byRepo
}

function buildRepoDependencyMap(
  workItems: CodeWorkItem[],
  bindings: Map<string, { dependsOn: string[] }>,
) {
  const dependencyByTask = new Map(workItems.map((item) => [item.id, item.repoId]))
  const byRepo = new Map<string, string[]>()
  for (const item of workItems) {
    const taskDependencies = item.dependsOn
      .map((dependencyId) => dependencyByTask.get(dependencyId) || '')
      .filter((repoId) => repoId && repoId !== item.repoId)
    const bindingDependencies = bindings.get(item.repoId)?.dependsOn ?? []
    byRepo.set(item.repoId, uniqueStrings([...(byRepo.get(item.repoId) ?? []), ...taskDependencies, ...bindingDependencies]))
  }
  for (const [repoId, binding] of bindings.entries()) {
    if (!byRepo.has(repoId)) {
      byRepo.set(repoId, uniqueStrings(binding.dependsOn))
    }
  }
  return byRepo
}

function buildRepoExecutionOrder(workItems: CodeWorkItem[], rawExecutionOrder: unknown) {
  const taskToRepo = new Map(workItems.map((item) => [item.id, item.repoId]))
  const order: string[] = []
  for (const taskId of normalizeStringList(rawExecutionOrder)) {
    const repoId = taskToRepo.get(taskId)
    if (repoId && !order.includes(repoId)) {
      order.push(repoId)
    }
  }
  for (const item of workItems) {
    if (!order.includes(item.repoId)) {
      order.push(item.repoId)
    }
  }
  return order
}

function buildDerivedCodeProgress(task: TaskRecord, repos: RepoResult[], executionOrder: string[]): TaskRecord['codeProgress'] {
  const running = repos.filter((repo) => repo.queueState === 'running')
  const ready = repos.filter((repo) => repo.queueState === 'ready')
  const blocked = repos.filter((repo) => repo.queueState === 'blocked')
  const failed = repos.filter((repo) => repo.queueState === 'failed')
  const done = repos.filter((repo) => repo.queueState === 'done')
  const reference = repos.filter((repo) => repo.queueState === 'reference')
  const executableRepos = repos.filter((repo) => repo.executionMode !== 'reference_only')
  const activeRepo = running[0] ?? ready[0] ?? failed[0] ?? blocked[0] ?? executableRepos[0] ?? repos[0]
  const settledCount = done.length + failed.length
  const totalExecutable = executableRepos.length || 1
  const progressPercent =
    task.status === 'coded' || task.status === 'archived'
      ? 100
      : Math.min(96, Math.max(8, Math.round(((settledCount + running.length * 0.5) / totalExecutable) * 100)))

  const summary =
    running.length > 0
      ? `当前正在推进 ${running.map((repo) => repo.displayName).join('、')}。`
      : ready.length > 0
        ? `当前可执行 ${ready.map((repo) => repo.displayName).join('、')}。`
        : failed.length > 0
          ? `当前有 ${failed.length} 个仓执行失败，建议先看结果再决定是否重试。`
          : blocked.length > 0
            ? `当前受阻塞：${blocked.map((repo) => repo.displayName).join('、')}。`
            : executableRepos.length > 0 && done.length === executableRepos.length
              ? '所有可执行仓已完成，实现结果已收敛。'
              : reference.length === repos.length
                ? '当前没有可执行仓，所有绑定仓都属于参考范围。'
                : task.nextAction || '等待进入 Code 阶段。'

  const steps = buildDerivedCodeSteps(task, { ready, running, blocked, failed, done, reference })

  return {
    available: repos.length > 0,
    source: repos.length > 0 ? 'derived' : 'none',
    summary,
    activeLabel: activeRepo ? `${activeRepo.displayName} · ${labelForQueueState(activeRepo.queueState ?? 'waiting')}` : '等待开始',
    progressPercent,
    activeRepoId: activeRepo?.id ?? '',
    repoExecutionOrder: executionOrder,
    runnableRepoIds: ready.map((repo) => repo.id),
    blockedRepoIds: blocked.map((repo) => repo.id),
    failedRepoIds: failed.map((repo) => repo.id),
    completedRepoIds: done.map((repo) => repo.id),
    referenceRepoIds: reference.map((repo) => repo.id),
    counts: {
      ready: ready.length,
      running: running.length,
      blocked: blocked.length,
      failed: failed.length,
      done: done.length,
      reference: reference.length,
    },
    steps,
  }
}

function normalizeTypedCodeProgress(raw: unknown): TaskRecord['codeProgress'] | null {
  const current = asRecord(raw)
  if (Object.keys(current).length === 0) {
    return null
  }
  const counts = asRecord(current.counts)
  const summary = asRecord(current.summary)
  const batchEntries = Array.isArray(current.repo_batches)
    ? current.repo_batches.map((item) => asRecord(item))
    : Array.isArray(current.batches)
      ? current.batches.map((item) => asRecord(item))
      : []
  const explicitSteps = Array.isArray(current.steps)
    ? current.steps.map((item, index) => {
        const step = asRecord(item)
        return {
          key: asString(step.key) || `step-${index + 1}`,
          label: asString(step.label) || `步骤 ${index + 1}`,
          state: normalizeStepState(asString(step.state)),
        }
      })
    : []
  const derivedCounts = {
    ready:
      asNumber(counts.ready) ||
      batchEntries.filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'ready').length,
    running:
      asNumber(counts.running) ||
      asNumber(summary.running_batches ?? summary.batch_running) ||
      batchEntries.filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'running').length,
    blocked:
      asNumber(counts.blocked) ||
      asNumber(summary.blocked_batches ?? summary.batch_blocked) ||
      batchEntries.filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'blocked').length,
    failed:
      asNumber(counts.failed) ||
      asNumber(summary.failed_batches ?? summary.batch_failed) ||
      batchEntries.filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'failed').length,
    done:
      asNumber(counts.done) ||
      asNumber(summary.completed_batches ?? summary.batch_completed) ||
      batchEntries.filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'done').length,
    reference: asNumber(counts.reference),
  }
  const activeBatchId = asString(current.current_batch_id) || asString(current.currentBatchId)
  const activeBatch = activeBatchId ? batchEntries.find((entry) => asString(entry.id) === activeBatchId) : null
  const activeReadyBatch = batchEntries.find((entry) => normalizeBatchStatus(asString(entry.status)) === 'ready')
  const activeRunningBatch = batchEntries.find((entry) => normalizeBatchStatus(asString(entry.status)) === 'running')
  const activeDoneBatch = batchEntries.find((entry) => normalizeBatchStatus(asString(entry.status)) === 'done')
  const activeFailedBatch = batchEntries.find((entry) => normalizeBatchStatus(asString(entry.status)) === 'failed')
  const activeBatchEntry = activeBatch ?? activeRunningBatch ?? activeReadyBatch ?? activeFailedBatch ?? activeDoneBatch ?? null
  const derivedRepoExecutionOrder = batchEntries
    .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
    .filter(Boolean)
  const derivedRunnableRepoIds = batchEntries
    .filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'ready')
    .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
    .filter(Boolean)
  const derivedBlockedRepoIds = batchEntries
    .filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'blocked')
    .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
    .filter(Boolean)
  const derivedFailedRepoIds = batchEntries
    .filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'failed')
    .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
    .filter(Boolean)
  const derivedCompletedRepoIds = batchEntries
    .filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'done')
    .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
    .filter(Boolean)
  const totalBatches = asNumber(summary.total_batches ?? summary.batch_total) || batchEntries.length
  const completedBatches = derivedCounts.done
  const completedUnits = completedBatches + derivedCounts.failed
  const derivedProgressPercent =
    totalBatches <= 0
      ? 0
      : Math.min(
          100,
          Math.max(
            derivedCounts.running > 0 ? 8 : 0,
            Math.round(((completedUnits + derivedCounts.running * 0.5) / Math.max(totalBatches, 1)) * 100),
          ),
        )
  const derivedSummary =
    derivedCounts.running > 0
      ? `当前正在推进 ${batchEntries
          .filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'running')
          .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
          .filter(Boolean)
          .join('、')}。`
      : derivedCounts.ready > 0
        ? `当前可执行 ${batchEntries
            .filter((entry) => normalizeBatchStatus(asString(entry.status)) === 'ready')
            .map((entry) => asString(entry.repo_id) || asString(entry.repoId))
            .filter(Boolean)
            .join('、')}。`
        : derivedCounts.failed > 0
          ? `当前有 ${derivedCounts.failed} 个仓执行失败，建议先看结果再决定是否重试。`
          : derivedCounts.blocked > 0
            ? `当前有 ${derivedCounts.blocked} 个仓受依赖阻塞。`
            : derivedCounts.done > 0 && derivedCounts.running === 0 && derivedCounts.ready === 0
              ? '所有可执行仓已完成，实现结果已收敛。'
              : '当前还没有开始执行。'
  const steps = explicitSteps.length > 0 ? explicitSteps : buildCodeStepsFromCounts(derivedCounts)
  const activeRepoId = asString(current.activeRepoId) || asString(current.active_repo_id) || asString(activeBatchEntry?.repo_id) || asString(activeBatchEntry?.repoId)
  const activeQueueState = activeBatchEntry ? normalizeBatchStatus(asString(activeBatchEntry.status)) : 'waiting'
  return {
    available: true,
    source: 'typed',
    summary: asString(current.summary) || derivedSummary,
    activeLabel:
      asString(current.activeLabel) ||
      asString(current.active_label) ||
      (activeRepoId ? `${activeRepoId} · ${labelForQueueState(activeQueueState)}` : '等待开始实现'),
    progressPercent: asNumber(current.progressPercent ?? current.progress_percent) || derivedProgressPercent,
    activeRepoId,
    repoExecutionOrder: normalizeStringList(current.repoExecutionOrder ?? current.repo_execution_order).length > 0
      ? normalizeStringList(current.repoExecutionOrder ?? current.repo_execution_order)
      : derivedRepoExecutionOrder,
    runnableRepoIds: normalizeStringList(current.runnableRepoIds ?? current.runnable_repo_ids).length > 0
      ? normalizeStringList(current.runnableRepoIds ?? current.runnable_repo_ids)
      : derivedRunnableRepoIds,
    blockedRepoIds: normalizeStringList(current.blockedRepoIds ?? current.blocked_repo_ids).length > 0
      ? normalizeStringList(current.blockedRepoIds ?? current.blocked_repo_ids)
      : derivedBlockedRepoIds,
    failedRepoIds: normalizeStringList(current.failedRepoIds ?? current.failed_repo_ids).length > 0
      ? normalizeStringList(current.failedRepoIds ?? current.failed_repo_ids)
      : derivedFailedRepoIds,
    completedRepoIds: normalizeStringList(current.completedRepoIds ?? current.completed_repo_ids).length > 0
      ? normalizeStringList(current.completedRepoIds ?? current.completed_repo_ids)
      : derivedCompletedRepoIds,
    referenceRepoIds: normalizeStringList(current.referenceRepoIds ?? current.reference_repo_ids),
    counts: {
      ready: derivedCounts.ready,
      running: derivedCounts.running,
      blocked: derivedCounts.blocked,
      failed: derivedCounts.failed,
      done: derivedCounts.done,
      reference: derivedCounts.reference,
    },
    steps,
  }
}

function buildCodeStepsFromCounts(counts: {
  ready: number
  running: number
  blocked: number
  failed: number
  done: number
  reference: number
}) {
  const executableCount = counts.ready + counts.running + counts.blocked + counts.failed + counts.done
  const dispatchDone = executableCount > 0 || counts.reference > 0
  const queueDone = counts.ready > 0 || counts.running > 0 || counts.done > 0 || counts.failed > 0
  const executionDone = counts.running === 0 && (counts.done > 0 || counts.failed > 0)
  const currentKey = !dispatchDone ? 'dispatch' : !queueDone ? 'queue' : executionDone ? '' : counts.running > 0 ? 'execute' : 'queue'
  return [
    { key: 'dispatch', label: '任务分发', state: normalizeDerivedStepState('dispatch', dispatchDone, currentKey) },
    { key: 'queue', label: '队列就绪', state: normalizeDerivedStepState('queue', queueDone, currentKey) },
    { key: 'execute', label: '执行实现', state: normalizeDerivedStepState('execute', executionDone, currentKey) },
  ] satisfies TaskRecord['codeProgress']['steps']
}

function normalizeBatchStatus(value: string): CodeRepoQueueState {
  switch (value) {
    case 'ready':
      return 'ready'
    case 'running':
    case 'coding':
    case 'in_progress':
      return 'running'
    case 'blocked':
    case 'waiting_on_dependency':
      return 'blocked'
    case 'failed':
    case 'verify_failed':
      return 'failed'
    case 'completed':
    case 'done':
    case 'coded':
      return 'done'
    default:
      return 'waiting'
  }
}

function buildDerivedCodeSteps(
  task: TaskRecord,
  counts: {
    ready: RepoResult[]
    running: RepoResult[]
    blocked: RepoResult[]
    failed: RepoResult[]
    done: RepoResult[]
    reference: RepoResult[]
  },
) {
  const executableCount = counts.ready.length + counts.running.length + counts.blocked.length + counts.failed.length + counts.done.length
  const dispatchDone = executableCount > 0 || counts.reference.length > 0
  const queueDone = counts.ready.length > 0 || counts.running.length > 0 || counts.done.length > 0 || counts.failed.length > 0
  const executionDone = counts.running.length === 0 && (counts.done.length > 0 || counts.failed.length > 0)
  const validationRequired = counts.reference.length !== task.repos.length
  const validationDone = !validationRequired || counts.done.length > 0 || counts.failed.length > 0
  const settled = task.status === 'coded' || task.status === 'archived' || (counts.ready.length === 0 && counts.running.length === 0 && counts.blocked.length === 0)
  const currentKey =
    !dispatchDone ? 'dispatch'
    : !queueDone ? 'queue'
    : counts.running.length > 0
      ? 'execute'
      : !validationDone
        ? 'verify'
        : !settled
          ? 'settle'
          : ''
  return [
    { key: 'dispatch', label: '任务分发', state: normalizeDerivedStepState('dispatch', dispatchDone, currentKey) },
    { key: 'queue', label: '队列就绪', state: normalizeDerivedStepState('queue', queueDone, currentKey) },
    { key: 'execute', label: '执行实现', state: normalizeDerivedStepState('execute', executionDone, currentKey) },
    { key: 'verify', label: '验证收口', state: normalizeDerivedStepState('verify', validationDone, currentKey) },
    { key: 'settle', label: '结果沉淀', state: normalizeDerivedStepState('settle', settled, currentKey) },
  ]
}

function normalizeDerivedStepState(key: string, done: boolean, currentKey: string): CodeProgressStepState {
  if (done) {
    return 'done'
  }
  return currentKey === key ? 'current' : 'pending'
}

function resolveExecutionMode(scopeTier: CodeRepoScopeTier): CodeRepoExecutionMode {
  if (scopeTier === 'validate_only') {
    return 'verify_only'
  }
  if (scopeTier === 'reference_only') {
    return 'reference_only'
  }
  return 'apply'
}

function resolveRepoQueueState(
  repo: RepoResult,
  executionMode: CodeRepoExecutionMode,
  blockedBy: string[],
  repoNext: string[],
): CodeRepoQueueState {
  if (executionMode === 'reference_only') {
    return 'reference'
  }
  if (repo.status === 'coding') {
    return 'running'
  }
  if (repo.status === 'coded' || repo.status === 'archived') {
    return 'done'
  }
  if (repo.failureType === 'blocked_by_dependency' || blockedBy.length > 0) {
    return 'blocked'
  }
  if (repo.status === 'failed') {
    return repoNext.includes(repo.id) ? 'ready' : 'failed'
  }
  if (repoNext.includes(repo.id) || repo.status === 'planned' || repo.status === 'initialized' || repo.status === 'refined') {
    return 'ready'
  }
  return 'waiting'
}

function parseJSONArtifact(content?: string) {
  if (!content) {
    return {}
  }
  try {
    const parsed = JSON.parse(content) as unknown
    return asRecord(parsed)
  } catch {
    return {}
  }
}

function emptyCodeProgress(): TaskRecord['codeProgress'] {
  return {
    available: false,
    source: 'none',
    summary: '当前还没有可用的 Code Progress。',
    activeLabel: '等待开始',
    progressPercent: 0,
    activeRepoId: '',
    repoExecutionOrder: [],
    runnableRepoIds: [],
    blockedRepoIds: [],
    failedRepoIds: [],
    completedRepoIds: [],
    referenceRepoIds: [],
    counts: {
      ready: 0,
      running: 0,
      blocked: 0,
      failed: 0,
      done: 0,
      reference: 0,
    },
    steps: [
      { key: 'dispatch', label: '任务分发', state: 'pending' },
      { key: 'queue', label: '队列就绪', state: 'pending' },
      { key: 'execute', label: '执行实现', state: 'pending' },
      { key: 'verify', label: '验证收口', state: 'pending' },
      { key: 'settle', label: '结果沉淀', state: 'pending' },
    ],
  }
}

function normalizeTaskStatus(value: string): TaskStatus {
  switch (value) {
    case 'initialized':
    case 'input_processing':
    case 'input_ready':
    case 'input_failed':
    case 'refining':
    case 'refined':
    case 'designing':
    case 'designed':
    case 'planning':
    case 'planned':
    case 'coding':
    case 'partially_coded':
    case 'coded':
    case 'archived':
    case 'failed':
      return value
    default:
      return 'initialized'
  }
}

function normalizeRepoStatus(value: string): RepoTaskStatus {
  switch (value) {
    case 'pending':
    case 'planned':
    case 'coding':
    case 'coded':
    case 'failed':
    case 'archived':
    case 'initialized':
    case 'refined':
      return value
    default:
      return 'initialized'
  }
}

function normalizeSourceType(value: string): SourceType {
  switch (value) {
    case 'text':
    case 'file':
    case 'lark_doc':
      return value
    default:
      return 'text'
  }
}

function normalizeBuildStatus(value: string): RepoResult['build'] {
  if (value === 'passed' || value === 'failed' || value === 'n/a') {
    return value
  }
  return undefined
}

function normalizeTimelineState(value: string): TaskTimelineItem['state'] {
  switch (value) {
    case 'done':
    case 'current':
    case 'pending':
    case 'blocked':
    case 'failed':
      return value
    default:
      return 'pending'
  }
}

function normalizeScopeTier(value: string): CodeRepoScopeTier {
  switch (value) {
    case 'must_change':
    case 'co_change':
    case 'validate_only':
    case 'reference_only':
      return value
    default:
      return 'unknown'
  }
}

function normalizeStepState(value: string): CodeProgressStepState {
  switch (value) {
    case 'done':
    case 'current':
    case 'pending':
      return value
    default:
      return 'pending'
  }
}

function normalizeStringList(raw: unknown) {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map((item) => asString(item)).filter(Boolean)
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)))
}

function labelForQueueState(state: CodeRepoQueueState) {
  switch (state) {
    case 'ready':
      return 'ready'
    case 'running':
      return 'running'
    case 'blocked':
      return 'blocked'
    case 'failed':
      return 'failed'
    case 'done':
      return 'done'
    case 'reference':
      return 'reference'
    default:
      return 'waiting'
  }
}

function asRecord(raw: unknown): Record<string, unknown> {
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
}

function asString(raw: unknown) {
  return typeof raw === 'string' ? raw : ''
}

function asNumber(raw: unknown) {
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : 0
}
