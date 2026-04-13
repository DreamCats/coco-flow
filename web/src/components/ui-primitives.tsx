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

export function MetricCard({
  label,
  tone,
  value,
}: {
  label: string
  value: string
  tone: 'emerald' | 'amber' | 'sky'
}) {
  const toneClass =
    tone === 'emerald'
      ? 'border-emerald-200 bg-[linear-gradient(180deg,_rgba(16,185,129,0.12),_rgba(236,253,245,0.9))] text-emerald-800 dark:border-emerald-300/20 dark:bg-[linear-gradient(180deg,_rgba(16,185,129,0.18),_rgba(16,24,20,0.92))] dark:text-emerald-100'
      : tone === 'amber'
        ? 'border-amber-200 bg-[linear-gradient(180deg,_rgba(245,158,11,0.12),_rgba(255,251,235,0.92))] text-amber-800 dark:border-amber-300/20 dark:bg-[linear-gradient(180deg,_rgba(245,158,11,0.18),_rgba(24,19,12,0.92))] dark:text-amber-100'
        : 'border-sky-200 bg-[linear-gradient(180deg,_rgba(14,165,233,0.12),_rgba(240,249,255,0.92))] text-sky-800 dark:border-sky-300/20 dark:bg-[linear-gradient(180deg,_rgba(14,165,233,0.18),_rgba(11,18,24,0.92))] dark:text-sky-100'

  return (
    <div className={`rounded-[22px] border px-4 py-3 shadow-[0_10px_25px_rgba(15,23,42,0.04)] ${toneClass}`}>
      <div className="text-[11px] uppercase tracking-[0.2em] opacity-70">{label}</div>
      <div className="mt-2 text-[28px] font-semibold tracking-[-0.04em]">{value}</div>
    </div>
  )
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
      className={`block min-w-[260px] rounded-[22px] border px-4 py-4 transition ${
        isActive
          ? 'border-stone-900 bg-stone-900 text-white shadow-[0_16px_30px_rgba(15,23,42,0.14)] dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
          : 'border-stone-200 bg-white text-stone-700 hover:border-stone-300 hover:bg-stone-50 dark:border-white/10 dark:bg-white/6 dark:text-stone-300 dark:hover:border-white/20 dark:hover:bg-white/10'
      }`}
      to={to}
    >
      <div className={`text-[11px] font-semibold uppercase tracking-[0.22em] ${isActive ? 'text-stone-400 dark:text-stone-500' : 'text-stone-500 dark:text-stone-400'}`}>
        导航
      </div>
      <div className="mt-2 text-lg font-semibold tracking-[-0.03em]">{title}</div>
      <div className={`mt-2 text-xs leading-5 ${isActive ? 'text-stone-300 dark:text-stone-600' : 'text-stone-500 dark:text-stone-400'}`}>{description}</div>
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

export function TimelineCard({
  detail,
  label,
  state,
}: {
  label: string
  detail: string
  state: 'done' | 'current' | 'pending'
}) {
  const tone =
    state === 'done'
      ? 'border-emerald-300/20 bg-emerald-400/10'
      : state === 'current'
        ? 'border-amber-300/20 bg-amber-400/10'
        : 'border-white/8 bg-white/4'

  return (
    <div className={`rounded-[18px] border p-4 ${tone}`}>
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-white">{label}</div>
        <div className="text-[11px] uppercase tracking-[0.2em] text-stone-400">{state === 'done' ? '已完成' : state === 'current' ? '进行中' : '待开始'}</div>
      </div>
      <div className="mt-3 text-sm leading-6 text-stone-300">{detail}</div>
    </div>
  )
}

export function CompactField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[18px] border border-white/8 bg-white/4 px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.2em] text-stone-400">{label}</div>
      <div className="mt-2 text-sm text-white">{value}</div>
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
    <section className="flex min-h-[720px] items-center justify-center rounded-[24px] border border-dashed border-stone-300 bg-stone-50 p-8 text-center text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
      {children}
    </section>
  )
}
