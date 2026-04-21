import { useEffect, useState } from 'react'
import { archiveCode, getTask, resetCode, startCode, startDesign, startPlan, startRefine, type TaskRecord } from '../../api'

type ConfirmationTone = 'danger' | 'warning' | 'neutral'

type PendingConfirmation = {
  eyebrow: string
  title: string
  description: string
  impacts: string[]
  confirmLabel: string
  tone: ConfirmationTone
  actionKey: string
  run: () => Promise<void>
}

export function useTaskDetail(taskId: string, onAfterAction: () => Promise<void>) {
  const [task, setTask] = useState<TaskRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [busyAction, setBusyAction] = useState('')
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null)

  async function load() {
    const detail = await getTask(taskId)
    setTask((current) => (isSameTaskRecord(current, detail) ? current : detail))
    setError('')
    return detail
  }

  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        setLoading(true)
        const detail = await getTask(taskId)
        if (cancelled) {
          return
        }
        setTask((current) => (isSameTaskRecord(current, detail) ? current : detail))
        setError('')
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载 task 详情失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [taskId])

  useEffect(() => {
    if (!task || !shouldPoll(task)) {
      return
    }
    let cancelled = false
    const timer = window.setInterval(() => {
      void getTask(taskId)
        .then(async (detail) => {
          if (cancelled) {
            return
          }
          setTask((current) => (isSameTaskRecord(current, detail) ? current : detail))
          if (!shouldPoll(detail)) {
            await onAfterAction()
          }
        })
        .catch(() => {})
    }, 2500)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [task, taskId, onAfterAction])

  async function runAction(label: string, runner: () => Promise<void>) {
    try {
      setBusyAction(label)
      setActionError('')
      await runner()
      await load()
      await onAfterAction()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `${label} 失败`)
    } finally {
      setBusyAction('')
    }
  }

  async function confirmPendingAction() {
    const current = pendingConfirmation
    if (!current) {
      return
    }
    setPendingConfirmation(null)
    await runAction(current.actionKey, current.run)
  }

  return {
    task,
    loading,
    error,
    actionError,
    busyAction,
    pendingConfirmation,
    closePendingConfirmation: () => setPendingConfirmation(null),
    confirmPendingAction,
    refresh: load,
    startRefineAction: () => {
      if (task && shouldConfirmRefineRestart(task.status)) {
        setPendingConfirmation({
          eyebrow: 'Refine Restart',
          title: '重新生成 Refine',
          description: '这会回退当前任务在 Refine 之后的产物，再基于当前输入重新整理需求边界。',
          impacts: buildRefineRestartImpacts(task.status),
          confirmLabel: '回退并重新提炼',
          tone: 'warning',
          actionKey: 'refine',
          run: async () => void (await startRefine(taskId)),
        })
        return Promise.resolve()
      }
      return runAction('refine', async () => void (await startRefine(taskId)))
    },
    startDesignAction: () => {
      if (task?.status === 'planned') {
        setPendingConfirmation({
          eyebrow: 'Design Restart',
          title: '重新生成 Design',
          description: '当前 Design 会被覆盖，现有 Plan 结果也会被清理，后续需要重新生成计划。',
          impacts: ['会覆盖当前 design.md 与相关设计产物', '会删除当前 plan.md、任务拆分和执行图', '重新设计完成后，需要重新生成 Plan'],
          confirmLabel: '回退 Plan 并重新设计',
          tone: 'warning',
          actionKey: 'design',
          run: async () => void (await startDesign(taskId)),
        })
        return Promise.resolve()
      }
      return runAction('design', async () => void (await startDesign(taskId)))
    },
    startPlanAction: () => runAction('plan', async () => void (await startPlan(taskId))),
    startCodeAction: (repoId?: string) => runAction('code', async () => void (await startCode(taskId, repoId))),
    resetCodeAction: (repoId?: string) => runAction('reset', async () => void (await resetCode(taskId, repoId))),
    archiveAction: (repoId?: string) => runAction('archive', async () => void (await archiveCode(taskId, repoId))),
  }
}

function shouldConfirmRefineRestart(status: TaskRecord['status']) {
  return new Set(['designed', 'planned', 'partially_coded', 'coded', 'failed']).has(status)
}

function buildRefineRestartImpacts(status: TaskRecord['status']) {
  const impacts = ['会覆盖当前 prd-refined.md', '会删除现有 design.md 与全部设计产物', '会删除现有 plan.md、任务拆分和执行图']
  if (status === 'partially_coded' || status === 'coded') {
    impacts.push('会清空当前 code 结果、diff、verify 和 repo 级执行记录')
  }
  return impacts
}

function shouldPoll(task: TaskRecord) {
  return (
    task.status === 'input_processing' ||
    task.status === 'initialized' ||
    task.status === 'refining' ||
    task.status === 'designing' ||
    task.status === 'planning' ||
    task.status === 'coding' ||
    (task.status === 'partially_coded' && task.codeProgress.counts.running > 0)
  )
}

function isSameTaskRecord(current: TaskRecord | null, next: TaskRecord) {
  if (!current) {
    return false
  }
  return (
    current.id === next.id &&
    current.title === next.title &&
    current.status === next.status &&
    current.sourceType === next.sourceType &&
    current.sourceFetchError === next.sourceFetchError &&
    current.sourceFetchErrorCode === next.sourceFetchErrorCode &&
    current.updatedAt === next.updatedAt &&
    current.owner === next.owner &&
    current.complexity === next.complexity &&
    current.nextAction === next.nextAction &&
    isSameStringList(current.repoNext, next.repoNext) &&
    isSameArtifacts(current.artifacts, next.artifacts) &&
    isSameTimeline(current.timeline, next.timeline) &&
    isSameRepos(current.repos, next.repos) &&
    isSameCodeProgress(current.codeProgress, next.codeProgress)
  )
}

function isSameStringList(current: string[], next: string[]) {
  if (current.length !== next.length) {
    return false
  }
  return current.every((item, index) => item === next[index])
}

function isSameArtifacts(current: Record<string, string>, next: Record<string, string>) {
  const currentKeys = Object.keys(current)
  const nextKeys = Object.keys(next)
  if (currentKeys.length !== nextKeys.length) {
    return false
  }
  return currentKeys.every((key) => current[key] === next[key])
}

function isSameTimeline(current: TaskRecord['timeline'], next: TaskRecord['timeline']) {
  if (current.length !== next.length) {
    return false
  }
  return current.every((item, index) => {
    const nextItem = next[index]
    return nextItem && item.label === nextItem.label && item.state === nextItem.state && item.detail === nextItem.detail
  })
}

function isSameRepos(current: TaskRecord['repos'], next: TaskRecord['repos']) {
  if (current.length !== next.length) {
    return false
  }
  return current.every((repo, index) => {
    const nextRepo = next[index]
    return nextRepo && JSON.stringify(repo) === JSON.stringify(nextRepo)
  })
}

function isSameCodeProgress(current: TaskRecord['codeProgress'], next: TaskRecord['codeProgress']) {
  return JSON.stringify(current) === JSON.stringify(next)
}
