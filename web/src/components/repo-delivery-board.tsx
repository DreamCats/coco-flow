import type { RepoResult, TaskRecord } from '../api'
import { KeyValue, RepoStatusBadge } from './ui-primitives'

const repoStatusPriority: Record<RepoResult['status'], number> = {
  coding: 0,
  failed: 1,
  planned: 2,
  refined: 3,
  initialized: 4,
  pending: 5,
  coded: 6,
  archived: 7,
}

export function RepoDeliveryBoard({
  task,
  actionBusy,
  codeStartingRepo,
  resettingRepo,
  archivingRepo,
  hasGeneratedPlan,
  polling,
  onArchive,
  onReset,
  onReviewDiff,
  onReviewResult,
  onStartCode,
}: {
  task: TaskRecord
  actionBusy: boolean
  codeStartingRepo: string | null
  resettingRepo: string | null
  archivingRepo: string | null
  hasGeneratedPlan: boolean
  polling: boolean
  onArchive: (repoId: string) => Promise<void>
  onReset: (repoId: string) => Promise<void>
  onReviewDiff: (repoId: string) => void
  onReviewResult: (repoId: string) => void
  onStartCode: (repoId: string) => Promise<void>
}) {
  const orderedRepos = [...task.repos].sort((left, right) => {
    const priorityGap = (repoStatusPriority[left.status] ?? 99) - (repoStatusPriority[right.status] ?? 99)
    if (priorityGap !== 0) {
      return priorityGap
    }
    return left.id.localeCompare(right.id)
  })

  return (
    <section className="rounded-[26px] border border-stone-200/90 bg-white/82 p-4 shadow-[0_14px_32px_rgba(17,24,39,0.06)] dark:border-white/10 dark:bg-white/[0.04] dark:shadow-none">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Repo Delivery</div>
          <h4 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950 dark:text-stone-50">仓库推进面板</h4>
        </div>
        <div className="text-xs text-stone-500 dark:text-stone-400">失败和待处理仓库会自动排在更前面</div>
      </div>

      <div className="space-y-4">
        {orderedRepos.map((repo) => (
          <RepoDeliveryCard
            actionBusy={actionBusy}
            archiving={archivingRepo === repo.id}
            canArchive={task.repos.length > 1 && canArchiveCodeForRepo(repo)}
            canReset={task.repos.length > 1 && canResetCodeForRepo(repo)}
            canStartCode={task.repos.length > 1 && canStartCodeForRepo(repo, hasGeneratedPlan)}
            codeStarting={codeStartingRepo === repo.id}
            key={repo.id}
            polling={polling}
            onArchive={onArchive}
            onReset={onReset}
            onReviewDiff={onReviewDiff}
            onReviewResult={onReviewResult}
            onStartCode={onStartCode}
            repo={repo}
            resetting={resettingRepo === repo.id}
          />
        ))}
      </div>
    </section>
  )
}

function RepoDeliveryCard({
  repo,
  canStartCode,
  canReset,
  canArchive,
  codeStarting,
  polling,
  resetting,
  archiving,
  actionBusy,
  onStartCode,
  onReset,
  onArchive,
  onReviewResult,
  onReviewDiff,
}: {
  repo: TaskRecord['repos'][number]
  canStartCode: boolean
  canReset: boolean
  canArchive: boolean
  codeStarting: boolean
  polling: boolean
  resetting: boolean
  archiving: boolean
  actionBusy: boolean
  onStartCode: (repoId: string) => Promise<void>
  onReset: (repoId: string) => Promise<void>
  onArchive: (repoId: string) => Promise<void>
  onReviewResult: (repoId: string) => void
  onReviewDiff: (repoId: string) => void
}) {
  const hasResult = Boolean(repo.commit || (repo.filesWritten && repo.filesWritten.length > 0) || repo.build === 'passed' || repo.build === 'failed')
  const hasDiff = Boolean(repo.diffSummary)

  return (
    <div className="rounded-[22px] border border-stone-200 bg-stone-50/90 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)] dark:border-white/10 dark:bg-white/[0.03] dark:shadow-none">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{repo.displayName}</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">{repo.id}</div>
          <div className="mt-3 text-sm leading-6 text-stone-600 dark:text-stone-300">{repoDeliverySummary(repo)}</div>
        </div>
        <div className="flex items-center gap-2">
          {polling && (repo.status === 'coding' || codeStarting) ? (
            <span className="flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:border-emerald-300/20 dark:bg-emerald-400/10 dark:text-emerald-100">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/70" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500 dark:bg-emerald-300" />
              </span>
              Live
            </span>
          ) : null}
          <RepoStatusBadge status={repo.status} />
        </div>
      </div>

      {repo.failureHint ? (
        <div className="mb-4 rounded-[18px] border border-rose-200/90 bg-rose-50/90 px-3 py-3 text-sm leading-6 text-rose-800 dark:border-rose-300/20 dark:bg-rose-400/10 dark:text-rose-100">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] opacity-80">失败摘要</div>
          <div className="mt-2 font-mono text-xs leading-6">{repo.failureHint}</div>
        </div>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <KeyValue label="构建结果" value={repo.build === 'passed' ? '已通过' : repo.build === 'failed' ? '未通过' : '待生成'} />
        <KeyValue label="提交" mono value={repo.commit ?? '尚未提交'} />
        <KeyValue label="分支" mono value={repo.branch ?? '尚未创建'} />
        <KeyValue label="工作区" mono value={repo.worktree ?? '尚未创建'} />
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {canStartCode ? (
          <ActionButton disabled={actionBusy} onClick={() => void onStartCode(repo.id)} tone="emerald">
            {codeStarting ? '实现进行中...' : repo.status === 'failed' ? '重试实现' : '开始实现'}
          </ActionButton>
        ) : null}
        {canReset ? (
          <ActionButton disabled={actionBusy} onClick={() => void onReset(repo.id)} tone="rose">
            {resetting ? '回退中...' : '回退实现'}
          </ActionButton>
        ) : null}
        {canArchive ? (
          <ActionButton disabled={actionBusy} onClick={() => void onArchive(repo.id)} tone="sky">
            {archiving ? '归档中...' : '归档任务'}
          </ActionButton>
        ) : null}
        {hasResult ? (
          <ActionButton disabled={false} onClick={() => onReviewResult(repo.id)} tone="neutral">
            查看结果
          </ActionButton>
        ) : null}
        {hasDiff ? (
          <ActionButton disabled={false} onClick={() => onReviewDiff(repo.id)} tone="neutral">
            查看 Diff
          </ActionButton>
        ) : null}
      </div>

      <div className="mt-4 rounded-[18px] border border-stone-200 bg-white/92 px-3 py-3 dark:border-white/10 dark:bg-stone-950/70">
        <div className="text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">变更文件</div>
        <div className="mt-2 space-y-2">
          {(repo.filesWritten && repo.filesWritten.length > 0 ? repo.filesWritten : ['尚无写入结果']).map((file) => (
            <div className="font-mono text-xs text-stone-800 dark:text-stone-200" key={file}>
              {file}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ActionButton({
  children,
  disabled,
  onClick,
  tone,
}: {
  children: string
  disabled?: boolean
  onClick: () => void
  tone: 'emerald' | 'neutral' | 'rose' | 'sky'
}) {
  const toneClass =
    tone === 'emerald'
      ? 'border-emerald-200/50 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-300/20 dark:bg-emerald-400/10 dark:text-emerald-100 dark:hover:bg-emerald-400/20'
      : tone === 'rose'
        ? 'border-rose-200/60 bg-rose-50 text-rose-700 hover:bg-rose-100 dark:border-rose-300/20 dark:bg-rose-400/10 dark:text-rose-100 dark:hover:bg-rose-400/20'
        : tone === 'sky'
          ? 'border-sky-200/60 bg-sky-50 text-sky-700 hover:bg-sky-100 dark:border-sky-300/20 dark:bg-sky-400/10 dark:text-sky-100 dark:hover:bg-sky-400/20'
          : 'border-stone-200 bg-white/92 text-stone-700 hover:bg-stone-100 dark:border-white/10 dark:bg-white/[0.05] dark:text-stone-200 dark:hover:bg-white/10'

  return (
    <button
      className={`rounded-2xl border px-3 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${toneClass}`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

function repoDeliverySummary(repo: TaskRecord['repos'][number]) {
  switch (repo.status) {
    case 'coding':
      return '正在后台生成实现并验证结果，适合先查看日志确认当前进度。'
    case 'failed':
      return '这次推进失败了，建议先查看结果或日志，再决定重试还是回退。'
    case 'planned':
      return '方案已经准备好，这个仓库可以直接开始实现。'
    case 'coded':
      return '实现已经完成，可以查看结果、核对 Diff，或直接归档收尾。'
    case 'archived':
      return '这个仓库已经完成归档，结果保留但执行环境已清理。'
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
