import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { stageStatusLabel, stageTone, taskStatusLabel } from './model'
import type { TaskStageStatus } from './model'
import type { TaskStatus } from '../../api'

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span className="whitespace-nowrap rounded-full border border-[#d9cec0] bg-[#fffaf2] px-3 py-1 text-xs text-[#8d7766] dark:border-[#46423e] dark:bg-[#191816] dark:text-[#bcae9f]">
      {taskStatusLabel(status)}
    </span>
  )
}

export function StageStatusBadge({ status }: { status: TaskStageStatus }) {
  return <span className={`rounded-full border px-3 py-1 text-xs ${stageTone(status)}`}>{stageStatusLabel(status)}</span>
}

export function SectionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
      <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">{title}</div>
      <div className="mt-4">{children}</div>
    </section>
  )
}

export function ArtifactPanel({ title, content, renderAs = 'markdown' }: { title: string; content: string; renderAs?: 'markdown' | 'plain' }) {
  return (
    <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{title}</div>
      {renderAs === 'plain' ? (
        <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
          {content || '当前还没有产物。'}
        </pre>
      ) : (
        <MarkdownBody content={content || '当前还没有产物。'} />
      )}
    </div>
  )
}

export function NotePanel({ content, renderAs = 'markdown' }: { content: string; renderAs?: 'markdown' | 'plain' }) {
  return (
    <div className="min-h-[220px] rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-7 text-[#8a7a67] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#8f8a82]">
      {renderAs === 'plain' ? <div>{content || '当前没有补充说明。'}</div> : <MarkdownBody content={content || '当前没有补充说明。'} compact />}
    </div>
  )
}

function MarkdownBody({ content, compact = false }: { content: string; compact?: boolean }) {
  return (
    <div className={`mt-3 text-[#141413] dark:text-[#faf9f5]`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className={compact ? 'mt-2 mb-3 text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]' : 'mt-2 mb-3 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'}>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className={compact ? 'mt-5 mb-3 text-[22px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]' : 'mt-6 mb-3 text-[24px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'}>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className={compact ? 'mt-4 mb-2 text-[18px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]' : 'mt-5 mb-2 text-[20px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]'}>
              {children}
            </h3>
          ),
          p: ({ children }) => <p className={compact ? 'my-2 text-[14px] leading-[1.8] text-[#4d4c48] dark:text-[#b0aea5]' : 'my-2 text-[15px] leading-[1.8] text-[#4d4c48] dark:text-[#b0aea5]'}>{children}</p>,
          ul: ({ children }) => <ul className={compact ? 'my-3 list-disc space-y-1.5 pl-5 text-[14px] leading-7 text-[#4d4c48] dark:text-[#b0aea5]' : 'my-3 list-disc space-y-1.5 pl-5 text-[15px] leading-7 text-[#4d4c48] dark:text-[#b0aea5]'}>{children}</ul>,
          ol: ({ children }) => <ol className={compact ? 'my-3 list-decimal space-y-1.5 pl-5 text-[14px] leading-7 text-[#4d4c48] dark:text-[#b0aea5]' : 'my-3 list-decimal space-y-1.5 pl-5 text-[15px] leading-7 text-[#4d4c48] dark:text-[#b0aea5]'}>{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          blockquote: ({ children }) => (
            <blockquote className="my-4 rounded-r-[16px] border-l-4 border-[#d1cfc5] bg-[#f5f4ed] px-4 py-3 text-[#5e5d59] dark:border-[#4b4a46] dark:bg-[#232220] dark:text-[#b0aea5]">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] dark:border-[#30302e] dark:bg-[#232220]">
              <table className="min-w-full border-collapse text-left text-sm">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-[#eeece2] dark:bg-[#2a2927]">{children}</thead>,
          th: ({ children }) => <th className="border-b border-[#ddd9cc] px-3 py-2 font-semibold text-[#141413] dark:border-[#3a3937] dark:text-[#faf9f5]">{children}</th>,
          td: ({ children }) => <td className="border-t border-[#e8e6dc] px-3 py-2 text-[#4d4c48] dark:border-[#30302e] dark:text-[#b0aea5]">{children}</td>,
          hr: () => <hr className="my-6 border-0 border-t border-[#e8e6dc] dark:border-[#30302e]" />,
          a: ({ href, children }) => (
            <a className="text-[#c96442] underline underline-offset-2 dark:text-[#f0c0b0]" href={href} rel="noreferrer" target="_blank">
              {children}
            </a>
          ),
          strong: ({ children }) => <strong className="font-semibold text-[#141413] dark:text-[#faf9f5]">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ className, children }) =>
            className ? (
              <code className="font-mono text-xs leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{children}</code>
            ) : (
              <code className="rounded bg-[#f1ede3] px-1.5 py-0.5 font-mono text-[0.9em] text-[#6b2e1f] dark:bg-[#2f2623] dark:text-[#f0c0b0]">{children}</code>
            ),
          pre: ({ children }) => (
            <pre className="my-4 overflow-x-auto rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-3 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#141413] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
              {children}
            </pre>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

export function TabButton({
  active,
  children,
  onClick,
}: {
  active: boolean
  children: ReactNode
  onClick: () => void
}) {
  return (
    <button
      className={`rounded-[12px] px-4 py-2 text-sm transition ${
        active
          ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
          : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

export function ActionButton({
  children,
  onClick,
  tone = 'primary',
  disabled = false,
}: {
  children: ReactNode
  onClick?: () => void
  tone?: 'primary' | 'secondary'
  disabled?: boolean
}) {
  return (
    <button
      className={
        tone === 'primary'
          ? 'rounded-[12px] border border-[#c96442] bg-[#c96442] px-3 py-1.5 text-xs text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-55'
          : 'rounded-[12px] border border-[#d1cfc5] bg-[#faf9f5] px-3 py-1.5 text-xs text-[#4d4c48] transition hover:bg-[#efeae0] disabled:cursor-not-allowed disabled:opacity-55 dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]'
      }
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  )
}

export function TipIcon({ children, label = '查看示例' }: { children: ReactNode; label?: string }) {
  return (
    <span className="group relative inline-flex">
      <button
        aria-label={label}
        className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-[#d65c45] bg-[#fff1ed] text-xs font-semibold text-[#b93624] shadow-[0_0_0_1px_rgba(214,92,69,0.16)] transition hover:bg-[#ffe4dc] focus:outline-none focus:ring-2 focus:ring-[#d65c45]/35 dark:border-[#8f3c2e] dark:bg-[#351b17] dark:text-[#ffb4a6] dark:hover:bg-[#452019]"
        type="button"
      >
        ?
      </button>
      <span className="absolute right-0 top-full z-30 hidden w-[320px] max-w-[calc(100vw-3rem)] pt-2 group-focus-within:block group-hover:block">
        <span className="block rounded-[12px] border border-[#d1cfc5] bg-[#fffdf9] px-3 py-3 text-left text-xs leading-5 text-[#4d4c48] shadow-[0_12px_34px_rgba(34,31,26,0.18)] dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#d8d3c8]">
          {children}
        </span>
      </span>
    </span>
  )
}

export function EmptyPanel({ children }: { children: ReactNode }) {
  return (
    <section className="flex min-h-[520px] items-center justify-center rounded-[24px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] p-8 text-center text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
      {children}
    </section>
  )
}
