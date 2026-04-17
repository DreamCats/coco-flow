import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { createKnowledgeDocument, deleteKnowledgeDocument, listKnowledge, updateKnowledgeDocumentContent } from '../api'
import { KnowledgeCreateDrawer } from '../components/knowledge/knowledge-create-drawer'
import { PanelMessage } from '../components/ui-primitives'
import type { KnowledgeDocument } from '../knowledge/types'

export function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [selectedDocumentId, setSelectedDocumentId] = useState('')
  const [query, setQuery] = useState('')
  const [showCreateDrawer, setShowCreateDrawer] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const [savingDocumentId, setSavingDocumentId] = useState('')
  const [editingDocumentId, setEditingDocumentId] = useState('')
  const [draftContent, setDraftContent] = useState('')
  const deferredQuery = useDeferredValue(query)

  const filteredDocuments = useMemo(() => {
    const keyword = deferredQuery.trim().toLowerCase()
    return [...documents]
      .filter((document) => {
        if (!keyword) {
          return true
        }
        return [document.title, document.desc, document.domainName, document.kind, document.status, document.keywords.join(' '), document.repos.join(' ')]
          .join(' ')
          .toLowerCase()
          .includes(keyword)
      })
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt) || left.title.localeCompare(right.title))
  }, [deferredQuery, documents])

  const selectedDocument =
    filteredDocuments.find((document) => document.id === selectedDocumentId) ??
    documents.find((document) => document.id === selectedDocumentId) ??
    null
  const isEditing = selectedDocument !== null && editingDocumentId === selectedDocument.id
  const activeContent = isEditing ? draftContent : selectedDocument ? serializeKnowledgeDocument(selectedDocument) : ''
  const preview = splitFrontmatter(activeContent)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        setLoading(true)
        const items = await listKnowledge()
        if (cancelled) {
          return
        }
        setDocuments(items)
        setError('')
      } catch (err) {
        if (cancelled) {
          return
        }
        setError(err instanceof Error ? err.message : '加载知识列表失败')
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (filteredDocuments.length === 0) {
      if (selectedDocumentId) {
        setSelectedDocumentId('')
      }
      return
    }
    if (!selectedDocumentId || !filteredDocuments.some((document) => document.id === selectedDocumentId)) {
      setSelectedDocumentId(filteredDocuments[0].id)
    }
  }, [filteredDocuments, selectedDocumentId])

  useEffect(() => {
    if (!selectedDocument) {
      setEditingDocumentId('')
      setDraftContent('')
      return
    }
    setEditingDocumentId('')
    setDraftContent(serializeKnowledgeDocument(selectedDocument))
  }, [selectedDocument?.id])

  function replaceDocument(nextDocument: KnowledgeDocument) {
    setDocuments((current) => {
      const index = current.findIndex((item) => item.id === nextDocument.id)
      if (index === -1) {
        return [nextDocument, ...current]
      }
      const next = [...current]
      next[index] = nextDocument
      return next
    })
  }

  function createDocument(payload: { title: string; content: string }) {
    setCreating(true)
    void createKnowledgeDocument(payload)
      .then((document) => {
        startTransition(() => {
          replaceDocument(document)
          setSelectedDocumentId(document.id)
          setShowCreateDrawer(false)
          setError('')
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '创建知识文档失败')
      })
      .finally(() => {
        setCreating(false)
      })
  }

  function saveDocument() {
    if (!selectedDocument || !isEditing) {
      return
    }
    setSavingDocumentId(selectedDocument.id)
    void updateKnowledgeDocumentContent(selectedDocument.id, draftContent)
      .then((document) => {
        startTransition(() => {
          replaceDocument(document)
          setEditingDocumentId('')
          setDraftContent(serializeKnowledgeDocument(document))
          setError('')
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '保存知识文档失败')
      })
      .finally(() => {
        setSavingDocumentId('')
      })
  }

  function deleteDocument() {
    if (!selectedDocument) {
      return
    }
    if (!window.confirm(`确认删除《${selectedDocument.title}》吗？`)) {
      return
    }
    const deletingId = selectedDocument.id
    void deleteKnowledgeDocument(deletingId)
      .then(() => {
        startTransition(() => {
          setDocuments((current) => current.filter((document) => document.id !== deletingId))
          if (selectedDocumentId === deletingId) {
            setSelectedDocumentId('')
          }
          setEditingDocumentId('')
          setDraftContent('')
          setError('')
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '删除知识文档失败')
      })
  }

  return (
    <>
      <div className="grid min-h-[760px] gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <aside className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-2.5 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.94)] lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden">
          <div className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Knowledge</div>
                <h2 className="mt-2 text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">知识列表</h2>
                <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">左侧按文档聚合，右侧直接预览和编辑 Markdown 文件。</div>
              </div>
              <button
                aria-label="新建知识文档"
                className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#c96442] bg-[#c96442] text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]"
                onClick={() => setShowCreateDrawer(true)}
                type="button"
              >
                <PlusIcon />
              </button>
            </div>
            <input
              className="mt-3 w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题、状态、repo 或关键词"
              type="text"
              value={query}
            />
          </div>

          <div className="mt-3 flex items-center justify-between px-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">文档</div>
            <div className="text-xs text-stone-500 dark:text-stone-400">{filteredDocuments.length} 条</div>
          </div>

          <div className="mt-2 space-y-2 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
            {loading ? (
              <SidebarMessage>加载中...</SidebarMessage>
            ) : filteredDocuments.length === 0 ? (
              <SidebarMessage>当前没有可展示的知识文档。</SidebarMessage>
            ) : (
              filteredDocuments.map((document) => (
                <button
                  className={`w-full rounded-[16px] border px-3 py-3 text-left transition ${
                    selectedDocument?.id === document.id
                      ? 'border-[#c96442] bg-[#fff7f2] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620]'
                      : 'border-[#e8e6dc] bg-[#faf9f5] hover:border-[#d1cfc5] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:hover:border-[#3a3937]'
                  }`}
                  key={document.id}
                  onClick={() => setSelectedDocumentId(document.id)}
                  type="button"
                >
                  <div className="line-clamp-2 text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">{document.title}</div>
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-[#87867f] dark:text-[#b0aea5]">
                    <span>{document.kind}</span>
                    <span>{document.status}</span>
                    {document.domainName ? <span>{document.domainName}</span> : null}
                  </div>
                  <div className="mt-2 text-xs text-[#87867f] dark:text-[#b0aea5]">{document.updatedAt || '--'}</div>
                </button>
              ))
            )}
          </div>
        </aside>

        {!selectedDocument ? (
          <PanelMessage>先从左侧选择一份知识文档，或新建一份 Markdown 文件。</PanelMessage>
        ) : (
          <section className="min-w-0 rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e8e6dc] pb-4 dark:border-[#30302e]">
              <div className="min-w-0 flex-1">
                <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Knowledge File</div>
                <h3 className="mt-2 truncate text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]" title={selectedDocument.title}>
                  {selectedDocument.title}
                </h3>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 dark:border-[#30302e] dark:bg-[#232220]">{selectedDocument.kind}</span>
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 dark:border-[#30302e] dark:bg-[#232220]">{selectedDocument.status}</span>
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 font-mono dark:border-[#30302e] dark:bg-[#232220]">{selectedDocument.id}.md</span>
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 dark:border-[#30302e] dark:bg-[#232220]">更新于 {selectedDocument.updatedAt || '--'}</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {isEditing ? (
                  <>
                    <button
                      className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
                      onClick={() => {
                        setEditingDocumentId('')
                        setDraftContent(serializeKnowledgeDocument(selectedDocument))
                      }}
                      type="button"
                    >
                      取消
                    </button>
                    <button
                      className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
                      disabled={savingDocumentId === selectedDocument.id}
                      onClick={saveDocument}
                      type="button"
                    >
                      {savingDocumentId === selectedDocument.id ? '保存中...' : '保存'}
                    </button>
                  </>
                ) : (
                  <button
                    className="rounded-[12px] border border-[#c96442] bg-[#fff7f2] px-4 py-2 text-sm font-semibold text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] transition hover:bg-[#fff0e2] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0] dark:hover:bg-[#4a3129]"
                    onClick={() => {
                      setDraftContent(serializeKnowledgeDocument(selectedDocument))
                      setEditingDocumentId(selectedDocument.id)
                    }}
                    type="button"
                  >
                    编辑源码
                  </button>
                )}
                <button
                  className="rounded-[12px] border border-[#e1c1bf] bg-[#fbf1f0] px-4 py-2 text-sm font-semibold text-[#b53333] transition hover:bg-[#f7e6e4] dark:border-[#7a3b3b] dark:bg-[#362020] dark:text-[#efb3b3] dark:hover:bg-[#442626]"
                  onClick={deleteDocument}
                  type="button"
                >
                  删除
                </button>
              </div>
            </div>

            {error ? <div className="mt-4 rounded-[16px] border border-[#e1c1bf] bg-[#fbf1f0] px-4 py-3 text-sm text-[#b53333] dark:border-[#7a3b3b] dark:bg-[#362020] dark:text-[#efb3b3]">{error}</div> : null}

            {isEditing ? (
              <div className="mt-4">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
                  <span>源码编辑模式</span>
                  <span>{countLines(draftContent)} 行</span>
                </div>
                <textarea
                  className="min-h-[620px] w-full resize-y rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-4 font-mono text-xs leading-6 text-[#141413] outline-none transition focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#141413] dark:text-[#faf9f5] dark:focus:border-[#3898ec]"
                  onChange={(event) => setDraftContent(event.target.value)}
                  value={draftContent}
                />
              </div>
            ) : (
              <div className="mt-4 min-w-0">
                {preview.frontmatter ? (
                  <div className="mb-4 rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-3 text-sm text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                    检测到 YAML frontmatter，右侧预览区仅渲染正文内容；如需修改 frontmatter，请使用“编辑源码”。
                  </div>
                ) : null}
                <div className="overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#fdfcf9] px-5 py-5 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#171615] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
                  <MarkdownPreview content={preview.body || '暂无内容'} />
                </div>
              </div>
            )}
          </section>
        )}
      </div>

      <KnowledgeCreateDrawer creating={creating} onClose={() => setShowCreateDrawer(false)} onSubmit={createDocument} open={showCreateDrawer} />
    </>
  )
}

function SidebarMessage({ children }: { children: string }) {
  return (
    <div className="rounded-[18px] border border-dashed border-[#d1cfc5] bg-[#faf9f5] px-4 py-6 text-center text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
      {children}
    </div>
  )
}

function MarkdownPreview({ content }: { content: string }) {
  return (
    <div className="text-[#141413] dark:text-[#faf9f5]">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => <h1 className="mt-2 mb-3 text-[32px] leading-[1.15] font-medium [font-family:Georgia,serif]">{children}</h1>,
          h2: ({ children }) => <h2 className="mt-6 mb-3 text-[24px] leading-[1.2] font-medium [font-family:Georgia,serif]">{children}</h2>,
          h3: ({ children }) => <h3 className="mt-5 mb-2 text-[20px] leading-[1.2] font-medium [font-family:Georgia,serif]">{children}</h3>,
          p: ({ children }) => <p className="my-2 text-[15px] leading-[1.8] text-[#4d4c48] dark:text-[#b0aea5]">{children}</p>,
          ul: ({ children }) => <ul className="my-3 list-disc space-y-1.5 pl-5 text-[15px] leading-7 text-[#4d4c48] dark:text-[#b0aea5]">{children}</ul>,
          ol: ({ children }) => <ol className="my-3 list-decimal space-y-1.5 pl-5 text-[15px] leading-7 text-[#4d4c48] dark:text-[#b0aea5]">{children}</ol>,
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
          th: ({ children }) => <th className="border-b border-[#ddd9cc] px-3 py-2 font-semibold dark:border-[#3a3937]">{children}</th>,
          td: ({ children }) => <td className="border-t border-[#e8e6dc] px-3 py-2 text-[#4d4c48] dark:border-[#30302e] dark:text-[#b0aea5]">{children}</td>,
          a: ({ href, children }) => (
            <a className="text-[#c96442] underline underline-offset-2 dark:text-[#f0c0b0]" href={href} rel="noreferrer" target="_blank">
              {children}
            </a>
          ),
          code: ({ className, children }) =>
            className ? (
              <code className="font-mono text-xs leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{children}</code>
            ) : (
              <code className="rounded bg-[#f1ede3] px-1.5 py-0.5 font-mono text-[0.9em] text-[#6b2e1f] dark:bg-[#2f2623] dark:text-[#f0c0b0]">{children}</code>
            ),
          pre: ({ children }) => (
            <pre className="my-4 overflow-x-auto rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-3 dark:border-[#30302e] dark:bg-[#141413]">
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

function serializeKnowledgeDocument(document: KnowledgeDocument) {
  const evidence = {
    inputTitle: document.evidence.inputTitle,
    inputDescription: document.evidence.inputDescription,
    repoMatches: document.evidence.repoMatches,
    contextHits: document.evidence.contextHits,
    retrievalNotes: document.evidence.retrievalNotes,
    openQuestions: document.evidence.openQuestions,
  }
  const meta: Record<string, string | string[] | Record<string, unknown>> = {
    kind: document.kind,
    id: document.id,
    trace_id: document.traceId,
    title: document.title,
    desc: document.desc,
    status: document.status,
    engines: document.engines,
    domain_id: document.domainId,
    domain_name: document.domainName,
    repos: document.repos,
    priority: document.priority,
    confidence: document.confidence,
    updated_at: document.updatedAt,
    owner: document.owner,
  }
  if (document.paths.length > 0) {
    meta.paths = document.paths
  }
  if (document.keywords.length > 0) {
    meta.keywords = document.keywords
  }
  if (Object.values(evidence).some((value) => (Array.isArray(value) ? value.length > 0 : Boolean(value)))) {
    meta.evidence = evidence
  }
  const frontmatter = ['---']
  Object.entries(meta).forEach(([key, value]) => {
    const serialized = typeof value === 'string' ? value : JSON.stringify(value, null, 0)
    frontmatter.push(`${key}: ${serialized}`)
  })
  frontmatter.push('---')
  return `${frontmatter.join('\n')}\n\n${document.body.trimEnd()}\n`
}

function splitFrontmatter(content: string) {
  const normalized = content.replace(/\r\n/g, '\n')
  if (!normalized.startsWith('---\n')) {
    return {
      frontmatter: '',
      body: normalized.trim(),
    }
  }
  const end = normalized.indexOf('\n---\n', 4)
  if (end === -1) {
    return {
      frontmatter: '',
      body: normalized.trim(),
    }
  }
  return {
    frontmatter: normalized.slice(4, end).trim(),
    body: normalized.slice(end + 5).trim(),
  }
}

function countLines(content: string) {
  return content.trim() ? content.split('\n').length : 0
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 16 16">
      <path d="M8 3.333v9.334M3.333 8h9.334" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  )
}
