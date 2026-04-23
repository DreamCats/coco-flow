import type { TaskRecord } from '../../../api'
import { updateTaskArtifact } from '../../../api'
import { useMemo, useState } from 'react'
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

export function DesignStage({ task, onTaskUpdated }: { task: TaskRecord; onTaskUpdated: () => Promise<void> | void }) {
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
    (task.repos.length > 0 ? `已绑定仓库：${task.repos.map((repo) => repo.displayName).join('、')}` : '当前还没有绑定仓库。后续会补一版正式的仓库绑定服务。')
  const currentDesign = task.artifacts['design.md'] || ''
  const currentValue = editingTab === 'artifact' ? currentDesign : task.artifacts['design.notes.md'] || ''
  const canSave = editingTab === 'artifact' ? draft.trim().length > 0 && draft.trim() !== currentValue.trim() : draft.trim() !== currentValue.trim()

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
                {task.repos.length > 0 ? '调整仓库' : '绑定仓库（可选）'}
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

function buildDesignProgress(task: TaskRecord): DesignProgressStep[] {
  const log = task.artifacts['design.log'] || ''
  const designSkillsBriefArtifact = task.artifacts['design-skills-brief.md'] || ''
  const refineSkillsReadArtifact = task.artifacts['refine-skills-read.md'] || ''
  const hasStarted = task.status === 'designing' || task.status === 'designed' || log.includes('=== DESIGN START ===')
  const hasKnowledge =
    hasArtifact(designSkillsBriefArtifact) ||
    hasArtifact(refineSkillsReadArtifact) ||
    log.includes('design_skills_ok:') ||
    log.includes('repo_research_prefilter_candidates:')
  const hasResearch =
    hasArtifact(task.artifacts['design-research.json']) ||
    log.includes('repo_research_prefilter_candidates:') ||
    log.includes('repo_research_agent_ok:') ||
    log.includes('repo_research_agent_fallback:')
  const hasBinding = hasArtifact(task.artifacts['design-repo-binding.json']) || log.includes('design_repo_binding: true')
  const hasDraft =
    hasArtifact(task.artifacts['design.md']) ||
    hasArtifact(task.artifacts['design-sections.json']) ||
    log.includes('design_sections: true') ||
    log.includes('native_design_fallback:')
  const hasVerified = hasArtifact(task.artifacts['design-verify.json']) || task.status === 'designed' || log.includes('status: designed')

  if (task.status === 'designed') {
    return [
      { label: '继承 Skills', done: true, current: false },
      { label: '仓库探索', done: true, current: false },
      { label: 'Repo Binding', done: true, current: false },
      { label: '生成成稿', done: true, current: false },
      { label: '完成校验', done: true, current: false },
    ]
  }

  if (task.status !== 'designing') {
    return [
      { label: '继承 Skills', done: false, current: false },
      { label: '仓库探索', done: false, current: false },
      { label: 'Repo Binding', done: false, current: false },
      { label: '生成成稿', done: false, current: false },
      { label: '完成校验', done: false, current: false },
    ]
  }

  const currentStep = !hasStarted
    ? '继承 Skills'
    : !hasKnowledge
      ? '继承 Skills'
      : !hasResearch
        ? '仓库探索'
        : !hasBinding
          ? 'Repo Binding'
          : !hasDraft
            ? '生成成稿'
            : !hasVerified
              ? '完成校验'
              : '完成校验'

  return [
    { label: '继承 Skills', done: hasKnowledge, current: currentStep === '继承 Skills' },
    { label: '仓库探索', done: hasResearch, current: currentStep === '仓库探索' },
    { label: 'Repo Binding', done: hasBinding, current: currentStep === 'Repo Binding' },
    { label: '生成成稿', done: hasDraft, current: currentStep === '生成成稿' },
    { label: '完成校验', done: hasVerified, current: currentStep === '完成校验' },
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
