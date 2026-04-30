import { Link, useLocation, useNavigate } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import { deleteTask, type TaskListItem } from '../../api'
import { ConfirmationModal } from '../../components/confirmation-modal'
import { useAppData } from '../../hooks/use-app-data'
import { truncateTaskTitle } from './model'
import { TaskCreateModal } from './task-create-modal'

export function TaskListPane({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean
  onToggleCollapsed: () => void
}) {
  const { tasks, loading, error, reload } = useAppData()
  const navigate = useNavigate()
  const location = useLocation()
  const [query, setQuery] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<TaskListItem | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  const filteredTasks = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) {
      return tasks
    }
    return tasks.filter((task) => task.title.toLowerCase().includes(keyword) || task.id.toLowerCase().includes(keyword) || task.repoIds.some((repoId) => repoId.toLowerCase().includes(keyword)))
  }, [tasks, query])

  async function confirmDeleteTask() {
    if (!deleteTarget) {
      return
    }
    try {
      setDeleteBusy(true)
      setDeleteError('')
      await deleteTask(deleteTarget.id)
      await reload()
      if (location.pathname === `/tasks/${deleteTarget.id}`) {
        void navigate({ to: '/tasks' })
      }
      setDeleteTarget(null)
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : '删除 task 失败')
    } finally {
      setDeleteBusy(false)
    }
  }

  return (
    <>
      <section className="border-b border-[#e8e6dc] bg-[#faf9f5] dark:border-[#30302e] dark:bg-[#1d1c1a] lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden lg:border-r lg:border-b-0">
        <div className={`border-b border-[#e8e6dc] dark:border-[#30302e] ${collapsed ? 'px-3 py-4' : 'px-5 py-5'}`}>
          <div className={`flex items-start gap-3 ${collapsed ? 'flex-col items-center' : 'justify-between'}`}>
            <div className={`min-w-0 ${collapsed ? 'hidden' : ''}`}>
              <h2 className="text-xl font-semibold tracking-[-0.02em] text-[#141413] dark:text-[#faf9f5]">任务</h2>
              <div className="mt-3 flex items-center gap-4 text-xs text-[#87867f] dark:text-[#b0aea5]">
                <span className="font-medium text-[#c96442]">全部 {tasks.length}</span>
                <span>运行中 {tasks.filter((task) => new Set(['refining', 'designing', 'planning', 'coding']).has(task.status)).length}</span>
                <span>失败 {tasks.filter((task) => task.status === 'failed').length}</span>
              </div>
            </div>
            <div className={`flex gap-2 ${collapsed ? 'flex-col' : ''}`}>
              <button
                className="inline-flex h-9 w-9 items-center justify-center rounded-[9px] border border-[#e8e6dc] bg-[#ffffff] text-[#87867f] transition hover:bg-[#f5f4ed] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:hover:bg-[#232220] dark:hover:text-[#faf9f5]"
                onClick={onToggleCollapsed}
                title={collapsed ? '展开任务列表' : '收起任务列表'}
                type="button"
              >
                {collapsed ? <ExpandListIcon /> : <CollapseListIcon />}
              </button>
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-[9px] bg-[#141413] text-[#faf9f5] transition hover:bg-[#5e5d59] dark:bg-[#faf9f5] dark:text-[#141413] dark:hover:bg-[#e8e6dc]"
              onClick={() => setShowCreateModal(true)}
              title="新建任务"
              type="button"
            >
              <PlusIcon />
            </button>
            </div>
          </div>

          <div className={`mt-4 rounded-[10px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 dark:border-[#30302e] dark:bg-[#232220] ${collapsed ? 'hidden' : ''}`}>
            <input
              className="w-full bg-transparent text-sm text-[#141413] outline-none placeholder:text-[#b0aea5] dark:text-[#faf9f5] dark:placeholder:text-[#87867f]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题、任务编号或仓库"
              type="text"
              value={query}
            />
          </div>
        </div>

        {loading ? (
          <TaskPaneMessage>正在加载 task 列表...</TaskPaneMessage>
        ) : error ? (
          <TaskPaneMessage>{error}</TaskPaneMessage>
        ) : filteredTasks.length === 0 ? (
          <TaskPaneMessage>当前没有匹配的 task。</TaskPaneMessage>
        ) : (
          <div className={`lg:min-h-0 lg:flex-1 lg:overflow-y-auto ${collapsed ? 'space-y-2 px-2 py-3' : 'divide-y divide-[#f0eee6] dark:divide-[#30302e]'}`}>
            {filteredTasks.map((task) => (
              <TaskListItemCard
                compact={collapsed}
                key={task.id}
                onDelete={() => {
                  setDeleteError('')
                  setDeleteTarget(task)
                }}
                task={task}
              />
            ))}
          </div>
        )}
      </section>

      {showCreateModal ? (
        <TaskCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreated={async (taskId) => {
            await reload()
            setShowCreateModal(false)
            void navigate({ to: '/tasks/$taskId', params: { taskId } })
          }}
        />
      ) : null}

      <ConfirmationModal
        busy={deleteBusy}
        confirmLabel="删除任务"
        description={deleteTarget ? `删除后会移除 task ${deleteTarget.id} 的目录和当前阶段产物，该操作不可恢复。` : ''}
        error={deleteError}
        eyebrow="Task Deletion"
        impacts={deleteTarget ? ['仅允许删除未进入 code 的 task', '当前 task 目录和所有 artifact 会一起删除', '如果你正在查看该 task，删除后会返回任务列表'] : []}
        onClose={() => {
          if (!deleteBusy) {
            setDeleteTarget(null)
            setDeleteError('')
          }
        }}
        onConfirm={() => void confirmDeleteTask()}
        open={Boolean(deleteTarget)}
        title={deleteTarget ? `删除 ${deleteTarget.id}` : ''}
        tone="danger"
      />
    </>
  )
}

function TaskListItemCard({ task, onDelete, compact }: { task: TaskListItem; onDelete: () => void; compact: boolean }) {
  const location = useLocation()
  const active = location.pathname === `/tasks/${task.id}`
  if (compact) {
    return (
      <Link
        className={`flex h-11 w-full items-center justify-center rounded-[10px] transition ${
          active
            ? 'bg-[#fff1ed] text-[#141413] dark:bg-[#351b17] dark:text-[#faf9f5]'
            : 'text-[#4d4c48] hover:bg-[#faf9f5] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:bg-[#232220] dark:hover:text-[#faf9f5]'
        }`}
        params={{ taskId: task.id }}
        resetScroll={false}
        title={`${task.title}\n${taskStatusText(task.status)}`}
        to="/tasks/$taskId"
      >
        <StatusDot status={task.status} />
      </Link>
    )
  }

  return (
    <div
      className={`block px-5 py-4 transition ${
        active
          ? 'bg-[#fff1ed] text-[#141413] dark:bg-[#351b17] dark:text-[#faf9f5]'
          : 'bg-[#faf9f5] text-[#141413] hover:bg-[#f5f4ed] dark:bg-[#1d1c1a] dark:text-[#faf9f5] dark:hover:bg-[#232220]'
      }`}
    >
      <Link className="block" params={{ taskId: task.id }} resetScroll={false} to="/tasks/$taskId">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 gap-3">
            <StatusDot status={task.status} />
            <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold leading-5 tracking-[-0.02em]" title={task.title}>
              {truncateTaskTitle(task.title, 18)}
            </div>
            <div className={`mt-1 text-xs ${active ? 'text-[#4d4c48] dark:text-[#b0aea5]' : 'text-[#87867f] dark:text-[#b0aea5]'}`}>
              {taskStatusText(task.status)}
              {task.repoCount > 0 ? ` · ${task.repoCount} 仓库` : ''}
            </div>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            {canDeleteTaskStatus(task.status) ? (
              <button
                className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[#b0aea5] transition hover:bg-[#f5f4ed] hover:text-[#4d4c48] dark:text-[#87867f] dark:hover:bg-[#30302e] dark:hover:text-[#b0aea5]"
                onClick={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                  onDelete()
                }}
                title="删除任务"
                type="button"
              >
                <CloseIcon />
              </button>
            ) : null}
          </div>
        </div>
        <div className={`mt-3 flex items-center justify-between pl-6 text-xs ${active ? 'text-[#4d4c48] dark:text-[#b0aea5]' : 'text-[#87867f] dark:text-[#b0aea5]'}`}>
          <span className="font-mono">{task.id}</span>
          <span>{task.updatedAt}</span>
        </div>
      </Link>
    </div>
  )
}

function TaskPaneMessage({ children }: { children: React.ReactNode }) {
  return (
    <section className="flex min-h-[420px] items-center justify-center rounded-[24px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] p-6 text-center text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
      {children}
    </section>
  )
}

function canDeleteTaskStatus(status: TaskListItem['status']) {
  return new Set(['initialized', 'input_processing', 'input_ready', 'input_failed', 'refined', 'designing', 'designed', 'planned', 'failed']).has(status)
}

function StatusDot({ status }: { status: TaskListItem['status'] }) {
  const tone = status === 'failed' ? 'bg-[#b53333]' : new Set(['refining', 'designing', 'planning', 'coding']).has(status) ? 'bg-[#c96442]' : new Set(['coded', 'archived']).has(status) ? 'bg-[#4fa06d]' : 'border border-[#b0aea5] bg-transparent'
  return <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${tone}`} />
}

function taskStatusText(status: TaskListItem['status']) {
  if (status === 'refining') {
    return '正在生成 · Refine'
  }
  if (status === 'designing') {
    return '正在生成 · Design'
  }
  if (status === 'planning') {
    return '正在生成 · Plan'
  }
  if (status === 'coding') {
    return '正在实现 · Code'
  }
  if (status === 'failed') {
    return '失败'
  }
  if (status === 'coded' || status === 'archived') {
    return '已完成'
  }
  return status
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  )
}

function CollapseListIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      <path d="M20 5v14" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

function ExpandListIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
      <path d="M4 5v14" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 14 14" width="14">
      <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  )
}
