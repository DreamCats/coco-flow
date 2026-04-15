import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { createKnowledgeDrafts, listKnowledge, updateKnowledgeDocument } from '../api'
import { KnowledgeCreateDrawer } from '../components/knowledge/knowledge-create-drawer'
import { KnowledgeSidebar } from '../components/knowledge/knowledge-sidebar'
import { KnowledgeWorkbench } from '../components/knowledge/knowledge-workbench'
import type { KnowledgeDocument, KnowledgeDraftInput, KnowledgeStatus } from '../knowledge/types'

export function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [selectedDocumentId, setSelectedDocumentId] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<KnowledgeStatus | 'all'>('all')
  const [domainFilter, setDomainFilter] = useState('all')
  const [showCreateDrawer, setShowCreateDrawer] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [creating, setCreating] = useState(false)
  const deferredQuery = useDeferredValue(query)
  const saveTimers = useRef<Record<string, number>>({})

  const filteredDocuments = useMemo(() => {
    const keyword = deferredQuery.trim().toLowerCase()
    return documents
      .filter((document) => {
        if (statusFilter !== 'all' && document.status !== statusFilter) {
          return false
        }
        if (domainFilter !== 'all' && document.domainName !== domainFilter) {
          return false
        }
        if (!keyword) {
          return true
        }
        return [
          document.title,
          document.domainName,
          document.desc,
          document.repos.join(' '),
          document.keywords.join(' '),
        ]
          .join(' ')
          .toLowerCase()
          .includes(keyword)
      })
      .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt) || left.title.localeCompare(right.title))
  }, [deferredQuery, documents, domainFilter, statusFilter])

  const selectedDocument =
    filteredDocuments.find((document) => document.id === selectedDocumentId) ??
    documents.find((document) => document.id === selectedDocumentId) ??
    null

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
      for (const timer of Object.values(saveTimers.current)) {
        window.clearTimeout(timer)
      }
    }
  }, [])

  useEffect(() => {
    if (filteredDocuments.length === 0) {
      return
    }
    if (!selectedDocumentId || !filteredDocuments.some((document) => document.id === selectedDocumentId)) {
      setSelectedDocumentId(filteredDocuments[0].id)
    }
  }, [filteredDocuments, selectedDocumentId])

  function updateDocument(id: string, patch: Partial<KnowledgeDocument>) {
    let nextDocument: KnowledgeDocument | null = null
    setDocuments((current) =>
      current.map((document) => {
        if (document.id !== id) {
          return document
        }
        nextDocument = {
          ...document,
          ...patch,
          updatedAt: formatNow(),
        }
        return nextDocument
      }),
    )
    if (!nextDocument) {
      return
    }
    if (saveTimers.current[id]) {
      window.clearTimeout(saveTimers.current[id])
    }
    saveTimers.current[id] = window.setTimeout(async () => {
      try {
        const saved = await updateKnowledgeDocument(id, nextDocument as KnowledgeDocument)
        setDocuments((current) => current.map((document) => (document.id === id ? saved : document)))
        setError('')
      } catch (err) {
        setError(err instanceof Error ? err.message : '保存知识文档失败')
      }
    }, 400)
  }

  function createDrafts(payload: KnowledgeDraftInput) {
    setCreating(true)
    void createKnowledgeDrafts(payload)
      .then((response) => {
        startTransition(() => {
          setDocuments((current) => [...response.documents, ...current])
          setSelectedDocumentId(response.documents[0]?.id ?? '')
          setShowCreateDrawer(false)
          setError('')
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '生成知识草稿失败')
      })
      .finally(() => {
        setCreating(false)
      })
  }

  return (
    <>
      {loading ? (
        <section className="flex min-h-[760px] items-center justify-center rounded-[24px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] p-8 text-center text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
          正在加载知识列表...
        </section>
      ) : null}
      {!loading && error ? (
        <section className="mb-4 rounded-[18px] border border-[#f0c1c1] bg-[#fff1f1] px-4 py-3 text-sm text-[#a53e3e]">
          {error}
        </section>
      ) : null}
      {!loading ? (
        <div className="grid gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[360px_minmax(0,1fr)]">
          <KnowledgeSidebar
            documents={filteredDocuments}
            domainFilter={domainFilter}
            onDomainFilterChange={setDomainFilter}
            onOpenCreate={() => setShowCreateDrawer(true)}
            onQueryChange={setQuery}
            onSelectDocument={setSelectedDocumentId}
            onStatusFilterChange={setStatusFilter}
            query={query}
            selectedDocumentId={selectedDocumentId}
            statusFilter={statusFilter}
          />
          <KnowledgeWorkbench document={selectedDocument} onUpdateDocument={updateDocument} />
        </div>
      ) : null}

      <KnowledgeCreateDrawer
        creating={creating}
        onClose={() => setShowCreateDrawer(false)}
        onSubmit={createDrafts}
        open={showCreateDrawer}
      />
    </>
  )
}

function formatNow(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = `${now.getMonth() + 1}`.padStart(2, '0')
  const day = `${now.getDate()}`.padStart(2, '0')
  const hours = `${now.getHours()}`.padStart(2, '0')
  const minutes = `${now.getMinutes()}`.padStart(2, '0')
  return `${year}-${month}-${day} ${hours}:${minutes}`
}
