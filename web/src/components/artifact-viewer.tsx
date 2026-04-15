import { startTransition, useEffect, useMemo, useState } from 'react'
import type { TaskArtifactName } from '../api'

export function ArtifactViewer({
  artifact,
  canEdit,
  content,
  isLive,
  lastRefreshedAt,
  liveLabel,
  onEdit,
  saving,
  taskID,
  sourcePath,
}: {
  artifact: TaskArtifactName
  canEdit?: boolean
  content: string
  isLive?: boolean
  lastRefreshedAt?: string
  liveLabel?: string
  onEdit?: () => void
  saving?: boolean
  taskID: string
  sourcePath?: string
}) {
  const isLog = artifact.endsWith('.log')
  const isJSON = artifact.endsWith('.json')
  const isMarkdown = artifact.endsWith('.md')
  const isPatch = artifact.endsWith('.patch')
  const lines = content.trim() === '' ? 0 : content.split('\n').length
  const normalized = content || '暂无内容'
  const [copyState, setCopyState] = useState<'idle' | 'done' | 'failed'>('idle')
  const [focusOpen, setFocusOpen] = useState(false)

  return (
    <div className="overflow-hidden rounded-[22px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98),0_8px_28px_rgba(0,0,0,0.2)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8e6dc] px-4 py-3 text-sm text-[#87867f] dark:border-[#30302e] dark:text-[#b0aea5]">
        <div>
          <div className="font-medium text-[#141413] dark:text-[#faf9f5]">{artifactLabel(artifact)}</div>
          <div className="mt-1 font-mono text-xs text-[#87867f] dark:text-[#b0aea5]">{sourcePath || `task/${taskID}/${artifact}`}</div>
        </div>
        <div className="flex items-center gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
          {isLive ? (
            <span className="flex items-center gap-2 rounded-full border border-[#ccd6c8] bg-[#f3f7f1] px-3 py-1 text-[#4a6b4a] dark:border-[#425142] dark:bg-[#263126] dark:text-[#d8e7d4]">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#7fa27f]/60 dark:bg-[#8bb28b]/60" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-[#5d7f5d] dark:bg-[#9dc39d]" />
              </span>
              {liveLabel || 'Live'}
            </span>
          ) : null}
          <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-2 py-1 text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
            {isLog ? 'Log' : isJSON ? 'JSON' : isPatch ? 'Patch' : isMarkdown ? 'Markdown' : 'Text'}
          </span>
          <span>{lines} lines</span>
          {canEdit ? (
            <button
              className="rounded-full border border-[#c96442] bg-[#fff7f2] px-3 py-1 text-[#c96442] transition hover:bg-[#fbe9df] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0] dark:hover:bg-[#4a2f28]"
              disabled={saving}
              onClick={onEdit}
              type="button"
            >
              {saving ? '保存中...' : '编辑'}
            </button>
          ) : null}
          {isMarkdown ? (
            <button
              className="rounded-full border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-1 text-[#4d4c48] transition hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
              onClick={() => setFocusOpen(true)}
              type="button"
            >
              放大
            </button>
          ) : null}
          <button
            className="rounded-full border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-1 text-[#4d4c48] transition hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
            onClick={() => {
              void navigator.clipboard
                .writeText(normalized)
                .then(() => {
                  startTransition(() => setCopyState('done'))
                  window.setTimeout(() => setCopyState('idle'), 1200)
                })
                .catch(() => {
                  startTransition(() => setCopyState('failed'))
                  window.setTimeout(() => setCopyState('idle'), 1200)
                })
            }}
            type="button"
          >
            {copyState === 'idle' ? '复制' : copyState === 'done' ? '已复制' : '复制失败'}
          </button>
        </div>
      </div>
      {isLive ? (
        <div className="border-b border-[#ccd6c8] bg-[#f3f7f1] px-4 py-2 text-xs text-[#4a6b4a] dark:border-[#425142] dark:bg-[#263126] dark:text-[#d8e7d4]">
          正在后台运行，内容会随轮询自动刷新。最近同步 {lastRefreshedAt || '--:--:--'}。
        </div>
      ) : null}
      <div className="h-[520px] overflow-auto px-4 py-4 lg:h-[640px]">
        {isLog || isPatch ? (
          <LogArtifact content={normalized} />
        ) : isJSON ? (
          <JsonArtifact content={normalized} />
        ) : (
          <MarkdownArtifact content={normalized} variant="panel" />
        )}
      </div>
      {isMarkdown ? (
        <ArtifactFocusDrawer
          artifact={artifact}
          content={normalized}
          open={focusOpen}
          onClose={() => setFocusOpen(false)}
          sourcePath={sourcePath || `task/${taskID}/${artifact}`}
        />
      ) : null}
    </div>
  )
}

function MarkdownArtifact({
  content,
  variant,
}: {
  content: string
  variant: 'drawer' | 'panel'
}) {
  const lines = content.split('\n')

  return (
    <div className={variant === 'drawer' ? 'space-y-3 text-[#141413] dark:text-[#faf9f5]' : 'space-y-2 text-[#141413] dark:text-[#faf9f5]'}>
      <div className={variant === 'drawer' ? 'space-y-3' : 'space-y-2'}>
        {lines.map((line, index) => {
          const trimmed = line.trim()
          if (trimmed === '') {
            return <div className={variant === 'drawer' ? 'h-3' : 'h-2'} key={index} />
          }
          if (trimmed.startsWith('### ')) {
            const title = trimmed.slice(4)
            return (
              <h3
                className={
                  variant === 'drawer'
                    ? 'mt-6 text-[24px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'
                    : 'mt-4 text-[20px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'
                }
                id={markdownHeadingID(title)}
                key={index}
              >
                {title}
              </h3>
            )
          }
          if (trimmed.startsWith('## ')) {
            const title = trimmed.slice(3)
            return (
              <h2
                className={
                  variant === 'drawer'
                    ? 'mt-8 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'
                    : 'mt-5 text-[24px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'
                }
                id={markdownHeadingID(title)}
                key={index}
              >
                {title}
              </h2>
            )
          }
          if (trimmed.startsWith('# ')) {
            const title = trimmed.slice(2)
            return (
              <h1
                className={
                  variant === 'drawer'
                    ? 'mt-2 text-[42px] leading-[1.1] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'
                    : 'mt-2 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'
                }
                id={markdownHeadingID(title)}
                key={index}
              >
                {title}
              </h1>
            )
          }
          if (trimmed.startsWith('- ')) {
            return (
              <div
                className={
                  variant === 'drawer'
                    ? 'flex gap-3 pl-1 text-[16px] leading-8 text-[#4d4c48] dark:text-[#b0aea5]'
                    : 'flex gap-3 pl-1 text-[15px] leading-8 text-[#4d4c48] dark:text-[#b0aea5]'
                }
                key={index}
              >
                <span
                  className={
                    variant === 'drawer'
                      ? 'mt-[13px] h-1.5 w-1.5 rounded-full bg-[#c96442] dark:bg-[#d97757]'
                      : 'mt-[12px] h-1.5 w-1.5 rounded-full bg-[#c96442] dark:bg-[#d97757]'
                  }
                />
                <span>{trimmed.slice(2)}</span>
              </div>
            )
          }
          if (trimmed.startsWith('|')) {
            return (
              <div
                className={
                  variant === 'drawer'
                    ? 'overflow-x-auto rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-3 font-mono text-xs text-[#5e5d59] shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]'
                    : 'overflow-x-auto rounded-[14px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-2 font-mono text-xs text-[#5e5d59] shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]'
                }
                key={index}
              >
                {trimmed}
              </div>
            )
          }
          return (
            <p
              className={variant === 'drawer' ? 'text-[17px] leading-[1.8] text-[#4d4c48] dark:text-[#b0aea5]' : 'text-[15px] leading-[1.8] text-[#4d4c48] dark:text-[#b0aea5]'}
              key={index}
            >
              {trimmed}
            </p>
          )
        })}
      </div>
    </div>
  )
}

function JsonArtifact({ content }: { content: string }) {
  const [mode, setMode] = useState<'summary' | 'full'>('summary')
  const pretty = useMemo(() => {
    try {
      return JSON.stringify(JSON.parse(content), null, 2)
    } catch {
      return content
    }
  }, [content])
  const summary = useMemo(() => summarizeJSON(content), [content])

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <ModeButton active={mode === 'summary'} label="关键信息" onClick={() => setMode('summary')} />
        <ModeButton active={mode === 'full'} label="完整 JSON" onClick={() => setMode('full')} />
      </div>
      <pre className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] text-[12px] leading-6 text-[#5e5d59] shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#141413] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
        <code>{mode === 'summary' ? summary : pretty}</code>
      </pre>
    </div>
  )
}

function LogArtifact({ content }: { content: string }) {
  const [mode, setMode] = useState<'highlights' | 'full'>('highlights')
  const allLines = content.split('\n')
  const highlightLines = allLines.filter((line) => isImportantLogLine(line))
  const lines = mode === 'highlights' && highlightLines.length > 0 ? highlightLines : allLines

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <ModeButton active={mode === 'highlights'} label="关键信息" onClick={() => setMode('highlights')} />
        <ModeButton active={mode === 'full'} label="完整日志" onClick={() => setMode('full')} />
      </div>
      <div className="space-y-1 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 text-[12px] leading-6 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#141413] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
        {lines.map((line, index) => (
        <div className={logLineTone(line)} key={`${index}-${line}`}>
          <code>{line || ' '}</code>
        </div>
        ))}
      </div>
    </div>
  )
}

function ModeButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      className={`rounded-full border px-3 py-1 text-xs transition ${
        active
          ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
          : 'border-[#d1cfc5] bg-[#e8e6dc] text-[#4d4c48] hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function logLineTone(line: string) {
  const lower = line.toLowerCase()
  if (lower.includes('error') || lower.includes('failed')) {
    return 'font-mono text-[#b53333] dark:text-[#efb3b3]'
  }
  if (lower.includes('passed') || lower.includes('success') || lower.includes('ok')) {
    return 'font-mono text-[#4a6b4a] dark:text-[#b7d1b7]'
  }
  if (lower.includes('retry') || lower.includes('warning')) {
    return 'font-mono text-[#9a6a18] dark:text-[#e4c07c]'
  }
  if (line.startsWith('===') || line.startsWith('[tool]')) {
    return 'font-mono text-[#6b7280] dark:text-[#c5c9d1]'
  }
  return 'font-mono text-[#4d4c48] dark:text-[#b0aea5]'
}

function isImportantLogLine(line: string) {
  const lower = line.toLowerCase()
  return (
    line.startsWith('===') ||
    line.startsWith('[tool]') ||
    lower.includes('error') ||
    lower.includes('failed') ||
    lower.includes('passed') ||
    lower.includes('success') ||
    lower.includes('retry') ||
    lower.includes('warning') ||
    lower.includes('auto_commit') ||
    lower.includes('result:')
  )
}

function summarizeJSON(content: string) {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    if (!parsed || Array.isArray(parsed)) {
      return JSON.stringify(parsed, null, 2)
    }

    const keys = [
      'status',
      'task_id',
      'repo_id',
      'branch',
      'commit',
      'build_ok',
      'files_written',
      'error',
      'started_at',
      'finished_at',
    ]

    const summary: Record<string, unknown> = {}
    for (const key of keys) {
      if (key in parsed) {
        summary[key] = parsed[key]
      }
    }
    if (Object.keys(summary).length === 0) {
      return JSON.stringify(parsed, null, 2)
    }
    return JSON.stringify(summary, null, 2)
  } catch {
    return content
  }
}

function markdownHeadingID(title: string) {
  return `md-${title
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')}`
}

function ArtifactFocusDrawer({
  artifact,
  content,
  open,
  onClose,
  sourcePath,
}: {
  artifact: TaskArtifactName
  content: string
  open: boolean
  onClose: () => void
  sourcePath: string
}) {
  useEffect(() => {
    if (!open) {
      return
    }

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose, open])

  if (!open) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto bg-[rgba(20,20,19,0.22)] p-4 backdrop-blur-sm dark:bg-[rgba(20,20,19,0.58)] sm:p-6 lg:p-8"
      onClick={onClose}
    >
      <div
        className="mx-auto flex h-[calc(100dvh-32px)] w-full max-w-[1180px] flex-col overflow-hidden rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_0_0_1px_rgba(240,238,230,0.94),0_12px_40px_rgba(20,20,19,0.12)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98),0_12px_40px_rgba(0,0,0,0.28)] sm:h-[calc(100dvh-48px)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">全景阅读</div>
            <h3 className="mt-2 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
              {artifactLabel(artifact)}
            </h3>
            <p className="mt-2 font-mono text-xs text-[#87867f] dark:text-[#b0aea5]">{sourcePath}</p>
          </div>
          <button
            className="rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-2 text-xs text-[#4d4c48] transition hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
            onClick={onClose}
            type="button"
          >
            关闭
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-[860px]">
            <MarkdownArtifact content={content} variant="drawer" />
          </div>
        </div>
      </div>
    </div>
  )
}

export function artifactLabel(name: TaskArtifactName) {
  switch (name) {
    case 'prd.source.md':
      return 'Source'
    case 'prd-refined.md':
      return 'Refined PRD'
    case 'refine.log':
      return 'Refine Log'
    case 'design.md':
      return 'Design'
    case 'plan.md':
      return 'Plan'
    case 'plan.log':
      return 'Plan Log'
    case 'code-result.json':
      return 'Code Result'
    case 'code.log':
      return 'Code Log'
    case 'diff.json':
      return 'Diff Summary'
    case 'diff.patch':
      return 'Diff Patch'
    default:
      return name
  }
}
