import type { TaskRecord } from '../../api'
import { ActionButton, EmptyPanel, StageStatusBadge } from './ui'
import { getTaskStage, type TaskStage, preferredCodeRepo } from './model'
import { InputStage } from './stages/input-stage'
import { RefineStage } from './stages/refine-stage'
import { DesignStage } from './stages/design-stage'
import { PlanStage } from './stages/plan-stage'
import { CodeStage } from './stages/code-stage'
import { ArchiveStage } from './stages/archive-stage'

type ActionHandlers = {
  onStartRefine: () => Promise<void> | void
  onStartDesign: () => Promise<void> | void
  onStartPlan: () => Promise<void> | void
  onStartCode: (repoId?: string) => Promise<void> | void
  onArchive: (repoId?: string) => Promise<void> | void
}

export function TaskStageDetailPanel({
  task,
  stage,
  stages,
  busyAction,
  actionError,
  handlers,
  onTaskUpdated,
}: {
  task: TaskRecord | null
  stage: TaskStage | null
  stages: TaskStage[]
  busyAction: string
  actionError: string
  handlers: ActionHandlers
  onTaskUpdated: () => Promise<void> | void
}) {
  if (!task || !stage) {
    return <EmptyPanel>请选择一个任务。</EmptyPanel>
  }

  const actions = buildStageActions(task, stage, stages, busyAction, handlers)

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
        {stage.id === 'refine' ? <RefineStage onTaskUpdated={onTaskUpdated} task={task} /> : null}
        {stage.id === 'design' ? <DesignStage onTaskUpdated={onTaskUpdated} task={task} /> : null}
        {stage.id === 'plan' ? <PlanStage task={task} /> : null}
        {stage.id === 'code' ? <CodeStage busyAction={busyAction} onStartCode={handlers.onStartCode} task={task} /> : null}
        {stage.id === 'archive' ? <ArchiveStage task={task} /> : null}
      </div>
    </div>
  )
}

function buildStageActions(task: TaskRecord, stage: TaskStage, stages: TaskStage[], busyAction: string, handlers: ActionHandlers) {
  if (stage.id === 'refine') {
    const disabledByInput = task.status === 'input_processing' || task.status === 'input_failed'
    const refining = task.status === 'refining'
    return [
      {
        label: busyAction === 'refine' || refining ? '提炼中...' : '开始提炼',
        onClick: handlers.onStartRefine,
        disabled: refining || disabledByInput || (busyAction !== '' && busyAction !== 'refine'),
        tone: 'primary' as const,
      },
    ]
  }
  if (stage.id === 'design') {
    if (stage.status === 'pending') {
      return [
        {
          label: '等待 Refine',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    if (task.repos.length === 0 || stage.status === 'blocked') {
      return [
        {
          label: '待绑定仓库',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    const running = stage.status === 'current' || busyAction === 'plan'
    return [
      {
        label: running ? '设计生成中...' : stage.status === 'done' || stage.status === 'failed' ? '重新生成设计' : '生成设计',
        onClick: handlers.onStartDesign,
        disabled: running || (busyAction !== '' && busyAction !== 'design'),
        tone: 'primary' as const,
      },
    ]
  }
  if (stage.id === 'plan') {
    const designStage = stages.find((item) => item.id === 'design') ?? getTaskStage(task, 'design')
    if (designStage.status === 'pending') {
      return [
        {
          label: '等待 Design',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    if (task.repos.length === 0 || stage.status === 'blocked') {
      return [
        {
          label: '待绑定仓库',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    if (designStage.status === 'current') {
      return [
        {
          label: '等待设计完成',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    const running = stage.status === 'current' || busyAction === 'plan'
    return [
      {
        label: running ? '计划生成中...' : stage.status === 'done' || stage.status === 'failed' ? '重新生成计划' : '生成计划',
        onClick: handlers.onStartPlan,
        disabled: running || (busyAction !== '' && busyAction !== 'plan'),
        tone: 'secondary' as const,
      },
    ]
  }
  if (stage.id === 'archive' && task.status === 'coded') {
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
