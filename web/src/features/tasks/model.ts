import type { RepoResult, TaskRecord, TaskStatus } from '../../api'

export type TaskStageID = 'input' | 'refine' | 'design' | 'plan' | 'code' | 'archive'
export type TaskStageStatus = 'todo' | 'active' | 'done' | 'blocked'

export type TaskStage = {
  id: TaskStageID
  label: string
  status: TaskStageStatus
  summary: string
}

export const stageOrder: TaskStageID[] = ['input', 'refine', 'design', 'plan', 'code', 'archive']

export function buildTaskStages(task: TaskRecord): TaskStage[] {
  const inputReady = isInputReady(task)
  const inputBlocked = task.status === 'input_processing' || task.status === 'input_failed'
  const hasRefined = hasArtifact(task.artifacts['prd-refined.md']) && !isPendingRefineTask(task)
  const hasDesign = hasArtifact(task.artifacts['design.md'])
  const hasPlan = hasArtifact(task.artifacts['plan.md'])
  const hasRepoBinding = task.repos.length > 0
  const hasCodeOutput = hasCodeActivity(task)

  return [
    {
      id: 'input',
      label: 'Input',
      status: inputBlocked ? 'active' : inputReady ? 'done' : 'active',
      summary: task.status === 'input_processing' ? '正在解析飞书文档并生成标准输入稿。' : task.status === 'input_failed' ? '输入处理失败，请检查链接、权限或手动补充正文。' : '收集 PRD 原文、飞书文档链接和研发补充说明。',
    },
    {
      id: 'refine',
      label: 'Refine',
      status: !inputReady ? 'todo' : hasRefined ? (hasDesign || hasPlan || hasCodeOutput ? 'done' : 'active') : 'active',
      summary: task.status === 'refining' ? '正在提炼核心诉求、风险、讨论点和边界。' : '提炼核心诉求、风险、讨论点和边界。',
    },
    {
      id: 'design',
      label: 'Design',
      status: !hasRefined ? 'todo' : !hasRepoBinding ? 'blocked' : hasDesign ? 'done' : task.status === 'planning' ? 'active' : 'active',
      summary: hasRepoBinding ? '绑定仓库后补齐代码调研和方案设计。' : '进入设计前需要先绑定仓库。',
    },
    {
      id: 'plan',
      label: 'Plan',
      status: !hasRefined ? 'todo' : !hasRepoBinding ? 'blocked' : hasPlan ? (hasCodeOutput ? 'done' : 'active') : task.status === 'planning' ? 'active' : 'todo',
      summary: '形成执行拆解、依赖顺序和验证方案。',
    },
    {
      id: 'code',
      label: 'Code',
      status: !hasPlan ? 'todo' : !hasRepoBinding ? 'blocked' : resolveCodeStageStatus(task),
      summary: '按仓推进实现与验证。',
    },
    {
      id: 'archive',
      label: 'Archive',
      status: task.status === 'archived' ? 'done' : task.status === 'coded' ? 'active' : 'todo',
      summary: '沉淀结果、验证结论与后续事项。',
    },
  ]
}

export function defaultStageForTask(task: TaskRecord): TaskStageID {
  const active = buildTaskStages(task).find((stage) => stage.status === 'active')
  return active?.id ?? 'input'
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
  return new Set(['input_ready', 'refining', 'refined', 'planning', 'planned', 'coding', 'partially_coded', 'coded', 'archived', 'failed']).has(task.status)
}

export function stageStatusLabel(status: TaskStageStatus) {
  switch (status) {
    case 'done':
      return 'done'
    case 'active':
      return 'active'
    case 'blocked':
      return 'blocked'
    default:
      return 'todo'
  }
}

export function stageTone(status: TaskStageStatus) {
  switch (status) {
    case 'done':
      return 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]'
    case 'active':
      return 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]'
    case 'blocked':
      return 'border-[#efbbb6] bg-[#ffe7e4] text-[#9f3d34] dark:border-[#75423f] dark:bg-[#3a1f1d] dark:text-[#f5b6b0]'
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

function hasCodeActivity(task: TaskRecord) {
  return task.status === 'coding' || task.status === 'partially_coded' || task.status === 'coded' || task.status === 'archived' || task.status === 'failed'
}

function resolveCodeStageStatus(task: TaskRecord): TaskStageStatus {
  if (task.status === 'coded' || task.status === 'archived') {
    return 'done'
  }
  if (task.status === 'coding' || task.status === 'partially_coded' || task.status === 'failed') {
    return 'active'
  }
  return 'todo'
}
