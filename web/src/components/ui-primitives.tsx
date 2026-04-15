import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import type { RepoResult, TaskStatus } from '../api'

function taskStatusLabel(status: TaskStatus) {
  switch (status) {
    case 'initialized':
      return '需求整理中'
    case 'refined':
      return '待生成方案'
    case 'planning':
      return '方案生成中'
    case 'planned':
      return '待进入实现'
    case 'coding':
      return '实现进行中'
    case 'partially_coded':
      return '部分已完成'
    case 'coded':
      return '已产出结果'
    case 'archived':
      return '已归档'
    case 'failed':
      return '处理中断'
    default:
      return status
  }
}

function repoStatusLabel(status: RepoResult['status']) {
  switch (status) {
    case 'pending':
      return '待推进'
    case 'initialized':
      return '已创建'
    case 'refined':
      return '已整理'
    case 'planned':
      return '待实现'
    case 'coding':
      return '实现中'
    case 'coded':
      return '已完成'
    case 'failed':
      return '失败'
    case 'archived':
      return '已归档'
    default:
      return status
  }
}

export function TopNavItem({
  description,
  isActive,
  title,
  to,
}: {
  title: string
  description: string
  to: '/tasks' | '/workspace'
  isActive: boolean
}) {
  return (
    <Link
      className={`block min-w-[220px] rounded-[18px] border px-4 py-3 transition ${
        isActive
          ? 'border-[#e8e6dc] bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#faf9f5] dark:text-[#141413] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
          : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] shadow-[0_0_0_1px_rgba(240,238,230,0.92)] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#2a2927] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)] dark:hover:text-[#faf9f5]'
      }`}
      to={to}
    >
      <div className="text-[18px] leading-[1.2] font-medium tracking-normal [font-family:Georgia,serif]">{title}</div>
      <div className={`mt-1.5 text-[13px] leading-5 ${isActive ? 'text-[#5e5d59] dark:text-[#5e5d59]' : 'text-[#87867f] dark:text-[#b0aea5]'}`}>{description}</div>
    </Link>
  )
}

export function FilterChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-stone-200 bg-white px-3 py-3 dark:border-white/10 dark:bg-white/6">
      <div className="text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">{label}</div>
      <div className="mt-1 text-lg font-semibold text-stone-950 dark:text-stone-50">{value}</div>
    </div>
  )
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const tone =
    status === 'coded'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : status === 'partially_coded'
        ? 'border-orange-200 bg-orange-50 text-orange-700'
        : status === 'planning'
          ? 'border-sky-200 bg-sky-50 text-sky-700'
        : status === 'planned'
          ? 'border-amber-200 bg-amber-50 text-amber-700'
          : status === 'archived'
            ? 'border-sky-200 bg-sky-50 text-sky-700'
            : status === 'failed'
              ? 'border-rose-200 bg-rose-50 text-rose-700'
              : 'border-stone-200 bg-stone-100 text-stone-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200'

  return <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] ${tone}`}>{taskStatusLabel(status)}</span>
}

export function RepoStatusBadge({ status }: { status: RepoResult['status'] }) {
  const tone =
    status === 'coded'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : status === 'planned'
        ? 'border-amber-200 bg-amber-50 text-amber-700'
        : status === 'failed'
          ? 'border-rose-200 bg-rose-50 text-rose-700'
          : status === 'archived'
            ? 'border-sky-200 bg-sky-50 text-sky-700'
            : 'border-stone-200 bg-stone-100 text-stone-700 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200'

  return <span className={`rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.2em] ${tone}`}>{repoStatusLabel(status)}</span>
}

export function CompactField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">{label}</div>
      <div className="mt-2 text-sm text-[#141413] dark:text-[#faf9f5]">{value}</div>
    </div>
  )
}

export function KeyValue({ label, mono, value }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-[18px] border border-stone-200 bg-stone-50 px-3 py-3 dark:border-white/10 dark:bg-white/6">
      <div className="text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">{label}</div>
      <div className={`mt-2 text-sm text-stone-900 dark:text-stone-100 ${mono ? 'font-mono text-xs' : ''}`}>{value}</div>
    </div>
  )
}

export function PathCard({ label, value }: { label: string; value: string }) {
  return <KeyValue label={label} mono value={value} />
}

export function MiniMeta({ label, value }: { label: string; value: string }) {
  return <KeyValue label={label} mono value={value} />
}

export function PanelMessage({ children }: { children: ReactNode }) {
  return (
    <section className="flex min-h-[720px] items-center justify-center rounded-[24px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] p-8 text-center text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
      {children}
    </section>
  )
}
