import type { RepoResult, TaskRecord } from '../../../api'
import { getTaskArtifact } from '../../../api'
import { useEffect, useMemo, useState } from 'react'
import { ArtifactPanel, NotePanel, SectionCard, TabButton, TaskStatusBadge } from '../ui'
import { codeActionLabelForRepo, executableCodeRepoCount, executableCodeRepos, preferredCodeRepo, repoReadyForCode } from '../model'

type ResultTab = 'result' | 'verify' | 'diff' | 'log'

export function CodeStage({
  task,
  busyAction,
  onStartCode,
}: {
  task: TaskRecord
  busyAction: string
  onStartCode: (repoId?: string) => Promise<void> | void
}) {
  const orderedRepos = useMemo(
    () =>
      [...executableCodeRepos(task)].sort((left, right) => {
        const indexGap = (left.executionIndex ?? Number.MAX_SAFE_INTEGER) - (right.executionIndex ?? Number.MAX_SAFE_INTEGER)
        if (indexGap !== 0) {
          return indexGap
        }
        return left.id.localeCompare(right.id)
      }),
    [task],
  )
  const hiddenReferenceRepoCount = Math.max(task.repos.length - executableCodeRepoCount(task), 0)
  const [selectedRepoID, setSelectedRepoID] = useState(preferredCodeRepo(task)?.id ?? orderedRepos[0]?.id ?? '')
  const [resultTab, setResultTab] = useState<ResultTab>('result')
  const [repoResult, setRepoResult] = useState('')
  const [repoLog, setRepoLog] = useState('')
  const [repoFetchError, setRepoFetchError] = useState('')
  const [repoLoading, setRepoLoading] = useState(false)

  useEffect(() => {
    setSelectedRepoID(preferredCodeRepo(task)?.id ?? orderedRepos[0]?.id ?? '')
  }, [orderedRepos, task.id, task.codeProgress.activeRepoId])

  const selectedRepo = useMemo(
    () => orderedRepos.find((repo) => repo.id === selectedRepoID) ?? preferredCodeRepo(task) ?? null,
    [orderedRepos, selectedRepoID, task],
  )

  useEffect(() => {
    if (!selectedRepo) {
      setRepoResult('')
      setRepoLog('')
      setRepoFetchError('')
      return
    }
    const repoId = selectedRepo.id
    let cancelled = false
    async function run() {
      try {
        setRepoLoading(true)
        setRepoFetchError('')
        const [resultResponse, logResponse] = await Promise.allSettled([
          getTaskArtifact(task.id, 'code-result.json', repoId),
          getTaskArtifact(task.id, 'code.log', repoId),
        ])
        if (cancelled) {
          return
        }
        setRepoResult(resultResponse.status === 'fulfilled' ? resultResponse.value.content : '')
        setRepoLog(logResponse.status === 'fulfilled' ? logResponse.value.content : '')
      } catch (error) {
        if (!cancelled) {
          setRepoFetchError(error instanceof Error ? error.message : '加载仓库结果失败')
        }
      } finally {
        if (!cancelled) {
          setRepoLoading(false)
        }
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [selectedRepo, task.id])

  if (orderedRepos.length === 0) {
    return (
      <SectionCard title="阶段详情">
        <NotePanel content="当前还没有绑定仓库，暂时无法展示 Code Progress 或 Repo Queue。" />
      </SectionCard>
    )
  }

  return (
    <SectionCard title="阶段详情">
      <div className="space-y-5">
        <CodeProgressPanel hiddenReferenceRepoCount={hiddenReferenceRepoCount} task={task} />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
          <RepoQueuePanel repos={orderedRepos} selectedRepoID={selectedRepo?.id ?? ''} onSelectRepo={setSelectedRepoID} />
          <ExecutionDetailPanel busyAction={busyAction} onStartCode={onStartCode} repo={selectedRepo} />
        </div>

        <ResultTabsPanel
          busy={repoLoading}
          error={repoFetchError}
          logContent={repoLog || task.artifacts['code.log'] || '当前没有可用的执行日志。'}
          repo={selectedRepo}
          resultContent={repoResult}
          tab={resultTab}
          task={task}
          onTabChange={setResultTab}
        />
      </div>
    </SectionCard>
  )
}

function CodeProgressPanel({ task, hiddenReferenceRepoCount }: { task: TaskRecord; hiddenReferenceRepoCount: number }) {
  const progress = task.codeProgress
  const activeTone =
    task.status === 'coding'
      ? 'bg-[#4fa06d]'
      : task.status === 'coded'
        ? 'bg-[#2c8c58]'
        : task.status === 'failed'
          ? 'bg-[#c96442]'
          : 'bg-[#cdbda6] dark:bg-[#4a4640]'

  return (
    <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Code Progress</div>
          <div className="mt-2 text-sm text-[#5e5d59] dark:text-[#b0aea5]">{progress.activeLabel || progress.summary}</div>
          <div className="mt-2 text-sm leading-6 text-[#141413] dark:text-[#faf9f5]">{progress.summary}</div>
          {hiddenReferenceRepoCount > 0 ? (
            <div className="mt-3 inline-flex max-w-full items-center rounded-full border border-dashed border-[#d8d3c8] bg-[#f5f4ed] px-3 py-1 text-xs text-[#8a7a67] dark:border-[#3a3937] dark:bg-[#232220] dark:text-[#8f8a82]">
              另有 {hiddenReferenceRepoCount} 个 `reference_only` 仓库仅作参考，不进入执行队列。
            </div>
          ) : null}
        </div>
        <div className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
          {progress.progressPercent}%
        </div>
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#efeae0] dark:bg-[#232220]">
        <div className={`h-full rounded-full transition-all duration-300 ${activeTone}`} style={{ width: `${progress.progressPercent}%` }} />
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-6">
        <StatPill label="ready" value={progress.counts.ready} />
        <StatPill label="running" value={progress.counts.running} />
        <StatPill label="blocked" value={progress.counts.blocked} />
        <StatPill label="failed" value={progress.counts.failed} />
        <StatPill label="done" value={progress.counts.done} />
        <StatPill label="reference" value={progress.counts.reference} />
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-5">
        {progress.steps.map((step) => (
          <div
            className={`rounded-[14px] border px-3 py-2 text-xs ${
              step.state === 'done'
                ? 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]'
                : step.state === 'current'
                  ? 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]'
                  : 'border-[#e8e6dc] bg-[#f5f4ed] text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#8f8a82]'
            }`}
            key={step.key}
          >
            {step.label}
          </div>
        ))}
      </div>
    </div>
  )
}

function RepoQueuePanel({
  repos,
  selectedRepoID,
  onSelectRepo,
}: {
  repos: RepoResult[]
  selectedRepoID: string
  onSelectRepo: (repoId: string) => void
}) {
  return (
    <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Repo Queue</div>
          <div className="mt-2 text-sm text-[#5e5d59] dark:text-[#b0aea5]">按执行顺序查看每个仓的 queue state、scope tier 和动作语义。</div>
        </div>
      </div>

      <div className="mt-4 space-y-3">
        {repos.map((repo, index) => {
          const selected = repo.id === selectedRepoID
          return (
            <button
              className={`w-full rounded-[18px] border px-4 py-4 text-left transition ${
                selected
                  ? 'border-[#d56b45] bg-[#fff3ee] shadow-[0_0_0_1px_rgba(213,107,69,0.28)] dark:border-[#c77b61] dark:bg-[#2a211b]'
                  : 'border-[#e7d8c0] bg-[#fffaf2] hover:bg-[#fff6ea] dark:border-[#4a4033] dark:bg-[#211d18] dark:hover:bg-[#29241e]'
              }`}
              key={repo.id}
              onClick={() => onSelectRepo(repo.id)}
              type="button"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#dbc9b3] text-lg text-[#7c5d3d] dark:border-[#5a4a38] dark:text-[#d7c2a6]">
                    {index + 1}
                  </div>
                  <div>
                    <div className="text-[18px] font-medium text-[#5a3a28] dark:text-[#f3e5d6]">{repo.displayName}</div>
                    <div className="mt-1 text-xs text-[#8a7a67] dark:text-[#b8ae9e]">{repo.path}</div>
                  </div>
                </div>
                <TaskStatusBadge status={mapRepoStatus(repo)} />
              </div>

              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <QueuePill label={queueLabel(repo.queueState)} tone={queueTone(repo.queueState)} />
                <QueuePill label={scopeTierLabel(repo.scopeTier)} tone="neutral" />
                <QueuePill label={executionModeLabel(repo.executionMode)} tone="neutral" />
              </div>

              {repo.blockedBy && repo.blockedBy.length > 0 ? (
                <div className="mt-3 text-xs leading-5 text-[#8a7a67] dark:text-[#b8ae9e]">blocked by: {repo.blockedBy.join(', ')}</div>
              ) : null}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function ExecutionDetailPanel({
  repo,
  busyAction,
  onStartCode,
}: {
  repo: RepoResult | null
  busyAction: string
  onStartCode: (repoId?: string) => Promise<void> | void
}) {
  if (!repo) {
    return <NotePanel content="当前没有可展示的执行细节。" />
  }

  const canTrigger = repoReadyForCode(repo)
  const actionLabel = codeActionLabelForRepo(repo)
  const triggerDisabled = !canTrigger || busyAction === 'code'

  return (
    <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Execution Detail</div>
          <div className="mt-2 text-[26px] leading-none font-medium text-[#141413] dark:text-[#faf9f5]">{repo.displayName}</div>
        </div>
        <TaskStatusBadge status={mapRepoStatus(repo)} />
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-2">
        <InfoPill label="scope_tier" value={scopeTierLabel(repo.scopeTier)} />
        <InfoPill label="mode" value={executionModeLabel(repo.executionMode)} />
        <InfoPill label="batch" value={repo.workItems?.map((item) => item.id).join(', ') || 'n/a'} />
        <InfoPill label="branch" value={repo.branch ?? '尚未创建'} />
      </div>

      {repo.rationale ? (
        <div className="mt-4 rounded-[16px] border border-[#ece6da] bg-[#fffaf2] px-4 py-3 text-sm leading-6 text-[#5e5d59] dark:border-[#383632] dark:bg-[#11100f] dark:text-[#b0aea5]">
          <div className="text-[10px] uppercase tracking-[0.35em] text-[#87867f] dark:text-[#8f8a82]">Decision</div>
          <div className="mt-2">{repo.rationale}</div>
        </div>
      ) : null}

      {repo.blockedBy && repo.blockedBy.length > 0 ? (
        <div className="mt-4 rounded-[16px] border border-[#d9c9a7] bg-[#fff7e8] px-4 py-3 text-sm leading-6 text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]">
          当前受阻塞：{repo.blockedBy.join(', ')}
        </div>
      ) : null}

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <DetailList
          empty="当前没有结构化 work items。"
          items={repo.workItems?.map((item) => `${item.id} · ${item.title}`) ?? []}
          title="Work Items"
        />
        <DetailList empty="当前没有 change scope。" items={repo.changeScope ?? []} title="Change Scope" />
        <DetailList empty="当前没有 done definition。" items={repo.doneDefinition ?? []} title="Done Definition" />
        <DetailList empty="当前没有 verification rules。" items={repo.verificationSteps ?? []} title="Verify Rules" />
      </div>

      {repo.executionMode !== 'reference_only' ? (
        <button
          className="mt-5 rounded-[16px] border border-[#d56b45] bg-[#d56b45] px-6 py-3 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(213,107,69,1)] transition hover:bg-[#df7b57] disabled:cursor-not-allowed disabled:opacity-55"
          disabled={triggerDisabled}
          onClick={() => void onStartCode(repo.id)}
          type="button"
        >
          {busyAction === 'code' && canTrigger ? '执行中...' : actionLabel}
        </button>
      ) : (
        <div className="mt-5 rounded-[16px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-3 text-sm text-[#8a7a67] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#8f8a82]">
          这个仓库属于 reference_only，本轮不提供执行按钮。
        </div>
      )}
    </div>
  )
}

function ResultTabsPanel({
  task,
  repo,
  tab,
  resultContent,
  logContent,
  error,
  busy,
  onTabChange,
}: {
  task: TaskRecord
  repo: RepoResult | null
  tab: ResultTab
  resultContent: string
  logContent: string
  error: string
  busy: boolean
  onTabChange: (tab: ResultTab) => void
}) {
  const diffContent = repo?.diffSummary?.patch || '当前没有可用的 diff patch。'
  const verifySummary = buildVerifySummary(repo)
  const resultSummary = buildResultSummary(repo, resultContent)

  return (
    <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-[#87867f] dark:text-[#b0aea5]">Result Tabs</div>
          <div className="mt-2 text-sm text-[#5e5d59] dark:text-[#b0aea5]">{repo ? `${repo.displayName} 的执行结果、验证、Diff 和日志。` : '当前没有选中的 repo。'}</div>
        </div>
        {repo ? <TaskStatusBadge status={mapRepoStatus(repo)} /> : null}
      </div>

      <div className="mt-4 inline-flex flex-wrap rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
        <TabButton active={tab === 'result'} onClick={() => onTabChange('result')}>
          结果
        </TabButton>
        <TabButton active={tab === 'verify'} onClick={() => onTabChange('verify')}>
          验证
        </TabButton>
        <TabButton active={tab === 'diff'} onClick={() => onTabChange('diff')}>
          Diff
        </TabButton>
        <TabButton active={tab === 'log'} onClick={() => onTabChange('log')}>
          日志
        </TabButton>
      </div>

      {error ? <div className="mt-4 text-sm text-[#b53333]">{error}</div> : null}
      {busy ? <div className="mt-4 text-sm text-[#8a7a67] dark:text-[#b8ae9e]">正在加载仓库结果...</div> : null}

      <div className="mt-4">
        {tab === 'result' ? <ArtifactPanel content={resultSummary} renderAs="plain" title="repo result" /> : null}
        {tab === 'verify' ? <ArtifactPanel content={verifySummary} renderAs="plain" title="verification summary" /> : null}
        {tab === 'diff' ? <ArtifactPanel content={diffContent} renderAs="plain" title="diff.patch" /> : null}
        {tab === 'log' ? <ArtifactPanel content={logContent || task.artifacts['code.log'] || '当前没有 code 日志。'} renderAs="plain" title="code.log" /> : null}
      </div>
    </div>
  )
}

function DetailList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="rounded-[16px] border border-[#ece6da] bg-[#fffaf2] px-4 py-3 dark:border-[#383632] dark:bg-[#11100f]">
      <div className="text-[10px] uppercase tracking-[0.35em] text-[#87867f] dark:text-[#8f8a82]">{title}</div>
      <div className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
        {items.length > 0 ? (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          empty
        )}
      </div>
    </div>
  )
}

function StatPill({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[14px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-2 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
      <div className="uppercase tracking-[0.35em]">{label}</div>
      <div className="mt-1 text-base text-[#141413] dark:text-[#faf9f5]">{value}</div>
    </div>
  )
}

function QueuePill({ label, tone }: { label: string; tone: 'ready' | 'running' | 'blocked' | 'done' | 'failed' | 'neutral' | 'reference' }) {
  const toneClass =
    tone === 'ready'
      ? 'border-[#d7c28a] bg-[#fff4d6] text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]'
      : tone === 'running'
        ? 'border-[#c8d8e7] bg-[#f2f7fb] text-[#2f5571] dark:border-[#35506a] dark:bg-[#1f2830] dark:text-[#cfe6fb]'
        : tone === 'blocked'
          ? 'border-[#d9c9a7] bg-[#fff7e8] text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]'
          : tone === 'done'
            ? 'border-[#cfe2d2] bg-[#f3f7f1] text-[#35533d] dark:border-[#35533d] dark:bg-[#1f2a22] dark:text-[#d4ead7]'
            : tone === 'failed'
              ? 'border-[#e1c1bf] bg-[#fbf1f0] text-[#8f3732] dark:border-[#6a3431] dark:bg-[#2b1f1f] dark:text-[#f5d3d1]'
              : tone === 'reference'
                ? 'border-[#d1cfc5] bg-[#f5f4ed] text-[#655d52] dark:border-[#4a4640] dark:bg-[#26231f] dark:text-[#d9d2c6]'
                : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]'
  return <span className={`rounded-full border px-3 py-1 ${toneClass}`}>{label}</span>
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex items-center gap-3 rounded-full border border-[#e2d8cb] bg-[#fffaf2] px-4 py-3 text-sm dark:border-[#3d3934] dark:bg-[#11100f]">
      <span className="text-[#9a9185] dark:text-[#8f8a82]">{label}</span>
      <span className="text-[#141413] dark:text-[#faf9f5]">{value}</span>
    </div>
  )
}

function buildVerifySummary(repo: RepoResult | null) {
  if (!repo) {
    return '当前没有可用的验证信息。'
  }
  const lines = [
    `repo: ${repo.displayName}`,
    `mode: ${executionModeLabel(repo.executionMode)}`,
    `build: ${buildLabel(repo.build)}`,
  ]
  if (repo.verificationChecks && repo.verificationChecks.length > 0) {
    lines.push('', 'checks:')
    for (const check of repo.verificationChecks) {
      lines.push(`- ${check.label}: ${check.expectation}`)
    }
  } else if (repo.verificationSteps && repo.verificationSteps.length > 0) {
    lines.push('', 'rules:')
    for (const step of repo.verificationSteps) {
      lines.push(`- ${step}`)
    }
  } else {
    lines.push('', '当前没有结构化验证规则。')
  }
  if (repo.failureHint) {
    lines.push('', 'failure:')
    lines.push(repo.failureHint)
  }
  return lines.join('\n')
}

function buildResultSummary(repo: RepoResult | null, resultContent: string) {
  if (resultContent.trim()) {
    return resultContent
  }
  if (!repo) {
    return '当前没有可用的结果信息。'
  }
  const lines = [
    `repo: ${repo.displayName}`,
    `queue_state: ${queueLabel(repo.queueState)}`,
    `mode: ${executionModeLabel(repo.executionMode)}`,
    `build: ${buildLabel(repo.build)}`,
    `branch: ${repo.branch ?? '尚未创建'}`,
    `worktree: ${repo.worktree ?? '尚未创建'}`,
  ]
  if (repo.filesWritten && repo.filesWritten.length > 0) {
    lines.push('', 'files_written:')
    for (const file of repo.filesWritten) {
      lines.push(`- ${file}`)
    }
  }
  if (repo.failureAction) {
    lines.push('', `failure_action: ${repo.failureAction}`)
  }
  return lines.join('\n')
}

function mapRepoStatus(repo: RepoResult): TaskRecord['status'] {
  if (repo.status === 'coding') {
    return 'coding'
  }
  if (repo.status === 'coded') {
    return 'coded'
  }
  if (repo.status === 'archived') {
    return 'archived'
  }
  if (repo.status === 'failed') {
    return 'failed'
  }
  if (repo.status === 'planned') {
    return 'planned'
  }
  return 'initialized'
}

function buildLabel(value?: RepoResult['build']) {
  if (value === 'passed') {
    return '已通过'
  }
  if (value === 'failed') {
    return '未通过'
  }
  return '待生成'
}

function queueLabel(value?: RepoResult['queueState']) {
  switch (value) {
    case 'ready':
      return 'ready'
    case 'running':
      return 'running'
    case 'blocked':
      return 'blocked'
    case 'failed':
      return 'failed'
    case 'done':
      return 'done'
    case 'reference':
      return 'reference'
    default:
      return 'waiting'
  }
}

function queueTone(value?: RepoResult['queueState']): 'ready' | 'running' | 'blocked' | 'done' | 'failed' | 'reference' | 'neutral' {
  switch (value) {
    case 'ready':
      return 'ready'
    case 'running':
      return 'running'
    case 'blocked':
      return 'blocked'
    case 'done':
      return 'done'
    case 'failed':
      return 'failed'
    case 'reference':
      return 'reference'
    default:
      return 'neutral'
  }
}

function scopeTierLabel(value?: RepoResult['scopeTier']) {
  switch (value) {
    case 'must_change':
      return 'must_change'
    case 'co_change':
      return 'co_change'
    case 'validate_only':
      return 'validate_only'
    case 'reference_only':
      return 'reference_only'
    default:
      return 'unknown'
  }
}

function executionModeLabel(value?: RepoResult['executionMode']) {
  switch (value) {
    case 'verify_only':
      return '验证仓'
    case 'reference_only':
      return '参考仓'
    case 'apply':
      return '实现仓'
    default:
      return '待判定'
  }
}
