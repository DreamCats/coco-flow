import type { TaskRecord } from '../../../api'
import { syncDesign, updateTaskArtifact } from '../../../api'
import { useEffect, useMemo, useState } from 'react'
import { hasArtifact } from '../model'
import { TaskRepoBindingModal } from '../task-repo-binding-modal'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, ArtifactPanel, NotePanel, SectionCard, TabButton, TipIcon } from '../ui'

type DesignTab = 'artifact' | 'notes' | 'log'
type DesignProgressStep = {
  label: string
  done: boolean
  current: boolean
}
type DesignBlocker = {
  title: string
  body: string
  action: string
  issues: string[]
  instructions: string[]
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
  const [syncing, setSyncing] = useState(false)
  const [syncError, setSyncError] = useState('')
  const steps = useMemo(() => buildDesignProgress(task), [task])
  const designSync = useMemo(() => buildDesignSync(task), [task])
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
    if (openRepoBindingToken > 0 && task.repos.length === 0) {
      setBindingRepos(true)
    }
  }, [openRepoBindingToken, task.repos.length])

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

  async function handleSync() {
    try {
      setSyncing(true)
      setSyncError('')
      await syncDesign(task.id)
      await onTaskUpdated()
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  return (
    <>
      <SectionCard title="阶段详情">
        {blocker ? (
          <div className="mb-4 rounded-[14px] border border-[#e7bf7a] bg-[#fff6e6] px-4 py-3 text-sm leading-6 text-[#75510d] dark:border-[#6b5428] dark:bg-[#2d2416] dark:text-[#f0d59b]">
            <div className="font-medium text-[#5f430d] dark:text-[#f5dfad]">{blocker.title}</div>
            <div className="mt-1">{blocker.body}</div>
            {blocker.issues.length > 0 ? (
              <div className="mt-3">
                <div className="text-xs font-medium text-[#5f430d] dark:text-[#f5dfad]">还缺什么</div>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5">
                  {blocker.issues.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {blocker.instructions.length > 0 ? (
              <div className="mt-3">
                <div className="text-xs font-medium text-[#5f430d] dark:text-[#f5dfad]">下一步补证</div>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5">
                  {blocker.instructions.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {blocker.action ? <div className="mt-3 text-xs text-[#8a6826] dark:text-[#d5bb83]">{blocker.action}</div> : null}
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
        <DesignSyncNotice busy={syncing} error={syncError} onSync={() => void handleSync()} sync={designSync} />

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
              {tab === 'artifact' ? (
                <TipIcon label="Design 确认项填写示例">
                  <div className="font-medium text-[#141413] dark:text-[#faf9f5]">确认后的答案写回 design.md</div>
                  <div className="mt-2">
                    字段语义、实验枚举值、文案 key、范围边界要写成明确结论，不要只删除“待确认”。
                  </div>
                  <pre className="mt-2 whitespace-pre-wrap rounded-[8px] bg-[#f5f4ed] p-2 font-mono text-[11px] leading-5 dark:bg-[#232220]">
{`### 文案 key
- Starting bid: \`ecom_live_auction_pin_card_message_starting_price\`

## 明确不做
- 不涉及 bag / 购物袋场景。`}
                  </pre>
                </TipIcon>
              ) : null}
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

type DesignSyncState = {
  synced: boolean | null
  changedArtifact: string
}

function DesignSyncNotice({
  busy,
  error,
  onSync,
  sync,
}: {
  busy: boolean
  error: string
  onSync: () => void
  sync: DesignSyncState
}) {
  if (sync.synced !== false) {
    return null
  }
  return (
    <div className="mt-4 rounded-[16px] border border-[#efc08a] bg-[#fff6e8] px-4 py-3 text-sm leading-6 text-[#8a5b18] dark:border-[#6f5330] dark:bg-[#2d2418] dark:text-[#f1c98c]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium">Design Markdown 已保存，但结构化设计契约未同步。</div>
          <div className="mt-1">
            {sync.changedArtifact || 'design.md'} 已被编辑。Plan 阶段当前会被阻断；请先同步设计契约，系统会保留当前 Markdown，只刷新 design-contracts.json。
          </div>
          {error ? <div className="mt-2 text-xs text-[#b53333] dark:text-[#ffb4a8]">{error}</div> : null}
        </div>
        <ActionButton disabled={busy} onClick={onSync} tone="secondary">
          {busy ? '同步中...' : '同步设计契约'}
        </ActionButton>
      </div>
    </div>
  )
}

function buildDesignSync(task: TaskRecord): DesignSyncState {
  const payload = parseJSON(task.artifacts['design-sync.json'])
  return {
    synced: typeof payload.synced === 'boolean' ? payload.synced : null,
    changedArtifact: asString(payload.changed_artifact) || asString(payload.changedArtifact),
  }
}

function parseJSON(content: string | undefined): Record<string, unknown> {
  if (!content) {
    return {}
  }
  try {
    const parsed = JSON.parse(content) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function buildDesignBlocker(task: TaskRecord): DesignBlocker | null {
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
  const research = parseJSON(task.artifacts['design-research-summary.json'])
  const researchReview = asRecord(research.research_review)
  const reviewIssues = asSummaryList(researchReview.blocking_issues)
  const reviewInstructions = asStringList(researchReview.research_instructions)
  return {
    title: severity === 'degraded' ? 'Design 产物需要人工确认' : 'Design 已被阻断',
    body: [issueText, reason].filter(Boolean).join(' '),
    action: task.nextAction || diagnosis.nextAction || '编辑 design.md 补齐待确认项，随后同步 Design 并进入 Plan。',
    issues: uniqueStrings([...(diagnosis.issues || []), ...reviewIssues]).slice(0, 6),
    instructions: uniqueStrings([...(diagnosis.instructions || []), ...reviewInstructions]).slice(0, 6),
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((item) => Object.keys(item).length > 0) : []
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map(asString).filter(Boolean) : []
}

function asSummaryList(value: unknown): string[] {
  return asRecordArray(value).map((item) => asString(item.summary)).filter(Boolean)
}

function uniqueStrings(items: string[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const item of items) {
    const value = item.trim()
    if (!value || seen.has(value)) {
      continue
    }
    seen.add(value)
    result.push(value)
  }
  return result
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
