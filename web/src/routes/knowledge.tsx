import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import YAML from 'yaml'
import { createKnowledgeDocument, deleteKnowledgeDocument, listKnowledge, updateKnowledgeDocumentContent } from '../api'
import { ConfirmationModal } from '../components/confirmation-modal'
import { KnowledgeCreateDrawer } from '../components/knowledge/knowledge-create-drawer'
import { PanelMessage } from '../components/ui-primitives'
import type { KnowledgeDocument, KnowledgeStatus } from '../knowledge/types'

type PreviewMode = 'rendered' | 'source'
const knowledgeStatuses: KnowledgeStatus[] = ['draft', 'approved']

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
  const [previewMode, setPreviewMode] = useState<PreviewMode>('rendered')
  const [metadataOpen, setMetadataOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeDocument | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const deferredQuery = useDeferredValue(query)

  const filteredDocuments = useMemo(() => {
    const keyword = deferredQuery.trim().toLowerCase()
    return [...documents]
      .filter((document) => {
        if (!keyword) {
          return true
        }
        return [
          document.title,
          document.desc,
          document.domainName,
          document.kind,
          document.status,
          document.repos.join(' '),
          document.rawContent ?? '',
        ]
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
  const activeContent = selectedDocument ? (isEditing ? draftContent : documentSource(selectedDocument)) : ''
  const parsedDocument = useMemo(() => parseDocumentSource(activeContent), [activeContent])
  const metadataEntries = useMemo(() => Object.entries(parsedDocument.data), [parsedDocument.data])

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
      setMetadataOpen(false)
      return
    }
    setEditingDocumentId('')
    setDraftContent(documentSource(selectedDocument))
    setPreviewMode('rendered')
    setMetadataOpen(Boolean(selectedDocument.rawFrontmatter?.trim()))
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
          setDraftContent(documentSource(document))
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

  function updateStatus(nextStatus: KnowledgeStatus) {
    if (!selectedDocument || selectedDocument.status === nextStatus) {
      return
    }
    if (parsedDocument.parseError) {
      setError('frontmatter YAML 解析失败，先修复源码后再切换状态')
      return
    }
    const currentSource = isEditing ? draftContent : documentSource(selectedDocument)
    const nextSource = updateSourceStatus(currentSource, selectedDocument, parsedDocument.data, nextStatus)
    const keepEditing = isEditing
    setSavingDocumentId(selectedDocument.id)
    if (keepEditing) {
      setDraftContent(nextSource)
    }
    void updateKnowledgeDocumentContent(selectedDocument.id, nextSource)
      .then((document) => {
        startTransition(() => {
          replaceDocument(document)
          setDraftContent(documentSource(document))
          setError('')
          if (!keepEditing) {
            setEditingDocumentId('')
          }
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '更新知识状态失败')
      })
      .finally(() => {
        setSavingDocumentId('')
      })
  }

  function deleteDocument() {
    if (!selectedDocument) {
      return
    }
    setDeleteTarget(selectedDocument)
  }

  function confirmDeleteDocument() {
    if (!deleteTarget) {
      return
    }
    const deletingId = deleteTarget.id
    setDeleteBusy(true)
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
          setDeleteTarget(null)
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '删除知识文档失败')
      })
      .finally(() => {
        setDeleteBusy(false)
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
                <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">左侧文档列表，右侧提供 metadata 折叠卡、正文预览和原文切换。</div>
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
              placeholder="搜索标题、状态、repo 或正文片段"
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
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#87867f] dark:text-[#b0aea5]">Status</span>
                  <div className="inline-flex rounded-[14px] bg-[#e8e6dc] p-1 shadow-[0_0_0_1px_rgba(209,207,197,0.9)] dark:bg-[#30302e] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]">
                    {knowledgeStatuses.map((status) => (
                      <StatusButton
                        active={selectedDocument.status === status}
                        disabled={savingDocumentId === selectedDocument.id}
                        key={status}
                        label={status}
                        onClick={() => updateStatus(status)}
                      />
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {isEditing ? (
                  <>
                    <button
                      className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
                      onClick={() => {
                        setEditingDocumentId('')
                        setDraftContent(documentSource(selectedDocument))
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
                      setDraftContent(documentSource(selectedDocument))
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

            <MetadataCard
              entries={metadataEntries}
              frontmatter={parsedDocument.frontmatter}
              frontmatterBlockCount={parsedDocument.frontmatterBlockCount}
              hasFrontmatter={parsedDocument.hasFrontmatter}
              parseError={parsedDocument.parseError}
              open={metadataOpen}
              onToggle={() => setMetadataOpen((current) => !current)}
            />

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
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                  <div className="text-xs text-[#87867f] dark:text-[#b0aea5]">
                    {parsedDocument.parseError
                      ? `frontmatter 解析失败：${parsedDocument.parseError}`
                      : parsedDocument.frontmatter
                        ? 'frontmatter 已从正文预览中剥离，正文单独按 Markdown 渲染。'
                        : '当前文档没有 frontmatter，直接按 Markdown 渲染。'}
                  </div>
                  <div className="inline-flex rounded-[14px] bg-[#e8e6dc] p-1 shadow-[0_0_0_1px_rgba(209,207,197,0.9)] dark:bg-[#30302e] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]">
                    <ToggleButton active={previewMode === 'rendered'} label="正文渲染" onClick={() => setPreviewMode('rendered')} />
                    <ToggleButton active={previewMode === 'source'} label="原文" onClick={() => setPreviewMode('source')} />
                  </div>
                </div>

                {previewMode === 'rendered' ? (
                  <div className="overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#fdfcf9] px-5 py-5 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#171615] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
                    <MarkdownPreview content={parsedDocument.content || '暂无内容'} />
                  </div>
                ) : (
                  <pre className="overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#141413] px-4 py-4 font-mono text-xs leading-6 text-[#faf9f5] shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:border-[#30302e]">
                    <code>{activeContent || '暂无内容'}</code>
                  </pre>
                )}
              </div>
            )}
          </section>
        )}
      </div>

      <KnowledgeCreateDrawer creating={creating} onClose={() => setShowCreateDrawer(false)} onSubmit={createDocument} open={showCreateDrawer} />

      <ConfirmationModal
        busy={deleteBusy}
        confirmLabel="删除文档"
        description={deleteTarget ? `《${deleteTarget.title}》会从知识库中移除，相关页面引用会失去这份内容来源。` : ''}
        eyebrow="Knowledge Deletion"
        impacts={deleteTarget ? ['会删除当前知识文档源码与 frontmatter', '当前列表选择会被清空，需要重新选择其他文档', '该操作不可恢复'] : []}
        onClose={() => {
          if (!deleteBusy) {
            setDeleteTarget(null)
          }
        }}
        onConfirm={confirmDeleteDocument}
        open={Boolean(deleteTarget)}
        title={deleteTarget ? `删除《${deleteTarget.title}》` : ''}
        tone="danger"
      />
    </>
  )
}

function MetadataCard({
  entries,
  frontmatter,
  frontmatterBlockCount,
  hasFrontmatter,
  parseError,
  open,
  onToggle,
}: {
  entries: Array<[string, unknown]>
  frontmatter: string
  frontmatterBlockCount: number
  hasFrontmatter: boolean
  parseError: string
  open: boolean
  onToggle: () => void
}) {
  return (
    <section className="mt-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <button
        className="flex w-full items-center justify-between gap-3 px-4 py-4 text-left"
        onClick={onToggle}
        type="button"
      >
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Metadata</div>
          <div className="mt-1 text-sm text-[#5e5d59] dark:text-[#b0aea5]">
            {parseError
              ? `frontmatter 存在，但 YAML 解析失败`
              : frontmatterBlockCount > 1
                ? `检测到 ${frontmatterBlockCount} 段连续 frontmatter，已从正文中统一剥离`
              : hasFrontmatter
                ? `检测到 ${entries.length} 个 frontmatter 字段`
                : '当前文档没有 frontmatter'}
          </div>
        </div>
        <span className="rounded-full border border-[#d1cfc5] bg-[#faf9f5] px-3 py-1 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
          {open ? '收起' : '展开'}
        </span>
      </button>

      {open ? (
        <div className="border-t border-[#e8e6dc] px-4 py-4 dark:border-[#30302e]">
          {entries.length > 0 ? (
            <div className="mb-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {entries.map(([key, value]) => (
                <div className="rounded-[14px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-3 dark:border-[#30302e] dark:bg-[#1d1c1a]" key={key}>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-[#87867f] dark:text-[#b0aea5]">{key}</div>
                  <div className="mt-2 break-words text-sm text-[#141413] dark:text-[#faf9f5]">{formatMetadataValue(value)}</div>
                </div>
              ))}
            </div>
          ) : null}
          <pre className="overflow-auto rounded-[16px] border border-[#e8e6dc] bg-[#141413] px-4 py-4 font-mono text-xs leading-6 text-[#faf9f5] shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:border-[#30302e]">
            <code>{frontmatter || '# no frontmatter'}</code>
          </pre>
        </div>
      ) : null}
    </section>
  )
}

function ToggleButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={`rounded-[12px] px-3 py-1.5 text-[12px] transition ${
        active
          ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
          : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function StatusButton({
  active,
  disabled,
  label,
  onClick,
}: {
  active: boolean
  disabled: boolean
  label: KnowledgeStatus
  onClick: () => void
}) {
  return (
    <button
      className={`rounded-[12px] px-3 py-1.5 text-[12px] transition ${
        active
          ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
          : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
      } disabled:cursor-not-allowed disabled:opacity-50`}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
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

function parseDocumentSource(source: string) {
  const normalized = source.trim() ? source : '\n'
  const extracted = extractLeadingFrontmatter(normalized)
  if (!extracted) {
    return {
      data: {},
      content: normalized.trim(),
      frontmatter: '',
      frontmatterBlockCount: 0,
      hasFrontmatter: false,
      parseError: '',
    }
  }
  const mergedData: Record<string, unknown> = {}
  let parseError = ''
  for (const block of extracted.blocks) {
    try {
      const parsed = YAML.parse(block)
      if (isRecord(parsed)) {
        Object.assign(mergedData, parsed)
      }
    } catch (error) {
      parseError = error instanceof Error ? error.message : 'unknown error'
      break
    }
  }
  const renderedFrontmatter = extracted.blocks.map((block) => `---\n${block}\n---`).join('\n\n')
  return {
    data: parseError ? {} : mergedData,
    content: extracted.body.trim(),
    frontmatter: renderedFrontmatter,
    frontmatterBlockCount: extracted.blocks.length,
    hasFrontmatter: true,
    parseError,
  }
}

function documentSource(document: KnowledgeDocument) {
  if (document.rawContent && document.rawContent.trim()) {
    return document.rawContent
  }
  if (document.rawFrontmatter && document.rawFrontmatter.trim()) {
    return `---\n${document.rawFrontmatter.trimEnd()}\n---\n\n${document.body.trimEnd()}\n`
  }
  return document.body.trimEnd()
}

function updateSourceStatus(
  source: string,
  document: KnowledgeDocument,
  parsedData: Record<string, unknown>,
  status: KnowledgeStatus,
) {
  const extracted = extractLeadingFrontmatter(source)
  const meta = {
    ...defaultFrontmatter(document),
    ...parsedData,
    id: document.id,
    status,
  }
  const frontmatter = YAML.stringify(meta).trim()
  const body = extracted ? extracted.body.replace(/^\n+/, '') : source.replace(/^\n+/, '')
  return body.trim()
    ? `---\n${frontmatter}\n---\n\n${body.trimEnd()}\n`
    : `---\n${frontmatter}\n---\n`
}

function extractLeadingFrontmatter(source: string) {
  const normalized = source.replace(/\r\n/g, '\n')
  let remaining = normalized
  const blocks: string[] = []
  while (remaining.startsWith('---\n')) {
    const end = remaining.indexOf('\n---\n', 4)
    if (end === -1) {
      break
    }
    blocks.push(remaining.slice(4, end).trim())
    remaining = remaining.slice(end + 5).replace(/^\n+/, '')
  }
  if (blocks.length === 0) {
    return null
  }
  return {
    blocks,
    body: remaining,
  }
}

function defaultFrontmatter(document: KnowledgeDocument) {
  return {
    kind: document.kind,
    id: document.id,
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
    evidence: document.evidence,
  }
}

function formatMetadataValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.length === 0 ? '[]' : value.join(', ')
  }
  if (value && typeof value === 'object') {
    return JSON.stringify(value, null, 2)
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }
  return String(value ?? '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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
