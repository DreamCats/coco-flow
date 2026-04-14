import type { TaskRecord } from '../api'

export function TaskPrimaryAction({
  task,
  actionError,
  actionBusy,
  batchCodeStarting,
  canArchiveCode,
  canResetCode,
  canStartCode,
  canStartPlan,
  canStartRemainingCode,
  codeActionLabel,
  codeStarting,
  lastRefreshedAt,
  planActionLabel,
  planStarting,
  polling,
  remainingReposCount,
  resetting,
  archiving,
  onArchive,
  onReset,
  onStartCode,
  onStartPlan,
  onStartRemainingCode,
}: {
  task: TaskRecord
  actionError: string
  actionBusy: boolean
  batchCodeStarting: boolean
  canArchiveCode: boolean
  canResetCode: boolean
  canStartCode: boolean
  canStartPlan: boolean
  canStartRemainingCode: boolean
  codeActionLabel: string
  codeStarting: boolean
  lastRefreshedAt: string
  planActionLabel: string
  planStarting: boolean
  polling: boolean
  remainingReposCount: number
  resetting: boolean
  archiving: boolean
  onArchive: () => void
  onReset: () => void
  onStartCode: () => void
  onStartPlan: () => void
  onStartRemainingCode: () => void
}) {
  const repoCount = task.repos.length
  const codedCount = task.repos.filter((repo) => repo.status === 'coded' || repo.status === 'archived').length
  const failedCount = task.repos.filter((repo) => repo.status === 'failed').length
  const runningCount = task.repos.filter((repo) => repo.status === 'coding').length
  const pendingRefine = isPendingRefineTask(task)
  const dominantFailure = summarizeFailureType(task)

  return (
    <section className="rounded-[28px] border border-emerald-300/18 bg-[linear-gradient(140deg,rgba(16,185,129,0.2),rgba(12,18,18,0.96)_42%,rgba(11,13,17,0.98)_100%)] p-5 shadow-[0_28px_60px_rgba(6,78,59,0.24)]">
      <div className="text-xs font-semibold uppercase tracking-[0.22em] text-emerald-200">主行动区</div>
      <div className="mt-3 text-[28px] font-semibold tracking-[-0.05em] text-white">{primaryHeadline(task)}</div>
      <p className="mt-3 max-w-[42rem] text-sm leading-6 text-emerald-50/80">{primaryNarrative(task)}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <MiniStat label="仓库总数" value={`${repoCount}`} />
        <MiniStat label="已完成" value={`${codedCount}`} />
        <MiniStat label="处理中断" value={`${failedCount + runningCount}`} />
      </div>

      {polling ? <RunningStatusCard status={task.status} lastRefreshedAt={lastRefreshedAt} /> : null}

      {task.status === 'initialized' ? (
        <NoticeBox tone="amber">
          {pendingRefine
            ? '飞书正文尚未拉取成功。请先补充 `prd.source.md` 的正文，再重新执行 refine。'
            : '需求正在整理中。若停留时间过长，可先查看 `refine.log`。'}
        </NoticeBox>
      ) : null}
      {task.status === 'planning' ? (
        <NoticeBox tone="sky">正在分析代码并生成方案。若停留时间过长，可先查看 `plan.log`。</NoticeBox>
      ) : null}
      {task.status === 'coding' ? (
        <NoticeBox tone="emerald">后台正在生成实现并验证结果。若停留时间过长，可先查看 `code.log`。</NoticeBox>
      ) : null}
      {task.status === 'failed' ? (
        <NoticeBox tone="rose">
          {dominantFailure
            ? `当前主要失败类型是「${dominantFailure.label}」。${dominantFailure.action}`
            : '本次推进失败了，建议先查看 code.log 和 code-result.json，再决定重试还是回退。'}
        </NoticeBox>
      ) : null}
      {task.repos.length > 1 && canStartRemainingCode ? (
        <NoticeBox tone="amber">这是一条多仓任务。建议优先一键推进剩余仓库，再到下方逐个处理例外情况。</NoticeBox>
      ) : null}
      {actionError ? <NoticeBox tone="rose">{actionError}</NoticeBox> : null}

      <div className="mt-5 flex flex-wrap gap-3">
        {canStartRemainingCode ? (
          <>
            <PrimaryButton disabled={actionBusy} onClick={onStartRemainingCode}>
              {batchCodeStarting ? '批量推进中...' : `依次推进剩余仓库 (${remainingReposCount})`}
            </PrimaryButton>
            <InlineHint>会按仓库顺序逐个执行，某个仓库失败后立即停止。</InlineHint>
          </>
        ) : null}

        {canStartCode ? (
          <>
            <PrimaryButton disabled={actionBusy} onClick={onStartCode}>
              {codeStarting ? '实现进行中...' : codeActionLabel}
            </PrimaryButton>
            <InlineHint>会创建隔离工作区、生成改动并尝试完成构建验证。</InlineHint>
          </>
        ) : null}

        {canResetCode ? (
          <>
            <SecondaryButton disabled={actionBusy} onClick={onReset} tone="rose">
              {resetting ? '回退中...' : '回退实现'}
            </SecondaryButton>
            <InlineHint>会删除本次生成的分支、worktree、diff 与结果记录。</InlineHint>
          </>
        ) : null}

        {canArchiveCode ? (
          <>
            <SecondaryButton disabled={actionBusy} onClick={onArchive} tone="sky">
              {archiving ? '归档中...' : '归档任务'}
            </SecondaryButton>
            <InlineHint>会清理分支和工作区，并把任务标记为已归档。</InlineHint>
          </>
        ) : null}

        {canStartPlan ? (
          <>
            <SecondaryButton disabled={actionBusy} onClick={onStartPlan} tone="neutral">
              {planStarting ? '方案生成中...' : planActionLabel}
            </SecondaryButton>
            <InlineHint>
              {task.status === 'planned' ? '会重新分析代码，并覆盖 `design.md` / `plan.md`。' : '会在后台生成 `design.md` / `plan.md`。'}
            </InlineHint>
          </>
        ) : null}
      </div>

      <div className="mt-5 rounded-[22px] border border-white/10 bg-black/25 px-4 py-3 font-mono text-sm text-emerald-100/95 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
        {task.nextAction}
      </div>
    </section>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[20px] border border-white/10 bg-white/[0.06] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]">
      <div className="text-[11px] uppercase tracking-[0.2em] text-stone-400/90">{label}</div>
      <div className="mt-2 text-[22px] font-semibold tracking-[-0.04em] text-white">{value}</div>
    </div>
  )
}

function NoticeBox({
  children,
  tone,
}: {
  children: string
  tone: 'amber' | 'emerald' | 'rose' | 'sky'
}) {
  const toneClass =
    tone === 'amber'
      ? 'mt-4 rounded-[20px] border border-amber-300/18 bg-amber-400/10 px-4 py-3 text-sm leading-6 text-amber-100'
      : tone === 'sky'
        ? 'mt-4 rounded-[20px] border border-sky-300/18 bg-sky-400/10 px-4 py-3 text-sm leading-6 text-sky-100'
        : tone === 'rose'
          ? 'mt-4 rounded-[20px] border border-rose-300/18 bg-rose-400/10 px-4 py-3 text-sm leading-6 text-rose-100'
          : 'mt-4 rounded-[20px] border border-emerald-300/18 bg-emerald-400/10 px-4 py-3 text-sm leading-6 text-emerald-100'

  return <div className={toneClass}>{children}</div>
}

function PrimaryButton({
  children,
  disabled,
  onClick,
}: {
  children: string
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      className="rounded-[20px] border border-emerald-200/36 bg-emerald-500/30 px-4 py-3 text-sm font-semibold text-emerald-50 shadow-[0_12px_24px_rgba(16,185,129,0.16)] transition hover:border-emerald-100/44 hover:bg-emerald-500/42 disabled:cursor-not-allowed disabled:opacity-60"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

function SecondaryButton({
  children,
  disabled,
  onClick,
  tone,
}: {
  children: string
  disabled?: boolean
  onClick: () => void
  tone: 'neutral' | 'rose' | 'sky'
}) {
  const toneClass =
    tone === 'rose'
      ? 'border-rose-200/28 bg-rose-400/14 text-rose-50 hover:border-rose-100/38 hover:bg-rose-400/22'
      : tone === 'sky'
        ? 'border-sky-200/28 bg-sky-400/14 text-sky-50 hover:border-sky-100/38 hover:bg-sky-400/22'
        : 'border-white/14 bg-white/[0.06] text-white hover:border-white/22 hover:bg-white/[0.1]'

  return (
    <button
      className={`rounded-[20px] border px-4 py-3 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${toneClass}`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

function InlineHint({ children }: { children: string }) {
  return <span className="self-center text-xs text-emerald-50/65">{children}</span>
}

function RunningStatusCard({
  status,
  lastRefreshedAt,
}: {
  status: TaskRecord['status']
  lastRefreshedAt: string
}) {
  return (
    <div className="mt-4 overflow-hidden rounded-[22px] border border-white/12 bg-black/25">
      <div className="h-1 w-full overflow-hidden bg-white/6">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-emerald-300/90" />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-300/70" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-300" />
          </span>
          <div>
            <div className="text-sm font-semibold text-white">{runningHeadline(status)}</div>
            <div className="mt-1 text-xs text-emerald-50/70">页面正在每 2.5 秒自动刷新任务状态和日志内容。</div>
          </div>
        </div>
        <div className="rounded-full border border-white/10 bg-white/[0.05] px-3 py-1 text-[11px] uppercase tracking-[0.18em] text-emerald-100/85">
          最近同步 {lastRefreshedAt || '--:--:--'}
        </div>
      </div>
    </div>
  )
}

function runningHeadline(status: TaskRecord['status']) {
  switch (status) {
    case 'initialized':
      return 'Refine 正在后台运行'
    case 'planning':
      return 'Plan 正在后台运行'
    case 'coding':
      return 'Code 正在后台运行'
    default:
      return '任务正在后台运行'
  }
}

function primaryHeadline(task: TaskRecord) {
  if (isPendingRefineTask(task)) {
    return '需要先补正文再继续'
  }
  switch (task.status) {
    case 'coded':
      return '结果已产出，准备收尾'
    case 'partially_coded':
      return '还有仓库待继续推进'
    case 'coding':
      return '实现正在推进'
    case 'planning':
      return '方案正在生成'
    case 'planned':
      return task.repos.length > 1 ? '方案已完成，等待批量实现' : '方案已完成，准备进入实现'
    case 'failed':
      return '这次推进中断了'
    case 'refined':
      return '需求已整理，等待生成方案'
    default:
      return '继续推进当前任务'
  }
}

function primaryNarrative(task: TaskRecord) {
  const repoCount = task.repos.length
  const codedCount = task.repos.filter((repo) => repo.status === 'coded' || repo.status === 'archived').length
  const failedCount = task.repos.filter((repo) => repo.status === 'failed').length

  if (isPendingRefineTask(task)) {
    return '当前任务已经记录了飞书文档来源，但正文尚未成功拉取。先补充 `prd.source.md`，再重新执行 refine，后续 plan/code 才能继续。'
  }
  if (task.status === 'partially_coded') {
    return `${codedCount} 个仓库已经完成，仍有 ${Math.max(repoCount - codedCount, 0)} 个仓库需要继续处理。`
  }
  if (task.status === 'failed' && repoCount > 1) {
    const dominantFailure = summarizeFailureType(task)
    if (dominantFailure) {
      return `${failedCount} 个仓库在推进中失败，当前主要是「${dominantFailure.label}」。${dominantFailure.action}`
    }
    return `${failedCount} 个仓库在推进中失败，建议先查看日志，再决定重试还是回退。`
  }
  if (task.status === 'coded') {
    return '实现结果已经准备好，接下来更适合确认产物、查看 Diff，并决定是否归档。'
  }
  if (task.status === 'planned') {
    return repoCount > 1 ? '方案已经生成完毕，现在更适合按仓库顺序推进实现。' : '方案已经生成完毕，现在可以直接开始实现。'
  }
  if (task.status === 'planning') {
    return '系统正在调研代码和生成方案，完成后会自动进入下一步可执行状态。'
  }
  if (task.status === 'coding') {
    return '后台正在生成实现并验证结果。你可以先查看日志，确认当前执行是否正常。'
  }
  if (task.status === 'refined') {
    return '需求已经整理成可执行任务，下一步最值得做的是生成方案。'
  }
  return '你可以在这里集中推进任务、查看结果，并决定接下来的动作。'
}

function summarizeFailureType(task: TaskRecord) {
  const failedRepos = task.repos.filter((repo) => repo.status === 'failed' && repo.failureType)
  if (failedRepos.length === 0) {
    return null
  }

  const counts = new Map<string, number>()
  for (const repo of failedRepos) {
    const current = repo.failureType as string
    counts.set(current, (counts.get(current) ?? 0) + 1)
  }

  const [type] = Array.from(counts.entries()).sort((left, right) => right[1] - left[1])[0]
  const sample = failedRepos.find((repo) => repo.failureType === type)
  return {
    label: failureTypeLabel(type),
    action: sample?.failureAction || '建议先查看日志，再决定重试还是回退。',
  }
}

function failureTypeLabel(value: string) {
  switch (value) {
    case 'build_failed':
      return '编译失败'
    case 'verify_failed':
      return '验证失败'
    case 'git_failed':
      return 'Git 失败'
    case 'agent_failed':
      return 'Agent 失败'
    default:
      return '运行失败'
  }
}

function isPendingRefineTask(task: TaskRecord) {
  return task.status === 'initialized' && task.sourceType === 'lark_doc' && task.artifacts['prd-refined.md']?.includes('状态：待补充源内容')
}
