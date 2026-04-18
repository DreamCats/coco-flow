import { Navigate, Outlet, useParams } from '@tanstack/react-router'
import { useEffect, useMemo, useState } from 'react'
import { PanelMessage } from '../../components/ui-primitives'
import { useAppData } from '../../hooks/use-app-data'
import { defaultStageForTask, buildTaskStages, type TaskStageID } from './model'
import { TaskListPane } from './task-list-pane'
import { TaskStageTimeline } from './task-stage-timeline'
import { TaskStageDetailPanel } from './stage-detail-panel'
import { TaskStatusBadge } from './ui'
import { useTaskDetail } from './use-task-detail'

export function TasksLayout() {
  return (
    <div className="grid gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[360px_minmax(0,1fr)]">
      <TaskListPane />
      <div className="min-h-0 overflow-hidden lg:min-h-0">
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
  const detail = useTaskDetail(taskId, reload)
  const [activeStageID, setActiveStageID] = useState<TaskStageID>('input')

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
    <div className="space-y-4 lg:h-full lg:overflow-y-auto lg:pr-1">
      <header className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Current Task</div>
            <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{detail.task.title}</h3>
            <p className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">右侧先看 6 阶段流水线，再进入单阶段详情。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <TaskStatusBadge status={detail.task.status} />
            <span className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1.5 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
              {detail.task.id}
            </span>
          </div>
        </div>

        <TaskStageTimeline activeStageID={activeStageID} onSelect={setActiveStageID} stages={stages} />
      </header>

      <TaskStageDetailPanel
        actionError={detail.actionError}
        busyAction={detail.busyAction}
        handlers={{
          onStartRefine: detail.startRefineAction,
          onStartPlan: detail.startPlanAction,
          onStartCode: detail.startCodeAction,
          onArchive: detail.archiveAction,
        }}
        stage={activeStage}
        task={detail.task}
      />
    </div>
  )
}
