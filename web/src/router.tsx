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
import { useEffect, useState, type ReactNode } from 'react'
import { AppDataProvider, useAppData } from './hooks/use-app-data'
import { SkillsPage } from './routes/skills'
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
  } catch {
    return { mode: 'local', remoteName: '', remoteHost: '' }
  }
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
  const [executionContext, setExecutionContext] = useState<ExecutionContext>(() => readExecutionContext())
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const applyTheme = () => {
      const nextTheme = resolveTheme(themeMode)
      document.documentElement.dataset.theme = nextTheme
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

  const skillsActive = location.pathname.startsWith('/skills') || location.pathname.startsWith('/knowledge')

  return (
    <div className="min-h-screen bg-[#f5f4ed] text-[#141413] transition-colors dark:bg-[#141413] dark:text-[#faf9f5]">
      <div className="flex min-h-screen flex-col lg:flex-row">
        <aside
          className={`flex border-b border-[#e8e6dc] bg-[#faf9f5] transition-[width] duration-200 dark:border-[#30302e] dark:bg-[#1d1c1a] lg:min-h-screen lg:flex-col lg:border-r lg:border-b-0 ${
            sidebarCollapsed ? 'lg:w-[96px]' : 'lg:w-[240px]'
          }`}
        >
          <div className={`relative flex min-w-[220px] items-center gap-3 px-5 py-5 lg:min-w-0 ${sidebarCollapsed ? 'lg:justify-between lg:px-3' : ''}`}>
            <div className="flex h-8 w-8 items-center justify-center rounded-[8px] bg-[#141413] text-xs font-semibold text-[#faf9f5]">cf</div>
            <div className={`min-w-0 ${sidebarCollapsed ? 'lg:hidden' : ''}`}>
              <div className="truncate text-lg font-semibold tracking-[-0.02em] text-[#141413] dark:text-[#faf9f5]">coco-flow</div>
              <div className="text-xs text-[#87867f] dark:text-[#b0aea5]">需求交付工作台</div>
            </div>
            <button
              className={`hidden h-8 w-8 items-center justify-center rounded-[8px] text-[#87867f] transition hover:bg-[#f5f4ed] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:bg-[#30302e] dark:hover:text-[#faf9f5] lg:inline-flex ${
                sidebarCollapsed ? 'lg:h-7 lg:w-7' : 'ml-auto'
              }`}
              onClick={() => setSidebarCollapsed((current) => !current)}
              title={sidebarCollapsed ? '展开导航' : '收起导航'}
              type="button"
            >
              <CollapseLeftIcon />
            </button>
          </div>

          <nav className={`flex flex-1 items-center gap-2 overflow-x-auto px-3 py-3 lg:flex-col lg:overflow-visible ${sidebarCollapsed ? 'lg:items-center lg:px-2' : 'lg:items-stretch lg:px-4'}`}>
            <SidebarNavItem
              collapsed={sidebarCollapsed}
              icon={<TaskIcon />}
              isActive={location.pathname.startsWith('/tasks') || location.pathname === '/'}
              title="任务"
              to="/tasks"
            />
            <SidebarNavItem collapsed={sidebarCollapsed} icon={<BookIcon />} isActive={skillsActive} title="知识库" to="/skills" />
            <SidebarNavItem collapsed={sidebarCollapsed} icon={<SettingsIcon />} isActive={location.pathname.startsWith('/workspace')} title="设置" to="/workspace" />
          </nav>

          <div className={`hidden border-t border-[#e8e6dc] p-4 dark:border-[#30302e] lg:block ${sidebarCollapsed ? 'lg:hidden' : ''}`}>
            <ExecutionContextChip context={executionContext} />
            <div className="mt-3 grid grid-cols-3 rounded-[10px] border border-[#e8e6dc] bg-[#faf9f5] p-1 dark:border-[#30302e] dark:bg-[#232220]">
              {(['system', 'light', 'dark'] as ThemeMode[]).map((mode) => {
                const active = themeMode === mode
                return (
                  <button
                    className={`rounded-[8px] px-2 py-1.5 text-[11px] transition ${
                      active
                        ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                        : 'text-[#87867f] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
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
        </aside>

        <main className="min-w-0 flex-1 overflow-hidden">
          {error ? <div className="border-b border-[#fecaca] bg-[#fef2f2] px-5 py-3 text-sm text-[#b91c1c]">{error}</div> : null}
          <div className={location.pathname.startsWith('/tasks') || location.pathname === '/' ? 'min-h-full' : 'min-h-screen overflow-y-auto p-6'}>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}

function SidebarNavItem({
  collapsed,
  icon,
  isActive,
  title,
  to,
}: {
  collapsed: boolean
  icon: ReactNode
  title: string
  to: '/tasks' | '/workspace' | '/skills'
  isActive: boolean
}) {
  return (
    <Link
      className={`flex shrink-0 items-center gap-3 rounded-[10px] px-3 py-2.5 text-sm transition ${collapsed ? 'lg:h-10 lg:w-10 lg:justify-center lg:px-0' : ''} ${
        isActive
          ? 'bg-[#f5f4ed] font-medium text-[#141413] dark:bg-[#30302e] dark:text-[#faf9f5]'
          : 'text-[#4d4c48] hover:bg-[#faf9f5] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:bg-[#232220] dark:hover:text-[#faf9f5]'
      }`}
      title={collapsed ? title : undefined}
      to={to}
    >
      <span className="flex h-5 w-5 items-center justify-center">{icon}</span>
      <span className={collapsed ? 'lg:hidden' : ''}>{title}</span>
    </Link>
  )
}

function ExecutionContextChip({ context }: { context: ExecutionContext }) {
  const isRemote = context.mode === 'remote'
  const label = isRemote ? `Remote · ${context.remoteName || context.remoteHost || 'Connected'}` : 'Local'
  const title = isRemote
    ? `Remote execution\nRemote: ${context.remoteName || '-'}\nHost: ${context.remoteHost || '-'}`
    : 'Local execution\nTasks, repos, and worktrees run on this machine'

  return (
    <div
      className={`inline-flex w-full items-center gap-2 rounded-[10px] border px-3 py-2 text-[12px] leading-none ${
        isRemote
          ? 'border-[#e8e6dc] bg-[#fff1ed] text-[#c96442] dark:border-[#8f3c2e] dark:bg-[#351b17] dark:text-[#f0c0b0]'
          : 'border-[#e8e6dc] bg-[#faf9f5] text-[#4d4c48] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]'
      }`}
      title={title}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          isRemote ? 'bg-[#c96442] dark:bg-[#d97757]' : 'bg-[#b0aea5] dark:bg-[#5e5d59]'
        }`}
      />
      <span className="whitespace-nowrap">{label}</span>
    </div>
  )
}

function TaskIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M8 6h10M8 12h10M8 18h10M5 6h.01M5 12h.01M5 18h.01" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  )
}

function CollapseLeftIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
    </svg>
  )
}

function BookIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5v-16Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M5 5.5A2.5 2.5 0 0 0 7.5 8H19" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </svg>
  )
}

function SettingsIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" stroke="currentColor" strokeWidth="1.7" />
      <path d="M19 13.5v-3l-2.1-.4a5.7 5.7 0 0 0-.6-1.4l1.2-1.8-2.1-2.1-1.8 1.2a6 6 0 0 0-1.5-.6L11.7 3h-3l-.4 2.1a6 6 0 0 0-1.5.6L5 4.5 2.9 6.6l1.2 1.8a5.7 5.7 0 0 0-.6 1.4L1.5 10.2v3l2 .4c.2.5.4 1 .7 1.5L3 16.9 5.1 19l1.8-1.2c.5.3 1 .5 1.5.6l.4 2.1h3l.4-2.1c.5-.1 1-.3 1.5-.6l1.8 1.2 2.1-2.1-1.2-1.8c.3-.5.5-1 .6-1.5l2-.4Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.4" />
    </svg>
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

const skillsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'skills',
  component: SkillsPage,
})

const legacyKnowledgeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: 'knowledge',
  component: () => <Navigate replace to="/skills" />,
})

const routeTree = rootRoute.addChildren([
  indexRoute,
  tasksRoute.addChildren([tasksIndexRoute, taskDetailRoute]),
  skillsRoute,
  legacyKnowledgeRoute,
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
