import type { RepoResult, TaskRecord } from '../../../api'
import { useEffect, useMemo, useState } from 'react'
import { ArtifactPanel, NotePanel, SectionCard, TabButton, TaskStatusBadge } from '../ui'
import { preferredCodeRepo, repoReadyForCode } from '../model'

export function CodeStage({
  task,
  busyAction,
  onStartCode,
}: {
  task: TaskRecord
  busyAction: string
  onStartCode: (repoId?: string) => Promise<void> | void
}) {
  const [tab, setTab] = useState<'artifact' | 'notes' | 'repos'>('repos')
  const [selectedRepoID, setSelectedRepoID] = useState(preferredCodeRepo(task)?.id ?? task.repos[0]?.id ?? '')
  const selectedRepo = useMemo(() => task.repos.find((repo) => repo.id === selectedRepoID) ?? preferredCodeRepo(task) ?? null, [selectedRepoID, task])

  useEffect(() => {
    setSelectedRepoID(preferredCodeRepo(task)?.id ?? task.repos[0]?.id ?? '')
  }, [task.id, task.repos])

  return (
    <SectionCard title="阶段详情">
      <div className="inline-flex rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
        <TabButton active={tab === 'artifact'} onClick={() => setTab('artifact')}>
          产物与查看
        </TabButton>
        <TabButton active={tab === 'notes'} onClick={() => setTab('notes')}>
          补充说明
        </TabButton>
        <TabButton active={tab === 'repos'} onClick={() => setTab('repos')}>
          仓库
        </TabButton>
      </div>

      <div className="mt-4">
        {tab === 'artifact' ? (
          <ArtifactPanel content={task.artifacts['code.log'] || task.nextAction || ''} title="code.log" />
        ) : tab === 'notes' ? (
          <NotePanel content={task.nextAction || '当前没有额外说明。'} />
        ) : (
          <CodeRepoPanel busyAction={busyAction} onStartCode={onStartCode} repos={task.repos} selectedRepo={selectedRepo} onSelectRepo={setSelectedRepoID} />
        )}
      </div>
    </SectionCard>
  )
}

function CodeRepoPanel({
  repos,
  selectedRepo,
  onSelectRepo,
  onStartCode,
  busyAction,
}: {
  repos: RepoResult[]
  selectedRepo: RepoResult | null
  onSelectRepo: (repoId: string) => void
  onStartCode: (repoId?: string) => Promise<void> | void
  busyAction: string
}) {
  if (repos.length === 0) {
    return <NotePanel content="当前还没有绑定仓库。后续会在 Design 阶段补齐正式的仓库绑定流程。" />
  }

  return (
    <div className="space-y-4">
      <div className="rounded-[20px] border border-[#ece6da] bg-[#fffdf9] p-4 dark:border-[#383632] dark:bg-[#151412]">
        <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">仓库选择</div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {repos.map((repo, index) => {
            const active = selectedRepo?.id === repo.id
            return (
              <button
                className={`rounded-[18px] border px-4 py-4 text-left transition ${
                  active
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
                      <div className="mt-1 text-sm text-[#8a7a67] dark:text-[#b8ae9e]">{repo.path}</div>
                    </div>
                  </div>
                  <TaskStatusBadge status={mapRepoStatus(repo)} />
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {selectedRepo ? (
        <div className="rounded-[20px] border border-[#ece6da] bg-[#fffdf9] p-4 dark:border-[#383632] dark:bg-[#151412]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">Selected Repo</div>
              <div className="mt-2 text-[28px] leading-none font-medium text-[#141413] dark:text-[#faf9f5]">{selectedRepo.displayName}</div>
            </div>
            <TaskStatusBadge status={mapRepoStatus(selectedRepo)} />
          </div>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            <InfoPill label="仓库标识" value={selectedRepo.displayName} />
            <InfoPill label="构建结果" value={selectedRepo.build ?? 'n/a'} />
            <InfoPill label="分支" value={selectedRepo.branch ?? '尚未创建'} />
            <InfoPill label="工作区" value={selectedRepo.worktree ?? '尚未创建'} />
          </div>
          <div className="mt-4 rounded-[18px] border border-[#ece6da] bg-[#fffaf2] px-4 py-4 text-sm text-[#8a7a67] dark:border-[#383632] dark:bg-[#11100f] dark:text-[#b8ae9e]">
            {selectedRepo.path}
          </div>
          {selectedRepo.failureHint ? <div className="mt-4 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{selectedRepo.failureHint}</div> : null}
          <button
            className="mt-6 rounded-[16px] border border-[#d56b45] bg-[#d56b45] px-6 py-3 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(213,107,69,1)] transition hover:bg-[#df7b57] disabled:cursor-not-allowed disabled:opacity-55"
            disabled={!repoReadyForCode(selectedRepo) || busyAction === 'code'}
            onClick={() => void onStartCode(selectedRepo.id)}
            type="button"
          >
            {repoReadyForCode(selectedRepo) ? (busyAction === 'code' ? '开始中...' : '开始实现') : '等待可实现'}
          </button>
        </div>
      ) : null}
    </div>
  )
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

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex items-center gap-3 rounded-full border border-[#e2d8cb] bg-[#fffaf2] px-4 py-3 text-sm dark:border-[#3d3934] dark:bg-[#11100f]">
      <span className="text-[#9a9185] dark:text-[#8f8a82]">{label}</span>
      <span className="text-[#141413] dark:text-[#faf9f5]">{value}</span>
    </div>
  )
}
