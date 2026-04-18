import type { ReactNode } from 'react'
import { stageStatusLabel, stageTone, taskStatusLabel } from './model'
import type { TaskStageStatus } from './model'
import type { TaskStatus } from '../../api'

export function TaskStatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span className="rounded-full border border-[#d9cec0] bg-[#fffaf2] px-3 py-1 text-xs text-[#8d7766] dark:border-[#46423e] dark:bg-[#191816] dark:text-[#bcae9f]">
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

export function ArtifactPanel({ title, content }: { title: string; content: string }) {
  return (
    <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
      <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{title}</div>
      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
        {content || '当前还没有产物。'}
      </pre>
    </div>
  )
}

export function NotePanel({ content }: { content: string }) {
  return (
    <div className="min-h-[220px] rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-7 text-[#8a7a67] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#8f8a82]">
      {content || '当前没有补充说明。'}
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

export function EmptyPanel({ children }: { children: ReactNode }) {
  return (
    <section className="flex min-h-[520px] items-center justify-center rounded-[24px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] p-8 text-center text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
      {children}
    </section>
  )
}
