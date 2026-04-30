import { Navigate, Outlet, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { ConfirmationModal } from '../../components/confirmation-modal'
import { PanelMessage } from '../../components/ui-primitives'
import { useAppData } from '../../hooks/use-app-data'
import { defaultStageForTask, buildTaskStages, truncateTaskTitle, type TaskStageID } from './model'
import { TaskListPane } from './task-list-pane'
import { TaskStageTimeline } from './task-stage-timeline'
import { TaskStageDetailPanel } from './stage-detail-panel'
import { TaskStatusBadge } from './ui'
import { useTaskDetail } from './use-task-detail'

export function TasksLayout() {
  const [taskListCollapsed, setTaskListCollapsed] = useState(false)

  return (
    <div
      className={`grid min-h-screen bg-[#f5f4ed] transition-[grid-template-columns] duration-200 dark:bg-[#141413] lg:h-screen lg:min-h-0 ${
        taskListCollapsed ? 'lg:grid-cols-[76px_minmax(0,1fr)]' : 'lg:grid-cols-[360px_minmax(0,1fr)]'
      }`}
    >
      <TaskListPane collapsed={taskListCollapsed} onToggleCollapsed={() => setTaskListCollapsed((current) => !current)} />
      <div className="min-h-0 overflow-hidden bg-[#faf9f5] dark:bg-[#1d1c1a] lg:min-h-0">
        <Outlet />
      </div>
    </div>
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
  const { taskId } = useParams({ from: '/tasks/$taskId' })
  const { reload } = useAppData()
  const [activeStageID, setActiveStageID] = useState<TaskStageID>('input')
  const detail = useTaskDetail(taskId, reload, setActiveStageID)

  const stages = useMemo(() => (detail.task ? buildTaskStages(detail.task) : []), [detail.task])

  useEffect(() => {
    if (!detail.task) {
      return
    }
    setActiveStageID(defaultStageForTask(detail.task))
  }, [detail.task?.id])

  const activeStage = stages.find((stage) => stage.id === activeStageID) ?? stages[0] ?? null

  if (detail.loading) {
    return <PanelMessage>正在加载任务详情...</PanelMessage>
  }
  if (detail.error) {
    return <PanelMessage>{detail.error}</PanelMessage>
  }
  if (!detail.task) {
    return <PanelMessage>未找到对应 task。</PanelMessage>
  }

  return (
    <>
      <div className="space-y-5 lg:h-full lg:overflow-y-auto">
        <header className="border-b border-[#e8e6dc] bg-[#faf9f5] px-6 py-5 dark:border-[#30302e] dark:bg-[#1d1c1a]">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <button
                className="inline-flex h-8 w-8 items-center justify-center rounded-[8px] text-[#4d4c48] transition hover:bg-[#f5f4ed] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:bg-[#30302e] dark:hover:text-[#faf9f5]"
                onClick={() => setActiveStageID(defaultStageForTask(detail.task!))}
                title="回到当前阶段"
                type="button"
              >
                <BackIcon />
              </button>
              <div className="min-w-0">
                <h3 className="truncate text-xl font-semibold tracking-[-0.02em] text-[#141413] dark:text-[#faf9f5]" title={detail.task.title}>
                  {truncateTaskTitle(detail.task.title, 28)}
                </h3>
                <div className="mt-1 font-mono text-xs text-[#87867f] dark:text-[#b0aea5]">{detail.task.id}</div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2 self-start whitespace-nowrap xl:self-auto">
              <TaskStatusBadge status={detail.task.status} />
            </div>
          </div>

          <div className="mt-5 grid gap-4 border-t border-[#f0eee6] pt-4 text-sm dark:border-[#30302e] md:grid-cols-4">
            <TaskMeta label="当前阶段" value={activeStage?.label ?? '-'} />
            <TaskMeta label="状态" value={detail.task.status} />
            <TaskMeta label="输入类型" value={detail.task.sourceType} />
            <TaskMeta label="更新时间" value={detail.task.updatedAt || '-'} />
          </div>

          <TaskStageTimeline activeStageID={activeStageID} onSelect={setActiveStageID} stages={stages} />
        </header>

        <TaskStageDetailPanel
          actionError={detail.actionError}
          busyAction={detail.busyAction}
          handlers={{
            onStartRefine: detail.startRefineAction,
            onStartDesign: detail.startDesignAction,
            onStartPlan: detail.startPlanAction,
            onStartCode: detail.startCodeAction,
            onResetCode: detail.resetCodeAction,
            onArchive: detail.archiveAction,
          }}
          onTaskUpdated={async () => {
            await detail.refresh()
            await reload()
          }}
          stage={activeStage}
          stages={stages}
          task={detail.task}
        />
      </div>

      <ConfirmationModal
        busy={detail.busyAction === detail.pendingConfirmation?.actionKey}
        confirmLabel={detail.pendingConfirmation?.confirmLabel ?? '确认'}
        description={detail.pendingConfirmation?.description ?? ''}
        impacts={detail.pendingConfirmation?.impacts ?? []}
        eyebrow={detail.pendingConfirmation?.eyebrow ?? 'Confirm Action'}
        onClose={detail.closePendingConfirmation}
        onConfirm={() => void detail.confirmPendingAction()}
        open={Boolean(detail.pendingConfirmation)}
        title={detail.pendingConfirmation?.title ?? ''}
        tone={detail.pendingConfirmation?.tone ?? 'warning'}
      />
    </>
  )
}

function TaskMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-[#87867f] dark:text-[#b0aea5]">{label}</div>
      <div className="mt-2 font-medium text-[#141413] dark:text-[#faf9f5]">{value}</div>
    </div>
  )
}

function BackIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  )
}
