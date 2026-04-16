import { startTransition, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { createKnowledgeDrafts, deleteKnowledgeDocument, getKnowledgeGenerationJob, listKnowledge, retryKnowledgeGenerationJob, updateKnowledgeDocument } from '../api'
import { KnowledgeCreateDrawer } from '../components/knowledge/knowledge-create-drawer'
import { KnowledgeSidebar } from '../components/knowledge/knowledge-sidebar'
import { KnowledgeWorkbench } from '../components/knowledge/knowledge-workbench'
import type { KnowledgeDocument, KnowledgeDraftInput, KnowledgeGenerationJob, KnowledgeStatus } from '../knowledge/types'

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
  const [activeJob, setActiveJob] = useState<KnowledgeGenerationJob | null>(null)
  const [hydratedJobId, setHydratedJobId] = useState('')
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

  useEffect(() => {
    if (!activeJob || !isRunningJob(activeJob.status)) {
      return
    }
    let cancelled = false
    const poll = () => {
      void getKnowledgeGenerationJob(activeJob.job_id)
        .then((job) => {
          if (cancelled) {
            return
          }
          setActiveJob(job)
          if (isTerminalJob(job.status)) {
            setCreating(false)
          }
        })
        .catch((err) => {
          if (cancelled) {
            return
          }
          setError(err instanceof Error ? err.message : '轮询知识生成状态失败')
          setCreating(false)
        })
    }

    poll()
    const timer = window.setInterval(poll, 200)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [activeJob])

  useEffect(() => {
    if (!activeJob || activeJob.status !== 'completed' || hydratedJobId === activeJob.job_id) {
      return
    }
    let cancelled = false
    void listKnowledge()
      .then((items) => {
        if (cancelled) {
          return
        }
        setDocuments(items)
        if (activeJob.document_ids.length > 0) {
          setSelectedDocumentId(activeJob.document_ids[0])
        }
        setHydratedJobId(activeJob.job_id)
      })
      .catch((err) => {
        if (cancelled) {
          return
        }
        setError(err instanceof Error ? err.message : '刷新知识列表失败')
      })
    return () => {
      cancelled = true
    }
  }, [activeJob, hydratedJobId])

  useEffect(() => {
    if (!activeJob || !isTerminalJob(activeJob.status)) {
      return
    }
    if (activeJob.status === 'failed' && activeJob.error) {
      setError(activeJob.error)
    }
  }, [activeJob])

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
          setActiveJob(response.job)
          setShowCreateDrawer(false)
          setError('')
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '启动知识生成失败')
        setCreating(false)
      })
  }

  function retryActiveJob() {
    if (!activeJob) {
      return
    }
    setCreating(true)
    setError('')
    void retryKnowledgeGenerationJob(activeJob.job_id)
      .then((response) => {
        startTransition(() => {
          setActiveJob(response.job)
          setHydratedJobId('')
        })
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '重试知识生成失败')
        setCreating(false)
      })
  }

  function handleRegenerateDocument(document: KnowledgeDocument) {
    createDrafts(buildRegeneratePayload(document))
  }

  function handleDeleteDomain(domainName: string, items: KnowledgeDocument[]) {
    const confirmed = window.confirm(`确认删除领域 ${domainName} 及其下 ${items.length} 个知识文件？`)
    if (!confirmed) {
      return
    }
    void Promise.all(items.map((item) => deleteKnowledgeDocument(item.id)))
      .then(() => {
        const removed = new Set(items.map((item) => item.id))
        setDocuments((current) => current.filter((item) => !removed.has(item.id)))
        setError('')
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : '删除领域失败')
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
      {!loading && activeJob ? <KnowledgeGenerationStatus creating={creating} job={activeJob} onRetry={retryActiveJob} /> : null}
      {!loading ? (
        <div className="grid gap-4 lg:h-full lg:min-h-0 lg:grid-cols-[360px_minmax(0,1fr)]">
          <KnowledgeSidebar
            documents={filteredDocuments}
            domainFilter={domainFilter}
            onDomainFilterChange={setDomainFilter}
            onDeleteDomain={handleDeleteDomain}
            onOpenCreate={() => setShowCreateDrawer(true)}
            onQueryChange={setQuery}
            onSelectDocument={setSelectedDocumentId}
            onStatusFilterChange={setStatusFilter}
            query={query}
            selectedDocumentId={selectedDocumentId}
            statusFilter={statusFilter}
          />
          <KnowledgeWorkbench
            creating={creating}
            document={selectedDocument}
            onRegenerate={handleRegenerateDocument}
            onUpdateDocument={updateDocument}
          />
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

function KnowledgeGenerationStatus({
  job,
  creating,
  onRetry,
}: {
  job: KnowledgeGenerationJob
  creating: boolean
  onRetry: () => void
}) {
  const title = job.status === 'completed' ? '知识草稿已生成' : job.status === 'failed' ? '知识草稿生成失败' : '知识草稿生成中'
  const canRetry = job.status === 'failed' || job.status === 'completed'
  const retryLabel = job.status === 'completed' ? '重新生成' : '重试生成'
  return (
    <section className="mb-4 rounded-[18px] border border-[#d8d2c3] bg-[#f5f1e8] px-4 py-4 text-sm text-[#4d4c48] dark:border-[#3a3937] dark:bg-[#232220] dark:text-[#d8d5cc]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold">{title}</div>
          <div className="mt-1 text-xs text-[#6f6d66] dark:text-[#aaa79d]">
            当前阶段：{job.stage_label} · 状态：{formatJobStatus(job.status)}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="font-mono text-xs">{job.progress}%</div>
          {canRetry ? (
            <button
              className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-3 py-1.5 text-xs font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={creating}
              onClick={onRetry}
              type="button"
            >
              {creating ? '重试中...' : retryLabel}
            </button>
          ) : null}
        </div>
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#e7dfd1] dark:bg-[#34322d]">
        <div
          className={`h-full rounded-full transition-all ${job.status === 'failed' ? 'bg-[#d06767]' : 'bg-[#c96442]'}`}
          style={{ width: `${Math.max(4, job.progress)}%` }}
        />
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-6">
        {stageItems.map((stage) => {
          const active = stage.status === job.status
          const done = job.progress >= stage.progress && job.status !== 'failed'
          return (
            <div
              className={`rounded-[14px] border px-3 py-2 text-xs ${
                active
                  ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
                  : done
                    ? 'border-[#d8d2c3] bg-[#faf9f5] text-[#4d4c48] dark:border-[#3a3937] dark:bg-[#1d1c1a] dark:text-[#d8d5cc]'
                    : 'border-[#e8e6dc] bg-[#f7f4ed] text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#8b897f]'
              }`}
              key={stage.status}
            >
              {stage.label}
            </div>
          )
        })}
      </div>
      <div className="mt-3 text-xs text-[#6f6d66] dark:text-[#aaa79d]">
        {job.status === 'failed' && job.error ? job.error : job.message}
      </div>
      {job.status === 'completed' && job.open_questions.length > 0 ? (
        <div className="mt-3 text-xs text-[#6f6d66] dark:text-[#aaa79d]">待确认：{job.open_questions.join('；')}</div>
      ) : null}
    </section>
  )
}

const stageItems = [
  { status: 'intent_normalizing', label: '意图收敛', progress: 10 },
  { status: 'term_mapping', label: '术语映射', progress: 24 },
  { status: 'repo_discovering', label: 'Repo 发现', progress: 40 },
  { status: 'candidate_ranking', label: '候选裁剪', progress: 52 },
  { status: 'anchor_selecting', label: '锚点筛选', progress: 62 },
  { status: 'term_family', label: '术语族群', progress: 70 },
  { status: 'repo_researching', label: 'Repo 研究', progress: 78 },
  { status: 'synthesizing', label: '草稿生成', progress: 88 },
  { status: 'validating', label: '结果校验', progress: 95 },
]

function isRunningJob(status: string): boolean {
  return !isTerminalJob(status)
}

function isTerminalJob(status: string): boolean {
  return status === 'completed' || status === 'failed'
}

function formatJobStatus(status: string): string {
  return {
    queued: '排队中',
    running: '准备中',
    intent_normalizing: '执行中',
    term_mapping: '执行中',
    repo_discovering: '执行中',
    candidate_ranking: '执行中',
    anchor_selecting: '执行中',
    term_family: '执行中',
    repo_researching: '执行中',
    synthesizing: '执行中',
    validating: '执行中',
    persisting: '执行中',
    completed: '完成',
    failed: '失败',
  }[status] || status
}

function buildRegeneratePayload(document: KnowledgeDocument): KnowledgeDraftInput {
  return {
    title: document.domainName || document.title,
    description: document.evidence.inputDescription || `${document.domainName}${document.title}`,
    selected_paths: document.evidence.pathMatches,
    repos: document.evidence.pathMatches,
    kinds: [document.kind],
    notes: extractNotes(document),
  }
}

function extractNotes(document: KnowledgeDocument): string {
  const notePrefix = '补充材料：'
  const note = document.evidence.retrievalNotes.find((item) => item.startsWith(notePrefix))
  return note ? note.slice(notePrefix.length) : ''
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
