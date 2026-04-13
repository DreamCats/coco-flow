import {
  Navigate,
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  useLocation,
} from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { AppDataProvider, useAppData } from './hooks/use-app-data'
import { MetricCard, TopNavItem } from './components/ui-primitives'
import { TasksIndexPage, TasksLayout, TaskDetailPage } from './routes/tasks'
import { WorkspacePage } from './routes/workspace'

const themeStorageKey = 'coco-ext-ui-theme'

type ThemeMode = 'system' | 'light' | 'dark'

const taskStatusPriority: Record<string, number> = {
  partially_coded: 0,
  coding: 1,
  planned: 2,
  planning: 3,
  refined: 4,
  initialized: 5,
  failed: 5,
  coded: 6,
  archived: 7,
}

function pickSpotlightTask(tasks: ReturnType<typeof useAppData>['tasks']) {
  return [...tasks].sort((left, right) => {
    const leftPriority = taskStatusPriority[left.status] ?? 99
    const rightPriority = taskStatusPriority[right.status] ?? 99
    if (leftPriority !== rightPriority) {
      return leftPriority - rightPriority
    }
    return right.updatedAt.localeCompare(left.updatedAt)
  })[0]
}

function taskNarrative(status: string) {
  switch (status) {
    case 'partially_coded':
      return '已有仓库完成实现，剩余范围还需要继续推进。'
    case 'coding':
      return '任务正在生成实现并验证结果，适合优先跟进。'
    case 'planned':
      return '实施方案已经准备好，可以安排进入实现阶段。'
    case 'planning':
      return '系统正在分析代码并整理实施方案，稍后就能进入下一步。'
    case 'refined':
      return '需求已经整理完成，接下来可以生成实施方案。'
    case 'initialized':
      return '任务刚创建，系统正在整理输入内容和涉及仓库。'
    case 'coded':
      return '实现结果已经产出，接下来适合确认结果并收尾。'
    case 'failed':
      return '这次推进中断了，建议先看日志，再决定如何继续。'
    default:
      return '这里会持续展示任务推进、涉及仓库和最新产物。'
  }
}

function taskHeadline(status: string) {
  switch (status) {
    case 'partially_coded':
      return '部分结果已产出'
    case 'coding':
      return '实现推进中'
    case 'planned':
      return '待进入实现'
    case 'planning':
      return '方案生成中'
    case 'refined':
      return '待生成方案'
    case 'initialized':
      return '需求整理中'
    case 'coded':
      return '已产出结果'
    case 'failed':
      return '处理中断'
    default:
      return '持续推进中'
  }
}

function isThemeMode(value: string | null): value is ThemeMode {
  return value === 'system' || value === 'light' || value === 'dark'
}

function systemTheme() {
  if (typeof window === 'undefined') {
    return 'light'
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolveTheme(mode: ThemeMode) {
  return mode === 'system' ? systemTheme() : mode
}

function AppShell() {
  const location = useLocation()
  const { tasks, workspace, loading, error } = useAppData()
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    if (typeof window === 'undefined') {
      return 'system'
    }
    const stored = window.localStorage.getItem(themeStorageKey)
    return isThemeMode(stored) ? stored : 'system'
  })
  const [activeTheme, setActiveTheme] = useState<'light' | 'dark'>(() => resolveTheme(themeMode))
  const activeTasks = tasks.filter((task) => task.status !== 'archived')
  const codedCount = tasks.filter((task) => task.status === 'coded' || task.status === 'partially_coded').length
  const multiRepoCount = tasks.filter((task) => task.repoCount > 1).length
  const waitingCodeCount = tasks.filter(
    (task) => task.status === 'planned' || task.status === 'partially_coded' || task.status === 'coding',
  ).length
  const spotlightTask = pickSpotlightTask(tasks)
  const repoSignals = (workspace?.reposInvolved ?? [])
    .map((repoId) => ({
      repoId,
      taskCount: tasks.filter((task) => task.repoIds.includes(repoId)).length,
      activeCount: tasks.filter(
        (task) =>
          task.repoIds.includes(repoId) && task.status !== 'archived' && task.status !== 'coded' && task.status !== 'failed',
      ).length,
    }))
    .sort((left, right) => right.activeCount - left.activeCount || right.taskCount - left.taskCount)
    .slice(0, 3)

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const applyTheme = () => {
      const nextTheme = resolveTheme(themeMode)
      document.documentElement.dataset.theme = nextTheme
      setActiveTheme(nextTheme)
    }

    applyTheme()
    window.localStorage.setItem(themeStorageKey, themeMode)
    media.addEventListener('change', applyTheme)
    return () => {
      media.removeEventListener('change', applyTheme)
    }
  }, [themeMode])

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(34,197,94,0.12),_transparent_32%),radial-gradient(circle_at_top_right,_rgba(249,115,22,0.15),_transparent_28%),linear-gradient(180deg,_#f6f4ee_0%,_#f2efe7_52%,_#ede7dc_100%)] text-stone-950 transition-colors dark:bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.18),_transparent_26%),radial-gradient(circle_at_top_right,_rgba(251,146,60,0.14),_transparent_22%),linear-gradient(180deg,_#111318_0%,_#0d1014_50%,_#0a0c10_100%)] dark:text-stone-100">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-4 md:px-6 lg:px-8">
        <header className="mb-4 rounded-[28px] border border-stone-200/80 bg-white/80 px-5 py-4 shadow-[0_1px_0_rgba(255,255,255,0.7)_inset,0_24px_50px_rgba(54,47,35,0.06)] backdrop-blur dark:border-white/10 dark:bg-white/6 dark:shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_24px_50px_rgba(0,0,0,0.24)]">
          <div className="flex flex-col gap-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-4xl">
                <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-700 dark:border-emerald-300/20 dark:bg-emerald-400/10 dark:text-emerald-200">
                  需求交付工作台
                </div>
                <h1 className="text-[42px] font-semibold tracking-[-0.06em] text-stone-950 dark:text-stone-50 md:text-[52px]">
                  从需求到交付
                </h1>
                <p className="mt-3 max-w-3xl text-base leading-7 text-stone-600 dark:text-stone-300">
                  在一个界面里查看需求整理、方案生成、实现推进和结果沉淀。你随时都能知道任务走到哪一步，下一步该推进什么。
                </p>
                {error ? <p className="mt-3 text-sm text-rose-600">{error}</p> : null}
              </div>
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-end gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">
                    主题
                  </span>
                  <div className="inline-flex rounded-full border border-stone-200 bg-white p-1 dark:border-white/10 dark:bg-white/6">
                    {(['system', 'light', 'dark'] as ThemeMode[]).map((mode) => {
                      const active = themeMode === mode
                      return (
                        <button
                          className={`rounded-full px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.2em] transition ${
                            active
                              ? 'bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-950'
                              : 'text-stone-500 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100'
                          }`}
                          key={mode}
                          onClick={() => setThemeMode(mode)}
                          type="button"
                        >
                          {mode}
                        </button>
                      )
                    })}
                  </div>
                </div>
                <div className="text-right text-xs text-stone-500 dark:text-stone-400">
                  当前主题：{activeTheme === 'dark' ? '暗色' : '浅色'}
                </div>
                <div className="grid gap-3 text-sm text-stone-600 dark:text-stone-300 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricCard label="进行中任务" value={loading ? '...' : `${activeTasks.length}`} tone="emerald" />
                  <MetricCard label="已有结果" value={loading ? '...' : `${codedCount}`} tone="amber" />
                  <MetricCard label="多仓任务" value={loading ? '...' : `${multiRepoCount}`} tone="sky" />
                  <MetricCard
                    label="待进入实现"
                    value={loading ? '...' : `${waitingCodeCount}`}
                    tone="amber"
                  />
                </div>
              </div>
            </div>

            <div className="grid gap-4 border-t border-stone-200/80 pt-5 dark:border-white/10 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
              <section className="overflow-hidden rounded-[28px] border border-stone-900 bg-[#111317] text-white shadow-[0_30px_80px_rgba(15,23,42,0.18)]">
                <div className="grid gap-4 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_280px]">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-300">当前焦点</div>
                    <h2 className="mt-3 text-[30px] font-semibold tracking-[-0.05em]">
                      {spotlightTask ? spotlightTask.title : '等待新的任务进入队列'}
                    </h2>
                    <p className="mt-3 max-w-2xl text-sm leading-6 text-stone-300">
                      {spotlightTask ? taskNarrative(spotlightTask.status) : '当前还没有任务，可以先创建一条需求开始推进。'}
                    </p>
                    {spotlightTask ? (
                      <div className="mt-5 grid gap-3 md:grid-cols-3">
                        <div className="rounded-[18px] border border-white/8 bg-white/4 px-4 py-3">
                          <div className="text-[11px] uppercase tracking-[0.2em] text-stone-400">当前阶段</div>
                          <div className="mt-2 text-sm font-semibold text-white">{taskHeadline(spotlightTask.status)}</div>
                        </div>
                        <div className="rounded-[18px] border border-white/8 bg-white/4 px-4 py-3">
                          <div className="text-[11px] uppercase tracking-[0.2em] text-stone-400">涉及仓库</div>
                          <div className="mt-2 text-sm font-semibold text-white">{spotlightTask.repoIds.join(', ') || '-'}</div>
                        </div>
                        <div className="rounded-[18px] border border-white/8 bg-white/4 px-4 py-3">
                          <div className="text-[11px] uppercase tracking-[0.2em] text-stone-400">最近更新</div>
                          <div className="mt-2 text-sm font-semibold text-white">{spotlightTask.updatedAt}</div>
                        </div>
                      </div>
                    ) : null}
                  </div>
                  <div className="rounded-[24px] border border-emerald-300/20 bg-emerald-400/10 p-4">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-200">整体概览</div>
                    <div className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-white">
                      {loading ? '加载中...' : `${workspace?.reposInvolved.length ?? 0} 个仓库 · ${tasks.length} 个任务`}
                    </div>
                    <p className="mt-3 text-sm leading-6 text-emerald-100/85">
                      这里汇总当前任务规模、仓库范围和推进节奏，方便你快速判断今天最值得跟进的工作。
                    </p>
                  </div>
                </div>
              </section>

              <div className="grid gap-4">
                <section className="rounded-[24px] border border-stone-200 bg-stone-50/80 p-4 dark:border-white/10 dark:bg-white/5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">重点仓库</div>
                      <h3 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950 dark:text-stone-50">最近最活跃的范围</h3>
                    </div>
                    <div className="rounded-full border border-stone-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:border-white/10 dark:bg-white/6 dark:text-stone-300">
                      最近关注
                    </div>
                  </div>
                  <div className="mt-4 space-y-3">
                    {repoSignals.length > 0 ? (
                      repoSignals.map((repo) => (
                        <div
                          className="grid gap-3 rounded-[18px] border border-stone-200 bg-white px-4 py-3 dark:border-white/10 dark:bg-white/6 sm:grid-cols-[minmax(0,1fr)_120px_120px]"
                          key={repo.repoId}
                        >
                          <div>
                            <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{repo.repoId}</div>
                            <div className="mt-1 text-xs text-stone-500 dark:text-stone-400">最近被多个任务反复涉及的仓库</div>
                          </div>
                          <div>
                            <div className="text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">任务数</div>
                            <div className="mt-2 text-lg font-semibold text-stone-950 dark:text-stone-50">{repo.taskCount}</div>
                          </div>
                          <div>
                            <div className="text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">进行中</div>
                            <div className="mt-2 text-lg font-semibold text-stone-950 dark:text-stone-50">{repo.activeCount}</div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="rounded-[18px] border border-dashed border-stone-300 bg-white px-4 py-4 text-sm text-stone-500 dark:border-white/15 dark:bg-white/6 dark:text-stone-400">
                        还没有足够的数据来识别重点仓库。
                      </div>
                    )}
                  </div>
                </section>

                <div className="flex flex-wrap items-center gap-2">
                  <TopNavItem
                    description="查看任务进度、下一步动作和关键产物。"
                    isActive={location.pathname.startsWith('/tasks') || location.pathname === '/'}
                    title="任务推进"
                    to="/tasks"
                  />
                  <TopNavItem
                    description="查看仓库、任务目录和隔离工作区的实际位置。"
                    isActive={location.pathname.startsWith('/workspace')}
                    title="路径视图"
                    to="/workspace"
                  />
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 border-t border-stone-200/80 pt-4 text-xs uppercase tracking-[0.2em] text-stone-500 dark:border-white/10 dark:text-stone-400">
              <span>Input</span>
              <span>→</span>
              <span>Refine</span>
              <span>→</span>
              <span>Plan</span>
              <span>→</span>
              <span>Code</span>
              <span>→</span>
              <span>Archive</span>
            </div>
          </div>
        </header>

        <main className="relative min-h-0 flex-1 overflow-y-auto rounded-[32px] border border-stone-200/80 bg-white/72 p-4 shadow-[0_1px_0_rgba(255,255,255,0.7)_inset,0_40px_80px_rgba(64,45,18,0.08)] backdrop-blur dark:border-white/10 dark:bg-white/4 dark:shadow-[0_1px_0_rgba(255,255,255,0.04)_inset,0_40px_80px_rgba(0,0,0,0.28)] lg:p-5">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

const rootRoute = createRootRoute({
  component: AppShell,
})

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: () => <Navigate replace to="/tasks" />,
})

const tasksRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'tasks',
  component: TasksLayout,
})

const tasksIndexRoute = createRoute({
  getParentRoute: () => tasksRoute,
  path: '/',
  component: TasksIndexPage,
})

const taskDetailRoute = createRoute({
  getParentRoute: () => tasksRoute,
  path: '$taskId',
  component: TaskDetailPage,
})

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'workspace',
  component: WorkspacePage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  tasksRoute.addChildren([tasksIndexRoute, taskDetailRoute]),
  workspaceRoute,
])

const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

export function AppRouter() {
  return (
    <AppDataProvider>
      <RouterProvider router={router} />
    </AppDataProvider>
  )
}
