import type { TaskRecord } from '../../../api'
import { useEffect, useMemo, useState } from 'react'
import { updateTaskArtifact } from '../../../api'
import { hasArtifact } from '../model'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, MarkdownBody, NotePanel, SectionCard } from '../ui'

type RefineProgressStep = {
  label: string
  done: boolean
  current: boolean
}

export function RefineStage({ task, onTaskUpdated }: { task: TaskRecord; onTaskUpdated: () => Promise<void> | void }) {
  const [showNotes, setShowNotes] = useState(false)
  const [editingTab, setEditingTab] = useState<'artifact' | 'notes' | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [streamedLog, setStreamedLog] = useState<string | null>(null)

  const steps = useMemo(() => buildRefineProgress(task), [task])
  const progressPercent = useMemo(() => buildRefineProgressPercent(task, steps), [task, steps])
  const activeLabel = steps.find((step) => step.current)?.label ?? (task.status === 'refined' ? '提炼完成' : '等待开始')
  const progressTone =
    task.status === 'refining'
      ? 'bg-[#4fa06d]'
      : task.status === 'refined'
        ? 'bg-[#2c8c58]'
        : 'bg-[#cdbda6] dark:bg-[#4a4640]'
  const notesContent = task.artifacts['refine.notes.md'] || '当前没有额外补充说明。'
  const isRunning = task.status === 'refining'
  const logContent = streamedLog ?? task.artifacts['refine.log'] ?? ''
  const visibleLogContent = logContent || '当前没有 refine 日志。'
  const currentValue = editingTab === 'artifact' ? task.artifacts['prd-refined.md'] || '' : task.artifacts['refine.notes.md'] || ''
  const canSave = editingTab === 'artifact' ? draft.trim().length > 0 && draft.trim() !== currentValue.trim() : draft.trim() !== currentValue.trim()

  useEffect(() => {
    if (!isRunning) {
      setStreamedLog(null)
      return
    }

    const source = new EventSource(`/api/tasks/${encodeURIComponent(task.id)}/logs/refine/stream`)
    const parseContent = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as { content?: unknown }
        return typeof payload.content === 'string' ? payload.content : ''
      } catch {
        return ''
      }
    }
    const handleSnapshot = (event: MessageEvent) => {
      setStreamedLog(parseContent(event))
    }
    const handleAppend = (event: MessageEvent) => {
      const chunk = parseContent(event)
      if (chunk) {
        setStreamedLog((current) => `${current ?? ''}${chunk}`)
      }
    }
    const handleDone = () => {
      source.close()
    }

    source.addEventListener('snapshot', handleSnapshot)
    source.addEventListener('append', handleAppend)
    source.addEventListener('done', handleDone)
    source.onerror = () => {
      source.close()
    }

    return () => {
      source.close()
    }
  }, [isRunning, task.id])

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
        <div className="rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-4 py-4 dark:border-[#30302e] dark:bg-[#1d1c1a]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className={`h-2 w-2 rounded-full ${isRunning ? 'bg-[#c96442]' : task.status === 'refined' ? 'bg-[#4fa06d]' : 'bg-[#b0aea5]'}`} />
              <div>
                <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{activeLabel}</div>
                <div className="mt-1 text-xs text-[#87867f] dark:text-[#b0aea5]">Refine 进度 {progressPercent}%</div>
              </div>
            </div>
            {isRunning ? <span className="rounded-full bg-[#fff1ed] px-3 py-1 text-xs font-medium text-[#c96442] dark:bg-[#351b17] dark:text-[#f0c0b0]">Streaming</span> : null}
          </div>
          <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-[#f5f4ed] dark:bg-[#30302e]">
            <div
              className={`flow-progress-fill h-full rounded-full transition-all duration-300 ${progressTone} ${isRunning ? 'flow-progress-fill-active' : ''}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-5">
            {steps.map((step) => (
              <div
                className={`rounded-[10px] border px-3 py-2 text-xs ${
                  step.done
                    ? 'border-[#b8dfcf] bg-[#e3f6ee] text-[#2c8c58] dark:border-[#395d51] dark:bg-[#052e16] dark:text-[#8cdabf]'
                    : step.current
                      ? 'border-[#f0c0b0] bg-[#fff1ed] text-[#c96442] dark:border-[#8f3c2e] dark:bg-[#351b17] dark:text-[#f0c0b0]'
                      : 'border-[#e8e6dc] bg-[#faf9f5] text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]'
                }`}
                key={step.label}
              >
                {step.label}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 grid overflow-hidden rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] dark:border-[#30302e] dark:bg-[#1d1c1a] lg:grid-cols-[minmax(0,7fr)_minmax(220px,3fr)]">
          <RefineArtifactPreview
            canEdit={!isRunning}
            content={task.artifacts['prd-refined.md'] || ''}
            isRunning={isRunning}
            onEdit={() => openEditor('artifact')}
          />
          <RefineLogTimeline content={visibleLogContent} isRunning={isRunning} />
        </div>

        <div className="mt-4 rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] dark:border-[#30302e] dark:bg-[#1d1c1a]">
          <div className="flex items-center justify-between gap-3 border-b border-[#e8e6dc] px-4 py-3 dark:border-[#30302e]">
            <button
              className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]"
              onClick={() => setShowNotes((current) => !current)}
              type="button"
            >
              补充说明
            </button>
            <ActionButton onClick={() => openEditor('notes')} tone="secondary">
              编辑补充
            </ActionButton>
          </div>
          {showNotes ? <div className="p-4"><NotePanel content={notesContent} /></div> : null}
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

function RefineArtifactPreview({
  content,
  isRunning,
  canEdit,
  onEdit,
}: {
  content: string
  isRunning: boolean
  canEdit: boolean
  onEdit: () => void
}) {
  const fallback = isRunning ? '# 正在生成 Refine 产物\n\n等待模型输出 `prd-refined.md` 内容...' : '当前还没有产物。'
  return (
    <section className="min-w-0 border-b border-[#e8e6dc] dark:border-[#30302e] lg:border-r lg:border-b-0">
      <div className="flex min-h-[56px] items-center justify-between gap-3 border-b border-[#e8e6dc] px-4 py-3 dark:border-[#30302e]">
        <div className="flex min-w-0 items-center gap-3">
          <DocumentIcon />
          <div className="truncate text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">prd-refined.md</div>
        </div>
        <div className="flex items-center gap-3">
          {isRunning ? <span className="rounded-full bg-[#fff1ed] px-3 py-1 text-xs font-medium text-[#c96442] dark:bg-[#351b17] dark:text-[#f0c0b0]">只读预览</span> : null}
          {canEdit ? (
            <ActionButton onClick={onEdit} tone="secondary">
              编辑原文
            </ActionButton>
          ) : null}
        </div>
      </div>
      <div className="min-h-[520px] overflow-auto px-6 py-5">
        <MarkdownBody compact content={content || fallback} />
        {isRunning ? <span className="ml-1 inline-block h-4 w-px animate-pulse bg-[#c96442] align-text-bottom" /> : null}
      </div>
    </section>
  )
}

function RefineLogTimeline({ content, isRunning }: { content: string; isRunning: boolean }) {
  const events = parseRefineLogEvents(content, isRunning)
  return (
    <aside className="min-w-0 bg-[#faf9f5] dark:bg-[#1d1c1a]">
      <div className="flex min-h-[56px] items-center justify-between gap-3 border-b border-[#e8e6dc] px-4 py-3 dark:border-[#30302e]">
        <div className="text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">执行日志</div>
        <div className="text-xs text-[#87867f] dark:text-[#b0aea5]">refine.log</div>
      </div>
      <div className="space-y-0 px-5 py-5">
        {events.map((event, index) => (
          <div className="relative grid grid-cols-[24px_minmax(0,1fr)] gap-3 pb-8 last:pb-0" key={`${event.title}-${index}`}>
            {index < events.length - 1 ? <div className="absolute left-[11px] top-7 h-[calc(100%-1.75rem)] w-px bg-[#e8e6dc] dark:bg-[#30302e]" /> : null}
            <span className={`relative z-10 mt-1 h-3 w-3 rounded-full border-2 ${eventDotTone(event.state)}`} />
            <div className="min-w-0">
              <div className="flex items-center justify-between gap-3">
                <div className="truncate text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{event.title}</div>
                <span className={`shrink-0 text-xs ${eventTextTone(event.state)}`}>{event.status}</span>
              </div>
              <div className="mt-1 text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{event.detail}</div>
            </div>
          </div>
        ))}
      </div>
    </aside>
  )
}

type RefineLogEvent = {
  title: string
  detail: string
  status: string
  state: 'done' | 'running' | 'pending' | 'failed'
}

function parseRefineLogEvents(content: string, isRunning: boolean): RefineLogEvent[] {
  const log = content || ''
  const hasStart = log.includes('=== REFINE START ===') || isRunning
  const hasInput = log.includes('scope_count:') || log.includes('manual_change_points_count:') || hasStart
  const hasWriter = log.includes('generation_path:') || log.includes('agent_prompt_start:') || log.includes('native') || log.includes('local')
  const hasVerify = log.includes('refine_check:') || log.includes('verify_ok') || log.includes('=== REFINE END ===')
  const failed = log.toLowerCase().includes('error') || log.toLowerCase().includes('failed')

  return [
    {
      title: 'agent session started',
      detail: hasStart ? '智能体会话已启动' : '等待启动 Refine',
      status: hasStart ? '完成' : '排队中',
      state: hasStart ? 'done' : 'pending',
    },
    {
      title: 'writer streaming',
      detail: hasWriter || isRunning ? '正在生成 prd-refined.md' : '等待 writer 生成正文',
      status: hasVerify ? '完成' : hasWriter || isRunning ? '进行中' : '排队中',
      state: hasVerify ? 'done' : hasWriter || isRunning ? 'running' : 'pending',
    },
    {
      title: failed ? 'verify failed' : 'verify pending',
      detail: hasVerify ? '内容生成完成，已进入校验或修复' : hasInput ? '等待内容生成完成后进行校验' : '等待输入解析',
      status: failed ? '失败' : hasVerify ? '完成' : '排队中',
      state: failed ? 'failed' : hasVerify ? 'done' : 'pending',
    },
  ]
}

function eventDotTone(state: RefineLogEvent['state']) {
  switch (state) {
    case 'done':
      return 'border-[#4fa06d] bg-[#4fa06d]'
    case 'running':
      return 'border-[#c96442] bg-[#c96442]'
    case 'failed':
      return 'border-[#b53333] bg-[#b53333]'
    default:
      return 'border-[#b0aea5] bg-[#faf9f5] dark:bg-[#1d1c1a]'
  }
}

function eventTextTone(state: RefineLogEvent['state']) {
  switch (state) {
    case 'done':
      return 'text-[#2c8c58] dark:text-[#8cdabf]'
    case 'running':
      return 'text-[#c96442] dark:text-[#f0c0b0]'
    case 'failed':
      return 'text-[#b53333] dark:text-[#ffb3b3]'
    default:
      return 'text-[#87867f] dark:text-[#b0aea5]'
  }
}

function DocumentIcon() {
  return (
    <svg aria-hidden="true" className="h-5 w-5 shrink-0 text-[#4d4c48] dark:text-[#b0aea5]" fill="none" viewBox="0 0 24 24">
      <path d="M7 3.5h6l4 4V20a.5.5 0 0 1-.5.5h-9A.5.5 0 0 1 7 20V3.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M13 3.5V8h4" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
    </svg>
  )
}

function buildRefineProgress(task: TaskRecord): RefineProgressStep[] {
  const log = task.artifacts['refine.log'] || ''
  const hasStarted = task.status === 'refining' || task.status === 'refined' || log.includes('=== REFINE START ===')
  const hasManualExtract = log.includes('manual_change_points_count:') || hasStarted
  const hasBrief = hasArtifact(task.artifacts['refine-brief.json']) || log.includes('brief_goal:')
  const hasDraft = hasArtifact(task.artifacts['prd-refined.md']) || task.status === 'refined'
  const hasVerified = hasArtifact(task.artifacts['refine-verify.json']) || log.includes('verify_ok:') || task.status === 'refined'

  if (task.status === 'refined') {
    return [
      { label: '读取输入', done: true, current: false },
      { label: '解析人工提炼', done: true, current: false },
      { label: '生成 Brief', done: true, current: false },
      { label: '渲染文档', done: true, current: false },
      { label: '完成校验', done: true, current: false },
    ]
  }

  if (task.status !== 'refining') {
    return [
      { label: '读取输入', done: false, current: false },
      { label: '提炼意图', done: false, current: false },
      { label: 'Skills 筛选', done: false, current: false },
      { label: '生成初稿', done: false, current: false },
      { label: '完成校验', done: false, current: false },
    ]
  }

  const currentStep = !hasStarted
    ? '读取输入'
    : !hasManualExtract
      ? '解析人工提炼'
      : !hasBrief
        ? '生成 Brief'
        : !hasDraft
          ? '渲染文档'
          : !hasVerified
            ? '完成校验'
            : '完成校验'

  return [
    { label: '读取输入', done: hasStarted, current: currentStep === '读取输入' },
    { label: '解析人工提炼', done: hasManualExtract, current: currentStep === '解析人工提炼' },
    { label: '生成 Brief', done: hasBrief, current: currentStep === '生成 Brief' },
    { label: '渲染文档', done: hasDraft, current: currentStep === '渲染文档' },
    { label: '完成校验', done: hasVerified, current: currentStep === '完成校验' },
  ]
}

function buildRefineProgressPercent(task: TaskRecord, steps: RefineProgressStep[]) {
  if (task.status === 'refined') {
    return 100
  }
  if (task.status !== 'refining') {
    return 0
  }
  const completedUnits = steps.filter((step) => step.done).length
  const currentUnits = steps.some((step) => step.current) ? 0.45 : 0
  return Math.max(8, Math.round(((completedUnits + currentUnits) / steps.length) * 100))
}
