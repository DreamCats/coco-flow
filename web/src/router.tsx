import {
  Link,
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
import { TopNavItem } from './components/ui-primitives'
import { KnowledgePage } from './routes/knowledge'
import { TasksIndexPage, TasksLayout, TaskDetailPage } from './routes/tasks'
import { WorkspacePage } from './routes/workspace'

const themeStorageKey = 'coco-ext-ui-theme'
const executionContextStorageKey = 'coco-flow-ui-execution-context'

type ThemeMode = 'system' | 'light' | 'dark'
type ExecutionContext = {
  mode: 'local' | 'remote'
  remoteName: string
  remoteHost: string
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

function readExecutionContext(): ExecutionContext {
  if (typeof window === 'undefined') {
    return { mode: 'local', remoteName: '', remoteHost: '' }
  }
  const raw = window.sessionStorage.getItem(executionContextStorageKey)
  if (!raw) {
    return { mode: 'local', remoteName: '', remoteHost: '' }
  }
  try {
    const parsed = JSON.parse(raw) as Partial<ExecutionContext>
    if (parsed.mode === 'remote') {
      return {
        mode: 'remote',
        remoteName: typeof parsed.remoteName === 'string' ? parsed.remoteName : '',
        remoteHost: typeof parsed.remoteHost === 'string' ? parsed.remoteHost : '',
      }
    }
  } catch {}
  return { mode: 'local', remoteName: '', remoteHost: '' }
}

function AppShell() {
  const location = useLocation()
  const { error } = useAppData()
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    if (typeof window === 'undefined') {
      return 'system'
    }
    const stored = window.localStorage.getItem(themeStorageKey)
    return isThemeMode(stored) ? stored : 'system'
  })
  const [activeTheme, setActiveTheme] = useState<'light' | 'dark'>(() => resolveTheme(themeMode))
  const [executionContext, setExecutionContext] = useState<ExecutionContext>(() => readExecutionContext())

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

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }
    const url = new URL(window.location.href)
    const mode = url.searchParams.get('coco_flow_context')
    if (mode !== 'remote') {
      setExecutionContext(readExecutionContext())
      return
    }
    const nextContext: ExecutionContext = {
      mode: 'remote',
      remoteName: url.searchParams.get('remote_name') || '',
      remoteHost: url.searchParams.get('remote_host') || '',
    }
    window.sessionStorage.setItem(executionContextStorageKey, JSON.stringify(nextContext))
    url.searchParams.delete('coco_flow_context')
    url.searchParams.delete('remote_name')
    url.searchParams.delete('remote_host')
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
    setExecutionContext(nextContext)
  }, [location.pathname, location.search, location.href])

  return (
    <div className="min-h-screen bg-[#f5f4ed] text-[#141413] transition-colors dark:bg-[#141413] dark:text-[#faf9f5]">
      <div className="mx-auto flex min-h-screen max-w-[1280px] flex-col px-4 py-4 md:px-6 lg:px-8">
        <header className="mb-3 rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5]/96 px-5 py-5 shadow-[0_0_0_1px_rgba(240,238,230,0.9),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a]/96 dark:shadow-[0_0_0_1px_rgba(48,48,46,0.94)]">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Workbench</div>
                <h1 className="mt-2 text-[34px] leading-[1.12] font-medium text-[#141413] [font-family:Georgia,serif] md:text-[42px] dark:text-[#faf9f5]">
                  需求交付工作台
                </h1>
                {error ? <p className="mt-3 text-sm text-[#b53333]">{error}</p> : null}
              </div>

              <div className="flex flex-col gap-2 lg:items-end">
                <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">菜单</div>
                <div className="flex flex-wrap items-center gap-3">
                  <ExecutionContextChip context={executionContext} />
                  <span className="text-sm text-[#5e5d59] dark:text-[#b0aea5]">主题</span>
                  <div className="inline-flex rounded-[16px] bg-[#e8e6dc] p-1 shadow-[0_0_0_1px_rgba(209,207,197,0.9)] dark:bg-[#30302e] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]">
                    {(['system', 'light', 'dark'] as ThemeMode[]).map((mode) => {
                      const active = themeMode === mode
                      return (
                        <button
                          className={`rounded-[12px] px-3 py-1.5 text-[12px] transition ${
                            active
                              ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                              : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
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
                  <span className="text-sm text-[#87867f] dark:text-[#b0aea5]">当前主题：{activeTheme === 'dark' ? '暗色' : '浅色'}</span>
                </div>
              </div>
            </div>

            <div className="border-t border-[#e8e6dc] pt-4 dark:border-[#30302e]">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">导航</div>
              <div className="mt-3 flex flex-wrap gap-3">
                <TopNavItem
                  description="查看任务进度、下一步动作和关键产物。"
                  isActive={location.pathname.startsWith('/tasks') || location.pathname === '/'}
                  title="任务推进"
                  to="/tasks"
                />
                <TopNavItem
                  description="浏览知识文档，直接维护 Markdown 文件和 frontmatter。"
                  isActive={location.pathname.startsWith('/knowledge')}
                  title="知识工作台"
                  to="/knowledge"
                />
              </div>
            </div>
          </div>
        </header>

        <main className="relative min-h-0 flex-1 overflow-y-auto rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5]/94 p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1a1918]/94 dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)] lg:p-5">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function ExecutionContextChip({ context }: { context: ExecutionContext }) {
  const isRemote = context.mode === 'remote'
  const label = isRemote ? `Remote · ${context.remoteName || context.remoteHost || 'Connected'}` : 'Local'
  const title = isRemote
    ? `Remote execution\nRemote: ${context.remoteName || '-'}\nHost: ${context.remoteHost || '-'}`
    : 'Local execution\nTasks, repos, and worktrees run on this machine'

  return (
    <Link
      className={`inline-flex items-center gap-2 rounded-[14px] border px-3 py-2 text-[12px] leading-none transition ${
        isRemote
          ? 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] shadow-[0_0_0_1px_rgba(240,238,230,0.92)] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)] dark:hover:text-[#faf9f5]'
          : 'border-[#e8e6dc] bg-[#f5f4ed] text-[#87867f] shadow-[0_0_0_1px_rgba(240,238,230,0.88)] hover:text-[#5e5d59] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#8f8a82] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.94)] dark:hover:text-[#b0aea5]'
      }`}
      title={title}
      to="/workspace"
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isRemote ? 'bg-[#c96442] dark:bg-[#d97757]' : 'bg-[#b0aea5] dark:bg-[#5e5d59]'
        }`}
      />
      <span className="whitespace-nowrap">{label}</span>
    </Link>
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

const knowledgeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'knowledge',
  component: KnowledgePage,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  tasksRoute.addChildren([tasksIndexRoute, taskDetailRoute]),
  knowledgeRoute,
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
