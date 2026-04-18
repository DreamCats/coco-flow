import type { TaskRecord } from '../api'
import { StatusBadge } from './ui-primitives'

type WorkflowNodeState = 'done' | 'current' | 'pending' | 'failed' | 'blocked'

type WorkflowNode = {
  key: string
  label: string
  state: WorkflowNodeState
  artifact: string
  detail: string
}

export function TaskWorkflowOverview({ task }: { task: TaskRecord }) {
  const nodes = buildWorkflowNodes(task)

  return (
    <section className="overflow-hidden rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="border-b border-[#e8e6dc] px-5 py-4 dark:border-[#30302e]">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Task Workflow Workbench</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h2 className="text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
              {task.title}
            </h2>
            <StatusBadge status={task.status} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
            <MetaPill label="task" value={task.id} />
            <MetaPill label="source" value={task.sourceType} />
            <MetaPill label="repos" value={`${task.repos.length}`} />
            <MetaPill label="updated" value={task.updatedAt || '--'} />
          </div>
        </div>
      </div>

      <div className="border-b border-[#e8e6dc] px-5 py-5 dark:border-[#30302e]">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Pipeline Strip</div>
            <div className="mt-1 text-sm text-[#5e5d59] dark:text-[#b0aea5]">先确认任务所处阶段，再决定是否继续推进或处理阻塞。</div>
          </div>
        </div>
        <div className="-mx-1 overflow-x-auto pb-1">
          <div className="flex min-w-max items-stretch gap-3 px-1">
            {nodes.map((node, index) => (
              <div className="flex items-center gap-3" key={node.key}>
                <div className="w-[220px] min-w-[220px]">
                  <PipelineNodeCard node={node} />
                </div>
                {index < nodes.length - 1 ? (
                  <div className="flex min-w-8 items-center justify-center">
                    <div className="h-[2px] w-8 bg-[#ddd9cc] dark:bg-[#3a3937]" />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

function PipelineNodeCard({ node }: { node: WorkflowNode }) {
  return (
    <div className={`rounded-[18px] border p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] ${toneClass(node.state)}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-semibold ${bulletTone(node.state)}`}>
            {bulletSymbol(node.state)}
          </span>
          <div className="text-sm font-semibold">{node.label}</div>
        </div>
        <div className="text-[10px] uppercase tracking-[0.3em] opacity-75">{node.state}</div>
      </div>
      <div className="mt-3 text-[11px] uppercase tracking-[0.4px] opacity-70">{node.artifact}</div>
      <div className="mt-2 text-sm leading-6 opacity-90">{node.detail}</div>
    </div>
  )
}

function MetaPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-full border border-[#e8e6dc] px-3 py-1 dark:border-[#30302e]">
      {label}: {value}
    </span>
  )
}

function buildWorkflowNodes(task: TaskRecord): WorkflowNode[] {
  const hasDesign = hasActionableArtifact(task.artifacts['design.md'])
  const hasPlan = hasActionableArtifact(task.artifacts['plan.md'])
  const blockedRepos = task.codeProgress.blockedRepoIds
  const hasReadyRepo = task.codeProgress.runnableRepoIds.length > 0
  const codeState = resolveCodeState(task, hasPlan, blockedRepos.length > 0, hasReadyRepo)
  const designState = resolveDesignState(task, hasDesign)
  const planState = resolvePlanState(task, hasPlan)

  return [
    {
      key: 'input',
      label: 'Input',
      state: 'done',
      artifact: 'prd.source.md',
      detail: inputDetail(task),
    },
    {
      key: 'refine',
      label: 'Refine',
      state: resolveRefineState(task),
      artifact: 'prd-refined.md',
      detail: refineDetail(task),
    },
    {
      key: 'design',
      label: 'Design',
      state: designState,
      artifact: 'design.md',
      detail: designDetail(task, hasDesign),
    },
    {
      key: 'plan',
      label: 'Plan',
      state: planState,
      artifact: 'plan.md',
      detail: planDetail(task, hasPlan),
    },
    {
      key: 'code',
      label: 'Code',
      state: codeState,
      artifact: 'code.log / code-result.json',
      detail: codeDetail(task, blockedRepos, hasReadyRepo),
    },
    {
      key: 'archive',
      label: 'Archive',
      state: resolveArchiveState(task),
      artifact: 'archive cleanup',
      detail: archiveDetail(task),
    },
  ]
}

function resolveRefineState(task: TaskRecord): WorkflowNodeState {
  if (task.status === 'initialized') {
    return 'current'
  }
  return 'done'
}

function resolveDesignState(task: TaskRecord, hasDesign: boolean): WorkflowNodeState {
  if (hasDesign) {
    return 'done'
  }
  if (task.status === 'planning') {
    return 'current'
  }
  if (task.status === 'failed' && !hasDesign) {
    return 'failed'
  }
  if (task.status === 'initialized' || task.status === 'refined') {
    return 'pending'
  }
  return 'pending'
}

function resolvePlanState(task: TaskRecord, hasPlan: boolean): WorkflowNodeState {
  if (hasPlan && task.status !== 'planning') {
    return 'done'
  }
  if (task.status === 'planning') {
    return 'current'
  }
  if (task.status === 'failed' && !hasPlan) {
    return 'failed'
  }
  if (task.status === 'initialized' || task.status === 'refined') {
    return 'pending'
  }
  return hasPlan ? 'done' : 'pending'
}

function resolveCodeState(task: TaskRecord, hasPlan: boolean, hasBlockedRepo: boolean, hasReadyRepo: boolean): WorkflowNodeState {
  if (task.status === 'coded' || task.status === 'archived') {
    return 'done'
  }
  if (!hasPlan) {
    return 'pending'
  }
  if ((task.status === 'planned' || task.status === 'failed') && hasBlockedRepo && !hasReadyRepo) {
    return 'blocked'
  }
  if (task.status === 'failed') {
    return 'failed'
  }
  if (task.status === 'planned' || task.status === 'coding' || task.status === 'partially_coded') {
    return 'current'
  }
  return 'pending'
}

function resolveArchiveState(task: TaskRecord): WorkflowNodeState {
  if (task.status === 'archived') {
    return 'done'
  }
  if (task.status === 'coded') {
    return 'current'
  }
  return 'pending'
}

function inputDetail(task: TaskRecord) {
  if (task.sourceType === 'lark_doc') {
    return '需求来自飞书文档，先确保源正文可用。'
  }
  return '需求输入已进入任务系统，可继续进入 refine。'
}

function refineDetail(task: TaskRecord) {
  if (task.status === 'initialized') {
    return isPendingRefineTask(task) ? '正文尚未拉取成功，当前仍停在 refine 前置准备。' : '正在整理需求，生成 refined PRD。'
  }
  return '已形成面向研发的 refined PRD。'
}

function designDetail(task: TaskRecord, hasDesign: boolean) {
  if (hasDesign) {
    return 'design.md 已生成，系统改造点和方案设计可直接阅读。'
  }
  if (task.status === 'planning') {
    return '正在生成设计稿，重点会落到系统改造点与方案设计。'
  }
  if (task.status === 'failed') {
    return '设计阶段中断，建议先查看 plan.log。'
  }
  return '等待进入设计阶段。'
}

function planDetail(task: TaskRecord, hasPlan: boolean) {
  if (hasPlan && task.status !== 'planning') {
    return 'plan.md 已生成，任务拆分和执行顺序已经可见。'
  }
  if (task.status === 'planning') {
    return '正在生成执行计划和任务拆分。'
  }
  if (task.status === 'failed') {
    return '计划阶段中断，建议先查看 plan.log。'
  }
  return '等待 design 完成后进入 plan。'
}

function codeDetail(task: TaskRecord, blockedRepos: string[], hasReadyRepo: boolean) {
  if (task.status === 'coded' || task.status === 'archived') {
    return '代码产物已生成完毕，可以转向收尾或归档。'
  }
  if ((task.status === 'planned' || task.status === 'failed') && blockedRepos.length > 0 && !hasReadyRepo) {
    return `当前 code 受依赖阻塞：${blockedRepos.join(', ')}。`
  }
  if (task.status === 'coding') {
    return task.codeProgress.summary || '至少一个 repo 正在执行 code，日志和结果会持续更新。'
  }
  if (task.status === 'partially_coded') {
    return task.codeProgress.summary || '已有部分 repo 完成，可继续推进剩余 repo。'
  }
  if (task.status === 'failed') {
    return task.codeProgress.summary || '当前存在失败 repo，建议先看 code.log / code-result.json。'
  }
  if (task.status === 'planned') {
    return task.codeProgress.runnableRepoIds.length > 0 ? `当前可优先推进 repo：${task.codeProgress.runnableRepoIds.join(', ')}` : task.codeProgress.summary || '方案已就绪，可进入 code。'
  }
  return '等待进入 code 阶段。'
}

function archiveDetail(task: TaskRecord) {
  if (task.status === 'archived') {
    return '任务已经归档，工作区和结果已进入收尾状态。'
  }
  if (task.status === 'coded') {
    return '代码结果已经齐备，当前可进入归档收尾。'
  }
  return '当前尚未进入归档阶段。'
}

function hasActionableArtifact(content?: string) {
  if (!content) {
    return false
  }
  return !content.includes('当前没有') && !content.includes('当前为空')
}

function isPendingRefineTask(task: TaskRecord) {
  return task.status === 'initialized' && task.sourceType === 'lark_doc' && task.artifacts['prd-refined.md']?.includes('状态：待补充源内容')
}

function toneClass(state: WorkflowNodeState) {
  switch (state) {
    case 'done':
      return 'border-[#cfe2d2] bg-[#f3f7f1] text-[#35533d] dark:border-[#35533d] dark:bg-[#1f2a22] dark:text-[#d4ead7]'
    case 'current':
      return 'border-[#c8d8e7] bg-[#f2f7fb] text-[#2f5571] dark:border-[#35506a] dark:bg-[#1f2830] dark:text-[#cfe6fb]'
    case 'failed':
      return 'border-[#e1c1bf] bg-[#fbf1f0] text-[#8f3732] dark:border-[#6a3431] dark:bg-[#2b1f1f] dark:text-[#f5d3d1]'
    case 'blocked':
      return 'border-[#d9c9a7] bg-[#fff7e8] text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]'
    default:
      return 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]'
  }
}

function bulletTone(state: WorkflowNodeState) {
  switch (state) {
    case 'done':
      return 'border-[#8fb396] bg-[#e7f2ea]'
    case 'current':
      return 'border-[#7eaad0] bg-[#e3f1fd]'
    case 'failed':
      return 'border-[#d6948f] bg-[#f9e1df]'
    case 'blocked':
      return 'border-[#cfb56f] bg-[#fff0c9]'
    default:
      return 'border-[#d1cfc5] bg-[#f5f4ed]'
  }
}

function bulletSymbol(state: WorkflowNodeState) {
  switch (state) {
    case 'done':
      return '✓'
    case 'current':
      return '•'
    case 'failed':
      return '!'
    case 'blocked':
      return '⏸'
    default:
      return '·'
  }
}
