import { useEffect, useState } from 'react'
import { getTask, type TaskRecord } from '../api'
import { MiniMeta, PanelMessage, PathCard } from '../components/ui-primitives'
import { useAppData } from '../hooks/use-app-data'

export function WorkspacePage() {
  const { tasks, workspace, loading, error } = useAppData()

  if (loading) {
    return <PanelMessage>正在加载 workspace...</PanelMessage>
  }
  if (error) {
    return <PanelMessage>{error}</PanelMessage>
  }
  if (!workspace) {
    return <PanelMessage>未加载到 workspace 数据。</PanelMessage>
  }

  return (
    <div className="space-y-4">
      <section className="rounded-[26px] border border-stone-200 bg-stone-50/70 p-5 dark:border-white/10 dark:bg-white/5">
        <div className="max-w-4xl">
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">路径视图</div>
          <h2 className="mt-2 text-[32px] font-semibold tracking-[-0.05em] text-stone-950 dark:text-stone-50">仓库与执行路径</h2>
          <p className="mt-3 text-sm leading-6 text-stone-600 dark:text-stone-300">
            这里展示任务目录、上下文目录和隔离工作区的实际位置，方便确认任务会落到哪里。
          </p>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-[24px] border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/6">
          <div className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">关键路径</div>
          <div className="space-y-3">
            <PathCard label="仓库根目录" value={workspace.repoRoot} />
            <PathCard label="任务目录" value={workspace.tasksRoot} />
            <PathCard label="上下文目录" value={workspace.contextRoot} />
            <PathCard label="隔离工作区" value={workspace.worktreeRoot} />
          </div>
        </section>

        <section className="rounded-[24px] border border-stone-200 bg-[#161a1f] p-4 text-stone-200">
          <div className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">涉及仓库</div>
          <div className="space-y-2">
            {workspace.reposInvolved.map((repo) => (
              <div className="rounded-2xl border border-white/8 bg-white/4 px-3 py-3 font-mono text-sm" key={repo}>
                {repo}
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="rounded-[24px] border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/6">
        <div className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">已生成的工作区</div>
        <div className="space-y-3">
          {tasks.map((task) => (
            <WorkspaceTaskRow key={task.id} taskID={task.id} />
          ))}
        </div>
      </section>
    </div>
  )
}

function WorkspaceTaskRow({ taskID }: { taskID: string }) {
  const [task, setTask] = useState<TaskRecord | null>(null)

  useEffect(() => {
    let cancelled = false
    void getTask(taskID)
      .then((detail) => {
        if (!cancelled) {
          setTask(detail)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [taskID])

  if (!task) {
    return null
  }

  const reposWithWorktree = task.repos.filter((repo) => repo.worktree)
  if (reposWithWorktree.length === 0) {
    return null
  }

  return (
    <>
      {reposWithWorktree.map((repo) => (
        <div
          className="grid gap-3 rounded-[22px] border border-stone-200 bg-stone-50/80 p-4 dark:border-white/10 dark:bg-white/5 lg:grid-cols-[minmax(0,1fr)_260px_220px]"
          key={`${task.id}-${repo.id}`}
        >
          <div>
            <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{task.title}</div>
            <div className="mt-1 text-xs text-stone-500 dark:text-stone-400">
              {task.id} · <span className="font-semibold text-stone-700 dark:text-stone-300">{repo.displayName}</span>
            </div>
            <div className="mt-3 rounded-2xl border border-stone-200 bg-white px-3 py-3 font-mono text-xs text-stone-600 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-300">
              {repo.worktree}
            </div>
          </div>
          <div className="space-y-2">
            <MiniMeta label="分支" value={repo.branch ?? '-'} />
            <MiniMeta label="构建" value={repo.build ?? '-'} />
          </div>
          <div className="space-y-2">
            <MiniMeta label="提交" value={repo.commit ?? '-'} />
            <MiniMeta label="文件数" value={`${repo.filesWritten?.length ?? 0}`} />
          </div>
        </div>
      ))}
    </>
  )
}
