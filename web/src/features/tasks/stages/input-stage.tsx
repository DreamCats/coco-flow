import type { TaskRecord } from '../../../api'
import { useMemo, useState } from 'react'
import { updateTaskArtifact } from '../../../api'
import { extractSourceSections, manualExtractTemplate, replaceSourceSections, validateManualExtract } from '../content'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

export function InputStage({ task, onTaskUpdated }: { task: TaskRecord; onTaskUpdated: () => Promise<void> | void }) {
  const [tab, setTab] = useState<'artifact' | 'notes'>('artifact')
  const [editingTab, setEditingTab] = useState<'artifact' | 'notes' | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const sections = useMemo(() => extractSourceSections(task.artifacts['prd.source.md'] || ''), [task.artifacts])
  const editingCurrentValue = editingTab === 'artifact' ? sections.source : sections.supplement
  const manualExtractError = editingTab === 'notes' ? validateManualExtract(draft) : ''
  const canSave =
    editingTab === 'artifact'
      ? draft.trim().length > 0 && draft.trim() !== editingCurrentValue.trim()
      : draft.trim() !== editingCurrentValue.trim() && !manualExtractError

  function openEditor(nextTab: 'artifact' | 'notes') {
    setEditingTab(nextTab)
    setDraft(nextTab === 'artifact' ? sections.source : sections.supplement || manualExtractTemplate)
    setSaveError('')
  }

  async function handleSave() {
    if (!editingTab) {
      return
    }
    if (editingTab === 'notes') {
      const error = validateManualExtract(draft)
      if (error) {
        setSaveError(error)
        return
      }
    }
    const nextContent = replaceSourceSections(task.artifacts['prd.source.md'] || '', {
      source: editingTab === 'artifact' ? draft : sections.source,
      supplement: editingTab === 'notes' ? draft : sections.supplement,
    })
    try {
      setSaving(true)
      setSaveError('')
      await updateTaskArtifact(task.id, 'prd.source.md', nextContent)
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
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
            <TabButton active={tab === 'artifact'} onClick={() => setTab('artifact')}>
              产物与查看
            </TabButton>
            <TabButton active={tab === 'notes'} onClick={() => setTab('notes')}>
              人工提炼范围
            </TabButton>
          </div>
          <ActionButton onClick={() => openEditor(tab)} tone="secondary">
            {tab === 'artifact' ? '编辑原文' : '编辑提炼范围'}
          </ActionButton>
        </div>
        <div className="mt-4">
          {tab === 'artifact' ? (
            <ArtifactPanel content={sections.source || task.artifacts['prd.source.md'] || ''} title="prd.source.md" />
          ) : (
            <NotePanel content={sections.supplement || '当前还没有填写人工提炼范围。请至少补齐“本次范围”和“人工提炼改动点”。'} />
          )}
        </div>
      </SectionCard>
      <TaskStageEditorModal
        busy={saving}
        canSave={canSave}
        description={editingTab === 'artifact' ? '这里编辑 Input 阶段沉淀下来的原始需求正文。' : '这里编辑服务端人工提炼范围。Refine 前必须先补齐。'}
        error={saveError}
        hint="保存后会覆盖 prd.source.md，并清理后续 refine / design / plan 产物。"
        monospace={editingTab === 'artifact'}
        onChange={setDraft}
        onClose={() => (!saving ? setEditingTab(null) : undefined)}
        onSave={() => void handleSave()}
        open={editingTab !== null}
        placeholder={editingTab === 'artifact' ? '请输入 PRD 原文...' : manualExtractTemplate}
        title={editingTab === 'artifact' ? '编辑 Input 原文' : '编辑人工提炼范围'}
        value={draft}
      />
    </>
  )
}
