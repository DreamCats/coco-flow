import { useEffect } from 'react'

export function TaskStageEditorModal({
  open,
  title,
  description,
  hint,
  value,
  onChange,
  onClose,
  onSave,
  busy,
  canSave,
  error,
  placeholder,
  monospace = false,
}: {
  open: boolean
  title: string
  description: string
  hint: string
  value: string
  onChange: (value: string) => void
  onClose: () => void
  onSave: () => void
  busy: boolean
  canSave: boolean
  error: string
  placeholder?: string
  monospace?: boolean
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
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && canSave && !busy) {
        onSave()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [busy, canSave, onClose, onSave, open])

  if (!open) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-[rgba(20,20,19,0.2)] backdrop-blur-sm dark:bg-[rgba(20,20,19,0.58)]"
      onClick={() => (!busy ? onClose() : undefined)}
    >
      <div
        className="absolute left-1/2 top-1/2 flex max-h-[calc(100vh-48px)] w-[min(840px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[28px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_24px_64px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_24px_64px_rgba(0,0,0,0.38)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Stage Edit</div>
              <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{description}</p>
              <p className="mt-2 text-xs leading-5 text-[#87867f] dark:text-[#8f8a82]">{hint}</p>
            </div>
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-full text-[#87867f] transition hover:bg-[#f1ece4] hover:text-[#4d4c48] disabled:cursor-not-allowed disabled:opacity-60 dark:text-[#8f8a82] dark:hover:bg-[#24221f] dark:hover:text-[#f1ede4]"
              disabled={busy}
              onClick={onClose}
              title="关闭"
              type="button"
            >
              <CloseIcon />
            </button>
          </div>
        </div>

        <div className="flex-1 px-6 py-5">
          <textarea
            className={`min-h-[420px] w-full resize-none rounded-[18px] border border-[#e8e6dc] bg-[#fffdf9] px-5 py-5 text-sm leading-7 text-[#141413] outline-none shadow-[0_0_0_1px_rgba(240,238,230,0.88)] transition focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#151412] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:focus:border-[#3898ec] ${monospace ? 'font-mono' : ''}`}
            onChange={(event) => onChange(event.target.value)}
            placeholder={placeholder}
            spellCheck={false}
            value={value}
          />
        </div>

        <div className="border-t border-[#e8e6dc] px-6 py-4 dark:border-[#30302e]">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className={`text-sm ${error ? 'text-[#b53333]' : 'text-[#87867f] dark:text-[#b0aea5]'}`}>
              {error || '支持快捷键 Cmd/Ctrl + Enter 保存。'}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-[14px] border border-[#d1cfc5] bg-[#faf9f5] px-4 py-2.5 text-sm text-[#4d4c48] transition hover:bg-[#efeae0] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]"
                disabled={busy}
                onClick={onClose}
                type="button"
              >
                取消
              </button>
              <button
                className="rounded-[14px] border border-[#c96442] bg-[#c96442] px-4 py-2.5 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-60"
                disabled={!canSave || busy}
                onClick={onSave}
                type="button"
              >
                {busy ? '保存中...' : '保存'}
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
