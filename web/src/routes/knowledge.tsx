import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react'
import { KnowledgeCreateDrawer } from '../components/knowledge/knowledge-create-drawer'
import { KnowledgeSidebar } from '../components/knowledge/knowledge-sidebar'
import { KnowledgeWorkbench } from '../components/knowledge/knowledge-workbench'
import { generateKnowledgeDrafts, knowledgeMockDocuments } from '../knowledge/mock-data'
import type {
  KnowledgeDocument,
  KnowledgeDraftInput,
  KnowledgeEngine,
  KnowledgeGroupMode,
  KnowledgeKind,
  KnowledgeStatus,
} from '../knowledge/types'

export function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>(knowledgeMockDocuments)
  const [selectedDocumentId, setSelectedDocumentId] = useState<string>(knowledgeMockDocuments[0]?.id ?? '')
  const [query, setQuery] = useState('')
  const [kindFilter, setKindFilter] = useState<KnowledgeKind | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<KnowledgeStatus | 'all'>('all')
  const [engineFilter, setEngineFilter] = useState<KnowledgeEngine | 'all'>('all')
  const [domainFilter, setDomainFilter] = useState('all')
  const [groupMode, setGroupMode] = useState<KnowledgeGroupMode>('domain')
  const [showCreateDrawer, setShowCreateDrawer] = useState(false)
  const [creating, setCreating] = useState(false)
  const deferredQuery = useDeferredValue(query)

  const filteredDocuments = useMemo(() => {
    const keyword = deferredQuery.trim().toLowerCase()
    return documents
      .filter((document) => {
        if (kindFilter !== 'all' && document.kind !== kindFilter) {
          return false
        }
        if (statusFilter !== 'all' && document.status !== statusFilter) {
          return false
        }
        if (engineFilter !== 'all' && !document.engines.includes(engineFilter)) {
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
  }, [deferredQuery, documents, domainFilter, engineFilter, kindFilter, statusFilter])

  const selectedDocument = filteredDocuments.find((document) => document.id === selectedDocumentId) ?? documents.find((document) => document.id === selectedDocumentId) ?? null

  useEffect(() => {
    if (filteredDocuments.length === 0) {
      return
    }
    if (!selectedDocumentId || !filteredDocuments.some((document) => document.id === selectedDocumentId)) {
      setSelectedDocumentId(filteredDocuments[0].id)
    }
  }, [filteredDocuments, selectedDocumentId])

  function updateDocument(id: string, patch: Partial<KnowledgeDocument>) {
    setDocuments((current) =>
      current.map((document) =>
        document.id === id
          ? {
              ...document,
              ...patch,
              updatedAt: formatNow(),
            }
          : document,
      ),
    )
  }

  function createDrafts(payload: KnowledgeDraftInput) {
    setCreating(true)
    window.setTimeout(() => {
      const nextDocuments = generateKnowledgeDrafts(payload)
      startTransition(() => {
        setDocuments((current) => [...nextDocuments, ...current])
        setSelectedDocumentId(nextDocuments[0]?.id ?? '')
        setShowCreateDrawer(false)
        setCreating(false)
      })
    }, 320)
  }

  return (
    <>
      <div className="grid gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[360px_minmax(0,1fr)]">
        <KnowledgeSidebar
          documents={filteredDocuments}
          domainFilter={domainFilter}
          engineFilter={engineFilter}
          groupMode={groupMode}
          kindFilter={kindFilter}
          onDomainFilterChange={setDomainFilter}
          onEngineFilterChange={setEngineFilter}
          onGroupModeChange={setGroupMode}
          onKindFilterChange={setKindFilter}
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

      <KnowledgeCreateDrawer creating={creating} onClose={() => setShowCreateDrawer(false)} onSubmit={createDrafts} open={showCreateDrawer} />
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
