import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { knowledgeRepoOptions } from '../../knowledge/mock-data'
import type { KnowledgeDraftInput, KnowledgeKind } from '../../knowledge/types'

type KnowledgeCreateDrawerProps = {
  creating: boolean
  open: boolean
  onClose: () => void
  onSubmit: (payload: KnowledgeDraftInput) => void
}

const defaultKinds: KnowledgeKind[] = ['flow', 'anchor']

export function KnowledgeCreateDrawer({ creating, open, onClose, onSubmit }: KnowledgeCreateDrawerProps) {
  const [description, setDescription] = useState('')
  const [selectedRepos, setSelectedRepos] = useState<string[]>(['live_pack', 'live_sdk'])
  const [manualRepos, setManualRepos] = useState('')
  const [selectedKinds, setSelectedKinds] = useState<KnowledgeKind[]>(defaultKinds)
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (!open) {
      return
    }
    setDescription('')
    setSelectedRepos(['live_pack', 'live_sdk'])
    setManualRepos('')
    setSelectedKinds(defaultKinds)
    setNotes('')
  }, [open])

  const mergedRepos = useMemo(() => {
    const items = manualRepos
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    return Array.from(new Set([...selectedRepos, ...items]))
  }, [manualRepos, selectedRepos])

  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(20,20,19,0.42)] p-4 backdrop-blur-sm">
      <div className="max-h-[min(860px,calc(100vh-32px))] w-full max-w-[720px] overflow-y-auto rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_24px_80px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Create Draft</div>
            <h3 className="mt-2 text-[30px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">新建知识草稿</h3>
            <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">第一版默认从描述和 repo 生成 `flow + anchor` 草稿。</div>
          </div>
          <button
            className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#e8e6dc] text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <FormBlock label="描述">
            <textarea
              className={`${fieldClassName} min-h-[120px] resize-y`}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="例如：竞拍讲解卡表达层"
              value={description}
            />
          </FormBlock>

          <FormBlock label="相关 repo">
            <div className="flex flex-wrap gap-2">
              {knowledgeRepoOptions.map((repo) => (
                <ToggleChip
                  active={selectedRepos.includes(repo)}
                  key={repo}
                  label={repo}
                  onClick={() => toggleRepo(repo, selectedRepos, setSelectedRepos)}
                />
              ))}
            </div>
            <textarea
              className={`${fieldClassName} mt-3 min-h-[88px] resize-y`}
              onChange={(event) => setManualRepos(event.target.value)}
              placeholder="补充 repo，逗号分隔"
              value={manualRepos}
            />
          </FormBlock>

          <FormBlock label="生成类型">
            <div className="flex flex-wrap gap-2">
              {(['flow', 'anchor', 'rule', 'domain'] as KnowledgeKind[]).map((kind) => (
                <ToggleChip
                  active={selectedKinds.includes(kind)}
                  key={kind}
                  label={kind}
                  onClick={() => toggleKind(kind, selectedKinds, setSelectedKinds)}
                />
              ))}
            </div>
            <div className="mt-3 text-xs text-[#87867f] dark:text-[#b0aea5]">默认推荐 `flow + anchor`。只有在 domain 缺失或你明确需要时，再补 `rule / domain`。</div>
          </FormBlock>

          <FormBlock label="补充材料">
            <textarea
              className={`${fieldClassName} min-h-[120px] resize-y`}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="可贴 PRD 摘要、现有链路说明或特别关注点"
              value={notes}
            />
          </FormBlock>

          <section className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">预览</div>
            <div className="mt-3 space-y-2 text-sm text-[#141413] dark:text-[#faf9f5]">
              <div>domain：{description.trim() || '未填写描述'}</div>
              <div>repo：{mergedRepos.length > 0 ? mergedRepos.join(', ') : '未选择 repo'}</div>
              <div>生成：{selectedKinds.length > 0 ? selectedKinds.join(', ') : '未选择生成类型'}</div>
            </div>
          </section>

          <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
            <button
              className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
              onClick={onClose}
              type="button"
            >
              取消
            </button>
            <button
              className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!description.trim() || mergedRepos.length === 0 || selectedKinds.length === 0 || creating}
              onClick={() =>
                onSubmit({
                  description,
                  repos: mergedRepos,
                  kinds: selectedKinds,
                  notes,
                })
              }
              type="button"
            >
              {creating ? '生成中...' : '生成草稿'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function FormBlock({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
      <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">{label}</div>
      {children}
    </section>
  )
}

function ToggleChip({
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
          : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function toggleRepo(repo: string, selectedRepos: string[], setSelectedRepos: (value: string[]) => void) {
  if (selectedRepos.includes(repo)) {
    setSelectedRepos(selectedRepos.filter((item) => item !== repo))
    return
  }
  setSelectedRepos([...selectedRepos, repo])
}

function toggleKind(kind: KnowledgeKind, selectedKinds: KnowledgeKind[], setSelectedKinds: (value: KnowledgeKind[]) => void) {
  if (selectedKinds.includes(kind)) {
    const nextKinds = selectedKinds.filter((item) => item !== kind)
    setSelectedKinds(nextKinds)
    return
  }
  setSelectedKinds([...selectedKinds, kind])
}

const fieldClassName =
  'w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#faf9f5] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]'
