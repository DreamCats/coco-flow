import { useEffect, useMemo, useState } from 'react'
import type { TaskArtifactName, TaskRecord } from '../api'
import { ArtifactViewer, artifactLabel } from './artifact-viewer'
import { DiffPanel } from './diff-panel'

export type WorkbenchPane = 'docs' | 'logs' | 'result' | 'diff'

const paneArtifacts: Record<Exclude<WorkbenchPane, 'diff'>, TaskArtifactName[]> = {
  docs: ['prd.source.md', 'prd-refined.md', 'design.md', 'plan.md'],
  logs: ['refine.log', 'plan.log', 'code.log'],
  result: ['code-result.json'],
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

  const repoScopedArtifact = task.repos.length > 1 && (artifact === 'code.log' || artifact === 'code-result.json')
  const activeRepoID = artifactRepo || selectedDiffRepo || task.repos[0]?.id || ''
  const liveArtifact = resolveLiveArtifact(task.status)
  const artifactLive = polling && liveArtifact === artifact

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

  return (
    <section className="rounded-[28px] border border-stone-200/90 bg-white/88 p-4 shadow-[0_18px_40px_rgba(17,24,39,0.08)] backdrop-blur dark:border-white/10 dark:bg-white/[0.045] dark:shadow-[0_18px_40px_rgba(0,0,0,0.2)]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Workbench</div>
          <h4 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950 dark:text-stone-50">阅读工作台</h4>
        </div>
        <div className="text-sm text-stone-500 dark:text-stone-400">统一查看文档、日志、结果和 Diff</div>
      </div>

      <div className="mb-4 rounded-[22px] border border-stone-200 bg-stone-50/90 p-2 dark:border-white/10 dark:bg-white/[0.03]">
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
                className={`rounded-full border px-3 py-2 text-sm font-medium transition ${
                  artifact === name
                    ? 'border-stone-900 bg-stone-900 text-white shadow-sm dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
                    : 'border-stone-200 bg-white text-stone-600 hover:border-stone-400 hover:text-stone-950 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-300 dark:hover:border-white/20 dark:hover:text-stone-100'
                }`}
                key={name}
                onClick={() => onArtifactChange(name)}
                type="button"
              >
                {artifactLabel(name)}
              </button>
            ))}
          </div>

          {repoScopedArtifact ? (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">仓库视角</span>
              {task.repos.map((repo) => (
                <button
                  className={`rounded-full border px-3 py-2 text-sm transition ${
                    activeRepoID === repo.id
                      ? 'border-stone-900 bg-stone-900 text-white shadow-sm dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
                      : 'border-stone-200 bg-white text-stone-600 hover:border-stone-400 hover:text-stone-950 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-300 dark:hover:border-white/20 dark:hover:text-stone-100'
                  }`}
                  key={`${artifact}-${repo.id}`}
                  onClick={() => {
                    onArtifactRepoChange(repo.id)
                    onSelectDiffRepo(repo.id)
                  }}
                  type="button"
                >
                  {repo.id}
                </button>
              ))}
            </div>
          ) : null}

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
        <DiffPanel repos={task.repos} selectedRepo={selectedDiffRepo} onSelectRepo={onSelectDiffRepo} />
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
      className={`rounded-full border px-3 py-2 text-sm font-medium transition ${
        active
          ? 'border-stone-900 bg-stone-900 text-white shadow-[0_8px_18px_rgba(17,24,39,0.12)] dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
          : 'border-transparent bg-white text-stone-600 hover:border-stone-300 hover:text-stone-950 dark:bg-transparent dark:text-stone-300 dark:hover:border-white/16 dark:hover:text-stone-100'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function resolvePane(artifact: TaskArtifactName): WorkbenchPane {
  if (artifact === 'code-result.json') {
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
