export type TaskStatus =
  | 'initialized'
  | 'refined'
  | 'planning'
  | 'planned'
  | 'coding'
  | 'partially_coded'
  | 'coded'
  | 'archived'
  | 'failed'

export type RepoTaskStatus = 'pending' | 'planned' | 'coding' | 'coded' | 'failed' | 'archived' | 'initialized' | 'refined'
export type SourceType = 'text' | 'file' | 'lark_doc'

export type TaskArtifactName =
  | 'prd.source.md'
  | 'prd-refined.md'
  | 'refine.log'
  | 'design.md'
  | 'plan.md'
  | 'plan.log'
  | 'code-result.json'
  | 'code.log'

export type RepoResult = {
  id: string
  displayName: string
  path: string
  status: RepoTaskStatus
  branch?: string
  worktree?: string
  commit?: string
  build?: 'passed' | 'failed' | 'n/a'
  failureHint?: string
  filesWritten?: string[]
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
  state: 'done' | 'current' | 'pending'
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
  updatedAt: string
  owner: string
  complexity: string
  nextAction: string
  repoNext: string[]
  repos: RepoResult[]
  timeline: TaskTimelineItem[]
  artifacts: Record<string, string>
}

export type WorkspaceSummary = {
  repoRoot: string
  tasksRoot: string
  contextRoot: string
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
  return fetchJSON<TaskRecord>(`/api/tasks/${taskId}`)
}

export async function getWorkspace() {
  return fetchJSON<WorkspaceSummary>('/api/workspace')
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
