import { useEffect, useMemo, useState } from 'react'
import type { TaskArtifactName, TaskRecord } from '../api'
import { ArtifactViewer, artifactLabel } from './artifact-viewer'
import { DiffPanel } from './diff-panel'
import { RepoStatusBadge } from './ui-primitives'

export type WorkbenchPane = 'docs' | 'logs' | 'result' | 'diff'

const paneArtifacts: Record<Exclude<WorkbenchPane, 'diff'>, TaskArtifactName[]> = {
  docs: ['prd.source.md', 'prd-refined.md', 'design.md', 'plan.md'],
  logs: ['refine.log', 'plan.log', 'code.log'],
  result: ['code-result.json', 'diff.json', 'diff.patch'],
}

const repoStatusPriority: Record<TaskRecord['repos'][number]['status'], number> = {
  coding: 0,
  failed: 1,
  planned: 2,
  refined: 3,
  initialized: 4,
  pending: 5,
  coded: 6,
  archived: 7,
}

export function TaskWorkbench({
  actionBusy,
  archivingRepo,
  artifact,
  artifactContent,
  artifactRepo,
  artifactSaving,
  canEditArtifact,
  codeStartingRepo,
  focusToken,
  forcedPane,
  hasGeneratedPlan,
  lastRefreshedAt,
  onArchive,
  onArtifactChange,
  onArtifactRepoChange,
  onEditArtifact,
  onPaneChange,
  onReset,
  onReviewDiff,
  onReviewResult,
  onSelectDiffRepo,
  onStartCode,
  polling,
  resettingRepo,
  selectedDiffRepo,
  task,
}: {
  actionBusy: boolean
  archivingRepo: string | null
  artifact: TaskArtifactName
  artifactContent: string
  artifactRepo: string
  artifactSaving: boolean
  canEditArtifact: boolean
  codeStartingRepo: string | null
  focusToken: number
  forcedPane: WorkbenchPane | null
  hasGeneratedPlan: boolean
  lastRefreshedAt: string
  onArchive: (repoId: string) => Promise<void>
  onArtifactChange: (artifact: TaskArtifactName) => void
  onArtifactRepoChange: (repoId: string) => void
  onEditArtifact: () => void
  onPaneChange?: (pane: WorkbenchPane) => void
  onReset: (repoId: string) => Promise<void>
  onReviewDiff: (repoId: string) => void
  onReviewResult: (repoId: string) => void
  onSelectDiffRepo: (repoId: string) => void
  onStartCode: (repoId: string) => Promise<void>
  polling: boolean
  resettingRepo: string | null
  selectedDiffRepo: string
  task: TaskRecord
}) {
  const [pane, setPane] = useState<WorkbenchPane>(() => resolvePane(artifact))
  const orderedRepos = useMemo(
    () =>
      [...task.repos].sort((left, right) => {
        const priorityGap = (repoStatusPriority[left.status] ?? 99) - (repoStatusPriority[right.status] ?? 99)
        if (priorityGap !== 0) {
          return priorityGap
        }
        return left.id.localeCompare(right.id)
      }),
    [task.repos],
  )
  const availableArtifacts = useMemo(
    () =>
      ({
        docs: paneArtifacts.docs.filter((name) => name in task.artifacts),
        logs: paneArtifacts.logs.filter((name) => name in task.artifacts),
        result: paneArtifacts.result.filter((name) => name in task.artifacts),
      }) satisfies Record<Exclude<WorkbenchPane, 'diff'>, TaskArtifactName[]>,
    [task.artifacts],
  )

  useEffect(() => {
    setPane(resolvePane(artifact))
  }, [artifact])

  useEffect(() => {
    if (!forcedPane) {
      return
    }
    setPane(forcedPane)
  }, [forcedPane, focusToken])

  const repoScopedArtifact =
    task.repos.length > 1 &&
    (artifact === 'code.log' || artifact === 'code-result.json' || artifact === 'diff.json' || artifact === 'diff.patch')
  const activeRepoID = artifactRepo || selectedDiffRepo || orderedRepos[0]?.id || ''
  const activeRepo = orderedRepos.find((repo) => repo.id === activeRepoID) ?? orderedRepos[0] ?? null
  const liveArtifact = resolveLiveArtifact(task.status)
  const artifactLive = polling && liveArtifact === artifact
  const canStartCode = activeRepo ? canStartCodeForRepo(activeRepo, hasGeneratedPlan) : false
  const canResetCode = activeRepo ? canResetCodeForRepo(activeRepo) : false
  const canArchiveCode = activeRepo ? canArchiveCodeForRepo(activeRepo) : false
  const hasResult = activeRepo ? hasRepoResult(activeRepo) : false
  const hasDiff = activeRepo ? Boolean(activeRepo.diffSummary) : false

  function switchPane(nextPane: WorkbenchPane) {
    setPane(nextPane)
    onPaneChange?.(nextPane)
    if (nextPane === 'diff') {
      return
    }

    const nextArtifacts = availableArtifacts[nextPane]
    if (!nextArtifacts.includes(artifact)) {
      onArtifactChange(nextArtifacts[0] ?? paneArtifacts[nextPane][0])
    }
  }

  function selectRepo(repoId: string) {
    onArtifactRepoChange(repoId)
    onSelectDiffRepo(repoId)
  }

  function openRepoResult(repoId: string) {
    selectRepo(repoId)
    onArtifactChange('code-result.json')
    switchPane('result')
    onReviewResult(repoId)
  }

  function openRepoDiff(repoId: string) {
    selectRepo(repoId)
    switchPane('diff')
    onReviewDiff(repoId)
  }

  return (
    <section className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Workbench</div>
          <h4 className="mt-2 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
            阅读工作台
          </h4>
        </div>
        <div className="text-sm text-[#87867f] dark:text-[#b0aea5]">统一查看文档、日志、结果、Diff 和仓库动作</div>
      </div>

      {activeRepo ? (
        <div className="mb-4 rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">仓库上下文</div>
              <div className="mt-2 text-[24px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                {activeRepo.displayName}
              </div>
            </div>
            <RepoStatusBadge status={activeRepo.status} />
          </div>

          {orderedRepos.length > 1 ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {orderedRepos.map((repo) => (
                <button
                  className={`rounded-full border px-3 py-2 text-sm transition ${
                    repo.id === activeRepo.id
                      ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
                      : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                  }`}
                  key={repo.id}
                  onClick={() => selectRepo(repo.id)}
                  type="button"
                >
                  {repo.id}
                </button>
              ))}
            </div>
          ) : null}

          <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1.3fr)_minmax(260px,0.7fr)]">
            <div>
              <div className="text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{repoWorkbenchSummary(activeRepo)}</div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetaTile label="仓库标识" value={activeRepo.id} />
                <MetaTile label="构建结果" value={buildLabel(activeRepo.build)} />
                <MetaTile label="分支" value={activeRepo.branch ?? '尚未创建'} mono />
                <MetaTile label="工作区" value={activeRepo.worktree ?? '尚未创建'} mono />
              </div>
              <div className="mt-3 rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] px-4 py-3 text-sm text-[#87867f] shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
                {activeRepo.path}
              </div>
            </div>

            <div className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">当前动作</div>
              <div className="mt-4 flex flex-wrap gap-2">
                {canStartCode ? (
                  <RepoActionButton
                    disabled={actionBusy}
                    onClick={() => void onStartCode(activeRepo.id)}
                    tone="brand"
                  >
                    {codeStartingRepo === activeRepo.id ? '实现进行中...' : activeRepo.status === 'failed' ? '重试实现' : '开始实现'}
                  </RepoActionButton>
                ) : null}
                {canResetCode ? (
                  <RepoActionButton
                    disabled={actionBusy}
                    onClick={() => void onReset(activeRepo.id)}
                    tone="danger"
                  >
                    {resettingRepo === activeRepo.id ? '回退中...' : '回退实现'}
                  </RepoActionButton>
                ) : null}
                {canArchiveCode ? (
                  <RepoActionButton
                    disabled={actionBusy}
                    onClick={() => void onArchive(activeRepo.id)}
                    tone="neutral"
                  >
                    {archivingRepo === activeRepo.id ? '归档中...' : '归档任务'}
                  </RepoActionButton>
                ) : null}
                {hasResult ? (
                  <RepoActionButton disabled={false} onClick={() => openRepoResult(activeRepo.id)} tone="neutral">
                    查看结果
                  </RepoActionButton>
                ) : null}
                {hasDiff ? (
                  <RepoActionButton disabled={false} onClick={() => openRepoDiff(activeRepo.id)} tone="neutral">
                    查看 Diff
                  </RepoActionButton>
                ) : null}
              </div>

              {activeRepo.failureHint ? (
                <div className="mt-4 rounded-[18px] border border-[#e1c1bf] bg-[#fbf1f0] px-4 py-3 text-sm leading-6 text-[#b53333]">
                  <div className="text-[10px] uppercase tracking-[0.5px] opacity-80">失败摘要</div>
                  <div className="mt-2 font-mono text-xs leading-6">{activeRepo.failureHint}</div>
                  {activeRepo.failureAction ? <div className="mt-2 text-xs leading-5">建议：{activeRepo.failureAction}</div> : null}
                </div>
              ) : null}

              <div className="mt-4 text-xs text-[#87867f] dark:text-[#b0aea5]">
                {activeRepo.filesWritten && activeRepo.filesWritten.length > 0
                  ? `已写入 ${activeRepo.filesWritten.length} 个文件`
                  : '当前还没有写入结果'}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="mb-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-2 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
        <div className="flex flex-wrap gap-2">
          <PaneButton active={pane === 'docs'} label="文档" onClick={() => switchPane('docs')} />
          <PaneButton active={pane === 'logs'} label="日志" onClick={() => switchPane('logs')} />
          <PaneButton active={pane === 'result'} label="结果" onClick={() => switchPane('result')} />
          <PaneButton active={pane === 'diff'} label="Diff" onClick={() => switchPane('diff')} />
        </div>
      </div>

      {pane !== 'diff' ? (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {availableArtifacts[pane].map((name) => (
              <button
                className={`rounded-full border px-3 py-2 text-sm transition ${
                  artifact === name
                    ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
                    : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                }`}
                key={name}
                onClick={() => onArtifactChange(name)}
                type="button"
              >
                {artifactLabel(name)}
              </button>
            ))}
          </div>

          <ArtifactViewer
            artifact={artifact}
            canEdit={canEditArtifact && !repoScopedArtifact && !artifactLive}
            content={artifactContent}
            isLive={artifactLive}
            liveLabel={artifactLive ? resolveLiveLabel(task.status) : ''}
            lastRefreshedAt={artifactLive ? lastRefreshedAt : ''}
            onEdit={onEditArtifact}
            saving={artifactSaving}
            sourcePath={repoScopedArtifact && activeRepoID ? `task/${task.id}/repos/${activeRepoID}/${artifact}` : undefined}
            taskID={task.id}
          />
        </>
      ) : (
        <DiffPanel repos={task.repos} selectedRepo={selectedDiffRepo || activeRepoID} onSelectRepo={selectRepo} />
      )}
    </section>
  )
}

function PaneButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      className={`rounded-full border px-3 py-2 text-sm transition ${
        active
          ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
          : 'border-transparent bg-[#faf9f5] text-[#5e5d59] hover:border-[#e8e6dc] hover:text-[#141413] dark:bg-transparent dark:text-[#b0aea5] dark:hover:border-[#30302e] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function MetaTile({
  label,
  mono,
  value,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="rounded-[16px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-3 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">{label}</div>
      <div className={`mt-2 text-sm text-[#141413] dark:text-[#faf9f5] ${mono ? 'font-mono text-xs' : ''}`}>{value}</div>
    </div>
  )
}

function RepoActionButton({
  children,
  disabled,
  onClick,
  tone,
}: {
  children: string
  disabled?: boolean
  onClick: () => void
  tone: 'brand' | 'danger' | 'neutral'
}) {
  const toneClass =
    tone === 'brand'
      ? 'border-[#c96442] bg-[#c96442] text-[#faf9f5] hover:bg-[#d97757]'
      : tone === 'danger'
        ? 'border-[#e1c1bf] bg-[#fbf1f0] text-[#b53333] hover:bg-[#f7e6e4]'
        : 'border-[#d1cfc5] bg-[#e8e6dc] text-[#4d4c48] hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]'

  return (
    <button
      className={`rounded-[12px] border px-4 py-2.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-60 ${toneClass}`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

function resolvePane(artifact: TaskArtifactName): WorkbenchPane {
  if (artifact === 'code-result.json' || artifact === 'diff.json' || artifact === 'diff.patch') {
    return 'result'
  }
  if (artifact.endsWith('.log')) {
    return 'logs'
  }
  return 'docs'
}

function resolveLiveArtifact(status: TaskRecord['status']): TaskArtifactName | '' {
  switch (status) {
    case 'initialized':
      return 'refine.log'
    case 'planning':
      return 'plan.log'
    case 'coding':
      return 'code.log'
    default:
      return ''
  }
}

function resolveLiveLabel(status: TaskRecord['status']) {
  switch (status) {
    case 'initialized':
      return 'Refine Live'
    case 'planning':
      return 'Plan Live'
    case 'coding':
      return 'Code Live'
    default:
      return 'Live'
  }
}

function hasRepoResult(repo: TaskRecord['repos'][number]) {
  return Boolean(repo.commit || (repo.filesWritten && repo.filesWritten.length > 0) || repo.build === 'passed' || repo.build === 'failed')
}

function buildLabel(value?: TaskRecord['repos'][number]['build']) {
  if (value === 'passed') {
    return '已通过'
  }
  if (value === 'failed') {
    return '未通过'
  }
  return '待生成'
}

function repoWorkbenchSummary(repo: TaskRecord['repos'][number]) {
  switch (repo.status) {
    case 'coding':
      return '正在后台生成实现并验证结果，适合先看日志，再决定是否继续等待。'
    case 'failed':
      return repo.failureAction || '这次推进失败了，建议先看结果或 Diff，再决定重试还是回退。'
    case 'planned':
      return '方案已经准备好，这个仓库可以直接开始实现。'
    case 'coded':
      return '实现已经完成，可以查看结果、核对 Diff，或直接归档收尾。'
    case 'archived':
      return '这个仓库已经归档，结果还在，但执行环境已经清理。'
    default:
      return '当前还没有进入实现阶段。'
  }
}

function canStartCodeForRepo(repo: TaskRecord['repos'][number], hasGeneratedPlan: boolean) {
  if (!hasGeneratedPlan) {
    return false
  }
  return repo.status === 'planned' || repo.status === 'failed'
}

function canResetCodeForRepo(repo: TaskRecord['repos'][number]) {
  return repo.status === 'coded' || repo.status === 'failed'
}

function canArchiveCodeForRepo(repo: TaskRecord['repos'][number]) {
  return repo.status === 'coded'
}
