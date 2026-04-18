import type { TaskRecord } from '../../api'
import { ActionButton, EmptyPanel, StageStatusBadge } from './ui'
import { type TaskStage, type TaskStageID, preferredCodeRepo } from './model'
import { InputStage } from './stages/input-stage'
import { RefineStage } from './stages/refine-stage'
import { DesignStage } from './stages/design-stage'
import { PlanStage } from './stages/plan-stage'
import { CodeStage } from './stages/code-stage'
import { ArchiveStage } from './stages/archive-stage'

type ActionHandlers = {
  onStartRefine: () => Promise<void> | void
  onStartPlan: () => Promise<void> | void
  onStartCode: (repoId?: string) => Promise<void> | void
  onArchive: (repoId?: string) => Promise<void> | void
}

export function TaskStageDetailPanel({
  task,
  stage,
  busyAction,
  actionError,
  handlers,
  onTaskUpdated,
}: {
  task: TaskRecord | null
  stage: TaskStage | null
  busyAction: string
  actionError: string
  handlers: ActionHandlers
  onTaskUpdated: () => Promise<void> | void
}) {
  if (!task || !stage) {
    return <EmptyPanel>请选择一个任务。</EmptyPanel>
  }

  const actions = buildStageActions(task, stage.id, busyAction, handlers)

  return (
    <div className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Stage Detail</div>
          <h4 className="mt-2 text-[28px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{stage.label}</h4>
          <p className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{stage.summary}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {actions.map((action) => (
            <ActionButton disabled={action.disabled} key={action.label} onClick={action.onClick} tone={action.tone}>
              {action.label}
            </ActionButton>
          ))}
          <StageStatusBadge status={stage.status} />
        </div>
      </div>

      {actionError ? <div className="mt-4 text-sm text-[#b53333]">{actionError}</div> : null}

      <div className="mt-5">
        {stage.id === 'input' ? <InputStage onTaskUpdated={onTaskUpdated} task={task} /> : null}
        {stage.id === 'refine' ? <RefineStage task={task} /> : null}
        {stage.id === 'design' ? <DesignStage task={task} /> : null}
        {stage.id === 'plan' ? <PlanStage task={task} /> : null}
        {stage.id === 'code' ? <CodeStage busyAction={busyAction} onStartCode={handlers.onStartCode} task={task} /> : null}
        {stage.id === 'archive' ? <ArchiveStage task={task} /> : null}
      </div>
    </div>
  )
}

function buildStageActions(task: TaskRecord, stageID: TaskStageID, busyAction: string, handlers: ActionHandlers) {
  if (stageID === 'refine') {
    const disabledByInput = task.status === 'input_processing' || task.status === 'input_failed'
    return [
      {
        label: busyAction === 'refine' ? '提炼中...' : '开始提炼',
        onClick: handlers.onStartRefine,
        disabled: disabledByInput || (busyAction !== '' && busyAction !== 'refine'),
        tone: 'primary' as const,
      },
    ]
  }
  if (stageID === 'design') {
    if (task.repos.length === 0) {
      return [
        {
          label: '待绑定仓库',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    return [
      {
        label: busyAction === 'plan' ? '生成中...' : '生成设计',
        onClick: handlers.onStartPlan,
        disabled: busyAction !== '' && busyAction !== 'plan',
        tone: 'primary' as const,
      },
    ]
  }
  if (stageID === 'plan' && task.repos.length > 0) {
    return [
      {
        label: busyAction === 'plan' ? '生成中...' : '生成计划',
        onClick: handlers.onStartPlan,
        disabled: busyAction !== '' && busyAction !== 'plan',
        tone: 'secondary' as const,
      },
    ]
  }
  if (stageID === 'archive' && task.status === 'coded') {
    const repo = preferredCodeRepo(task)
    return [
      {
        label: busyAction === 'archive' ? '归档中...' : '归档任务',
        onClick: () => handlers.onArchive(repo?.id),
        disabled: busyAction !== '' && busyAction !== 'archive',
        tone: 'primary' as const,
      },
    ]
  }
  return []
}
