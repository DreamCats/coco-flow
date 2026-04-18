import { useEffect, useState } from 'react'
import { archiveCode, getTask, resetCode, startCode, startDesign, startPlan, startRefine, type TaskRecord } from '../../api'

export function useTaskDetail(taskId: string, onAfterAction: () => Promise<void>) {
  const [task, setTask] = useState<TaskRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [busyAction, setBusyAction] = useState('')

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

  return {
    task,
    loading,
    error,
    actionError,
    busyAction,
    refresh: load,
    startRefineAction: () => runAction('refine', async () => void (await startRefine(taskId))),
    startDesignAction: () => {
      if (
        task?.status === 'planned' &&
        !window.confirm('确认重新设计吗？这会覆盖当前 design 产物，清理现有 plan 结果；设计完成后需要重新生成 Plan。')
      ) {
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
