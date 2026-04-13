import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getWorkspace, listTasks, type TaskListItem, type WorkspaceSummary } from '../api'

type AppDataContextValue = {
  tasks: TaskListItem[]
  workspace: WorkspaceSummary | null
  loading: boolean
  error: string
  reload: () => Promise<void>
}

const AppDataContext = createContext<AppDataContextValue>({
  tasks: [],
  workspace: null,
  loading: true,
  error: '',
  reload: async () => {},
})

export function AppDataProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<TaskListItem[]>([])
  const [workspace, setWorkspace] = useState<WorkspaceSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async (cancelled = false) => {
    try {
      setLoading(true)
      const [taskItems, workspaceSummary] = await Promise.all([listTasks(), getWorkspace()])
      if (cancelled) {
        return
      }
      setTasks(taskItems)
      setWorkspace(workspaceSummary)
      setError('')
    } catch (err) {
      if (cancelled) {
        return
      }
      setError(err instanceof Error ? err.message : '加载数据失败')
    } finally {
      if (!cancelled) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    let cancelled = false
    void load(cancelled)
    return () => {
      cancelled = true
    }
  }, [])

  const reload = async () => {
    await load(false)
  }

  const value = useMemo(
    () => ({ tasks, workspace, loading, error, reload }),
    [tasks, workspace, loading, error],
  )

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>
}

export function useAppData() {
  return useContext(AppDataContext)
}
