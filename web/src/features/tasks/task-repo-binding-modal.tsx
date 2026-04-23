import { useEffect, useState } from 'react'
import { updateTaskRepos, type RepoCandidate, type TaskRecord } from '../../api'
import { RepoPicker } from '../../components/repo-picker'

export function TaskRepoBindingModal({
  open,
  task,
  onClose,
  onUpdated,
}: {
  open: boolean
  task: TaskRecord
  onClose: () => void
  onUpdated: () => Promise<void> | void
}) {
  const [selectedRepos, setSelectedRepos] = useState<RepoCandidate[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) {
      return
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    setSelectedRepos(
      task.repos.map((repo) => ({
        id: repo.id,
        displayName: repo.displayName,
        path: repo.path,
      })),
    )
    setError('')
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [open, task])

  async function handleSave() {
    try {
      setSaving(true)
      setError('')
      await updateTaskRepos(
        task.id,
        selectedRepos.map((repo) => repo.path),
      )
      await onUpdated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 bg-[rgba(20,20,19,0.2)] backdrop-blur-sm dark:bg-[rgba(20,20,19,0.58)]" onClick={() => (!saving ? onClose() : undefined)}>
      <div
        className="absolute left-1/2 top-1/2 flex max-h-[calc(100vh-48px)] w-[min(1080px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[28px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_24px_64px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_24px_64px_rgba(0,0,0,0.38)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Repo Binding</div>
              <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">绑定仓库</h3>
              <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                Design 生成前必须先绑定相关仓库。保存后会清理当前 task 的 Design / Plan / Code 下游产物，并回到可重新生成 Design 的状态。
              </p>
            </div>
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-full text-[#87867f] transition hover:bg-[#f1ece4] hover:text-[#4d4c48] disabled:cursor-not-allowed disabled:opacity-60 dark:text-[#8f8a82] dark:hover:bg-[#24221f] dark:hover:text-[#f1ede4]"
              disabled={saving}
              onClick={onClose}
              title="关闭"
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <RepoPicker onChange={setSelectedRepos} selectedRepos={selectedRepos} />
        </div>

        <div className="border-t border-[#e8e6dc] px-6 py-4 dark:border-[#30302e]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className={`text-sm ${error ? 'text-[#b53333]' : 'text-[#87867f] dark:text-[#b0aea5]'}`}>
              {error || '请先绑定相关仓库，再生成 Design。'}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-[14px] border border-[#d1cfc5] bg-[#faf9f5] px-4 py-2.5 text-sm text-[#4d4c48] transition hover:bg-[#efeae0] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]"
                disabled={saving}
                onClick={onClose}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-[14px] border border-[#c96442] bg-[#c96442] px-4 py-2.5 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={saving}
                onClick={() => void handleSave()}
                type="button"
              >
                {saving ? '保存中...' : '保存仓库绑定'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 14 14" width="14">
      <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  )
}
