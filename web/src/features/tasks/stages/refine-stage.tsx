import type { TaskRecord } from '../../../api'
import { useMemo, useState } from 'react'
import { updateTaskArtifact } from '../../../api'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

type RefineTab = 'artifact' | 'notes' | 'log'
type RefineProgressStep = {
  label: string
  done: boolean
  current: boolean
}

export function RefineStage({ task, onTaskUpdated }: { task: TaskRecord; onTaskUpdated: () => Promise<void> | void }) {
  const [tab, setTab] = useState<RefineTab>('artifact')
  const [editingTab, setEditingTab] = useState<'artifact' | 'notes' | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')

  const steps = useMemo(() => buildRefineProgress(task), [task])
  const completedCount = steps.filter((step) => step.done).length
  const progressPercent = Math.max(8, Math.round((completedCount / steps.length) * 100))
  const activeLabel = steps.find((step) => step.current)?.label ?? (task.status === 'refined' ? '提炼完成' : '等待开始')
  const notesContent = task.artifacts['refine.notes.md'] || '当前没有额外补充说明。'
  const logContent = task.artifacts['refine.log'] || '当前没有 refine 日志。'
  const currentValue = editingTab === 'artifact' ? task.artifacts['prd-refined.md'] || '' : task.artifacts['refine.notes.md'] || ''
  const canSave = editingTab === 'artifact' ? draft.trim().length > 0 && draft.trim() !== currentValue.trim() : draft.trim() !== currentValue.trim()

  function openEditor(nextTab: 'artifact' | 'notes') {
    setEditingTab(nextTab)
    setDraft(nextTab === 'artifact' ? task.artifacts['prd-refined.md'] || '' : task.artifacts['refine.notes.md'] || '')
    setSaveError('')
  }

  async function handleSave() {
    if (!editingTab) {
      return
    }
    try {
      setSaving(true)
      setSaveError('')
      await updateTaskArtifact(task.id, editingTab === 'artifact' ? 'prd-refined.md' : 'refine.notes.md', draft)
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
              <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Refine Progress</div>
              <div className="mt-2 text-sm text-[#5e5d59] dark:text-[#b0aea5]">{activeLabel}</div>
            </div>
            <div className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
              {progressPercent}%
            </div>
          </div>
          <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#efeae0] dark:bg-[#232220]">
            <div
              className="h-full rounded-full bg-[#c96442] transition-all duration-300"
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
              日志
            </TabButton>
          </div>
          {tab !== 'log' ? (
            <ActionButton onClick={() => openEditor(tab === 'artifact' ? 'artifact' : 'notes')} tone="secondary">
              {tab === 'artifact' ? '编辑原文' : '编辑补充'}
            </ActionButton>
          ) : null}
        </div>

        <div className="mt-4">
          {tab === 'artifact' ? <ArtifactPanel content={task.artifacts['prd-refined.md'] || ''} title="prd-refined.md" /> : null}
          {tab === 'notes' ? <NotePanel content={notesContent} /> : null}
          {tab === 'log' ? <ArtifactPanel content={logContent} title="refine.log" /> : null}
        </div>
      </SectionCard>

      <TaskStageEditorModal
        busy={saving}
        canSave={canSave}
        description={editingTab === 'artifact' ? '这里编辑 Refine 阶段生成的精炼需求稿。' : '这里记录人工补充说明、对齐结论或后续提醒。'}
        error={saveError}
        hint={editingTab === 'artifact' ? '保存后会覆盖 prd-refined.md，并清理后续 design / plan 产物。' : '这里是人工介入说明区，不会直接覆盖 refine 日志。'}
        monospace={editingTab === 'artifact'}
        onChange={setDraft}
        onClose={() => (!saving ? setEditingTab(null) : undefined)}
        onSave={() => void handleSave()}
        open={editingTab !== null}
        placeholder={editingTab === 'artifact' ? '请输入 Refine 产物...' : '请输入补充说明...'}
        title={editingTab === 'artifact' ? '编辑 Refine 产物' : '编辑 Refine 补充说明'}
        value={draft}
      />
    </>
  )
}

function buildRefineProgress(task: TaskRecord): RefineProgressStep[] {
  const log = task.artifacts['refine.log'] || ''
  const hasIntent = Boolean(task.artifacts['refine-intent.json']) || log.includes('intent_goal:')
  const hasKnowledgeSelection = Boolean(task.artifacts['refine-knowledge-selection.json']) || log.includes('selected_knowledge_ids:')
  const hasKnowledgeRead = Boolean(task.artifacts['refine-knowledge-read.md']) || log.includes('knowledge_read_mode:')
  const hasDraft = Boolean(task.artifacts['prd-refined.md']) || log.includes('generate_prompt_ok:')
  const hasVerified = Boolean(task.artifacts['refine-verify.json']) || task.status === 'refined'

  if (task.status === 'refined') {
    return [
      { label: '读取输入', done: true, current: false },
      { label: '提炼意图', done: true, current: false },
      { label: '知识筛选', done: true, current: false },
      { label: '生成初稿', done: true, current: false },
      { label: '完成校验', done: true, current: false },
    ]
  }

  const currentStep = !hasIntent
    ? '读取输入'
    : !hasKnowledgeSelection
      ? '提炼意图'
      : !hasKnowledgeRead
        ? '知识筛选'
        : !hasDraft
          ? '生成初稿'
          : '完成校验'

  return [
    { label: '读取输入', done: true, current: currentStep === '读取输入' && task.status === 'refining' },
    { label: '提炼意图', done: hasIntent, current: currentStep === '提炼意图' && task.status === 'refining' },
    { label: '知识筛选', done: hasKnowledgeSelection, current: currentStep === '知识筛选' && task.status === 'refining' },
    { label: '生成初稿', done: hasDraft, current: currentStep === '生成初稿' && task.status === 'refining' },
    { label: '完成校验', done: hasVerified, current: currentStep === '完成校验' && task.status === 'refining' },
  ]
}
