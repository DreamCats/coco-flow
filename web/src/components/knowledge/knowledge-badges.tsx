import type { KnowledgeConfidence, KnowledgeKind, KnowledgeStatus } from '../../knowledge/types'

export function KnowledgeKindBadge({ kind }: { kind: KnowledgeKind }) {
  const tones: Record<KnowledgeKind, string> = {
    domain: 'border-[#cbb691] bg-[#f5ecdc] text-[#765d2a]',
    flow: 'border-[#b8d6f3] bg-[#eef7ff] text-[#2a5f8f]',
    rule: 'border-[#d8c0ec] bg-[#f7efff] text-[#6a3f8a]',
    anchor: 'border-[#b7ddcd] bg-[#edf9f1] text-[#23644d]',
  }

  return <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${tones[kind]}`}>{kind}</span>
}

export function KnowledgeStatusBadge({ status }: { status: KnowledgeStatus }) {
  const tones: Record<KnowledgeStatus, string> = {
    draft: 'border-[#e8caa2] bg-[#fff4e7] text-[#9c5d18]',
    approved: 'border-[#b7ddcd] bg-[#edf9f1] text-[#23644d]',
    archived: 'border-[#d1d1cc] bg-[#f1f1ed] text-[#66645d]',
  }

  return <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${tones[status]}`}>{status}</span>
}

export function KnowledgeConfidenceBadge({ confidence }: { confidence: KnowledgeConfidence }) {
  const tones: Record<KnowledgeConfidence, string> = {
    low: 'border-[#f0c1c1] bg-[#fff1f1] text-[#a53e3e]',
    medium: 'border-[#e8caa2] bg-[#fff4e7] text-[#9c5d18]',
    high: 'border-[#b7ddcd] bg-[#edf9f1] text-[#23644d]',
  }

  return (
    <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${tones[confidence]}`}>
      {confidence}
    </span>
  )
}
