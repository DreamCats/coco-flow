import type { PlanReadinessScore, TaskRecord } from '../../../api'
import { evaluatePlanReadiness, getTaskArtifact, syncPlan, updateTaskArtifact } from '../../../api'
import { useEffect, useMemo, useState } from 'react'
import { hasArtifact } from '../model'
import { TaskStageEditorModal } from '../task-stage-editor-modal'
import { ActionButton, ArtifactPanel, SectionCard, TabButton, TipIcon } from '../ui'

type PlanTab = 'graph' | 'raw' | 'log' | `repo:${string}`
type PlanEditingTab = 'raw' | 'repo' | null
type PlanProgressStep = {
  label: string
  done: boolean
  current: boolean
}
type PlanWorkItem = {
  id: string
  repoId: string
  title: string
  goal: string
  changeScope: string[]
  specificSteps: string[]
  dependsOn: string[]
  blocks: string[]
}
type PlanEdge = {
  from: string
  to: string
  type: string
  reason: string
}
type StructuredPlan = {
  workItems: PlanWorkItem[]
  edges: PlanEdge[]
  executionOrder: string[]
  parallelGroups: string[][]
  coordinationPoints: string[]
  gateStatus: string
  codeAllowed: boolean | null
  blockers: string[]
  sync: {
    synced: boolean | null
    status: string
    reason: string
    changedArtifact: string
    repoId: string
    updatedAt: string
  }
}

export function PlanStage({ task, onTaskUpdated }: { task: TaskRecord; onTaskUpdated: () => Promise<void> | void }) {
  const [tab, setTab] = useState<PlanTab>(() => (task.repos[0]?.id ? `repo:${task.repos[0].id}` : 'graph'))
  const [editingTab, setEditingTab] = useState<PlanEditingTab>(null)
  const [editingRepoId, setEditingRepoId] = useState('')
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [syncError, setSyncError] = useState('')
  const [repoPlans, setRepoPlans] = useState<Record<string, string>>({})
  const [repoPlanLoading, setRepoPlanLoading] = useState(false)
  const [readinessOverride, setReadinessOverride] = useState<PlanReadinessScore | null>(null)
  const [readinessOpen, setReadinessOpen] = useState(false)
  const [readinessBusy, setReadinessBusy] = useState(false)
  const [readinessError, setReadinessError] = useState('')
  const steps = useMemo(() => buildPlanProgress(task), [task])
  const progressPercent = useMemo(() => buildPlanProgressPercent(task, steps), [task, steps])
  const plan = useMemo(() => buildStructuredPlan(task), [task])
  const cachedReadiness = useMemo(() => normalizePlanReadiness(parseJSON(task.artifacts['plan-readiness-score.json'])), [task.artifacts])
  const readiness = readinessOverride || cachedReadiness
  const activeLabel = steps.find((step) => step.current)?.label ?? (task.status === 'planned' ? '计划完成' : '等待开始')
  const progressTone =
    task.status === 'planning'
      ? 'bg-[#4fa06d]'
      : task.status === 'planned'
        ? 'bg-[#2c8c58]'
        : 'bg-[#cdbda6] dark:bg-[#4a4640]'
  const planMarkdown = task.artifacts['plan.md'] || ''
  const logContent = task.artifacts['plan.log'] || task.nextAction || '当前没有 plan 过程日志。'
  const activeRepoId = tab.startsWith('repo:') ? tab.slice('repo:'.length) : ''
  const editingCurrentValue = editingTab === 'repo' ? repoPlans[editingRepoId] || '' : planMarkdown
  const canSave = draft.trim().length > 0 && draft.trim() !== editingCurrentValue.trim()
  const canEvaluate = hasArtifact(task.artifacts['design.md']) && hasArtifact(task.artifacts['plan.md'])

  useEffect(() => {
    setReadinessOverride(null)
    setReadinessError('')
  }, [task.id])

  useEffect(() => {
    if (!tab.startsWith('repo:')) {
      return
    }
    const repoId = tab.slice('repo:'.length)
    if (task.repos.some((repo) => repo.id === repoId)) {
      return
    }
    setTab(task.repos[0]?.id ? `repo:${task.repos[0].id}` : 'graph')
  }, [tab, task.repos])

  useEffect(() => {
    let cancelled = false
    const repoIds = task.repos.map((repo) => repo.id).filter(Boolean)
    if (repoIds.length === 0) {
      setRepoPlans({})
      return
    }

    async function loadRepoPlans() {
      setRepoPlanLoading(true)
      const nextPlans: Record<string, string> = {}
      await Promise.all(
        repoIds.map(async (repoId) => {
          try {
            const artifact = await getTaskArtifact(task.id, 'plan.md', repoId)
            nextPlans[repoId] = artifact.content
          } catch {
            nextPlans[repoId] = ''
          }
        }),
      )
      if (!cancelled) {
        setRepoPlans(nextPlans)
        setRepoPlanLoading(false)
      }
    }

    void loadRepoPlans()
    return () => {
      cancelled = true
    }
  }, [task.id, task.repos])

  function openRawEditor() {
    setDraft(planMarkdown)
    setEditingRepoId('')
    setSaveError('')
    setEditingTab('raw')
  }

  function openRepoEditor(repoId: string) {
    setDraft(repoPlans[repoId] || '')
    setEditingRepoId(repoId)
    setSaveError('')
    setEditingTab('repo')
  }

  async function handleSave() {
    if (!editingTab) {
      return
    }
    try {
      setSaving(true)
      setSaveError('')
      const repoId = editingTab === 'repo' ? editingRepoId : undefined
      const result = await updateTaskArtifact(task.id, 'plan.md', draft, repoId)
      if (repoId) {
        setRepoPlans((current) => ({ ...current, [repoId]: result.content }))
      }
      await onTaskUpdated()
      setEditingTab(null)
      setEditingRepoId('')
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
      await syncPlan(task.id)
      await onTaskUpdated()
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : '同步失败')
    } finally {
      setSyncing(false)
    }
  }

  async function handleEvaluateReadiness() {
    try {
      setReadinessBusy(true)
      setReadinessError('')
      const result = await evaluatePlanReadiness(task.id)
      setReadinessOverride(result)
      await onTaskUpdated()
    } catch (error) {
      setReadinessError(error instanceof Error ? error.message : '评测失败')
    } finally {
      setReadinessBusy(false)
    }
  }

  return (
    <>
      <SectionCard title="阶段详情">
        <PlanProgressCard activeLabel={activeLabel} isRunning={task.status === 'planning'} progressPercent={progressPercent} progressTone={progressTone} steps={steps} />
        <PlanReadinessCard
          busy={readinessBusy}
          canEvaluate={canEvaluate}
          error={readinessError}
          onEvaluate={() => void handleEvaluateReadiness()}
          onOpenDetails={() => setReadinessOpen(true)}
          readiness={readiness}
        />
        <PlanGateNotice plan={plan} />

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex flex-wrap rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
            <TabButton active={tab === 'graph'} onClick={() => setTab('graph')}>
              关系图
            </TabButton>
            {task.repos.map((repo) => (
              <TabButton active={tab === `repo:${repo.id}`} key={repo.id} onClick={() => setTab(`repo:${repo.id}`)}>
                {repo.displayName || repo.id}
              </TabButton>
            ))}
            <TabButton active={tab === 'raw'} onClick={() => setTab('raw')}>
              原文
            </TabButton>
            <TabButton active={tab === 'log'} onClick={() => setTab('log')}>
              日志
            </TabButton>
          </div>
          <div className="flex flex-wrap gap-2">
            {activeRepoId ? (
              <ActionButton disabled={repoPlanLoading} onClick={() => openRepoEditor(activeRepoId)} tone="secondary">
                编辑仓计划
              </ActionButton>
            ) : null}
            {tab === 'raw' ? (
              <ActionButton onClick={openRawEditor} tone="secondary">
                编辑原文
              </ActionButton>
            ) : null}
          </div>
        </div>
        <PlanSyncNotice busy={syncing} error={syncError} onSync={() => void handleSync()} plan={plan} />

        <div className="mt-4">
          {tab === 'graph' ? <PlanGraphPanel plan={plan} /> : null}
          {activeRepoId ? (
            <RepoPlanPanel
              loading={repoPlanLoading}
              markdown={repoPlans[activeRepoId] || ''}
              onEdit={() => openRepoEditor(activeRepoId)}
              repo={task.repos.find((repo) => repo.id === activeRepoId)}
              repoId={activeRepoId}
            />
          ) : null}
          {tab === 'raw' ? <ArtifactPanel content={planMarkdown} title="plan.md" /> : null}
          {tab === 'log' ? <ArtifactPanel content={logContent} renderAs="plain" title="plan.log" /> : null}
        </div>
      </SectionCard>

      <TaskStageEditorModal
        busy={saving}
        canSave={canSave}
        description={editDescription(editingTab, editingRepoId)}
        error={saveError}
        hint={editHint(editingTab)}
        monospace
        onChange={setDraft}
        onClose={() => (!saving ? setEditingTab(null) : undefined)}
        onSave={() => void handleSave()}
        open={editingTab !== null}
        placeholder={editPlaceholder(editingTab)}
        title={editTitle(editingTab, editingRepoId)}
        value={draft}
      />
      <PlanReadinessDetails onClose={() => setReadinessOpen(false)} open={readinessOpen} readiness={readiness} />
    </>
  )
}

function PlanGateNotice({ plan }: { plan: StructuredPlan }) {
  if (plan.codeAllowed !== false || plan.blockers.length === 0) {
    return null
  }
  return (
    <div className="mt-4 rounded-[16px] border border-[#efc08a] bg-[#fff6e8] px-4 py-3 text-sm leading-6 text-[#8a5b18] dark:border-[#6f5330] dark:bg-[#2d2418] dark:text-[#f1c98c]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 font-medium">
            <span>Plan 仍有待确认项，暂不能进入 Code</span>
            <TipIcon label="待确认项处理示例">
              <div className="font-medium text-[#141413] dark:text-[#faf9f5]">待确认项需要被解决</div>
              <div className="mt-2">
                把确认后的答案写回文档，而不是只删除条目。字段语义、枚举值、文案 key、范围边界写到 Design；文件范围和执行步骤写到对应仓库 Plan。
              </div>
              <pre className="mt-2 whitespace-pre-wrap rounded-[8px] bg-[#f5f4ed] p-2 font-mono text-[11px] leading-5 dark:bg-[#232220]">
{`Design:
Starting bid: \`ecom_live_auction_pin_card_message_starting_price\`
不涉及 bag / 购物袋场景。

live_pack Plan:
删除 converter_helpers.go 相关任务。`}
              </pre>
            </TipIcon>
          </div>
          <div className="mt-1">
            请先把确认后的答案写回 Design 或对应仓库 Plan，保存后同步产物，再进入 Code。
          </div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5">
            {plan.blockers.slice(0, 5).map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function PlanSyncNotice({
  busy,
  error,
  onSync,
  plan,
}: {
  busy: boolean
  error: string
  onSync: () => void
  plan: StructuredPlan
}) {
  if (plan.sync.synced !== false) {
    return null
  }
  const target = [plan.sync.repoId, plan.sync.changedArtifact || 'plan.md'].filter(Boolean).join(' ')
  return (
    <div className="mt-4 rounded-[16px] border border-[#efc08a] bg-[#fff6e8] px-4 py-3 text-sm leading-6 text-[#8a5b18] dark:border-[#6f5330] dark:bg-[#2d2418] dark:text-[#f1c98c]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-medium">Plan Markdown 已保存，但执行契约未同步。</div>
          <div className="mt-1">
            {target ? `${target} 已被编辑。` : null}Code 阶段当前会被阻断；请先同步执行契约，系统会保留你编辑后的 Markdown，只刷新结构化 JSON。
          </div>
          {error ? <div className="mt-2 text-xs text-[#b53333] dark:text-[#ffb4a8]">{error}</div> : null}
        </div>
        <ActionButton disabled={busy} onClick={onSync} tone="secondary">
          {busy ? '同步中...' : '同步执行契约'}
        </ActionButton>
      </div>
    </div>
  )
}

function PlanReadinessCard({
  busy,
  canEvaluate,
  error,
  onEvaluate,
  onOpenDetails,
  readiness,
}: {
  busy: boolean
  canEvaluate: boolean
  error: string
  onEvaluate: () => void
  onOpenDetails: () => void
  readiness: PlanReadinessScore | null
}) {
  const status = readinessStatus(readiness)
  return (
    <div className="mt-4 rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Pre-Code Readiness Score</div>
          <div className="mt-2 flex flex-wrap items-end gap-3">
            <div className="text-[32px] leading-none font-semibold text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
              {readiness ? readiness.score.toFixed(1) : '--'}
            </div>
            <div className="pb-1 text-sm text-[#5e5d59] dark:text-[#b0aea5]">/ 100</div>
            <span className={`mb-0.5 rounded-full border px-3 py-1 text-xs ${status.className}`}>{status.label}</span>
          </div>
          <div className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
            {readiness ? `评测时间：${formatReadinessTime(readiness.generated_at)}` : '生成 Plan 后可评测 Design / Plan 是否足够支撑 Code。'}
          </div>
          {error ? <div className="mt-2 text-xs leading-5 text-[#b53333] dark:text-[#ffb4a8]">{error}</div> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <ActionButton disabled={!canEvaluate || busy} onClick={onEvaluate} tone="secondary">
            {busy ? '评测中...' : readiness ? '重新评测' : '评测质量'}
          </ActionButton>
          <ActionButton disabled={!readiness} onClick={onOpenDetails} tone="secondary">
            查看得分依据
          </ActionButton>
        </div>
      </div>
      {readiness ? (
        <div className="mt-4 grid gap-2 md:grid-cols-4">
          {readiness.sections.map((section) => (
            <div className="rounded-[14px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 dark:border-[#30302e] dark:bg-[#232220]" key={section.id}>
              <div className="text-xs text-[#87867f] dark:text-[#8f8a82]">{section.label}</div>
              <div className="mt-1 text-lg font-medium text-[#141413] dark:text-[#faf9f5]">{(section.score * 100).toFixed(1)}</div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function PlanReadinessDetails({
  onClose,
  open,
  readiness,
}: {
  onClose: () => void
  open: boolean
  readiness: PlanReadinessScore | null
}) {
  if (!open || !readiness) {
    return null
  }
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-[1px]" role="dialog" aria-modal="true">
      <button aria-label="关闭评测详情" className="flex-1 cursor-default" onClick={onClose} type="button" />
      <div className="flex h-full w-full max-w-[760px] flex-col border-l border-[#e8e6dc] bg-[#fffdf9] shadow-2xl dark:border-[#30302e] dark:bg-[#151412]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div>
            <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">Readiness Detail</div>
            <div className="mt-2 text-2xl font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
              PCRS {readiness.score.toFixed(1)} / 100
            </div>
            <div className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{readiness.formula}</div>
          </div>
          <ActionButton onClick={onClose} tone="secondary">
            关闭
          </ActionButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {Object.entries(readiness.inputs).map(([key, value]) => (
              <div className="rounded-[14px] border border-[#ece6da] bg-[#f5f4ed] px-3 py-3 dark:border-[#30302e] dark:bg-[#232220]" key={key}>
                <div className="break-all text-xs text-[#87867f] dark:text-[#8f8a82]">{key}</div>
                <div className="mt-1 text-lg font-medium text-[#141413] dark:text-[#faf9f5]">{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-5 space-y-4">
            {readiness.sections.map((section) => (
              <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#191816]" key={section.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{section.label}</div>
                    <div className="mt-1 text-xs leading-5 text-[#87867f] dark:text-[#8f8a82]">{section.reason}</div>
                  </div>
                  <div className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1 text-xs text-[#4d4c48] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#f1ede4]">
                    {(section.score * 100).toFixed(1)}
                  </div>
                </div>
                <div className="mt-3 overflow-x-auto">
                  <table className="min-w-full border-collapse text-left text-sm">
                    <thead className="text-xs text-[#87867f] dark:text-[#8f8a82]">
                      <tr>
                        <th className="border-b border-[#e8e6dc] py-2 pr-3 font-medium dark:border-[#30302e]">指标</th>
                        <th className="border-b border-[#e8e6dc] py-2 pr-3 font-medium dark:border-[#30302e]">权重</th>
                        <th className="border-b border-[#e8e6dc] py-2 pr-3 font-medium dark:border-[#30302e]">得分</th>
                        <th className="border-b border-[#e8e6dc] py-2 font-medium dark:border-[#30302e]">依据</th>
                      </tr>
                    </thead>
                    <tbody>
                      {section.children.map((metric) => (
                        <tr key={metric.id}>
                          <td className="border-b border-[#f0eee6] py-2 pr-3 text-[#141413] dark:border-[#2a2927] dark:text-[#faf9f5]">{metric.label}</td>
                          <td className="border-b border-[#f0eee6] py-2 pr-3 text-[#5e5d59] dark:border-[#2a2927] dark:text-[#b0aea5]">{metric.weight}</td>
                          <td className="border-b border-[#f0eee6] py-2 pr-3 text-[#5e5d59] dark:border-[#2a2927] dark:text-[#b0aea5]">{(metric.score * 100).toFixed(1)}</td>
                          <td className="border-b border-[#f0eee6] py-2 text-[#5e5d59] dark:border-[#2a2927] dark:text-[#b0aea5]">{metric.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>

          {readiness.recommendations.length > 0 ? (
            <div className="mt-5 rounded-[18px] border border-[#efc08a] bg-[#fff6e8] px-4 py-4 text-sm leading-6 text-[#8a5b18] dark:border-[#6f5330] dark:bg-[#2d2418] dark:text-[#f1c98c]">
              <div className="font-medium">修正建议</div>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {readiness.recommendations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function PlanProgressCard({
  activeLabel,
  isRunning,
  progressPercent,
  progressTone,
  steps,
}: {
  activeLabel: string
  isRunning: boolean
  progressPercent: number
  progressTone: string
  steps: PlanProgressStep[]
}) {
  return (
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
      <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-[#efeae0] dark:bg-[#232220]">
        <div className={`flow-progress-fill h-full rounded-full transition-all duration-300 ${progressTone} ${isRunning ? 'flow-progress-fill-active' : ''}`} style={{ width: `${progressPercent}%` }} />
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
  )
}

function PlanGraphPanel({ plan }: { plan: StructuredPlan }) {
  return (
    <div className="space-y-4">
      <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
        <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">执行顺序</div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          {plan.executionOrder.length > 0 ? (
            plan.executionOrder.map((item, index) => (
              <span className="flex items-center gap-2" key={`${item}-${index}`}>
                <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 text-[#4d4c48] dark:border-[#3a3937] dark:bg-[#232220] dark:text-[#f1ede4]">
                  {item}
                </span>
                {index < plan.executionOrder.length - 1 ? <span className="text-[#87867f]">→</span> : null}
              </span>
            ))
          ) : (
            <span className="text-[#87867f] dark:text-[#b0aea5]">当前没有执行顺序。</span>
          )}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {plan.edges.length > 0 ? (
          plan.edges.map((edge) => (
            <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]" key={`${edge.from}-${edge.to}-${edge.reason}`}>
              <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">
                {edge.from} → {edge.to}
              </div>
              <div className="mt-2 text-xs uppercase tracking-[0.18em] text-[#87867f] dark:text-[#8f8a82]">{edge.type || 'dependency'}</div>
              <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{edge.reason || '未注明原因。'}</p>
            </div>
          ))
        ) : (
          <ArtifactPanel content="当前没有跨任务依赖。多仓任务如果互相依赖，应在 Design 或 Plan 中补齐。" renderAs="plain" title="依赖边" />
        )}
      </div>

      {plan.coordinationPoints.length > 0 ? <ArtifactPanel content={plan.coordinationPoints.map((item) => `- ${item}`).join('\n')} title="协作点" /> : null}
    </div>
  )
}

function RepoPlanPanel({
  loading,
  markdown,
  onEdit,
  repo,
  repoId,
}: {
  loading: boolean
  markdown: string
  onEdit: () => void
  repo?: TaskRecord['repos'][number]
  repoId: string
}) {
  return (
    <div className="space-y-4">
      <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{repo?.displayName || repoId}</div>
            <div className="mt-1 break-all text-xs text-[#87867f] dark:text-[#8f8a82]">{repo?.path || repoId}</div>
          </div>
          <ActionButton disabled={loading} onClick={onEdit} tone="secondary">
            编辑 Markdown
          </ActionButton>
        </div>
      </div>
      <ArtifactPanel content={loading ? '正在读取仓库计划...' : markdown || '当前没有仓库级 plan.md。'} title={`${repoId} plan.md`} />
    </div>
  )
}

function buildPlanProgress(task: TaskRecord): PlanProgressStep[] {
  const log = task.artifacts['plan.log'] || ''
  const skillsBriefArtifact = task.artifacts['plan-skills-brief.md'] || ''
  const hasStarted = task.status === 'planning' || task.status === 'planned' || log.includes('=== PLAN START ===')
  const hasKnowledge = hasArtifact(skillsBriefArtifact) || log.includes('plan_skills_ok:')
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

function buildStructuredPlan(task: TaskRecord): StructuredPlan {
  const workItemsPayload = parseJSON(task.artifacts['plan-work-items.json'])
  const graphPayload = parseJSON(task.artifacts['plan-execution-graph.json'])
  const resultPayload = parseJSON(task.artifacts['plan-result.json'])
  const syncPayload = parseJSON(task.artifacts['plan-sync.json'])
  return {
    workItems: normalizePlanWorkItems(workItemsPayload.work_items),
    edges: normalizePlanEdges(graphPayload.edges),
    executionOrder: normalizeStringList(graphPayload.execution_order),
    parallelGroups: normalizeParallelGroups(graphPayload.parallel_groups),
    coordinationPoints: normalizeCoordinationPoints(graphPayload.coordination_points),
    gateStatus: asString(resultPayload.gate_status),
    codeAllowed: typeof resultPayload.code_allowed === 'boolean' ? resultPayload.code_allowed : null,
    blockers: normalizeStringList(resultPayload.blockers),
    sync: {
      synced: typeof syncPayload.synced === 'boolean' ? syncPayload.synced : null,
      status: asString(syncPayload.status),
      reason: asString(syncPayload.reason),
      changedArtifact: asString(syncPayload.changed_artifact) || asString(syncPayload.changedArtifact),
      repoId: asString(syncPayload.repo_id) || asString(syncPayload.repoId),
      updatedAt: asString(syncPayload.updated_at) || asString(syncPayload.updatedAt),
    },
  }
}

function normalizePlanReadiness(raw: Record<string, unknown>): PlanReadinessScore | null {
  const score = asNumber(raw.score)
  if (score === null) {
    return null
  }
  return {
    task_id: asString(raw.task_id),
    generated_at: asString(raw.generated_at),
    score,
    status: asString(raw.status),
    formula: asString(raw.formula),
    inputs: normalizeNumberRecord(raw.inputs),
    sections: normalizeReadinessSections(raw.sections),
    recommendations: normalizeStringList(raw.recommendations),
    notes: normalizeStringList(raw.notes),
  }
}

function normalizeReadinessSections(raw: unknown): PlanReadinessScore['sections'] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map(normalizeReadinessSection).filter((item): item is PlanReadinessScore['sections'][number] => Boolean(item))
}

function normalizeReadinessSection(raw: unknown): PlanReadinessScore['sections'][number] | null {
  const current = asRecord(raw)
  const id = asString(current.id)
  if (!id) {
    return null
  }
  return {
    id,
    label: asString(current.label) || id,
    weight: asNumber(current.weight) ?? 0,
    score: asNumber(current.score) ?? 0,
    reason: asString(current.reason),
    children: normalizeReadinessMetrics(current.children),
  }
}

function normalizeReadinessMetrics(raw: unknown): PlanReadinessScore['sections'][number]['children'] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .map((entry) => {
      const current = asRecord(entry)
      const id = asString(current.id)
      if (!id) {
        return null
      }
      return {
        id,
        label: asString(current.label) || id,
        weight: asNumber(current.weight) ?? 0,
        score: asNumber(current.score) ?? 0,
        reason: asString(current.reason),
      }
    })
    .filter((entry): entry is PlanReadinessScore['sections'][number]['children'][number] => Boolean(entry))
}

function normalizeNumberRecord(raw: unknown): Record<string, number> {
  const current = asRecord(raw)
  const result: Record<string, number> = {}
  Object.entries(current).forEach(([key, value]) => {
    const numberValue = asNumber(value)
    if (numberValue !== null) {
      result[key] = numberValue
    }
  })
  return result
}

function readinessStatus(readiness: PlanReadinessScore | null) {
  if (!readiness) {
    return {
      label: '未评测',
      className: 'border-[#d1cfc5] bg-[#f5f4ed] text-[#5e5d59] dark:border-[#3a3937] dark:bg-[#232220] dark:text-[#b0aea5]',
    }
  }
  if (readiness.status === 'ready' || readiness.score >= 85) {
    return {
      label: '可以进入 Code',
      className: 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]',
    }
  }
  if (readiness.status === 'review' || readiness.score >= 70) {
    return {
      label: '建议人工 Review',
      className: 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]',
    }
  }
  return {
    label: '回到 Design / Plan 修正',
    className: 'border-[#efb1a4] bg-[#fff1ed] text-[#9c3524] dark:border-[#7b3a31] dark:bg-[#321c18] dark:text-[#ffb4a8]',
  }
}

function formatReadinessTime(value: string) {
  if (!value) {
    return '未知'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function normalizePlanWorkItems(raw: unknown): PlanWorkItem[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .map((entry) => {
      const current = asRecord(entry)
      const id = asString(current.id)
      const repoId = asString(current.repo_id) || asString(current.repoId)
      if (!id || !repoId) {
        return null
      }
      return {
        id,
        repoId,
        title: asString(current.title),
        goal: asString(current.goal),
        changeScope: normalizeStringList(current.change_scope ?? current.changeScope),
        specificSteps: normalizeStringList(current.specific_steps ?? current.specificSteps),
        dependsOn: normalizeStringList(current.depends_on ?? current.dependsOn),
        blocks: normalizeStringList(current.blocks),
      } satisfies PlanWorkItem
    })
    .filter((entry): entry is PlanWorkItem => Boolean(entry))
}

function normalizePlanEdges(raw: unknown): PlanEdge[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .map((entry) => {
      const current = asRecord(entry)
      const from = asString(current.from)
      const to = asString(current.to)
      if (!from || !to) {
        return null
      }
      return {
        from,
        to,
        type: asString(current.type),
        reason: asString(current.reason),
      } satisfies PlanEdge
    })
    .filter((entry): entry is PlanEdge => Boolean(entry))
}

function normalizeParallelGroups(raw: unknown) {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map((entry) => normalizeStringList(entry)).filter((entry) => entry.length > 0)
}

function normalizeCoordinationPoints(raw: unknown) {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw
    .map((entry) => {
      if (typeof entry === 'string') {
        return entry
      }
      const current = asRecord(entry)
      return [asString(current.id), asString(current.title), asString(current.reason)].filter(Boolean).join(': ')
    })
    .filter(Boolean)
}

function parseJSON(content: string | undefined): Record<string, unknown> {
  if (!content?.trim()) {
    return {}
  }
  try {
    const payload = JSON.parse(content)
    return asRecord(payload)
  } catch {
    return {}
  }
}

function normalizeStringList(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return []
  }
  return raw.map((item) => asString(item)).filter(Boolean)
}

function asRecord(raw: unknown): Record<string, unknown> {
  return raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {}
}

function asString(raw: unknown) {
  if (typeof raw === 'string') {
    return raw.trim()
  }
  if (typeof raw === 'number' || typeof raw === 'boolean') {
    return String(raw)
  }
  return ''
}

function asNumber(raw: unknown) {
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return raw
  }
  if (typeof raw === 'string' && raw.trim()) {
    const parsed = Number(raw)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function editTitle(editingTab: PlanEditingTab, repoId: string) {
  if (editingTab === 'repo') {
    return `编辑 ${repoId} Plan`
  }
  return '编辑 Plan 原文'
}

function editDescription(editingTab: PlanEditingTab, repoId: string) {
  if (editingTab === 'repo') {
    return `这里编辑 ${repoId} 的仓库级执行计划。`
  }
  return '这里编辑 Plan 阶段生成的执行方案原文。'
}

function editHint(editingTab: PlanEditingTab) {
  if (editingTab === 'repo') {
    return '保存后只覆盖该仓的 plan.md，并标记执行契约未同步；需要点击“同步执行契约”后才能进入 Code。'
  }
  return '保存后会覆盖 plan.md，并标记执行契约未同步；需要点击“同步执行契约”后才能进入 Code。'
}

function editPlaceholder(editingTab: PlanEditingTab) {
  if (editingTab === 'repo') {
    return '请输入该仓库的 Plan 文档...'
  }
  return '请输入 Plan 文档...'
}
