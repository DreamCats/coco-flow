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
    <div className="fixed inset-0 z-50 flex justify-end bg-stone-950/38 backdrop-blur-sm" onClick={() => (!busy ? onClose() : undefined)}>
      <div
        className="flex h-full w-full max-w-[760px] flex-col border-l border-stone-200 bg-[#12151a] text-white shadow-[-24px_0_60px_rgba(15,23,42,0.28)] dark:border-white/10"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-white/8 px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-400">Artifact Edit</div>
              <h3 className="mt-2 text-[28px] font-semibold tracking-[-0.05em] text-white">{artifactLabel(artifact)}</h3>
              <p className="mt-2 text-sm leading-6 text-stone-400">{editHint(artifact, taskStatus)}</p>
            </div>
            <button
              className="rounded-full border border-white/10 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
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
            className="h-full min-h-[420px] w-full resize-none rounded-[24px] border border-white/10 bg-[#0b0e12] px-5 py-5 font-mono text-sm leading-7 text-stone-100 outline-none transition focus:border-emerald-300/40"
            onChange={(event) => onChange(event.target.value)}
            spellCheck={false}
            value={value}
          />
        </div>

        <div className="border-t border-white/8 px-6 py-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-rose-300">{error || '保存后会直接覆盖 task 目录中的对应 Markdown 文件。'}</div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-2xl border border-white/10 px-4 py-2.5 text-sm text-stone-300 transition hover:border-white/20 hover:text-white disabled:cursor-not-allowed disabled:opacity-60"
                disabled={busy}
                onClick={onClose}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-2xl bg-emerald-400 px-4 py-2.5 text-sm font-semibold text-stone-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
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
