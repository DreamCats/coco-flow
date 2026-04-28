import { type ReactNode, useEffect } from 'react'

type ConfirmationTone = 'danger' | 'warning' | 'neutral'

export function ConfirmationModal({
  open,
  eyebrow = 'Confirm Action',
  title,
  description,
  impacts = [],
  impactTitle = '将会发生什么',
  confirmLabel,
  cancelLabel = '取消',
  tone = 'warning',
  busy = false,
  confirmDisabled = false,
  error = '',
  children,
  onConfirm,
  onClose,
}: {
  open: boolean
  eyebrow?: string
  title: string
  description: string
  impacts?: string[]
  impactTitle?: string
  confirmLabel: string
  cancelLabel?: string
  tone?: ConfirmationTone
  busy?: boolean
  confirmDisabled?: boolean
  error?: string
  children?: ReactNode
  onConfirm: () => void
  onClose: () => void
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

  const toneStyles = resolveToneStyles(tone)

  return (
    <div
      className="fixed inset-0 z-50 bg-[rgba(20,20,19,0.24)] backdrop-blur-sm dark:bg-[rgba(20,20,19,0.62)]"
      onClick={() => (!busy ? onClose() : undefined)}
    >
      <div
        className="absolute left-1/2 top-1/2 flex w-[min(640px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[28px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_24px_64px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_24px_64px_rgba(0,0,0,0.38)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">{eyebrow}</div>
              <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{description}</p>
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

        <div className="space-y-4 px-6 py-5">
          {children ? <div>{children}</div> : null}

          {impacts.length > 0 ? (
            <section className={`rounded-[20px] border p-4 ${toneStyles.panel}`}>
              <div className="text-[10px] uppercase tracking-[0.42em] text-[#87867f] dark:text-[#b0aea5]">{impactTitle}</div>
              <div className="mt-3 space-y-2.5">
                {impacts.map((item) => (
                  <div className="flex items-start gap-3 text-sm leading-6 text-[#4d4c48] dark:text-[#f1ede4]" key={item}>
                    <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${toneStyles.dot}`} />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <div className={`rounded-[16px] border px-4 py-3 text-sm ${error ? 'border-[#e1c1bf] bg-[#fbf1f0] text-[#b53333] dark:border-[#7a3b3b] dark:bg-[#362020] dark:text-[#efb3b3]' : 'border-[#e8e6dc] bg-[#f5f4ed] text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]'}`}>
            {error || '确认后会立即执行操作。'}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 border-t border-[#e8e6dc] px-6 py-4 dark:border-[#30302e]">
          <button
            className="rounded-[14px] border border-[#d1cfc5] bg-[#faf9f5] px-5 py-3 text-sm text-[#4d4c48] transition hover:bg-[#efeae0] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]"
            disabled={busy}
            onClick={onClose}
            type="button"
          >
            {cancelLabel}
          </button>
          <button
            className={`rounded-[14px] border px-5 py-3 text-sm text-[#faf9f5] transition disabled:cursor-not-allowed disabled:opacity-60 ${toneStyles.button}`}
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
            type="button"
          >
            {busy ? '处理中...' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function resolveToneStyles(tone: ConfirmationTone) {
  if (tone === 'danger') {
    return {
      panel: 'border-[#e1c1bf] bg-[#fbf1f0] dark:border-[#7a3b3b] dark:bg-[#362020]',
      dot: 'bg-[#b53333]',
      button: 'border-[#b53333] bg-[#b53333] shadow-[0_0_0_1px_rgba(181,51,51,1)] hover:bg-[#c24141]',
    }
  }
  if (tone === 'neutral') {
    return {
      panel: 'border-[#e8e6dc] bg-[#f5f4ed] dark:border-[#30302e] dark:bg-[#232220]',
      dot: 'bg-[#87867f]',
      button: 'border-[#30302e] bg-[#30302e] shadow-[0_0_0_1px_rgba(48,48,46,1)] hover:bg-[#3d3d3a]',
    }
  }
  return {
    panel: 'border-[#ead5c6] bg-[#fff4eb] dark:border-[#7f5848] dark:bg-[#39261f]',
    dot: 'bg-[#c96442]',
    button: 'border-[#c96442] bg-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,1)] hover:bg-[#d97757]',
  }
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 14 14" width="14">
      <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  )
}
