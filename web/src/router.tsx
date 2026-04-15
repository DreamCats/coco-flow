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
import { TopNavItem } from './components/ui-primitives'
import { TasksIndexPage, TasksLayout, TaskDetailPage } from './routes/tasks'
import { WorkspacePage } from './routes/workspace'

const themeStorageKey = 'coco-ext-ui-theme'

type ThemeMode = 'system' | 'light' | 'dark'

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
  const { error } = useAppData()
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    if (typeof window === 'undefined') {
      return 'system'
    }
    const stored = window.localStorage.getItem(themeStorageKey)
    return isThemeMode(stored) ? stored : 'system'
  })
  const [activeTheme, setActiveTheme] = useState<'light' | 'dark'>(() => resolveTheme(themeMode))

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
                  description="查看仓库、任务目录和隔离工作区的实际位置。"
                  isActive={location.pathname.startsWith('/workspace')}
                  title="路径视图"
                  to="/workspace"
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
