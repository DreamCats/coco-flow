import type { TaskRecord } from '../../../api'
import { updateTaskArtifact } from '../../../api'
import { useMemo, useState } from 'react'
import { hasArtifact } from '../model'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, ArtifactPanel, SectionCard, TabButton } from '../ui'

type PlanTab = 'artifact' | 'log' | 'graph'
type PlanEditingTab = 'artifact' | null
type PlanProgressStep = {
  label: string
  done: boolean
  current: boolean
}

export function PlanStage({ task, onTaskUpdated }: { task: TaskRecord; onTaskUpdated: () => Promise<void> | void }) {
  const [tab, setTab] = useState<PlanTab>('artifact')
  const [editingTab, setEditingTab] = useState<PlanEditingTab>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const steps = useMemo(() => buildPlanProgress(task), [task])
  const progressPercent = useMemo(() => buildPlanProgressPercent(task, steps), [task, steps])
  const activeLabel = steps.find((step) => step.current)?.label ?? (task.status === 'planned' ? '计划完成' : '等待开始')
  const progressTone =
    task.status === 'planning'
      ? 'bg-[#4fa06d]'
      : task.status === 'planned'
        ? 'bg-[#2c8c58]'
        : 'bg-[#cdbda6] dark:bg-[#4a4640]'
  const graphContent = useMemo(() => buildPlanGraph(task), [task])
  const planMarkdown = task.artifacts['plan.md'] || ''
  const logContent = task.artifacts['plan.log'] || task.nextAction || '当前没有 plan 过程日志。'
  const currentValue = planMarkdown
  const canSave = draft.trim().length > 0 && draft.trim() !== currentValue.trim()

  function openEditor(nextTab: Exclude<PlanEditingTab, null>) {
    setDraft(planMarkdown)
    setSaveError('')
    setEditingTab(nextTab)
  }

  async function handleSave() {
    if (!editingTab) {
      return
    }
    try {
      setSaving(true)
      setSaveError('')
      await updateTaskArtifact(task.id, editArtifactName(), draft)
      await onTaskUpdated()
      setEditingTab(null)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <SectionCard title="阶段详情">
        <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Plan Progress</div>
              <div className="mt-2 text-sm text-[#5e5d59] dark:text-[#b0aea5]">{activeLabel}</div>
            </div>
            <div className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
              {progressPercent}%
            </div>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#efeae0] dark:bg-[#232220]">
            <div className={`h-full rounded-full transition-all duration-300 ${progressTone}`} style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-6">
            {steps.map((step) => (
              <div
                className={`rounded-[14px] border px-3 py-2 text-xs ${
                  step.done
                    ? 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]'
                    : step.current
                      ? 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]'
                      : 'border-[#e8e6dc] bg-[#f5f4ed] text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#8f8a82]'
                }`}
                key={step.label}
              >
                {step.label}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex flex-wrap rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
            <TabButton active={tab === 'artifact'} onClick={() => setTab('artifact')}>
              Plan 原文
            </TabButton>
            <TabButton active={tab === 'log'} onClick={() => setTab('log')}>
              过程日志
            </TabButton>
            <TabButton active={tab === 'graph'} onClick={() => setTab('graph')}>
              关系图
            </TabButton>
          </div>
          <div className="flex flex-wrap gap-2">
            <ActionButton onClick={() => openEditor('artifact')} tone="secondary">
              编辑计划
            </ActionButton>
          </div>
        </div>
        <div className="mt-4">
          {tab === 'artifact' ? <ArtifactPanel content={planMarkdown} title="plan.md" /> : null}
          {tab === 'log' ? <ArtifactPanel content={logContent} renderAs="plain" title="plan.log" /> : null}
          {tab === 'graph' ? <ArtifactPanel content={graphContent} renderAs="plain" title="执行关系" /> : null}
        </div>
      </SectionCard>

      <TaskStageEditorModal
        busy={saving}
        canSave={canSave}
        description={editDescription()}
        error={saveError}
        hint={editHint()}
        monospace={editingTab === 'artifact' || editingTab === 'design'}
        onChange={setDraft}
        onClose={() => (!saving ? setEditingTab(null) : undefined)}
        onSave={() => void handleSave()}
        open={editingTab !== null}
        placeholder={editPlaceholder()}
        title={editTitle()}
        value={draft}
      />
    </>
  )
}

function buildPlanGraph(task: TaskRecord) {
  const graphArtifact = task.artifacts['plan-execution-graph.json'] || ''
  const workItemsArtifact = task.artifacts['plan-work-items.json'] || ''
  const graphSummary = parsePlanGraphArtifact(graphArtifact)
  if (graphSummary) {
    return graphSummary
  }
  const workItemSummary = parsePlanWorkItemsArtifact(workItemsArtifact)
  if (workItemSummary) {
    return workItemSummary
  }
  const repos = task.repos.map((repo) => repo.displayName)
  if (repos.length === 0) {
    return '当前没有仓库绑定，后续计划会在绑定仓库后补齐关系图。'
  }
  if (repos.length === 1) {
    return `${repos[0]}\n  ↓\n验证与收口`
  }
  return repos.map((repo, index) => (index === repos.length - 1 ? repo : `${repo}\n  ↓`)).join('\n')
}

function buildPlanProgress(task: TaskRecord): PlanProgressStep[] {
  const log = task.artifacts['plan.log'] || ''
  const skillsBriefArtifact = task.artifacts['plan-skills-brief.md'] || task.artifacts['plan-knowledge-brief.md'] || ''
  const hasStarted = task.status === 'planning' || task.status === 'planned' || log.includes('=== PLAN START ===')
  const hasKnowledge = hasArtifact(skillsBriefArtifact) || log.includes('plan_skills_ok:') || log.includes('plan_knowledge_ok:')
  const hasOutline = hasArtifact(task.artifacts['plan-task-outline.json']) || hasArtifact(task.artifacts['plan-work-items.json']) || log.includes('plan_task_outline_ok:')
  const hasGraph = hasArtifact(task.artifacts['plan-execution-graph.json']) || log.includes('plan_graph_ok:')
  const hasValidation = hasArtifact(task.artifacts['plan-validation.json']) || log.includes('plan_validation_ok:')
  const hasDraft = hasArtifact(task.artifacts['plan.md']) || log.includes('plan_generate_ok:')
  const hasVerified = hasArtifact(task.artifacts['plan-verify.json']) || task.status === 'planned' || log.includes('plan_verify_ok:')

  if (task.status === 'planned') {
    return [
      { label: '继承 Skills', done: true, current: false },
      { label: '拆分任务', done: true, current: false },
      { label: '关系建图', done: true, current: false },
      { label: '验证收敛', done: true, current: false },
      { label: '生成成稿', done: true, current: false },
      { label: '完成校验', done: true, current: false },
    ]
  }

  if (task.status !== 'planning') {
    return [
      { label: '继承 Skills', done: false, current: false },
      { label: '拆分任务', done: false, current: false },
      { label: '关系建图', done: false, current: false },
      { label: '验证收敛', done: false, current: false },
      { label: '生成成稿', done: false, current: false },
      { label: '完成校验', done: false, current: false },
    ]
  }

  const currentStep = !hasStarted
    ? '继承 Skills'
    : !hasKnowledge
      ? '继承 Skills'
      : !hasOutline
        ? '拆分任务'
        : !hasGraph
          ? '关系建图'
          : !hasValidation
            ? '验证收敛'
            : !hasDraft
              ? '生成成稿'
              : !hasVerified
                ? '完成校验'
                : '完成校验'

  return [
    { label: '继承 Skills', done: hasKnowledge, current: currentStep === '继承 Skills' },
    { label: '拆分任务', done: hasOutline, current: currentStep === '拆分任务' },
    { label: '关系建图', done: hasGraph, current: currentStep === '关系建图' },
    { label: '验证收敛', done: hasValidation, current: currentStep === '验证收敛' },
    { label: '生成成稿', done: hasDraft, current: currentStep === '生成成稿' },
    { label: '完成校验', done: hasVerified, current: currentStep === '完成校验' },
  ]
}

function buildPlanProgressPercent(task: TaskRecord, steps: PlanProgressStep[]) {
  if (task.status === 'planned') {
    return 100
  }
  if (task.status !== 'planning') {
    return 0
  }
  const completedUnits = steps.filter((step) => step.done).length
  const currentUnits = steps.some((step) => step.current) ? 0.45 : 0
  return Math.max(8, Math.round(((completedUnits + currentUnits) / steps.length) * 100))
}

function parsePlanGraphArtifact(content: string) {
  if (!content.trim()) {
    return ''
  }
  try {
    const payload = JSON.parse(content) as {
      execution_order?: string[]
      parallel_groups?: string[][]
      coordination_points?: string[]
    }
    const lines: string[] = []
    if (Array.isArray(payload.execution_order) && payload.execution_order.length > 0) {
      lines.push(`- execution_order: ${payload.execution_order.join(' -> ')}`)
    }
    if (Array.isArray(payload.parallel_groups) && payload.parallel_groups.length > 0) {
      lines.push('- parallel_groups:')
      for (const group of payload.parallel_groups) {
        if (Array.isArray(group) && group.length > 0) {
          lines.push(`  - ${group.join(', ')}`)
        }
      }
    }
    if (Array.isArray(payload.coordination_points) && payload.coordination_points.length > 0) {
      lines.push('- coordination_points:')
      for (const item of payload.coordination_points) {
        lines.push(`  - ${item}`)
      }
    }
    return lines.join('\n')
  } catch {
    return ''
  }
}

function parsePlanWorkItemsArtifact(content: string) {
  if (!content.trim()) {
    return ''
  }
  try {
    const payload = JSON.parse(content) as { work_items?: Array<{ id?: string; repo_id?: string; title?: string; depends_on?: string[] }> }
    if (!Array.isArray(payload.work_items) || payload.work_items.length === 0) {
      return ''
    }
    const lines: string[] = []
    for (const item of payload.work_items.slice(0, 8)) {
      const title = [item.id, item.repo_id, item.title].filter(Boolean).join(' ')
      if (title) {
        lines.push(`- ${title}`)
      }
      if (Array.isArray(item.depends_on) && item.depends_on.length > 0) {
        lines.push(`  depends_on: ${item.depends_on.join(', ')}`)
      }
    }
    return lines.join('\n')
  } catch {
    return ''
  }
}

function editArtifactName() {
  return 'plan.md' as const
}

function editTitle() {
  return '编辑 Plan 原文'
}

function editDescription() {
  return '这里编辑 Plan 阶段生成的执行方案原文。'
}

function editHint() {
  return '保存后会覆盖 plan.md；当前不会自动回写结构化 Plan artifact。'
}

function editPlaceholder() {
  return '请输入 Plan 文档...'
}
