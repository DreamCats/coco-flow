import { Link, useLocation, useNavigate } from '@tanstack/react-router'
import { useMemo, useState } from 'react'
import { deleteTask, type TaskListItem } from '../../api'
import { useAppData } from '../../hooks/use-app-data'
import { TaskCreateModal } from './task-create-modal'
import { TaskStatusBadge } from './ui'

export function TaskListPane() {
  const { tasks, loading, error, reload } = useAppData()
  const navigate = useNavigate()
  const location = useLocation()
  const [query, setQuery] = useState('')
  const [showCreateModal, setShowCreateModal] = useState(false)

  const filteredTasks = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    if (!keyword) {
      return tasks
    }
    return tasks.filter((task) => task.title.toLowerCase().includes(keyword) || task.id.toLowerCase().includes(keyword) || task.repoIds.some((repoId) => repoId.toLowerCase().includes(keyword)))
  }, [tasks, query])

  async function handleDelete(task: TaskListItem) {
    if (!window.confirm(`确认删除 task ${task.id}？仅允许删除未进入 code 的 task。`)) {
      return
    }
    try {
      await deleteTask(task.id)
      await reload()
      if (location.pathname === `/tasks/${task.id}`) {
        void navigate({ to: '/tasks' })
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '删除 task 失败')
    }
  }

  return (
    <>
      <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-2.5 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.94)] lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden">
        <div className="mb-2.5 rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">任务推进</div>
              <h2 className="mt-2 text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">任务队列</h2>
              <p className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">选择任务后，在右侧按阶段推进。</p>
            </div>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#c96442] bg-[#c96442] text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]"
              onClick={() => setShowCreateModal(true)}
              title="新建任务"
              type="button"
            >
              <PlusIcon />
            </button>
          </div>

          <div className="mt-3 rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 dark:border-[#30302e] dark:bg-[#232220]">
            <input
              className="w-full bg-transparent text-sm text-[#141413] outline-none placeholder:text-[#87867f] dark:text-[#faf9f5] dark:placeholder:text-[#87867f]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题、任务编号或仓库"
              type="text"
              value={query}
            />
          </div>
        </div>

        <div className="mb-2 flex items-center justify-between px-1">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">任务列表</div>
          <div className="text-xs text-stone-500 dark:text-stone-400">{loading ? '...' : `${filteredTasks.length} 条`}</div>
        </div>

        {loading ? (
          <TaskPaneMessage>正在加载 task 列表...</TaskPaneMessage>
        ) : error ? (
          <TaskPaneMessage>{error}</TaskPaneMessage>
        ) : filteredTasks.length === 0 ? (
          <TaskPaneMessage>当前没有匹配的 task。</TaskPaneMessage>
        ) : (
          <div className="space-y-1.5 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
            {filteredTasks.map((task) => (
              <TaskListItemCard key={task.id} onDelete={() => void handleDelete(task)} task={task} />
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
    </>
  )
}

function TaskListItemCard({ task, onDelete }: { task: TaskListItem; onDelete: () => void }) {
  const location = useLocation()
  const active = location.pathname === `/tasks/${task.id}`
  return (
    <div
      className={`block rounded-[18px] border px-3.5 py-3 transition ${
        active
          ? 'border-[#c96442] bg-[#fff7f2] text-[#141413] shadow-[0_0_0_1px_rgba(201,100,66,0.2),0_4px_24px_rgba(20,20,19,0.06)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(217,119,87,0.24)]'
          : 'border-[#e8e6dc] bg-[#faf9f5] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.9)] hover:bg-[#f5f4ed] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)] dark:hover:bg-[#2a2927]'
      }`}
    >
      <Link className="block" params={{ taskId: task.id }} resetScroll={false} to="/tasks/$taskId">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[15px] font-semibold leading-5 tracking-[-0.03em]">{task.title}</div>
            <div className={`mt-1 text-[11px] font-mono ${active ? 'text-[#87867f] dark:text-[#d8b2a6]' : 'text-stone-500 dark:text-stone-400'}`}>{task.id}</div>
          </div>
          <div className="flex flex-col items-end gap-2">
            <TaskStatusBadge status={task.status} />
            {canDeleteTaskStatus(task.status) ? (
              <button
                className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[#87867f] transition hover:bg-[#f1ece4] hover:text-[#4d4c48] dark:text-[#8f8a82] dark:hover:bg-[#24221f] dark:hover:text-[#f1ede4]"
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
        <div className={`mt-3 flex items-center justify-between text-xs ${active ? 'text-[#5e5d59] dark:text-[#d8b2a6]' : 'text-stone-500 dark:text-stone-400'}`}>
          <span>{task.repoCount > 0 ? `${task.repoCount} 仓库` : '尚未绑定仓库'}</span>
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
  return new Set(['initialized', 'refined', 'planned', 'failed']).has(status)
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
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
