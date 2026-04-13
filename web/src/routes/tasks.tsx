import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  archiveCode,
  createTask,
  deleteTask,
  getTaskArtifact,
  getTask,
  startRemainingCode,
  resetCode,
  startCode,
  startPlan,
  updateTaskArtifact,
  type RepoCandidate,
  type TaskArtifactName,
  type TaskListItem,
  type TaskRecord,
  type TaskStatus,
} from '../api'
import { ActionPanel } from '../components/action-panel'
import { ArtifactEditorDrawer } from '../components/artifact-editor-drawer'
import { RepoPicker } from '../components/repo-picker'
import { RepoDeliveryBoard } from '../components/repo-delivery-board'
import { TaskPrimaryAction } from '../components/task-primary-action'
import { TaskWorkbench, type WorkbenchPane } from '../components/task-workbench'
import {
  CompactField,
  KeyValue,
  PanelMessage,
  RepoStatusBadge,
  StatusBadge,
  TimelineCard,
} from '../components/ui-primitives'
import { useAppData } from '../hooks/use-app-data'

export function TasksLayout() {
  const { tasks, loading, error, reload } = useAppData()
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | TaskStatus>('all')
  const [repoFilter, setRepoFilter] = useState('all')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createInput, setCreateInput] = useState('')
  const [createTitle, setCreateTitle] = useState('')
  const [selectedRepos, setSelectedRepos] = useState<RepoCandidate[]>([])
  const createDialogRef = useRef<HTMLDivElement | null>(null)

  const repoOptions = useMemo(() => {
    const set = new Set<string>()
    for (const task of tasks) {
      for (const repoId of task.repoIds) {
        set.add(repoId)
      }
    }
    return Array.from(set).sort()
  }, [tasks])

  const filteredTasks = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return tasks.filter((task) => {
      if (statusFilter !== 'all' && task.status !== statusFilter) {
        return false
      }
      if (repoFilter !== 'all' && !task.repoIds.includes(repoFilter)) {
        return false
      }
      if (!keyword) {
        return true
      }
      return (
        task.title.toLowerCase().includes(keyword) ||
        task.id.toLowerCase().includes(keyword) ||
        task.repoIds.some((repoId) => repoId.toLowerCase().includes(keyword))
      )
    })
  }, [tasks, query, statusFilter, repoFilter])

  useEffect(() => {
    if (!showCreateForm) {
      return
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowCreateForm(false)
        setCreateError('')
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [showCreateForm])

  useEffect(() => {
    if (!showCreateForm) {
      return
    }

    const frame = window.requestAnimationFrame(() => {
      const block = window.matchMedia('(min-width: 640px)').matches ? 'center' : 'end'
      createDialogRef.current?.scrollIntoView({
        behavior: 'smooth',
        block,
        inline: 'nearest',
      })
    })

    return () => {
      window.cancelAnimationFrame(frame)
    }
  }, [showCreateForm])

  async function submitCreateTask() {
    try {
      setCreating(true)
      setCreateError('')
      const result = await createTask({
        input: createInput.trim(),
        title: createTitle.trim() || undefined,
        repos: selectedRepos.map((repo) => repo.path),
      })
      await reload()
      setShowCreateForm(false)
      setCreateInput('')
      setCreateTitle('')
      setSelectedRepos([])
      void navigate({ to: '/tasks/$taskId', params: { taskId: result.task_id }, resetScroll: false })
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : '创建 task 失败')
    } finally {
      setCreating(false)
    }
  }

  function closeCreateForm() {
    setShowCreateForm(false)
    setCreateError('')
    setSelectedRepos([])
  }

  return (
    <>
      <div className="grid gap-4 lg:h-[calc(100vh-235px)] lg:min-h-0 lg:grid-cols-[360px_minmax(0,1fr)]">
        <section className="rounded-[24px] border border-stone-200 bg-stone-50/80 p-2.5 dark:border-white/10 dark:bg-white/5 lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden">
          <div className="mb-2.5 rounded-[20px] border border-stone-200/80 bg-white/88 p-2.5 shadow-[0_10px_30px_rgba(15,23,42,0.04)] dark:border-white/10 dark:bg-white/[0.04]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-stone-500 dark:text-stone-400">任务推进</div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <h2 className="text-[24px] font-semibold tracking-[-0.05em] text-stone-950 dark:text-stone-50">任务队列</h2>
                  <span className="text-xs text-stone-500 dark:text-stone-400">
                    最近更新 {tasks[0]?.updatedAt ?? '-'}
                  </span>
                </div>
              </div>
              <div className="shrink-0">
                <button
                  className="rounded-2xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-stone-800"
                  onClick={() => setShowCreateForm((current) => !current)}
                  type="button"
                >
                  {showCreateForm ? '收起入口' : '新建任务'}
                </button>
              </div>
            </div>

            <div className="mt-2.5 flex flex-wrap items-center gap-2 text-xs">
              <QueueSummaryItem label="全部任务" value={loading ? '...' : `${tasks.length}`} />
              <QueueSummaryItem
                label="已有结果"
                value={loading ? '...' : `${tasks.filter((task) => task.status === 'coded' || task.status === 'partially_coded').length}`}
              />
              <QueueSummaryItem
                label="待推进"
                value={loading ? '...' : `${tasks.filter((task) => task.status === 'planned' || task.status === 'planning').length}`}
              />
            </div>

            <div className="mt-2.5 space-y-2">
              <input
                className="w-full rounded-2xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-900 outline-none transition placeholder:text-stone-400 focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-white/20"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索标题、仓库或任务编号"
                type="text"
                value={query}
              />
              <div className="grid grid-cols-2 gap-2">
                <select
                  className="rounded-2xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 outline-none focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-200 dark:focus:border-white/20"
                  onChange={(event) => setStatusFilter(event.target.value as 'all' | TaskStatus)}
                  value={statusFilter}
                >
                  <option value="all">全部状态</option>
                  <option value="planned">待进入实现</option>
                  <option value="planning">方案生成中</option>
                  <option value="coding">实现进行中</option>
                  <option value="partially_coded">部分已完成</option>
                  <option value="coded">已产出结果</option>
                  <option value="archived">已归档</option>
                  <option value="failed">处理中断</option>
                </select>
                <select
                  className="rounded-2xl border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 outline-none focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-200 dark:focus:border-white/20"
                  onChange={(event) => setRepoFilter(event.target.value)}
                  value={repoFilter}
                >
                  <option value="all">全部仓库</option>
                  {repoOptions.map((repoId) => (
                    <option key={repoId} value={repoId}>
                      {repoId}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="mb-2 flex items-center justify-between px-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">任务列表</div>
            <div className="text-xs text-stone-500 dark:text-stone-400">{loading ? '...' : `${filteredTasks.length} 条`}</div>
          </div>

          {loading ? (
            <PanelMessage>正在加载 task 列表...</PanelMessage>
          ) : error ? (
            <PanelMessage>{error}</PanelMessage>
          ) : filteredTasks.length === 0 ? (
            <PanelMessage>当前过滤条件下没有 task。</PanelMessage>
          ) : tasks.length === 0 ? (
            <PanelMessage>当前没有 task。</PanelMessage>
          ) : (
            <div className="space-y-1.5 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
              {filteredTasks.map((task) => (
                <TaskListItemCard key={task.id} task={task} />
              ))}
            </div>
          )}
        </section>

        <div className="min-h-0 overflow-hidden lg:min-h-0">
          <Outlet />
        </div>
      </div>

      {showCreateForm ? (
        <div
          className="absolute inset-4 z-50 flex items-end rounded-[28px] bg-stone-950/30 backdrop-blur-sm transition dark:bg-black/55 sm:items-center sm:justify-center lg:inset-5"
          onClick={closeCreateForm}
        >
          <div
            className="mx-4 my-4 flex max-h-[calc(100%-32px)] w-full flex-col overflow-hidden rounded-[28px] border border-stone-200 bg-white shadow-[0_30px_80px_rgba(15,23,42,0.18)] transition duration-200 ease-out dark:border-white/10 dark:bg-[#14171c] dark:shadow-[0_30px_80px_rgba(0,0,0,0.35)] sm:mx-6 sm:my-6 sm:max-w-[900px] sm:max-h-[calc(100%-48px)]"
            onClick={(event) => event.stopPropagation()}
            ref={createDialogRef}
          >
            <div className="flex items-start justify-between gap-4 border-b border-stone-200 px-5 py-5 dark:border-white/10 md:px-6">
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">新建任务</div>
                <h3 className="mt-2 text-[30px] font-semibold tracking-[-0.05em] text-stone-950 dark:text-stone-50">新建需求任务</h3>
                <p className="mt-2 text-sm leading-6 text-stone-500 dark:text-stone-400">
                  先确认需求内容和涉及仓库，系统会在后台整理需求，生成可继续推进的任务。
                </p>
              </div>
              <button
                className="rounded-full border border-stone-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500 transition hover:border-stone-300 hover:text-stone-900 dark:border-white/10 dark:text-stone-400 dark:hover:border-white/20 dark:hover:text-stone-100"
                onClick={closeCreateForm}
                type="button"
              >
                关闭
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 md:px-6">
              <div className="space-y-4">
              <textarea
                className="min-h-32 w-full rounded-[22px] border border-stone-200 px-4 py-4 text-sm text-stone-900 outline-none focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-white/20"
                onChange={(event) => setCreateInput(event.target.value)}
                placeholder="输入需求描述、PRD 文本或飞书链接"
                value={createInput}
              />
              <input
                className="w-full rounded-[22px] border border-stone-200 px-4 py-4 text-sm text-stone-900 outline-none focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-white/20"
                onChange={(event) => setCreateTitle(event.target.value)}
                placeholder="可选标题"
                type="text"
                value={createTitle}
              />
              <RepoPicker onChange={setSelectedRepos} selectedRepos={selectedRepos} />
              {createError ? <div className="text-sm text-rose-600">{createError}</div> : null}
              </div>
            </div>
            <div className="border-t border-stone-200 px-5 py-4 dark:border-white/10 md:px-6">
              <div className="flex flex-wrap gap-2">
                <button
                  className="rounded-2xl bg-stone-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={creating || !createInput.trim() || selectedRepos.length === 0}
                  onClick={() => void submitCreateTask()}
                  type="button"
                >
                  {creating ? '创建中...' : '创建任务'}
                </button>
                <button
                  className="rounded-2xl border border-stone-200 px-5 py-3 text-sm text-stone-700 transition hover:border-stone-300 hover:bg-stone-50 dark:border-white/10 dark:text-stone-300 dark:hover:border-white/20 dark:hover:bg-white/10"
                  onClick={closeCreateForm}
                  type="button"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}

export function TasksIndexPage() {
  const { tasks, loading, error } = useAppData()
  if (loading) {
    return <PanelMessage>正在加载任务...</PanelMessage>
  }
  if (error) {
    return <PanelMessage>{error}</PanelMessage>
  }
  if (tasks.length === 0) {
    return <PanelMessage>当前没有 task。</PanelMessage>
  }
  return <Navigate params={{ taskId: tasks[0]!.id }} replace to="/tasks/$taskId" />
}

export function TaskDetailPage() {
  const navigate = useNavigate()
  const { reload } = useAppData()
  const { taskId } = useParams({ from: '/tasks/$taskId' })
  const [task, setTask] = useState<TaskRecord | null>(null)
  const [artifact, setArtifact] = useState<TaskArtifactName>('prd-refined.md')
  const [artifactContent, setArtifactContent] = useState('')
  const [artifactRepo, setArtifactRepo] = useState('')
  const artifactRequestKeyRef = useRef('')
  const workbenchRef = useRef<HTMLDivElement | null>(null)
  const [selectedDiffRepo, setSelectedDiffRepo] = useState('')
  const [workbenchFocusToken, setWorkbenchFocusToken] = useState(0)
  const [workbenchForcedPane, setWorkbenchForcedPane] = useState<WorkbenchPane | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastRefreshedAt, setLastRefreshedAt] = useState('')
  const [planStarting, setPlanStarting] = useState(false)
  const [codeStartingRepo, setCodeStartingRepo] = useState<string | null>(null)
  const [batchCodeStarting, setBatchCodeStarting] = useState(false)
  const [resettingRepo, setResettingRepo] = useState<string | null>(null)
  const [archivingRepo, setArchivingRepo] = useState<string | null>(null)
  const [actionError, setActionError] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [editorArtifact, setEditorArtifact] = useState<TaskArtifactName>('prd-refined.md')
  const [editorDraft, setEditorDraft] = useState('')
  const [editorInitial, setEditorInitial] = useState('')
  const [editorSaving, setEditorSaving] = useState(false)
  const [editorError, setEditorError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setLoading(true)
        const detail = await getTask(taskId)
        if (cancelled) {
          return
        }
        setTask(detail)
        const firstDiffRepo = detail.repos.find((repo) => repo.diffSummary)?.id ?? detail.repos[0]?.id ?? ''
        setSelectedDiffRepo(firstDiffRepo)
        setArtifactRepo(firstDiffRepo)
        setLastRefreshedAt(formatRefreshTime(new Date()))
        setError('')
        setActionError('')
      } catch (err) {
        if (cancelled) {
          return
        }
        setError(err instanceof Error ? err.message : '加载 task 详情失败')
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    setArtifact('prd-refined.md')
    setArtifactContent('')
    setWorkbenchForcedPane('docs')
    setEditorOpen(false)
    setEditorDraft('')
    setEditorInitial('')
    setEditorError('')
    void load()
    return () => {
      cancelled = true
    }
  }, [taskId])

  useEffect(() => {
    if (!task || (!new Set<TaskStatus>(['initialized', 'planning', 'coding']).has(task.status) && !batchCodeStarting)) {
      return
    }

    let cancelled = false
    const timer = window.setInterval(() => {
      void getTask(taskId)
        .then((detail) => {
          if (cancelled) {
            return
          }
          setTask(detail)
          const firstDiffRepo = detail.repos.find((repo) => repo.diffSummary)?.id ?? detail.repos[0]?.id ?? ''
          setSelectedDiffRepo(firstDiffRepo)
          setArtifactRepo((current) => current || firstDiffRepo)
          setLastRefreshedAt(formatRefreshTime(new Date()))
          if (!shouldContinuePolling(detail, batchCodeStarting)) {
            setPlanStarting(false)
            setCodeStartingRepo(null)
            setBatchCodeStarting(false)
            setResettingRepo(null)
            setArchivingRepo(null)
            void reload()
          }
        })
        .catch(() => {})
    }, 2500)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [task, taskId, reload, batchCodeStarting])

  useEffect(() => {
    if (!task) {
      return
    }

    const repoScopedArtifact = task.repos.length > 1 && (artifact === 'code.log' || artifact === 'code-result.json')
    if (!repoScopedArtifact) {
      setArtifactContent(task.artifacts[artifact] || '')
      return
    }

    const targetRepoID = artifactRepo || task.repos.find((repo) => hasRepoArtifactData(repo, artifact))?.id || task.repos[0]?.id || ''
    if (!targetRepoID) {
      setArtifactContent('当前没有可查看的仓库结果。')
      artifactRequestKeyRef.current = ''
      return
    }

    let cancelled = false
    const requestKey = `${task.id}:${artifact}:${targetRepoID}`
    if (artifactRequestKeyRef.current !== requestKey) {
      artifactRequestKeyRef.current = requestKey
      setArtifactContent('加载中...')
    }
    void getTaskArtifact(task.id, artifact, targetRepoID)
      .then((result) => {
        if (!cancelled) {
          setArtifactContent(result.content)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setArtifactContent(err instanceof Error ? err.message : '加载 artifact 失败')
        }
      })

    return () => {
      cancelled = true
    }
  }, [artifact, artifactRepo, task])

  if (loading) {
    return <PanelMessage>正在加载任务详情...</PanelMessage>
  }
  if (error) {
    return <PanelMessage>{error}</PanelMessage>
  }
  if (!task) {
    return <PanelMessage>未找到对应 task。</PanelMessage>
  }
  const hasGeneratedPlan = hasActionableArtifact(task.artifacts['design.md']) && hasActionableArtifact(task.artifacts['plan.md'])
  const deletableStatuses = new Set<TaskStatus>(['initialized', 'refined', 'planned', 'failed'])
  const canDelete = deletableStatuses.has(task.status)
  const canStartPlan = task.status === 'refined' || task.status === 'planned'
  const singleRepo = task.repos.length === 1 ? task.repos[0] : null
  const canStartCode = singleRepo ? canStartCodeForRepo(singleRepo, hasGeneratedPlan) : false
  const canResetCode = singleRepo ? canResetCodeForRepo(singleRepo) : false
  const canArchiveCode = singleRepo ? canArchiveCodeForRepo(singleRepo) : false
  const remainingRepos = task.repos.filter((repo) => canStartCodeForRepo(repo, hasGeneratedPlan))
  const canStartRemainingCode = task.repos.length > 1 && remainingRepos.length > 0 && task.status !== 'coding'
  const planActionLabel = task.status === 'planned' ? '重新 Plan' : '开始 Plan'
  const codeActionLabel = singleRepo?.status === 'failed' ? '重试实现' : '开始实现'
  const actionBusy = Boolean(planStarting || codeStartingRepo || batchCodeStarting || resettingRepo || archivingRepo)
  const polling = shouldContinuePolling(task, batchCodeStarting)
  const currentTask = task
  const canEditArtifact = canEditTaskArtifact(task.status, artifact)
  const editorDirty = editorDraft !== editorInitial
  const editorCanSave = editorDraft.trim() !== '' && editorDirty && !editorSaving

  async function handleDeleteTask() {
    const confirmed = window.confirm(`确认删除 task ${currentTask.id}？仅允许删除未进入 code 的 task。`)
    if (!confirmed) {
      return
    }
    try {
      await deleteTask(currentTask.id)
      await reload()
      void navigate({ to: '/tasks' })
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '删除 task 失败')
    }
  }

  async function handleStartPlan() {
    try {
      setPlanStarting(true)
      setActionError('')
      const result = await startPlan(currentTask.id)
      setTask({
        ...currentTask,
        status: result.status as TaskStatus,
        nextAction: '方案正在生成，请稍候刷新任务详情。',
      })
      setArtifact('plan.log')
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '启动 plan 失败')
      setPlanStarting(false)
    }
  }

  async function handleStartSingleCode() {
    try {
      setCodeStartingRepo(singleRepo?.id ?? currentTask.id)
      setActionError('')
      const result = await startCode(currentTask.id, singleRepo?.id)
      setTask({
        ...currentTask,
        status: result.status as TaskStatus,
        nextAction: '实现正在执行，请稍候刷新任务详情。',
      })
      setArtifact('code.log')
      setArtifactRepo(singleRepo?.id ?? '')
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '启动实现失败')
      setCodeStartingRepo(null)
    }
  }

  async function handleResetSingleCode() {
    const confirmed = window.confirm('回退后会删除这次生成的分支、worktree、diff 和结果记录。确认继续吗？')
    if (!confirmed) {
      return
    }
    try {
      setResettingRepo(singleRepo?.id ?? currentTask.id)
      setActionError('')
      const result = await resetCode(currentTask.id, singleRepo?.id)
      setTask({
        ...currentTask,
        status: result.status as TaskStatus,
        nextAction: '实现结果已回退，可重新生成方案或再次开始实现。',
      })
      setArtifact('plan.md')
      setArtifactRepo('')
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '回退实现失败')
      setResettingRepo(null)
    }
  }

  async function handleArchiveSingleCode() {
    const confirmed = window.confirm('归档后会清理这次实现产生的分支和 worktree，但会保留结果记录。确认继续吗？')
    if (!confirmed) {
      return
    }
    try {
      setArchivingRepo(singleRepo?.id ?? currentTask.id)
      setActionError('')
      const result = await archiveCode(currentTask.id, singleRepo?.id)
      setTask({
        ...currentTask,
        status: result.status as TaskStatus,
        nextAction: '任务已归档，无后续操作。',
      })
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '归档失败')
      setArchivingRepo(null)
    }
  }

  async function handleStartRemainingCode() {
    try {
      setBatchCodeStarting(true)
      setActionError('')
      const result = await startRemainingCode(currentTask.id)
      setTask({
        ...currentTask,
        status: result.status as TaskStatus,
        nextAction: `正在按顺序推进剩余 ${remainingRepos.length} 个仓库，请稍候刷新任务详情。`,
      })
      setArtifact('code.log')
      setArtifactRepo(remainingRepos[0]?.id ?? artifactRepo)
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : '启动批量实现失败')
      setBatchCodeStarting(false)
    }
  }

  function handleRepoContextChange(repoId: string) {
    setSelectedDiffRepo(repoId)
    setArtifactRepo(repoId)
  }

  function focusWorkbench(pane: WorkbenchPane) {
    setWorkbenchForcedPane(pane)
    setWorkbenchFocusToken((current) => current + 1)
    window.requestAnimationFrame(() => {
      workbenchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  function openArtifactEditor() {
    if (!canEditArtifact) {
      return
    }
    const initial = normalizeEditableContent(artifactContent)
    setEditorArtifact(artifact)
    setEditorDraft(initial)
    setEditorInitial(initial)
    setEditorError('')
    setEditorOpen(true)
  }

  function closeArtifactEditor() {
    if (editorSaving) {
      return
    }
    if (editorDirty && !window.confirm('当前有未保存的修改，确认关闭编辑抽屉吗？')) {
      return
    }
    setEditorOpen(false)
    setEditorError('')
  }

  async function handleSaveArtifact() {
    try {
      setEditorSaving(true)
      setEditorError('')
      const targetArtifact = editorArtifact
      const result = await updateTaskArtifact(currentTask.id, targetArtifact, editorDraft)
      const detail = await getTask(currentTask.id)
      setTask(detail)
      setArtifact(targetArtifact)
      setArtifactContent(result.content)
      setLastRefreshedAt(formatRefreshTime(new Date()))
      setWorkbenchForcedPane('docs')
      setEditorOpen(false)
      setEditorInitial(editorDraft)
      await reload()
    } catch (err) {
      setEditorError(err instanceof Error ? err.message : '保存文档失败')
    } finally {
      setEditorSaving(false)
    }
  }

  return (
    <>
      <div className="space-y-4 lg:h-full lg:overflow-y-auto lg:pr-1">
      <section className="overflow-hidden rounded-[24px] border border-stone-200 bg-[#111317] text-white shadow-[0_30px_80px_rgba(15,23,42,0.18)]">
        <div className="border-b border-white/8 bg-[linear-gradient(135deg,_rgba(16,185,129,0.18),_transparent_38%),linear-gradient(180deg,_rgba(255,255,255,0.04),_rgba(255,255,255,0))] px-5 py-5">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={task.status} />
            <span className="rounded-full border border-white/12 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-300">
              {task.sourceType}
            </span>
            <span className="rounded-full border border-white/12 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-300">
              {task.complexity}
            </span>
          </div>
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.24em] text-stone-400">Task Detail</div>
              <h3 className="mt-2 text-[34px] font-semibold tracking-[-0.05em] text-white">{task.title}</h3>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-stone-300">{taskStatusSummary(currentTask)}</p>
              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <CompactField label="任务编号" value={task.id} />
                <CompactField label="最近更新" value={task.updatedAt} />
                <CompactField label="负责人" value={task.owner} />
                <CompactField label="涉及仓库" value={`${task.repos.length}`} />
              </div>
            </div>
            <TaskPrimaryAction
              actionBusy={actionBusy}
              actionError={actionError}
              archiving={Boolean(archivingRepo)}
              batchCodeStarting={batchCodeStarting}
              canArchiveCode={canArchiveCode}
              canResetCode={canResetCode}
              canStartCode={canStartCode}
              canStartPlan={canStartPlan}
              canStartRemainingCode={canStartRemainingCode}
              codeActionLabel={codeActionLabel}
              codeStarting={Boolean(codeStartingRepo)}
              onArchive={() => void handleArchiveSingleCode()}
              onReset={() => void handleResetSingleCode()}
              onStartCode={() => void handleStartSingleCode()}
              onStartPlan={() => void handleStartPlan()}
              onStartRemainingCode={() => void handleStartRemainingCode()}
              planActionLabel={planActionLabel}
              planStarting={planStarting}
              polling={polling}
              lastRefreshedAt={lastRefreshedAt}
              remainingReposCount={remainingRepos.length}
              resetting={Boolean(resettingRepo)}
              task={task}
            />
          </div>
        </div>
      </section>

      <section className="rounded-[24px] border border-stone-200 bg-[#15181d] p-4 text-white shadow-[0_18px_40px_rgba(15,23,42,0.14)]">
        <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-stone-400">推进阶段</div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {task.timeline.map((step) => (
            <TimelineCard key={step.label} detail={step.detail} label={step.label} state={step.state} />
          ))}
        </div>
      </section>

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
        <div ref={workbenchRef}>
          <TaskWorkbench
            artifact={artifact}
            artifactContent={artifactContent}
            artifactRepo={artifactRepo}
            artifactSaving={editorSaving}
            canEditArtifact={canEditArtifact}
            focusToken={workbenchFocusToken}
            forcedPane={workbenchForcedPane}
            lastRefreshedAt={lastRefreshedAt}
            onArtifactChange={setArtifact}
            onArtifactRepoChange={setArtifactRepo}
            onEditArtifact={openArtifactEditor}
            onPaneChange={setWorkbenchForcedPane}
            onSelectDiffRepo={handleRepoContextChange}
            polling={polling}
            selectedDiffRepo={selectedDiffRepo}
            task={task}
          />
        </div>

        <aside className="space-y-4">
          <RepoDeliveryBoard
            actionBusy={actionBusy}
            archivingRepo={archivingRepo}
            codeStartingRepo={codeStartingRepo}
            hasGeneratedPlan={hasGeneratedPlan}
            polling={polling}
            onArchive={async (repoId) => {
              const confirmed = window.confirm('归档后会清理这次实现产生的分支和 worktree，但会保留结果记录。确认继续吗？')
              if (!confirmed) {
                return
              }
              try {
                setArchivingRepo(repoId)
                setActionError('')
                const result = await archiveCode(currentTask.id, repoId)
                setTask({
                  ...currentTask,
                  status: result.status as TaskStatus,
                  nextAction: `仓库 ${repoId} 已归档。`,
                })
                await reload()
              } catch (err) {
                setActionError(err instanceof Error ? err.message : '归档失败')
                setArchivingRepo(null)
              }
            }}
            onReviewDiff={(repoId) => {
              handleRepoContextChange(repoId)
              focusWorkbench('diff')
            }}
            onReviewResult={(repoId) => {
              setArtifact('code-result.json')
              handleRepoContextChange(repoId)
              focusWorkbench('result')
            }}
            onStartCode={async (repoId) => {
              try {
                setCodeStartingRepo(repoId)
                setActionError('')
                const result = await startCode(currentTask.id, repoId)
                setTask({
                  ...currentTask,
                  status: result.status as TaskStatus,
                  nextAction: `仓库 ${repoId} 正在生成实现，请稍候刷新任务详情。`,
                })
                setArtifact('code.log')
                handleRepoContextChange(repoId)
                await reload()
              } catch (err) {
                setActionError(err instanceof Error ? err.message : '启动实现失败')
                setCodeStartingRepo(null)
              }
            }}
            onReset={async (repoId) => {
              const confirmed = window.confirm('回退后会删除这次生成的分支、worktree、diff 和结果记录。确认继续吗？')
              if (!confirmed) {
                return
              }
              try {
                setResettingRepo(repoId)
                setActionError('')
                const result = await resetCode(currentTask.id, repoId)
                setTask({
                  ...currentTask,
                  status: result.status as TaskStatus,
                  nextAction: `仓库 ${repoId} 的实现结果已回退。`,
                })
                setArtifact('plan.md')
                setArtifactRepo('')
                await reload()
              } catch (err) {
                setActionError(err instanceof Error ? err.message : '回退实现失败')
                setResettingRepo(null)
              }
            }}
            resettingRepo={resettingRepo}
            task={task}
          />
          <RepoScopeCard task={task} />
          <ActionPanel task={task} />
          <DeletePolicyCard canDelete={canDelete} onDelete={canDelete ? handleDeleteTask : undefined} />
        </aside>
      </div>
      </div>
      <ArtifactEditorDrawer
        artifact={editorArtifact}
        busy={editorSaving}
        canSave={editorCanSave}
        error={editorError}
        onChange={setEditorDraft}
        onClose={closeArtifactEditor}
        onSave={() => void handleSaveArtifact()}
        open={editorOpen}
        taskStatus={task.status}
        value={editorDraft}
      />
    </>
  )
}

function hasActionableArtifact(content?: string) {
  if (!content) {
    return false
  }
  return !content.includes("当前没有") && !content.includes("当前为空")
}

function taskStatusSummary(task: TaskRecord) {
  const codedCount = task.repos.filter((repo) => repo.status === 'coded' || repo.status === 'archived').length
  const failedCount = task.repos.filter((repo) => repo.status === 'failed').length
  const runningCount = task.repos.filter((repo) => repo.status === 'coding').length

  switch (task.status) {
    case 'planned':
      return task.repos.length > 1
        ? '方案已经准备好。你可以一键推进剩余仓库，或者在下方按仓库逐个处理。'
        : '方案已经准备好。下一步最适合直接开始实现。'
    case 'planning':
      return '系统正在调研代码并生成方案，完成后会自动进入可实现状态。'
    case 'coding':
      return runningCount > 0 ? `${runningCount} 个仓库正在执行实现，当前更适合查看日志和等待结果。` : '系统正在后台执行实现。'
    case 'partially_coded':
      return `${codedCount} 个仓库已经完成，仍有 ${Math.max(task.repos.length - codedCount, 0)} 个仓库待继续推进。`
    case 'coded':
      return '所有关联仓库都已产出结果。现在更适合集中查看结果、Diff，并决定是否归档。'
    case 'failed':
      return failedCount > 0 ? `${failedCount} 个仓库在推进中失败。建议先查看日志，再决定重试还是回退。` : '任务推进中断。建议先查看日志，再决定如何继续。'
    case 'refined':
      return '需求已经整理完成。下一步最值得做的是生成实施方案。'
    default:
      return '在这里集中查看任务进度、实施方案、实现结果和下一步动作。'
  }
}

function hasRepoArtifactData(repo: TaskRecord['repos'][number], artifact: TaskArtifactName) {
  if (artifact === 'code.log') {
    return repo.status === 'coding' || repo.status === 'coded' || repo.status === 'failed' || repo.status === 'archived'
  }
  if (artifact === 'code-result.json') {
    return Boolean(repo.commit || (repo.filesWritten && repo.filesWritten.length > 0) || repo.build === 'passed' || repo.build === 'failed')
  }
  return false
}

function canStartCodeForRepo(repo: TaskRecord['repos'][number], hasGeneratedPlan: boolean) {
  if (!hasGeneratedPlan) {
    return false
  }
  return repo.status === 'planned' || repo.status === 'failed'
}

function canResetCodeForRepo(repo: TaskRecord['repos'][number]) {
  return repo.status === 'coded' || repo.status === 'failed'
}

function canArchiveCodeForRepo(repo: TaskRecord['repos'][number]) {
  return repo.status === 'coded'
}

function shouldContinuePolling(task: TaskRecord, batchCodeStarting: boolean) {
  if (new Set<TaskStatus>(['initialized', 'planning', 'coding']).has(task.status)) {
    return true
  }
  if (!batchCodeStarting) {
    return false
  }
  if (task.status === 'failed' || task.status === 'coded' || task.status === 'archived') {
    return false
  }
  return task.repos.some((repo) => repo.status === 'planned' || repo.status === 'failed')
}

function formatRefreshTime(value: Date) {
  return value.toLocaleTimeString('zh-CN', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function canEditTaskArtifact(status: TaskStatus, artifact: TaskArtifactName) {
  switch (artifact) {
    case 'prd.source.md':
      return status === 'initialized' || status === 'refined' || status === 'planned'
    case 'prd-refined.md':
      return status === 'refined' || status === 'planned'
    case 'design.md':
    case 'plan.md':
      return status === 'planned'
    default:
      return false
  }
}

function normalizeEditableContent(content: string) {
  if (!hasActionableArtifact(content)) {
    return ''
  }
  return content.replace(/\r\n/g, '\n')
}

function DeletePolicyCard({
  canDelete,
  onDelete,
}: {
  canDelete: boolean
  onDelete?: () => void
}) {
  return (
    <section className="rounded-[24px] border border-stone-200/70 bg-stone-50/75 p-4 dark:border-white/8 dark:bg-white/[0.028]">
      <div className="mb-3 text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Delete Policy</div>
      {canDelete ? (
        <div className="rounded-[18px] border border-emerald-200/80 bg-emerald-50/88 px-3 py-3 text-sm leading-6 text-emerald-800 dark:border-emerald-300/16 dark:bg-emerald-400/10 dark:text-emerald-100">
          <div>当前阶段支持直接删除。如果这条需求不再继续，可以在这里移除。</div>
          {onDelete ? (
            <button
              className="mt-3 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-2 text-sm font-semibold text-rose-700 transition hover:border-rose-200/40 hover:bg-rose-400/20 dark:text-rose-100"
              onClick={onDelete}
              type="button"
            >
              删除任务
            </button>
          ) : null}
        </div>
      ) : (
        <div className="rounded-[18px] border border-amber-200/80 bg-amber-50/88 px-3 py-3 text-sm leading-6 text-amber-900 dark:border-amber-300/16 dark:bg-amber-400/10 dark:text-amber-100">
          当前任务已经进入实现流程。如需回退，建议先处理已有结果后再操作。
        </div>
      )}
    </section>
  )
}

function TaskListItemCard({ task }: { task: TaskListItem }) {
  const location = useLocation()
  const active = location.pathname === `/tasks/${task.id}`
  const repoSummary =
    task.status === 'initialized'
      ? '正在整理需求输入'
      : task.status === 'planning'
        ? '正在分析代码与方案'
        : task.status === 'coding'
          ? '后台实现执行中'
          : formatTaskListRepos(task.repoIds)
  const nextStepHint = taskListNextStep(task.status)

  return (
    <Link
      className={`block rounded-[18px] border px-3.5 py-3 transition ${
        active
          ? 'border-stone-900 bg-stone-900 text-white shadow-[0_16px_34px_rgba(15,23,42,0.18)] dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
          : 'border-stone-200 bg-white text-stone-900 hover:border-stone-300 hover:bg-stone-100/80 dark:border-white/10 dark:bg-white/6 dark:text-stone-100 dark:hover:border-white/20 dark:hover:bg-white/10'
      }`}
      params={{ taskId: task.id }}
      resetScroll={false}
      to="/tasks/$taskId"
    >
      <div className="flex items-center justify-between gap-3">
        <StatusBadge status={task.status} />
        <div className={`text-xs ${active ? 'text-stone-300 dark:text-stone-500' : 'text-stone-500 dark:text-stone-400'}`}>{task.updatedAt}</div>
      </div>
      <div className="mt-2 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold leading-5 tracking-[-0.03em]">{task.title}</div>
          <div className={`mt-1 text-[11px] font-mono ${active ? 'text-stone-400 dark:text-stone-500' : 'text-stone-500 dark:text-stone-400'}`}>{task.id}</div>
        </div>
        <div
          className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
            active
              ? 'border-white/15 text-stone-200 dark:border-stone-300 dark:text-stone-700'
              : 'border-stone-200 text-stone-600 dark:border-white/10 dark:text-stone-300'
          }`}
        >
          {task.repoCount} 仓库
        </div>
      </div>
      <div className={`mt-2 flex items-center justify-between gap-3 text-xs ${active ? 'text-stone-300 dark:text-stone-500' : 'text-stone-500 dark:text-stone-400'}`}>
        <span className="min-w-0 truncate">{repoSummary}</span>
        <span className="shrink-0">{nextStepHint}</span>
      </div>
    </Link>
  )
}

function QueueSummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-stone-50/90 px-3 py-1.5 dark:border-white/10 dark:bg-white/[0.03]">
      <span className="text-[11px] uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">{label}</span>
      <span className="text-sm font-semibold text-stone-950 dark:text-stone-50">{value}</span>
    </div>
  )
}

function formatTaskListRepos(repoIds: string[]) {
  if (repoIds.length === 0) {
    return '暂未绑定仓库'
  }
  if (repoIds.length <= 2) {
    return repoIds.join(' · ')
  }
  return `${repoIds.slice(0, 2).join(' · ')} +${repoIds.length - 2}`
}

function taskListNextStep(status: TaskStatus) {
  switch (status) {
    case 'initialized':
    case 'refined':
      return '等待方案'
    case 'planning':
      return '生成中'
    case 'planned':
      return '可实现'
    case 'coding':
      return '看日志'
    case 'partially_coded':
      return '继续推进'
    case 'coded':
      return '看结果'
    case 'failed':
      return '先排查'
    case 'archived':
      return '已收尾'
    default:
      return '处理中'
  }
}

function RepoScopeCard({ task }: { task: TaskRecord }) {
  return (
    <section className="rounded-[24px] border border-stone-200/70 bg-stone-50/75 p-4 dark:border-white/8 dark:bg-white/[0.028]">
      <div className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">涉及仓库</div>
      <div className="space-y-3">
        <KeyValue label="仓库数量" value={`${task.repos.length}`} />
        <KeyValue label="仓库标识" value={task.repos.map((repo) => repo.id).join(', ')} />
      </div>

      <div className="mt-4 space-y-2">
        {task.repos.map((repo) => (
          <div className="rounded-[18px] border border-stone-200/80 bg-white/72 px-3 py-3 dark:border-white/8 dark:bg-white/[0.03]" key={repo.id}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{repo.displayName}</div>
                <div className="mt-1 font-mono text-[11px] text-stone-500 dark:text-stone-400">{repo.path}</div>
              </div>
              <RepoStatusBadge status={repo.status} />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
