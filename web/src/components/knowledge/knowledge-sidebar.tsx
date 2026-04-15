import type { KnowledgeDocument, KnowledgeKind, KnowledgeStatus } from '../../knowledge/types'
import { KnowledgeKindBadge, KnowledgeStatusBadge } from './knowledge-badges'

const knowledgeKindOrder: KnowledgeKind[] = ['domain', 'flow', 'rule']
const knowledgeKindFallbackTitle: Record<KnowledgeKind, string> = {
  domain: '业务方向概览',
  flow: '关键链路待补',
  rule: '业务规则待补',
}

type KnowledgeSidebarProps = {
  documents: KnowledgeDocument[]
  selectedDocumentId: string
  query: string
  onQueryChange: (value: string) => void
  statusFilter: KnowledgeStatus | 'all'
  onStatusFilterChange: (value: KnowledgeStatus | 'all') => void
  domainFilter: string
  onDomainFilterChange: (value: string) => void
  onDeleteDomain: (domainName: string, documents: KnowledgeDocument[]) => void
  onDeleteDocument: (document: KnowledgeDocument) => void
  onSelectDocument: (id: string) => void
  onOpenCreate: () => void
}

export function KnowledgeSidebar({
  documents,
  selectedDocumentId,
  query,
  onQueryChange,
  statusFilter,
  onStatusFilterChange,
  domainFilter,
  onDomainFilterChange,
  onDeleteDomain,
  onDeleteDocument,
  onSelectDocument,
  onOpenCreate,
}: KnowledgeSidebarProps) {
  const domainOptions = Array.from(new Set(documents.map((document) => document.domainName))).sort()
  const groupedByDomain = documents.reduce<Record<string, KnowledgeDocument[]>>((acc, document) => {
    acc[document.domainName] = acc[document.domainName] ? [...acc[document.domainName], document] : [document]
    return acc
  }, {})
  const orderedDomains = Object.keys(groupedByDomain).sort((left, right) => left.localeCompare(right))
  const showCompletenessSlots = statusFilter === 'all'

  return (
    <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-2.5 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.94)] lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden">
      <div className="mb-2.5 rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">知识列表</h2>
          </div>
          <button
            aria-label="新建知识草稿"
            className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#c96442] bg-[#c96442] text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]"
            onClick={onOpenCreate}
            title="新建知识草稿"
            type="button"
          >
            <PlusIcon />
          </button>
        </div>

        <div className="mt-3 space-y-2">
          <input
            className="w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]"
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="搜索 domain、标题、repo 或关键词"
            type="text"
            value={query}
          />

          <div className="grid grid-cols-2 gap-2">
            <select
              className="rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#5e5d59] outline-none focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:focus:border-[#3898ec]"
              onChange={(event) => onStatusFilterChange(event.target.value as KnowledgeStatus | 'all')}
              value={statusFilter}
            >
              <option value="all">全部状态</option>
              <option value="draft">draft</option>
              <option value="approved">approved</option>
              <option value="archived">archived</option>
            </select>
            <select
              className="rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#5e5d59] outline-none focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:focus:border-[#3898ec]"
              onChange={(event) => onDomainFilterChange(event.target.value)}
              value={domainFilter}
            >
              <option value="all">全部 domain</option>
              {domainOptions.map((domain) => (
                <option key={domain} value={domain}>
                  {domain}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="mb-2 flex items-center justify-between px-1">
        <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">知识列表</div>
        <div className="text-xs text-stone-500 dark:text-stone-400">{documents.length} 条</div>
      </div>

      <div className="space-y-1.5 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
        {documents.length === 0 ? (
          <div className="rounded-[18px] border border-dashed border-[#d1cfc5] bg-[#faf9f5] px-4 py-6 text-center text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
            当前筛选条件下没有知识文件。
          </div>
        ) : (
          orderedDomains.map((domainName) => (
            <section
              className="group rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]"
              key={domainName}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[18px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{domainName}</div>
                  <div className="mt-1 text-xs text-[#87867f] dark:text-[#b0aea5]">
                    {groupedByDomain[domainName].length}/3 已补齐 · 最近更新 {groupedByDomain[domainName][0]?.updatedAt ?? '-'}
                  </div>
                </div>
                <button
                  aria-label={`删除领域 ${domainName}`}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] border border-[#e1c1bf] bg-[#fbf1f0] text-[#b53333] opacity-0 transition hover:bg-[#f7e6e4] group-hover:opacity-100 focus:opacity-100 dark:border-[#7a3b3b] dark:bg-[#362020] dark:text-[#efb3b3] dark:hover:bg-[#442626]"
                  onClick={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    onDeleteDomain(domainName, groupedByDomain[domainName])
                  }}
                  title="删除整个领域卡片"
                  type="button"
                >
                  <TrashIcon />
                </button>
              </div>

              <div className="mt-3 space-y-2">
                {showCompletenessSlots
                  ? knowledgeKindOrder.map((kind) => {
                      const document = groupedByDomain[domainName].find((item) => item.kind === kind)
                      if (!document) {
                        return <KnowledgePlaceholderRow domainName={domainName} key={`${domainName}-${kind}`} kind={kind} />
                      }
                      return (
                        <KnowledgeRow
                          document={document}
                          key={document.id}
                          onDelete={onDeleteDocument}
                          selected={document.id === selectedDocumentId}
                          onSelect={onSelectDocument}
                        />
                      )
                    })
                  : groupedByDomain[domainName]
                      .sort((left, right) => left.title.localeCompare(right.title))
                      .map((document) => (
                        <KnowledgeRow
                          document={document}
                          key={document.id}
                          onDelete={onDeleteDocument}
                          selected={document.id === selectedDocumentId}
                          onSelect={onSelectDocument}
                        />
                      ))}
              </div>
            </section>
          ))
        )}
      </div>
    </section>
  )
}

function KnowledgeRow({
  document,
  onDelete,
  selected,
  onSelect,
}: {
  document: KnowledgeDocument
  onDelete: (document: KnowledgeDocument) => void
  selected: boolean
  onSelect: (id: string) => void
}) {
  return (
    <button
      className={`group w-full rounded-[16px] border px-3 py-3 text-left transition ${
        selected
          ? 'border-[#c96442] bg-[#fff7f2] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620]'
          : 'border-[#e8e6dc] bg-[#faf9f5] hover:border-[#d1cfc5] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:hover:border-[#3a3937]'
      }`}
      onClick={() => onSelect(document.id)}
      type="button"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">{document.title}</div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <KnowledgeKindBadge kind={document.kind} />
          <KnowledgeStatusBadge status={document.status} />
          <button
            aria-label={`删除知识 ${document.title}`}
            className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] border border-[#e1c1bf] bg-[#fbf1f0] text-[#b53333] opacity-0 transition hover:bg-[#f7e6e4] group-hover:opacity-100 focus:opacity-100 dark:border-[#7a3b3b] dark:bg-[#362020] dark:text-[#efb3b3] dark:hover:bg-[#442626]"
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              onDelete(document)
            }}
            title="删除知识卡片"
            type="button"
          >
            <TrashIcon />
          </button>
        </div>
      </div>
      <div className="mt-2 text-xs text-[#87867f] dark:text-[#b0aea5]">{document.updatedAt}</div>
    </button>
  )
}

function KnowledgePlaceholderRow({
  domainName,
  kind,
}: {
  domainName: string
  kind: KnowledgeKind
}) {
  return (
    <div className="w-full rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-3 py-3 text-left dark:border-[#3a3937] dark:bg-[#1d1c1a]">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-[#87867f] dark:text-[#b0aea5]">{knowledgeKindFallbackTitle[kind]}</div>
          <div className="mt-1 text-xs text-[#a19f96] dark:text-[#8b897f]">{domainName} 还没有 {kind} 文件</div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <KnowledgeKindBadge kind={kind} />
          <span className="rounded-full border border-dashed border-[#d1cfc5] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#87867f] dark:border-[#3a3937] dark:text-[#b0aea5]">
            待补齐
          </span>
        </div>
      </div>
    </div>
  )
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 16 16">
      <path d="M8 3.333v9.334M3.333 8h9.334" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24">
      <path d="M5 7h14M10 11v6M14 11v6M9 4h6l1 2H8l1-2zm-1 3h8l-.7 11a2 2 0 0 1-2 2H10.7a2 2 0 0 1-2-2L8 7z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </svg>
  )
}
