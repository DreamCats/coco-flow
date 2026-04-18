import type { RepoResult, TaskRecord, TaskStatus, TaskTimelineItem } from '../../api'

export type TaskStageID = 'input' | 'refine' | 'design' | 'plan' | 'code' | 'archive'
export type TaskStageStatus = TaskTimelineItem['state']

export type TaskStage = {
  id: TaskStageID
  label: string
  status: TaskStageStatus
  summary: string
}

export const stageOrder: TaskStageID[] = ['input', 'refine', 'design', 'plan', 'code', 'archive']

export function buildTaskStages(task: TaskRecord): TaskStage[] {
  const fallbackStages = buildFallbackTaskStages(task)
  const timelineByStage = new Map<TaskStageID, TaskTimelineItem>()
  for (const item of task.timeline) {
    const stageID = mapTimelineLabelToStageID(item.label)
    if (stageID) {
      timelineByStage.set(stageID, item)
    }
  }

  return stageOrder.map((stageID) => {
    const fallback = fallbackStages.find((stage) => stage.id === stageID)!
    const timelineItem = timelineByStage.get(stageID)
    return {
      ...fallback,
      status: timelineItem?.state ?? fallback.status,
      summary: timelineItem?.detail?.trim() || fallback.summary,
    }
  })
}

export function getTaskStage(task: TaskRecord, stageID: TaskStageID): TaskStage {
  return buildTaskStages(task).find((stage) => stage.id === stageID) ?? buildFallbackTaskStages(task).find((stage) => stage.id === stageID) ?? {
    id: stageID,
    label: stageID[0]!.toUpperCase() + stageID.slice(1),
    status: 'pending',
    summary: '',
  }
}

function buildFallbackTaskStages(task: TaskRecord): TaskStage[] {
  const inputReady = isInputReady(task)
  const hasRefined = hasArtifact(task.artifacts['prd-refined.md']) && !isPendingRefineTask(task)
  const hasDesign = hasArtifact(task.artifacts['design.md'])
  const hasPlan = hasArtifact(task.artifacts['plan.md'])
  const hasRepoBinding = task.repos.length > 0

  return [
    {
      id: 'input',
      label: 'Input',
      status: task.status === 'input_failed' ? 'failed' : task.status === 'input_processing' ? 'current' : inputReady ? 'done' : 'current',
      summary: task.status === 'input_processing' ? '正在解析飞书文档并生成标准输入稿。' : task.status === 'input_failed' ? '输入处理失败，请检查链接、权限或手动补充正文。' : '收集 PRD 原文、飞书文档链接和研发补充说明。',
    },
    {
      id: 'refine',
      label: 'Refine',
      status: !inputReady ? 'pending' : task.status === 'refining' ? 'current' : hasRefined ? 'done' : 'current',
      summary: task.status === 'refining' ? '正在提炼核心诉求、风险、讨论点和边界。' : '提炼核心诉求、风险、讨论点和边界。',
    },
    {
      id: 'design',
      label: 'Design',
      status: !hasRefined ? 'pending' : !hasRepoBinding ? 'blocked' : hasDesign ? 'done' : task.status === 'designing' ? 'current' : 'current',
      summary: hasRepoBinding ? '绑定仓库后补齐代码调研和方案设计。' : '进入设计前需要先绑定仓库。',
    },
    {
      id: 'plan',
      label: 'Plan',
      status: !hasRefined || !hasDesign ? 'pending' : !hasRepoBinding ? 'blocked' : hasPlan ? 'done' : task.status === 'planning' ? 'current' : 'current',
      summary: '形成执行拆解、依赖顺序和验证方案。',
    },
    {
      id: 'code',
      label: 'Code',
      status: !hasPlan ? 'pending' : !hasRepoBinding ? 'blocked' : resolveCodeStageStatus(task),
      summary: '按仓推进实现与验证。',
    },
    {
      id: 'archive',
      label: 'Archive',
      status: task.status === 'archived' ? 'done' : task.status === 'coded' ? 'current' : 'pending',
      summary: '沉淀结果、验证结论与后续事项。',
    },
  ]
}

export function defaultStageForTask(task: TaskRecord): TaskStageID {
  const stages = buildTaskStages(task)
  return (
    stages.find((stage) => stage.status === 'current')?.id ??
    stages.find((stage) => stage.status === 'failed')?.id ??
    stages.find((stage) => stage.status === 'pending')?.id ??
    stages.find((stage) => stage.status === 'blocked')?.id ??
    'input'
  )
}

export function hasArtifact(content?: string) {
  if (!content) {
    return false
  }
  return !content.includes('当前没有') && !content.includes('当前为空')
}

export function isPendingRefineTask(task: TaskRecord) {
  return task.status === 'initialized' && task.sourceType === 'lark_doc' && task.artifacts['prd-refined.md']?.includes('状态：待补充源内容')
}

export function isInputReady(task: TaskRecord) {
  return new Set(['input_ready', 'refining', 'refined', 'designing', 'designed', 'planning', 'planned', 'coding', 'partially_coded', 'coded', 'archived', 'failed']).has(task.status)
}

export function stageStatusLabel(status: TaskStageStatus) {
  switch (status) {
    case 'done':
      return 'done'
    case 'current':
      return 'current'
    case 'blocked':
      return 'blocked'
    case 'failed':
      return 'failed'
    default:
      return 'pending'
  }
}

export function stageTone(status: TaskStageStatus) {
  switch (status) {
    case 'done':
      return 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]'
    case 'current':
      return 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]'
    case 'blocked':
      return 'border-[#efbbb6] bg-[#ffe7e4] text-[#9f3d34] dark:border-[#75423f] dark:bg-[#3a1f1d] dark:text-[#f5b6b0]'
    case 'failed':
      return 'border-[#e59696] bg-[#ffe3e3] text-[#a12b2b] dark:border-[#7d3c3c] dark:bg-[#3a1b1b] dark:text-[#ffb3b3]'
    default:
      return 'border-[#d7d2c8] bg-[#f2efe9] text-[#655d52] dark:border-[#4a4640] dark:bg-[#26231f] dark:text-[#d9d2c6]'
  }
}

export function taskStatusLabel(status: TaskStatus) {
  switch (status) {
    case 'initialized':
      return '待整理输入'
    case 'input_processing':
      return '输入处理中'
    case 'input_ready':
      return '待提炼'
    case 'input_failed':
      return '输入失败'
    case 'refining':
      return '提炼中'
    case 'refined':
      return '待设计'
    case 'designing':
      return '设计中'
    case 'designed':
      return '待计划'
    case 'planning':
      return '设计/计划生成中'
    case 'planned':
      return '待实现'
    case 'coding':
      return '实现中'
    case 'partially_coded':
      return '部分已完成'
    case 'coded':
      return '待归档'
    case 'archived':
      return '已归档'
    case 'failed':
      return '处理中断'
    default:
      return status
  }
}

export function truncateTaskTitle(title: string, maxChars = 18) {
  const normalized = title.trim()
  if (measureDisplayWidth(normalized) <= maxChars) {
    return normalized
  }
  const ellipsis = '...'
  const maxWidth = Math.max(0, maxChars - measureDisplayWidth(ellipsis))
  let currentWidth = 0
  let index = 0
  while (index < normalized.length) {
    const char = normalized[index]!
    const width = measureCharWidth(char)
    if (currentWidth + width > maxWidth) {
      break
    }
    currentWidth += width
    index += 1
  }
  return `${normalized.slice(0, index)}${ellipsis}`
}

function measureDisplayWidth(value: string) {
  let total = 0
  for (const char of value) {
    total += measureCharWidth(char)
  }
  return total
}

function measureCharWidth(char: string) {
  return /[\u2e80-\u9fff\uff00-\uffef]/.test(char) ? 1 : 0.5
}

export function repoReadyForCode(repo: RepoResult) {
  return repo.status === 'planned' || repo.status === 'failed'
}

export function preferredCodeRepo(task: TaskRecord): RepoResult | null {
  return task.repos.find(repoReadyForCode) ?? task.repos[0] ?? null
}

function resolveCodeStageStatus(task: TaskRecord): TaskStageStatus {
  if (task.status === 'coded' || task.status === 'archived') {
    return 'done'
  }
  if (task.status === 'failed') {
    return 'failed'
  }
  if (task.status === 'coding' || task.status === 'partially_coded') {
    return 'current'
  }
  if (task.status === 'planned') {
    return 'current'
  }
  return 'pending'
}

function mapTimelineLabelToStageID(label: string): TaskStageID | null {
  switch (label.trim().toLowerCase()) {
    case 'input':
      return 'input'
    case 'refine':
      return 'refine'
    case 'design':
      return 'design'
    case 'plan':
      return 'plan'
    case 'code':
      return 'code'
    case 'archive':
      return 'archive'
    default:
      return null
  }
}
