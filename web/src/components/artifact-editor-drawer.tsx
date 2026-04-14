import { useEffect } from 'react'
import type { TaskArtifactName } from '../api'
import { artifactLabel } from './artifact-viewer'

export function ArtifactEditorDrawer({
  artifact,
  busy,
  canSave,
  error,
  onChange,
  onClose,
  onSave,
  open,
  taskStatus,
  value,
}: {
  artifact: TaskArtifactName
  busy: boolean
  canSave: boolean
  error: string
  onChange: (value: string) => void
  onClose: () => void
  onSave: () => void
  open: boolean
  taskStatus: string
  value: string
}) {
  useEffect(() => {
    if (!open) {
      return
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [busy, onClose, open])

  if (!open) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-[rgba(20,20,19,0.22)] backdrop-blur-sm dark:bg-[rgba(20,20,19,0.58)]"
      onClick={() => (!busy ? onClose() : undefined)}
    >
      <div
        className="flex h-full w-full max-w-[820px] flex-col border-l border-[#e8e6dc] bg-[#faf9f5] text-[#141413] shadow-[-24px_0_60px_rgba(20,20,19,0.12)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#faf9f5] dark:shadow-[-24px_0_60px_rgba(0,0,0,0.32)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Artifact Edit</div>
              <h3 className="mt-2 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                {artifactLabel(artifact)}
              </h3>
              <p className="mt-2 text-[15px] leading-7 text-[#5e5d59] dark:text-[#b0aea5]">{editHint(artifact, taskStatus)}</p>
            </div>
            <button
              className="rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-2 text-xs text-[#4d4c48] transition hover:bg-[#ddd9cc] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
              disabled={busy}
              onClick={onClose}
              type="button"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="flex-1 px-6 py-5">
          <textarea
            className="h-full min-h-[420px] w-full resize-none rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] px-5 py-5 font-mono text-sm leading-7 text-[#141413] outline-none shadow-[0_0_0_1px_rgba(240,238,230,0.88)] transition focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:focus:border-[#3898ec]"
            onChange={(event) => onChange(event.target.value)}
            spellCheck={false}
            value={value}
          />
        </div>

        <div className="border-t border-[#e8e6dc] px-6 py-4 dark:border-[#30302e]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className={`text-sm ${error ? 'text-[#b53333]' : 'text-[#87867f] dark:text-[#b0aea5]'}`}>
              {error || '保存后会直接覆盖 task 目录中的对应 Markdown 文件。'}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-4 py-2.5 text-sm text-[#4d4c48] transition hover:bg-[#ddd9cc] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
                disabled={busy}
                onClick={onClose}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2.5 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!canSave || busy}
                onClick={onSave}
                type="button"
              >
                {busy ? '保存中...' : '保存修改'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function editHint(artifact: TaskArtifactName, taskStatus: string) {
  switch (artifact) {
    case 'prd.source.md':
      return `保存后会清理 refined/design/plan，并将任务状态回退到 initialized。当前状态：${taskStatus}。`
    case 'prd-refined.md':
      return `保存后会清理 design/plan，并将任务状态回退到 refined。当前状态：${taskStatus}。`
    case 'design.md':
    case 'plan.md':
      return `保存后保留 planned 状态，适合手工微调方案文档。当前状态：${taskStatus}。`
    default:
      return `当前状态：${taskStatus}。`
  }
}
