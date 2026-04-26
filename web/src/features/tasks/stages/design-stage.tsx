import type { TaskRecord } from '../../../api'
import { updateTaskArtifact } from '../../../api'
import { useEffect, useMemo, useState } from 'react'
import { hasArtifact } from '../model'
import { TaskRepoBindingModal } from '../task-repo-binding-modal'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

type DesignTab = 'artifact' | 'notes' | 'log'
type DesignProgressStep = {
  label: string
  done: boolean
  current: boolean
}

const DESIGN_PROGRESS_LABELS = ['准备输入', '选择 Skills', '仓库调研', '生成设计', '完成设计'] as const
type DesignProgressLabel = (typeof DESIGN_PROGRESS_LABELS)[number]

export function DesignStage({
  task,
  onTaskUpdated,
  openRepoBindingToken = 0,
}: {
  task: TaskRecord
  onTaskUpdated: () => Promise<void> | void
  openRepoBindingToken?: number
}) {
  const [tab, setTab] = useState<DesignTab>('artifact')
  const [editingTab, setEditingTab] = useState<'artifact' | 'notes' | null>(null)
  const [bindingRepos, setBindingRepos] = useState(false)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const steps = useMemo(() => buildDesignProgress(task), [task])
  const progressPercent = useMemo(() => buildDesignProgressPercent(task, steps), [task, steps])
  const activeLabel = steps.find((step) => step.current)?.label ?? (task.status === 'designed' ? '设计完成' : '等待开始')
  const progressTone =
    task.status === 'designing'
      ? 'bg-[#4fa06d]'
      : task.status === 'designed'
        ? 'bg-[#2c8c58]'
        : 'bg-[#cdbda6] dark:bg-[#4a4640]'
  const notes =
    task.artifacts['design.notes.md'] ||
    (task.repos.length > 0 ? `已绑定仓库：${task.repos.map((repo) => repo.displayName).join('、')}` : '当前还没有绑定仓库。生成设计前请先绑定相关仓库。')
  const currentDesign = task.artifacts['design.md'] || ''
  const currentValue = editingTab === 'artifact' ? currentDesign : task.artifacts['design.notes.md'] || ''
  const canSave = editingTab === 'artifact' ? draft.trim().length > 0 && draft.trim() !== currentValue.trim() : draft.trim() !== currentValue.trim()
  const blocker = buildDesignBlocker(task)

  useEffect(() => {
    if (openRepoBindingToken > 0) {
      setBindingRepos(true)
    }
  }, [openRepoBindingToken])

  function openEditor(nextTab: 'artifact' | 'notes') {
    setDraft(nextTab === 'artifact' ? currentDesign : task.artifacts['design.notes.md'] || '')
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
      await updateTaskArtifact(task.id, editingTab === 'artifact' ? 'design.md' : 'design.notes.md', draft)
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
        {blocker ? (
          <div className="mb-4 rounded-[14px] border border-[#e7bf7a] bg-[#fff6e6] px-4 py-3 text-sm leading-6 text-[#75510d] dark:border-[#6b5428] dark:bg-[#2d2416] dark:text-[#f0d59b]">
            <div className="font-medium text-[#5f430d] dark:text-[#f5dfad]">{blocker.title}</div>
            <div className="mt-1">{blocker.body}</div>
            {blocker.action ? <div className="mt-2 text-xs text-[#8a6826] dark:text-[#d5bb83]">{blocker.action}</div> : null}
          </div>
        ) : null}
        <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Design Progress</div>
              <div className="mt-2 text-sm text-[#5e5d59] dark:text-[#b0aea5]">{activeLabel}</div>
            </div>
            <div className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
              {progressPercent}%
            </div>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#efeae0] dark:bg-[#232220]">
            <div
              className={`h-full rounded-full transition-all duration-300 ${progressTone}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-5">
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
          <div className="inline-flex rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
            <TabButton active={tab === 'artifact'} onClick={() => setTab('artifact')}>
              产物与查看
            </TabButton>
            <TabButton active={tab === 'notes'} onClick={() => setTab('notes')}>
              补充说明
            </TabButton>
            <TabButton active={tab === 'log'} onClick={() => setTab('log')}>
              过程日志
            </TabButton>
          </div>
          {tab !== 'log' ? (
            <div className="flex flex-wrap gap-2">
              <ActionButton onClick={() => setBindingRepos(true)} tone="secondary">
                {task.repos.length > 0 ? '调整仓库' : '绑定仓库'}
              </ActionButton>
              <ActionButton onClick={() => openEditor(tab === 'artifact' ? 'artifact' : 'notes')} tone="secondary">
                {tab === 'artifact' ? '编辑原文' : '编辑补充'}
              </ActionButton>
            </div>
          ) : null}
        </div>
        <div className="mt-4">
          {tab === 'artifact' ? (
            <ArtifactPanel content={currentDesign} title="design.md" />
          ) : tab === 'log' ? (
            <ArtifactPanel content={task.artifacts['design.log'] || task.nextAction || '当前没有 design 过程日志。'} renderAs="plain" title="design.log" />
          ) : (
            <NotePanel content={notes} />
          )}
        </div>
      </SectionCard>

      <TaskStageEditorModal
        busy={saving}
        canSave={canSave}
        description={editingTab === 'artifact' ? '这里编辑 Design 阶段生成的设计文档原文。' : '这里记录人工补充说明、设计取舍或后续提醒。'}
        error={saveError}
        hint={editingTab === 'artifact' ? '保存后会覆盖 design.md，并把任务状态回落到 designed。' : '这里是 Design 阶段的人工补充说明区，不会覆盖 design.log。'}
        monospace={editingTab === 'artifact'}
        onChange={setDraft}
        onClose={() => (!saving ? setEditingTab(null) : undefined)}
        onSave={() => void handleSave()}
        open={editingTab !== null}
        placeholder={editingTab === 'artifact' ? '请输入 Design 文档...' : '请输入 Design 补充说明...'}
        title={editingTab === 'artifact' ? '编辑 Design 原文' : '编辑 Design 补充说明'}
        value={draft}
      />
      <TaskRepoBindingModal
        onClose={() => setBindingRepos(false)}
        onUpdated={onTaskUpdated}
        open={bindingRepos}
        task={task}
      />
    </>
  )
}

function buildDesignBlocker(task: TaskRecord): { title: string; body: string; action: string } | null {
  const diagnosis = task.diagnosis
  if (!diagnosis || diagnosis.stage !== 'design' || diagnosis.ok) {
    return null
  }
  const severity = diagnosis.severity || ''
  const blocked = severity === 'needs_human' || severity === 'degraded' || task.status === 'failed'
  if (!blocked) {
    return null
  }
  const reason = diagnosis.reason || 'Design 阶段需要人工确认后才能继续。'
  const issueText = diagnosis.issueCount > 0 ? `共发现 ${diagnosis.issueCount} 个问题。` : ''
  return {
    title: severity === 'degraded' ? 'Design 产物需要人工确认' : 'Design 已被阻断',
    body: [issueText, reason].filter(Boolean).join(' '),
    action: task.nextAction || '请查看 design-diagnosis.json 和 design-decision.json，确认后重新执行 Design。',
  }
}

function buildDesignProgress(task: TaskRecord): DesignProgressStep[] {
  const log = task.artifacts['design.log'] || ''
  const designInputArtifact = task.artifacts['design-input.json'] || ''
  const refineSkillsReadArtifact = task.artifacts['refine-skills-read.md'] || ''
  const hasStarted = task.status === 'designing' || task.status === 'designed' || log.includes('=== DESIGN START ===')
  const hasPrepared =
    hasArtifact(designInputArtifact) ||
    log.includes('design_prepare_ok:') ||
    log.includes('design_v3_prepare_ok:')
  const hasSkills =
    hasArtifact(designInputArtifact) ||
    hasArtifact(refineSkillsReadArtifact) ||
    log.includes('design_skills_ok:') ||
    log.includes('design_v3_prepare_ok:')
  const hasResearch =
    hasArtifact(task.artifacts['design-research-summary.json']) ||
    hasArtifact(task.artifacts['design-research-plan.json']) ||
    log.includes('design_research_ok:') ||
    log.includes('design_v3_repo_research_ok:')
  const hasDraft =
    hasArtifact(task.artifacts['design.md']) ||
    hasArtifact(task.artifacts['design-sections.json']) ||
    log.includes('design_writer_ok:') ||
    log.includes('design_v3_writer_ok:')
  const hasFinished =
    hasArtifact(task.artifacts['design-verify.json']) ||
    task.status === 'designed' ||
    log.includes('status: designed') ||
    log.includes('design_v3_gate_ok:')

  if (task.status === 'designed') {
    return DESIGN_PROGRESS_LABELS.map((label) => ({ label, done: true, current: false }))
  }

  if (task.status !== 'designing') {
    return DESIGN_PROGRESS_LABELS.map((label) => ({ label, done: false, current: false }))
  }

  const currentStep: DesignProgressLabel = !hasStarted
    ? '准备输入'
    : !hasPrepared
      ? '准备输入'
      : !hasSkills
        ? '选择 Skills'
      : !hasResearch
        ? '仓库调研'
        : !hasDraft
          ? '生成设计'
          : !hasFinished
            ? '完成设计'
            : '完成设计'

  return [
    { label: '准备输入', done: hasPrepared, current: currentStep === '准备输入' },
    { label: '选择 Skills', done: hasSkills, current: currentStep === '选择 Skills' },
    { label: '仓库调研', done: hasResearch, current: currentStep === '仓库调研' },
    { label: '生成设计', done: hasDraft, current: currentStep === '生成设计' },
    { label: '完成设计', done: hasFinished, current: currentStep === '完成设计' },
  ]
}

function buildDesignProgressPercent(task: TaskRecord, steps: DesignProgressStep[]) {
  if (task.status === 'designed') {
    return 100
  }
  if (task.status !== 'designing') {
    return 0
  }
  const completedUnits = steps.filter((step) => step.done).length
  const currentUnits = steps.some((step) => step.current) ? 0.45 : 0
  return Math.max(8, Math.round(((completedUnits + currentUnits) / steps.length) * 100))
}
