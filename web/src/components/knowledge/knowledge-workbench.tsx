import { useState, type ReactNode } from 'react'
import type { KnowledgeConfidence, KnowledgeDocument, KnowledgeEngine, KnowledgeStatus } from '../../knowledge/types'
import { KnowledgeConfidenceBadge, KnowledgeKindBadge, KnowledgeStatusBadge } from './knowledge-badges'

type KnowledgeWorkbenchProps = {
  document: KnowledgeDocument | null
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void
}

type WorkbenchTab = 'summary' | 'body' | 'evidence' | 'publish'

export function KnowledgeWorkbench({ document, onUpdateDocument }: KnowledgeWorkbenchProps) {
  const [tab, setTab] = useState<WorkbenchTab>('evidence')

  if (!document) {
    return (
      <section className="flex min-h-[760px] items-center justify-center rounded-[24px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] p-8 text-center text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
        先从左侧选择一份知识文件，或新建一个知识草稿。
      </section>
    )
  }

  return (
    <section className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Knowledge Workbench</div>
          <h3 className="mt-2 text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
            {document.domainName} · {document.title}
          </h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <KnowledgeKindBadge kind={document.kind} />
            <KnowledgeStatusBadge status={document.status} />
            <KnowledgeConfidenceBadge confidence={document.confidence} />
          </div>
        </div>
        <div className="text-sm text-[#87867f] dark:text-[#b0aea5]">先看证据，再决定是否修改和发布。</div>
      </div>

      <div className="mb-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-2 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
        <div className="flex flex-wrap gap-2">
          <TabButton active={tab === 'summary'} label="摘要" onClick={() => setTab('summary')} />
          <TabButton active={tab === 'body'} label="正文" onClick={() => setTab('body')} />
          <TabButton active={tab === 'evidence'} label="证据" onClick={() => setTab('evidence')} />
          <TabButton active={tab === 'publish'} label="发布" onClick={() => setTab('publish')} />
        </div>
      </div>

      {tab === 'summary' ? <SummaryTab document={document} onUpdateDocument={onUpdateDocument} /> : null}
      {tab === 'body' ? <BodyTab document={document} onUpdateDocument={onUpdateDocument} /> : null}
      {tab === 'evidence' ? <EvidenceTab document={document} /> : null}
      {tab === 'publish' ? <PublishTab document={document} onUpdateDocument={onUpdateDocument} /> : null}
    </section>
  )
}

function SummaryTab({
  document,
  onUpdateDocument,
}: {
  document: KnowledgeDocument
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="space-y-4">
        <Field label="title">
          <input
            className={fieldClassName}
            onChange={(event) => onUpdateDocument(document.id, { title: event.target.value })}
            type="text"
            value={document.title}
          />
        </Field>
        <Field label="desc">
          <textarea
            className={`${fieldClassName} min-h-[120px] resize-y`}
            onChange={(event) => onUpdateDocument(document.id, { desc: event.target.value })}
            value={document.desc}
          />
        </Field>
        <Field label="repos">
          <input
            className={fieldClassName}
            onChange={(event) => onUpdateDocument(document.id, { repos: parseCommaList(event.target.value) })}
            type="text"
            value={document.repos.join(', ')}
          />
        </Field>
        <Field label="paths">
          <textarea
            className={`${fieldClassName} min-h-[120px] resize-y`}
            onChange={(event) => onUpdateDocument(document.id, { paths: parseLineList(event.target.value) })}
            value={document.paths.join('\n')}
          />
        </Field>
      </section>

      <section className="space-y-4">
        <Field label="keywords">
          <textarea
            className={`${fieldClassName} min-h-[120px] resize-y`}
            onChange={(event) => onUpdateDocument(document.id, { keywords: parseCommaList(event.target.value) })}
            value={document.keywords.join(', ')}
          />
        </Field>
        <Field label="engines">
          <div className="flex flex-wrap gap-2">
            <EngineToggle
              active={document.engines.includes('refine')}
              label="refine"
              onClick={() => toggleEngine(document, 'refine', onUpdateDocument)}
            />
            <EngineToggle
              active={document.engines.includes('plan')}
              label="plan"
              onClick={() => toggleEngine(document, 'plan', onUpdateDocument)}
            />
          </div>
        </Field>
        <MetaCard label="domain" value={document.domainName} />
        <MetaCard label="id" value={document.id} mono />
        <MetaCard label="updated_at" value={document.updatedAt} />
        <MetaCard label="owner" value={document.owner} />
      </section>
    </div>
  )
}

function BodyTab({
  document,
  onUpdateDocument,
}: {
  document: KnowledgeDocument
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
        <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Markdown Body</div>
        <textarea
          className={`${fieldClassName} min-h-[520px] resize-y font-mono text-xs leading-6`}
          onChange={(event) => onUpdateDocument(document.id, { body: event.target.value })}
          value={document.body}
        />
      </section>
      <section className="space-y-4">
        <MetaCard label="编辑提示" value="第一版先直接编辑 Markdown；后续再拆成结构化 section editor。" />
        <MetaCard label="推荐顺序" value="先看证据，再改正文；正文里不确定的地方继续保留 Open Questions。" />
      </section>
    </div>
  )
}

function EvidenceTab({ document }: { document: KnowledgeDocument }) {
  const { evidence } = document
  return (
    <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="space-y-4">
        <EvidenceCard title="输入与命中">
          <EvidenceLine label="输入描述" value={evidence.inputDescription} />
          <EvidenceList label="命中 repo" items={evidence.repoMatches} />
          <EvidenceList label="命中关键词" items={evidence.keywordMatches} />
          <EvidenceList label="命中路径" items={evidence.pathMatches} />
        </EvidenceCard>
        <EvidenceCard title="代码证据">
          <EvidenceList label="候选文件" items={evidence.candidateFiles} mono />
          <EvidenceList label=".livecoding/context 命中" items={evidence.contextHits} />
        </EvidenceCard>
      </section>
      <section className="space-y-4">
        <EvidenceCard title="系统解释">
          <EvidenceList label="检索说明" items={evidence.retrievalNotes} />
        </EvidenceCard>
        <EvidenceCard title="待确认问题">
          <EvidenceList label="Open Questions" items={evidence.openQuestions} />
        </EvidenceCard>
      </section>
    </div>
  )
}

function PublishTab({
  document,
  onUpdateDocument,
}: {
  document: KnowledgeDocument
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void
}) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="space-y-4">
        <Field label="状态">
          <div className="flex flex-wrap gap-2">
            <StatusToggle active={document.status === 'draft'} label="draft" onClick={() => updateStatus(document.id, 'draft', onUpdateDocument)} />
            <StatusToggle active={document.status === 'approved'} label="approved" onClick={() => updateStatus(document.id, 'approved', onUpdateDocument)} />
            <StatusToggle active={document.status === 'archived'} label="archived" onClick={() => updateStatus(document.id, 'archived', onUpdateDocument)} />
          </div>
        </Field>
        <Field label="置信度">
          <div className="flex flex-wrap gap-2">
            <ConfidenceToggle active={document.confidence === 'low'} label="low" onClick={() => updateConfidence(document.id, 'low', onUpdateDocument)} />
            <ConfidenceToggle active={document.confidence === 'medium'} label="medium" onClick={() => updateConfidence(document.id, 'medium', onUpdateDocument)} />
            <ConfidenceToggle active={document.confidence === 'high'} label="high" onClick={() => updateConfidence(document.id, 'high', onUpdateDocument)} />
          </div>
        </Field>
        <Field label="引擎可见性">
          <div className="flex flex-wrap gap-2">
            <EngineToggle
              active={document.engines.includes('refine')}
              label="refine"
              onClick={() => toggleEngine(document, 'refine', onUpdateDocument)}
            />
            <EngineToggle
              active={document.engines.includes('plan')}
              label="plan"
              onClick={() => toggleEngine(document, 'plan', onUpdateDocument)}
            />
          </div>
        </Field>
      </section>

      <section className="space-y-4">
        <MetaCard label="发布规则" value="draft 不进入主链路；approved 默认参与 refine / plan；archived 只保留历史记录。" />
        <MetaCard label="当前建议" value={document.status === 'draft' ? '先补证据和 Open Questions，再发布。' : document.status === 'approved' ? '已可作为默认知识输入参与引擎。' : '已归档，仅保留历史参考。'} />
      </section>
    </div>
  )
}

function TabButton({
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
      className={`rounded-full border px-3 py-2 text-sm transition ${
        active
          ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
          : 'border-transparent bg-[#faf9f5] text-[#5e5d59] hover:border-[#e8e6dc] hover:text-[#141413] dark:bg-transparent dark:text-[#b0aea5] dark:hover:border-[#30302e] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">{label}</div>
      {children}
    </div>
  )
}

function MetaCard({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">{label}</div>
      <div className={`mt-2 text-sm text-[#141413] dark:text-[#faf9f5] ${mono ? 'font-mono text-xs' : ''}`}>{value}</div>
    </div>
  )
}

function EvidenceCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">{title}</div>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function EvidenceLine({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">{label}</div>
      <div className="mt-1 text-sm text-[#141413] dark:text-[#faf9f5]">{value}</div>
    </div>
  )
}

function EvidenceList({ label, items, mono = false }: { label: string; items: string[]; mono?: boolean }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">{label}</div>
      <div className="mt-2 space-y-2">
        {items.length === 0 ? <div className="text-sm text-stone-500 dark:text-stone-400">-</div> : null}
        {items.map((item) => (
          <div
            className={`rounded-[14px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#faf9f5] ${mono ? 'font-mono text-xs' : ''}`}
            key={`${label}-${item}`}
          >
            {item}
          </div>
        ))}
      </div>
    </div>
  )
}

function StatusToggle({ active, label, onClick }: { active: boolean; label: KnowledgeStatus; onClick: () => void }) {
  return (
    <button className={toggleClassName(active)} onClick={onClick} type="button">
      {label}
    </button>
  )
}

function ConfidenceToggle({ active, label, onClick }: { active: boolean; label: KnowledgeConfidence; onClick: () => void }) {
  return (
    <button className={toggleClassName(active)} onClick={onClick} type="button">
      {label}
    </button>
  )
}

function EngineToggle({ active, label, onClick }: { active: boolean; label: KnowledgeEngine; onClick: () => void }) {
  return (
    <button className={toggleClassName(active)} onClick={onClick} type="button">
      {label}
    </button>
  )
}

function toggleEngine(
  document: KnowledgeDocument,
  engine: KnowledgeEngine,
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void,
) {
  const engines = document.engines.includes(engine)
    ? document.engines.filter((item) => item !== engine)
    : [...document.engines, engine]
  onUpdateDocument(document.id, { engines: engines.length > 0 ? engines : [engine] })
}

function updateStatus(
  id: string,
  status: KnowledgeStatus,
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void,
) {
  onUpdateDocument(id, { status })
}

function updateConfidence(
  id: string,
  confidence: KnowledgeConfidence,
  onUpdateDocument: (id: string, patch: Partial<KnowledgeDocument>) => void,
) {
  onUpdateDocument(id, { confidence })
}

function parseCommaList(value: string): string[] {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function parseLineList(value: string): string[] {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

const fieldClassName =
  'w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#faf9f5] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]'

function toggleClassName(active: boolean) {
  return `rounded-full border px-3 py-2 text-sm transition ${
    active
      ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
      : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
  }`
}
