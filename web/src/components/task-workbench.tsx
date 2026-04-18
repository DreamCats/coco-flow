import { useEffect, useMemo, useState } from 'react'
import type { TaskArtifactName, TaskRecord } from '../api'
import { ArtifactViewer, artifactLabel } from './artifact-viewer'
import { DiffPanel } from './diff-panel'
import { RepoStatusBadge } from './ui-primitives'

export type WorkbenchPane = 'docs' | 'logs' | 'result' | 'diff'
type StageWorkbenchKind = 'refine' | 'design' | 'plan' | 'code' | 'archive'

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
  artifact,
  artifactContent,
  artifactRepo,
  artifactSaving,
  canEditArtifact,
  focusToken,
  forcedPane,
  lastRefreshedAt,
  onArtifactChange,
  onArtifactRepoChange,
  onEditArtifact,
  onPaneChange,
  onSelectDiffRepo,
  polling,
  selectedDiffRepo,
  task,
}: {
  artifact: TaskArtifactName
  artifactContent: string
  artifactRepo: string
  artifactSaving: boolean
  canEditArtifact: boolean
  focusToken: number
  forcedPane: WorkbenchPane | null
  lastRefreshedAt: string
  onArtifactChange: (artifact: TaskArtifactName) => void
  onArtifactRepoChange: (repoId: string) => void
  onEditArtifact: () => void
  onPaneChange?: (pane: WorkbenchPane) => void
  onSelectDiffRepo: (repoId: string) => void
  polling: boolean
  selectedDiffRepo: string
  task: TaskRecord
}) {
  const [pane, setPane] = useState<WorkbenchPane>(() => resolvePane(artifact))
  const stageProfile = useMemo(() => resolveStageProfile(task), [task])
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
  const liveArtifact = resolveLiveArtifact(task.status)
  const artifactLive = polling && liveArtifact === artifact
  const recommendedArtifacts = stageProfile.artifacts.filter((name) => availableArtifacts[resolveArtifactPane(name)].includes(name))

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

  return (
    <section className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Stage Workbench</div>
          <h4 className="mt-2 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
            {stageProfile.title}
          </h4>
        </div>
        <div className="text-sm text-[#87867f] dark:text-[#b0aea5]">{stageProfile.subtitle}</div>
      </div>

      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <div className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">默认视角</div>
          <div className="mt-2 text-sm leading-6 text-[#141413] dark:text-[#faf9f5]">{stageProfile.narrative}</div>
        </div>
        <div className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">推荐入口</div>
          <div className="mt-3 flex flex-wrap gap-2">
            {recommendedArtifacts.map((name) => (
              <StageArtifactButton
                active={artifact === name && pane !== 'diff'}
                key={name}
                label={artifactLabel(name)}
                onClick={() => {
                  onArtifactChange(name)
                  switchPane(resolveArtifactPane(name))
                }}
              />
            ))}
            {stageProfile.showDiffBrowser ? (
              <StageArtifactButton active={pane === 'diff'} label="Diff 浏览器" onClick={() => switchPane('diff')} />
            ) : null}
          </div>
        </div>
      </div>

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

function StageArtifactButton({
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
          : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
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

function resolvePane(artifact: TaskArtifactName): WorkbenchPane {
  if (artifact === 'code-result.json' || artifact === 'diff.json' || artifact === 'diff.patch') {
    return 'result'
  }
  if (artifact.endsWith('.log')) {
    return 'logs'
  }
  return 'docs'
}

function resolveArtifactPane(artifact: TaskArtifactName): Exclude<WorkbenchPane, 'diff'> {
  return resolvePane(artifact) as Exclude<WorkbenchPane, 'diff'>
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

function resolveStageProfile(task: TaskRecord): {
  kind: StageWorkbenchKind
  title: string
  subtitle: string
  narrative: string
  artifacts: TaskArtifactName[]
  showDiffBrowser: boolean
} {
  if (task.status === 'initialized' || task.status === 'refined') {
    return {
      kind: 'refine',
      title: 'Refine Workbench',
      subtitle: '优先看原始需求、refined 结果和 refine 日志。',
      narrative: isPendingRefineTask(task)
        ? '当前 refine 还卡在源内容准备。建议先对照 `prd.source.md` 和 `prd-refined.md`，确认是不是缺正文或来源拉取失败。'
        : '这一阶段的重点是把原始输入和 refined 输出对照起来看，再结合 refine.log 判断需求是否已经被整理清楚。',
      artifacts: ['prd.source.md', 'prd-refined.md', 'refine.log'],
      showDiffBrowser: false,
    }
  }

  if (task.status === 'planning' && !hasActionableArtifact(task.artifacts['design.md'])) {
    return {
      kind: 'design',
      title: 'Design Workbench',
      subtitle: '优先看 design.md 和与 design 相关的 plan 日志。',
      narrative: '当前正在从 refined PRD 生成设计稿。先看 `design.md` 是否已经落出系统改造点，再用 `plan.log` 判断代码调研和生成过程是否正常。',
      artifacts: ['design.md', 'plan.log', 'prd-refined.md'],
      showDiffBrowser: false,
    }
  }

  if (task.status === 'planning' || task.status === 'planned') {
    return {
      kind: 'plan',
      title: 'Plan Workbench',
      subtitle: '优先看 plan.md、任务拆分和执行过程日志。',
      narrative: '这一阶段的重点是确认执行策略、任务拆分和顺序，而不是在文档列表里自己找材料。先看 `plan.md`，需要时再回到 `design.md` 和 `plan.log`。',
      artifacts: ['plan.md', 'design.md', 'plan.log'],
      showDiffBrowser: false,
    }
  }

  if (task.status === 'coding' || task.status === 'partially_coded' || task.status === 'failed' || task.status === 'coded' || task.status === 'archived') {
    return {
      kind: 'code',
      title: 'Code Workbench',
      subtitle: '优先看 code 结果、日志和 Diff，而不是先翻方案文档。',
      narrative: task.codeProgress.summary || '这一阶段最关键的是快速判断当前 repo 结果对不对、构建有没有过、Diff 改了什么。优先看 `code-result.json`、`code.log` 和 Diff 浏览器。',
      artifacts: ['code-result.json', 'code.log', 'diff.json', 'diff.patch'],
      showDiffBrowser: true,
    }
  }

  return {
    kind: 'archive',
    title: 'Archive Workbench',
    subtitle: '当前以结果确认和收尾信息为主。',
    narrative: '任务已经接近收尾，重点是确认结果、保留必要产物，并决定是否归档。',
    artifacts: ['code-result.json', 'plan.md', 'design.md'],
    showDiffBrowser: true,
  }
}

function hasActionableArtifact(content?: string) {
  if (!content) {
    return false
  }
  return !content.includes('当前没有') && !content.includes('当前为空')
}

function isPendingRefineTask(task: TaskRecord) {
  return task.status === 'initialized' && task.sourceType === 'lark_doc' && task.artifacts['prd-refined.md']?.includes('状态：待补充源内容')
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

export function RepoContextPanel({
  actionBusy,
  archivingRepo,
  codeStartingRepo,
  hasGeneratedPlan,
  onArchive,
  onReset,
  onReviewDiff,
  onReviewResult,
  onSelectRepo,
  onStartCode,
  resettingRepo,
  selectedRepo,
  task,
}: {
  actionBusy: boolean
  archivingRepo: string | null
  codeStartingRepo: string | null
  hasGeneratedPlan: boolean
  onArchive: (repoId: string) => Promise<void>
  onReset: (repoId: string) => Promise<void>
  onReviewDiff: (repoId: string) => void
  onReviewResult: (repoId: string) => void
  onSelectRepo: (repoId: string) => void
  onStartCode: (repoId: string) => Promise<void>
  resettingRepo: string | null
  selectedRepo: string
  task: TaskRecord
}) {
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
  const activeRepo = orderedRepos.find((repo) => repo.id === selectedRepo) ?? orderedRepos[0] ?? null

  if (!activeRepo) {
    return null
  }

  const canStartCode = canStartCodeForRepo(activeRepo, hasGeneratedPlan)
  const canResetCode = canResetCodeForRepo(activeRepo)
  const canArchiveCode = canArchiveCodeForRepo(activeRepo)
  const hasResult = hasRepoResult(activeRepo)
  const hasDiff = Boolean(activeRepo.diffSummary)
  const repoSummary = repoWorkbenchSummary(activeRepo)
  const resultSummary =
    activeRepo.filesWritten && activeRepo.filesWritten.length > 0 ? `已写入 ${activeRepo.filesWritten.length} 个文件。` : '当前还没有写入结果。'
  const blockedRepos = orderedRepos.filter((repo) => repo.failureType === 'blocked_by_dependency')
  const laneSummary = summarizeRepoLane(orderedRepos, task.repoNext)

  return (
    <section className="flex h-full flex-col rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Repo Execution Lane</div>
          <h4 className="mt-2 text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
            {task.repos.length > 1 ? '多仓执行链路' : activeRepo.displayName}
          </h4>
        </div>
        <RepoStatusBadge status={activeRepo.status} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <LaneCountPill label="ready" tone="ready" value={laneSummary.ready} />
        <LaneCountPill label="running" tone="running" value={laneSummary.running} />
        <LaneCountPill label="blocked" tone="blocked" value={laneSummary.blocked} />
        <LaneCountPill label="done" tone="done" value={laneSummary.done} />
      </div>

      <div className="mt-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Code Stage Summary</div>
            <div className="mt-2 text-sm leading-6 text-[#141413] dark:text-[#faf9f5]">
              {task.repoNext.length > 0
                ? `优先推进：${task.repoNext.join(', ')}`
                : blockedRepos.length > 0
                  ? `受阻塞：${blockedRepos.map((repo) => repo.id).join(', ')}`
                  : '当前没有 ready repo。'}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <LaneLegend tone="ready" label="ready" />
            <LaneLegend tone="running" label="running" />
            <LaneLegend tone="blocked" label="blocked" />
            <LaneLegend tone="done" label="done" />
            <LaneLegend tone="failed" label="failed" />
          </div>
        </div>
      </div>

      <div className="mt-4 -mx-1 overflow-x-auto pb-1">
        <div className="flex min-w-max items-stretch gap-3 px-1">
          {orderedRepos.map((repo, index) => (
            <div className="flex items-center gap-3" key={repo.id}>
              <button
                className={`w-[224px] min-w-[224px] rounded-[18px] border p-4 text-left transition ${repoLaneCardTone(repo, task.repoNext, repo.id === activeRepo.id)}`}
                onClick={() => onSelectRepo(repo.id)}
                type="button"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-current/20 text-[11px] font-semibold">
                      {index + 1}
                    </span>
                    <div className="text-sm font-semibold">{repo.id}</div>
                  </div>
                  <LaneStatePill repo={repo} repoNext={task.repoNext} />
                </div>
                <div className="mt-3 text-xs leading-5 opacity-80">{repoLaneDetail(repo)}</div>
                {task.repoNext.includes(repo.id) ? (
                  <div className="mt-3 rounded-full border border-current/20 px-2 py-1 text-[10px] uppercase tracking-[0.4px] opacity-90">
                    next executable
                  </div>
                ) : null}
              </button>
              {index < orderedRepos.length - 1 ? (
                <div className="flex min-w-8 items-center justify-center">
                  <div className="h-[2px] w-8 bg-[#ddd9cc] dark:bg-[#3a3937]" />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {blockedRepos.length > 0 ? (
        <div className="mt-4 rounded-[18px] border border-[#d9c9a7] bg-[#fff7e8] px-4 py-3 text-sm leading-6 text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]">
          当前存在依赖阻塞：{blockedRepos.map((repo) => repo.id).join(', ')}。先推进它们依赖的上游 repo，再回到这里继续往后走。
        </div>
      ) : null}

      <div className="mt-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Selected Repo</div>
            <div className="mt-2 text-xl text-[#141413] dark:text-[#faf9f5]">{activeRepo.displayName}</div>
          </div>
          <RepoStatusBadge status={activeRepo.status} />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <RepoMetaPill label="仓库标识" value={activeRepo.id} />
          <RepoMetaPill label="构建结果" value={buildLabel(activeRepo.build)} />
          <RepoMetaPill label="分支" value={activeRepo.branch ?? '尚未创建'} mono />
          <RepoMetaPill label="工作区" value={activeRepo.worktree ?? '尚未创建'} mono />
        </div>

        <div className="mt-3 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-3 text-sm text-[#87867f] shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          {activeRepo.path}
        </div>

        {activeRepo.failureHint ? (
          <div className="mt-4 rounded-[18px] border border-[#e1c1bf] bg-[#fbf1f0] px-4 py-3 text-sm leading-6 text-[#b53333]">
            <div className="text-[10px] uppercase tracking-[0.5px] opacity-80">失败摘要</div>
            <div className="mt-2 font-mono text-xs leading-6">{activeRepo.failureHint}</div>
            {activeRepo.failureAction ? <div className="mt-2 text-xs leading-5">建议：{activeRepo.failureAction}</div> : null}
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          {canStartCode ? (
            <RepoActionButton
              disabled={actionBusy}
              onClick={() => void onStartCode(activeRepo.id)}
              title={
                activeRepo.status === 'failed'
                  ? `${repoSummary} ${resultSummary} 会在这个仓库重试实现，重新生成改动并再次执行构建验证。`
                  : activeRepo.executionMode === 'verify_only'
                    ? `${repoSummary} ${resultSummary} 会在这个仓库执行验证，并记录验证结果。`
                    : `${repoSummary} ${resultSummary} 会在这个仓库创建隔离工作区，生成改动并尝试完成构建验证。`
              }
              tone="brand"
            >
              {codeStartingRepo === activeRepo.id
                ? '执行中...'
                : activeRepo.executionMode === 'verify_only'
                  ? activeRepo.status === 'failed'
                    ? '重新验证'
                    : '执行验证'
                  : activeRepo.status === 'failed'
                    ? '重试实现'
                    : '开始实现'}
            </RepoActionButton>
          ) : null}
          {canResetCode ? (
            <RepoActionButton
              disabled={actionBusy}
              onClick={() => void onReset(activeRepo.id)}
              title={`${repoSummary} ${resultSummary} 会删除这个仓库本次生成的分支、worktree、diff 与结果记录。`}
              tone="danger"
            >
              {resettingRepo === activeRepo.id ? '回退中...' : '回退实现'}
            </RepoActionButton>
          ) : null}
          {canArchiveCode ? (
            <RepoActionButton
              disabled={actionBusy}
              onClick={() => void onArchive(activeRepo.id)}
              title={`${repoSummary} ${resultSummary} 会清理这个仓库的分支和工作区，并把结果保留下来供后续查看。`}
              tone="neutral"
            >
              {archivingRepo === activeRepo.id ? '归档中...' : '归档任务'}
            </RepoActionButton>
          ) : null}
          {hasResult ? (
            <RepoActionButton
              disabled={false}
              onClick={() => onReviewResult(activeRepo.id)}
              title={`${repoSummary} ${resultSummary} 打开结果面板，查看这个仓库的 code-result.json。`}
              tone="neutral"
            >
              查看结果
            </RepoActionButton>
          ) : null}
          {hasDiff ? (
            <RepoActionButton
              disabled={false}
              onClick={() => onReviewDiff(activeRepo.id)}
              title={`${repoSummary} ${resultSummary} 切换到 Diff 面板，查看这个仓库的改动详情。`}
              tone="neutral"
            >
              查看 Diff
            </RepoActionButton>
          ) : null}
        </div>
      </div>
    </section>
  )
}

function RepoMetaPill({
  label,
  mono,
  value,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-[#e8e6dc] bg-[#faf9f5] px-3 py-1.5 text-xs text-[#5e5d59] shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <span className="uppercase tracking-[0.35px] text-[#87867f] dark:text-[#b0aea5]">{label}</span>
      <span className={mono ? 'font-mono text-[11px] text-[#141413] dark:text-[#faf9f5]' : 'text-[#141413] dark:text-[#faf9f5]'}>{value}</span>
    </div>
  )
}

function LaneCountPill({
  label,
  tone,
  value,
}: {
  label: string
  tone: 'ready' | 'running' | 'blocked' | 'done'
  value: number
}) {
  return (
    <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs ${laneLegendTone(tone)}`}>
      <span className="uppercase tracking-[0.35px]">{label}</span>
      <span className="rounded-full border border-current/20 px-2 py-0.5 text-[11px] font-semibold">{value}</span>
    </div>
  )
}

function LaneLegend({
  tone,
  label,
}: {
  tone: 'ready' | 'running' | 'blocked' | 'done' | 'failed'
  label: string
}) {
  return (
    <span className={`rounded-full border px-3 py-1 ${laneLegendTone(tone)}`}>
      {label}
    </span>
  )
}

function LaneStatePill({
  repo,
  repoNext,
}: {
  repo: TaskRecord['repos'][number]
  repoNext: string[]
}) {
  const state = repoLaneState(repo, repoNext)
  return <span className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-[0.35px] ${laneLegendTone(state)}`}>{state}</span>
}

function RepoActionButton({
  children,
  disabled,
  onClick,
  tone,
  title,
}: {
  children: string
  disabled?: boolean
  onClick: () => void
  tone: 'brand' | 'danger' | 'neutral'
  title?: string
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
      title={title}
      type="button"
    >
      {children}
    </button>
  )
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
  if (repo.executionMode === 'reference_only') {
    return '这个仓库当前只作为参考链路，不进入执行队列。'
  }
  if (repo.executionMode === 'verify_only' && repo.status === 'planned') {
    return '这个仓库属于联动验证范围，当前更适合执行验证，而不是直接开始实现。'
  }
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

function repoLaneDetail(repo: TaskRecord['repos'][number]) {
  if (repo.executionMode === 'reference_only') {
    return 'reference only'
  }
  if (repo.failureType === 'blocked_by_dependency') {
    return repo.failureAction || '等待上游依赖。'
  }
  switch (repo.status) {
    case 'coding':
      return '实现中'
    case 'failed':
      return '执行失败'
    case 'planned':
      return 'ready'
    case 'coded':
      return '结果已生成'
    case 'archived':
      return '已归档'
    default:
      return '待推进'
  }
}

function repoLaneState(repo: TaskRecord['repos'][number], repoNext: string[]): 'ready' | 'running' | 'blocked' | 'done' | 'failed' {
  if (repo.queueState === 'reference') {
    return 'done'
  }
  if (repo.queueState === 'ready' || repo.queueState === 'running' || repo.queueState === 'blocked' || repo.queueState === 'done' || repo.queueState === 'failed') {
    return repo.queueState
  }
  if (repo.failureType === 'blocked_by_dependency') {
    return 'blocked'
  }
  if (repo.status === 'coding') {
    return 'running'
  }
  if (repo.status === 'coded' || repo.status === 'archived') {
    return 'done'
  }
  if (repo.status === 'failed') {
    return repoNext.includes(repo.id) ? 'ready' : 'failed'
  }
  if (repoNext.includes(repo.id) || repo.status === 'planned') {
    return 'ready'
  }
  return 'ready'
}

function laneLegendTone(state: 'ready' | 'running' | 'blocked' | 'done' | 'failed') {
  switch (state) {
    case 'ready':
      return 'border-[#d7c28a] bg-[#fff4d6] text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]'
    case 'running':
      return 'border-[#c8d8e7] bg-[#f2f7fb] text-[#2f5571] dark:border-[#35506a] dark:bg-[#1f2830] dark:text-[#cfe6fb]'
    case 'blocked':
      return 'border-[#d9c9a7] bg-[#fff7e8] text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]'
    case 'done':
      return 'border-[#cfe2d2] bg-[#f3f7f1] text-[#35533d] dark:border-[#35533d] dark:bg-[#1f2a22] dark:text-[#d4ead7]'
    case 'failed':
      return 'border-[#e1c1bf] bg-[#fbf1f0] text-[#8f3732] dark:border-[#6a3431] dark:bg-[#2b1f1f] dark:text-[#f5d3d1]'
  }
}

function repoLaneCardTone(repo: TaskRecord['repos'][number], repoNext: string[], selected: boolean) {
  if (selected) {
    return 'border-[#c96442] bg-[#fff7f2] text-[#6b2e1f] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
  }
  switch (repoLaneState(repo, repoNext)) {
    case 'blocked':
      return 'border-[#d9c9a7] bg-[#fff7e8] text-[#7a5b18] dark:border-[#6d5a2e] dark:bg-[#2a2419] dark:text-[#f0dfb0]'
    case 'done':
      return 'border-[#cfe2d2] bg-[#f3f7f1] text-[#35533d] dark:border-[#35533d] dark:bg-[#1f2a22] dark:text-[#d4ead7]'
    case 'running':
      return 'border-[#c8d8e7] bg-[#f2f7fb] text-[#2f5571] dark:border-[#35506a] dark:bg-[#1f2830] dark:text-[#cfe6fb]'
    case 'failed':
      return 'border-[#e1c1bf] bg-[#fbf1f0] text-[#8f3732] dark:border-[#6a3431] dark:bg-[#2b1f1f] dark:text-[#f5d3d1]'
    case 'ready':
      return 'border-[#e8d7b2] bg-[#fffaf0] text-[#6a5530] dark:border-[#615033] dark:bg-[#272117] dark:text-[#f0dfb0]'
  }
}

function summarizeRepoLane(repos: TaskRecord['repos'][number][], repoNext: string[]) {
  return repos.reduce(
    (acc, repo) => {
      const state = repoLaneState(repo, repoNext)
      acc[state] += 1
      return acc
    },
    { ready: 0, running: 0, blocked: 0, done: 0, failed: 0 },
  )
}

function canStartCodeForRepo(repo: TaskRecord['repos'][number], hasGeneratedPlan: boolean) {
  if (!hasGeneratedPlan) {
    return false
  }
  if (repo.executionMode === 'reference_only') {
    return false
  }
  return repo.queueState === 'ready' || repo.queueState === 'failed' || repo.status === 'planned' || repo.status === 'failed'
}

function canResetCodeForRepo(repo: TaskRecord['repos'][number]) {
  return repo.status === 'coded' || repo.status === 'failed'
}

function canArchiveCodeForRepo(repo: TaskRecord['repos'][number]) {
  return repo.status === 'coded'
}
