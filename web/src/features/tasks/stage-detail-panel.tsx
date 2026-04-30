import type { TaskRecord } from '../../api'
import { useState } from 'react'
import { ConfirmationModal } from '../../components/confirmation-modal'
import { ActionButton, EmptyPanel, StageStatusBadge } from './ui'
import { codeActionLabelForRepo, getTaskStage, type TaskStage, preferredCodeRepo, repoReadyForCode } from './model'
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
  onResetCode: (repoId?: string) => Promise<void> | void
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
  const [repoBindingPromptOpen, setRepoBindingPromptOpen] = useState(false)
  const [openRepoBindingToken, setOpenRepoBindingToken] = useState(0)
  if (!task || !stage) {
    return <EmptyPanel>请选择一个任务。</EmptyPanel>
  }

  const effectiveHandlers = {
    ...handlers,
    onStartDesign: () => {
      if (task.repos.length === 0) {
        setRepoBindingPromptOpen(true)
        return Promise.resolve()
      }
      return handlers.onStartDesign()
    },
  }

  const actions = buildStageActions(task, stage, stages, busyAction, effectiveHandlers)

  return (
    <div className="px-6 pb-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs text-[#87867f] dark:text-[#b0aea5]">阶段详情</div>
          <h4 className="mt-1 text-lg font-semibold tracking-[-0.02em] text-[#141413] dark:text-[#faf9f5]">{stage.label}</h4>
          <p className="mt-1 text-sm leading-6 text-[#4d4c48] dark:text-[#b0aea5]">{stage.summary}</p>
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

      <div className="mt-4">
        {stage.id === 'input' ? <InputStage onTaskUpdated={onTaskUpdated} task={task} /> : null}
        {stage.id === 'refine' ? <RefineStage onTaskUpdated={onTaskUpdated} task={task} /> : null}
        {stage.id === 'design' ? <DesignStage onTaskUpdated={onTaskUpdated} openRepoBindingToken={openRepoBindingToken} task={task} /> : null}
        {stage.id === 'plan' ? <PlanStage onTaskUpdated={onTaskUpdated} task={task} /> : null}
        {stage.id === 'code' ? <CodeStage busyAction={busyAction} onResetCode={handlers.onResetCode} onStartCode={handlers.onStartCode} task={task} /> : null}
        {stage.id === 'archive' ? <ArchiveStage task={task} /> : null}
      </div>

      <ConfirmationModal
        confirmLabel="去绑定仓库"
        description="Design 生成前必须先绑定相关仓库。请先补齐仓库绑定，再开始设计。"
        impacts={['当前任务还没有绑定任何仓库', '系统不会再自动推断仓库', '绑定仓库后即可重新点击“生成设计”']}
        eyebrow="Repo Binding Required"
        onClose={() => setRepoBindingPromptOpen(false)}
        onConfirm={() => {
          setRepoBindingPromptOpen(false)
          setOpenRepoBindingToken((current) => current + 1)
        }}
        open={repoBindingPromptOpen}
        title="请先绑定仓库"
        tone="warning"
      />
    </div>
  )
}

function buildStageActions(task: TaskRecord, stage: TaskStage, stages: TaskStage[], busyAction: string, handlers: ActionHandlers) {
  if (stage.id === 'refine') {
    const disabledByInput = task.status === 'input_processing' || task.status === 'input_failed'
    const refining = task.status === 'refining'
    const downstreamRunning = new Set(['designing', 'planning', 'coding']).has(task.status)
    const canRestart = stage.status === 'done' || new Set(['designed', 'planned', 'partially_coded', 'coded', 'failed']).has(task.status)
    return [
      {
        label: busyAction === 'refine' || refining ? '提炼中...' : downstreamRunning ? '等待当前阶段完成' : canRestart ? '重新提炼' : '开始提炼',
        onClick: handlers.onStartRefine,
        disabled: refining || disabledByInput || downstreamRunning || (busyAction !== '' && busyAction !== 'refine'),
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
    const running = task.status === 'designing' || busyAction === 'design'
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
    const running = task.status === 'planning' || busyAction === 'plan'
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
  if (stage.id === 'code') {
    const repo = preferredCodeRepo(task)
    if (!repo) {
      return [
        {
          label: '等待仓库',
          onClick: undefined,
          disabled: true,
          tone: 'secondary' as const,
        },
      ]
    }
    return [
      {
        label: busyAction === 'code' || task.status === 'coding' ? '执行中...' : codeActionLabelForRepo(repo),
        onClick: repo.executionMode === 'reference_only' ? undefined : () => handlers.onStartCode(repo.id),
        disabled:
          repo.executionMode === 'reference_only' ||
          !repoReadyForCode(repo) ||
          task.status === 'coding' ||
          (busyAction !== '' && busyAction !== 'code'),
        tone: repo.executionMode === 'verify_only' ? ('secondary' as const) : ('primary' as const),
      },
    ]
  }
  return []
}
