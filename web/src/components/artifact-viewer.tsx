import { startTransition, useMemo, useState } from 'react'
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
  const lines = content.trim() === '' ? 0 : content.split('\n').length
  const normalized = content || '暂无内容'
  const [copyState, setCopyState] = useState<'idle' | 'done' | 'failed'>('idle')

  return (
    <div className="overflow-hidden rounded-[22px] border border-stone-200 bg-[#0d1014] shadow-[0_20px_60px_rgba(17,24,39,0.12)]">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 px-4 py-3 text-sm text-stone-300">
        <div>
          <div className="font-semibold text-stone-100">{artifactLabel(artifact)}</div>
          <div className="mt-1 font-mono text-xs text-stone-500">{sourcePath || `task/${taskID}/${artifact}`}</div>
        </div>
        <div className="flex items-center gap-2 text-xs text-stone-500">
          {isLive ? (
            <span className="flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 py-1 text-emerald-100">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-300/70" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-300" />
              </span>
              {liveLabel || 'Live'}
            </span>
          ) : null}
          <span className="rounded-full border border-white/10 px-2 py-1">
            {isLog ? 'Log' : isJSON ? 'JSON' : isMarkdown ? 'Markdown' : 'Text'}
          </span>
          <span>{lines} lines</span>
          {canEdit ? (
            <button
              className="rounded-full border border-emerald-300/25 bg-emerald-400/10 px-3 py-1 text-emerald-100 transition hover:border-emerald-200/40 hover:bg-emerald-400/18 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={saving}
              onClick={onEdit}
              type="button"
            >
              {saving ? '保存中...' : '编辑'}
            </button>
          ) : null}
          <button
            className="rounded-full border border-white/10 px-3 py-1 text-stone-300 transition hover:border-white/20 hover:text-white"
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
        <div className="border-b border-emerald-300/12 bg-emerald-400/10 px-4 py-2 text-xs text-emerald-100/90">
          正在后台运行，内容会随轮询自动刷新。最近同步 {lastRefreshedAt || '--:--:--'}。
        </div>
      ) : null}
      <div className="max-h-[520px] overflow-auto px-4 py-4">
        {isLog ? (
          <LogArtifact content={normalized} />
        ) : isJSON ? (
          <JsonArtifact content={normalized} />
        ) : (
          <MarkdownArtifact content={normalized} />
        )}
      </div>
    </div>
  )
}

function MarkdownArtifact({ content }: { content: string }) {
  const lines = content.split('\n')
  const headings = useMemo(() => extractMarkdownHeadings(lines), [lines])

  return (
    <div className="space-y-4">
      {headings.length > 0 ? (
        <div className="rounded-[18px] border border-white/8 bg-white/4 px-3 py-3">
          <div className="mb-2 text-[11px] uppercase tracking-[0.2em] text-stone-500">目录导航</div>
          <div className="flex flex-wrap gap-2">
            {headings.map((heading) => (
              <button
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  heading.level === 1
                    ? 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100'
                    : heading.level === 2
                      ? 'border-sky-300/30 bg-sky-400/10 text-sky-100'
                      : 'border-amber-300/30 bg-amber-400/10 text-amber-100'
                }`}
                key={heading.id}
                onClick={() => {
                  document.getElementById(heading.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }}
                type="button"
              >
                {heading.title}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-2 text-stone-100">
        {lines.map((line, index) => {
          const trimmed = line.trim()
          if (trimmed === '') {
            return <div className="h-2" key={index} />
          }
          if (trimmed.startsWith('### ')) {
            const title = trimmed.slice(4)
            return (
              <h3 className="mt-4 text-lg font-semibold text-amber-100" id={markdownHeadingID(title)} key={index}>
                {title}
              </h3>
            )
          }
          if (trimmed.startsWith('## ')) {
            const title = trimmed.slice(3)
            return (
              <h2 className="mt-5 text-xl font-semibold text-white" id={markdownHeadingID(title)} key={index}>
                {title}
              </h2>
            )
          }
          if (trimmed.startsWith('# ')) {
            const title = trimmed.slice(2)
            return (
              <h1 className="mt-2 text-2xl font-semibold tracking-[-0.03em] text-white" id={markdownHeadingID(title)} key={index}>
                {title}
              </h1>
            )
          }
          if (trimmed.startsWith('- ')) {
            return (
              <div className="flex gap-3 pl-1 text-[13px] leading-7 text-stone-200" key={index}>
                <span className="mt-[10px] h-1.5 w-1.5 rounded-full bg-emerald-300" />
                <span>{trimmed.slice(2)}</span>
              </div>
            )
          }
          if (trimmed.startsWith('|')) {
            return (
              <div className="overflow-x-auto rounded-xl border border-white/8 bg-white/3 px-3 py-2 font-mono text-xs text-stone-300" key={index}>
                {trimmed}
              </div>
            )
          }
          return (
            <p className="text-[13px] leading-7 text-stone-200" key={index}>
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
      <pre className="rounded-[18px] bg-[#0b0e12] text-[12px] leading-6 text-sky-100">
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
      <div className="space-y-1 rounded-[18px] bg-[#0a0d10] text-[12px] leading-6">
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
          ? 'border-stone-200 bg-stone-100 text-stone-950'
          : 'border-white/10 bg-transparent text-stone-400 hover:border-white/20 hover:text-stone-200'
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
    return 'font-mono text-rose-300'
  }
  if (lower.includes('passed') || lower.includes('success') || lower.includes('ok')) {
    return 'font-mono text-emerald-300'
  }
  if (lower.includes('retry') || lower.includes('warning')) {
    return 'font-mono text-amber-300'
  }
  if (line.startsWith('===') || line.startsWith('[tool]')) {
    return 'font-mono text-sky-300'
  }
  return 'font-mono text-stone-200'
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

function extractMarkdownHeadings(lines: string[]) {
  return lines
    .map((line) => line.trim())
    .filter((line) => line.startsWith('#'))
    .map((line) => {
      const level = line.startsWith('### ') ? 3 : line.startsWith('## ') ? 2 : line.startsWith('# ') ? 1 : 0
      const title = level === 3 ? line.slice(4) : level === 2 ? line.slice(3) : level === 1 ? line.slice(2) : line
      return {
        level,
        title,
        id: markdownHeadingID(title),
      }
    })
    .filter((item) => item.level > 0 && item.title)
}

function markdownHeadingID(title: string) {
  return `md-${title
    .toLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')}`
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
    default:
      return name
  }
}
