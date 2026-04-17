import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type { RepoCandidate } from '../../api'
import { KnowledgePathPicker } from './knowledge-path-picker'
import type { KnowledgeDraftInput, KnowledgeKind } from '../../knowledge/types'

type KnowledgeCreateDrawerProps = {
  creating: boolean
  open: boolean
  onClose: () => void
  onSubmit: (payload: KnowledgeDraftInput) => void
}

const defaultKinds: KnowledgeKind[] = ['flow']

export function KnowledgeCreateDrawer({ creating, open, onClose, onSubmit }: KnowledgeCreateDrawerProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [selectedRepos, setSelectedRepos] = useState<RepoCandidate[]>([])
  const [selectedKinds, setSelectedKinds] = useState<KnowledgeKind[]>(defaultKinds)
  const [notes, setNotes] = useState('')
  const [showPathPicker, setShowPathPicker] = useState(false)

  useEffect(() => {
    if (!open) {
      return
    }
    setTitle('')
    setDescription('')
    setSelectedRepos([])
    setSelectedKinds(defaultKinds)
    setNotes('')
    setShowPathPicker(false)
  }, [open])

  const repoPaths = useMemo(() => selectedRepos.map((repo) => repo.path), [selectedRepos])

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
            <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">第一版默认从描述和 repo 生成 `flow` 草稿。</div>
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
          <FormBlock label="标题">
            <input
              className={fieldClassName}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：竞拍讲解卡表达层"
              type="text"
              value={title}
            />
          </FormBlock>

          <FormBlock label="描述">
            <textarea
              className={`${fieldClassName} min-h-[120px] resize-y`}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="例如：这是竞拍讲解卡表达层相关业务，涉及卡片渲染、讲解状态和模板切换。我想生成一份系统链路知识，用来帮助定位入口和依赖模块。"
              value={description}
            />
          </FormBlock>

          <FormBlock label="相关 repo">
            <div className="space-y-2">
              {selectedRepos.length === 0 ? (
                <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#faf9f5] px-4 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
                  还没有选择路径。
                </div>
              ) : (
                selectedRepos.map((repo) => (
                  <div
                    className="flex items-start justify-between gap-3 rounded-[16px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-3 dark:border-[#30302e] dark:bg-[#1d1c1a]"
                    key={repo.path}
                  >
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">{repo.displayName}</div>
                      <div className="mt-1 break-all font-mono text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{repo.path}</div>
                    </div>
                    <button
                      className="rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-1.5 text-xs text-[#4d4c48] transition hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
                      onClick={() => removeRepo(repo.path, selectedRepos, setSelectedRepos)}
                      type="button"
                    >
                      移除
                    </button>
                  </div>
                ))
              )}
            </div>
            <div className="mt-3 flex justify-end">
              <button
                className="rounded-[12px] border border-[#c96442] bg-[#fff7f2] px-4 py-2 text-sm font-semibold text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] transition hover:bg-[#fff0e2] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0] dark:hover:bg-[#4a3129]"
                onClick={() => setShowPathPicker(true)}
                type="button"
              >
                选择路径
              </button>
            </div>
          </FormBlock>

          <FormBlock label="生成类型">
            <div className="flex flex-wrap gap-2">
              {(['flow', 'domain', 'rule'] as KnowledgeKind[]).map((kind) => (
                <ToggleChip
                  active={selectedKinds.includes(kind)}
                  key={kind}
                  label={kind}
                  onClick={() => toggleKind(kind, selectedKinds, setSelectedKinds)}
                />
              ))}
            </div>
            <div className="mt-3 text-xs text-[#87867f] dark:text-[#b0aea5]">默认推荐 `flow`。只有在 domain 缺失或你明确需要时，再补 `domain`。`rule` 暂不作为默认产物。</div>
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
              <div>标题：{title.trim() || '未填写标题'}</div>
              <div>描述：{description.trim() || '未填写描述'}</div>
              <div>repo：{repoPaths.length > 0 ? repoPaths.join(', ') : '未选择路径'}</div>
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
              disabled={!title.trim() || !description.trim() || repoPaths.length === 0 || selectedKinds.length === 0 || creating}
              onClick={() =>
                onSubmit({
                  title,
                  description,
                  selected_paths: repoPaths,
                  repos: repoPaths,
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

      <KnowledgePathPicker
        onAddPath={(repo) => addRepo(repo, selectedRepos, setSelectedRepos)}
        onClose={() => setShowPathPicker(false)}
        open={showPathPicker}
        selectedPaths={repoPaths}
      />
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

function addRepo(repo: RepoCandidate, selectedRepos: RepoCandidate[], setSelectedRepos: (value: RepoCandidate[]) => void) {
  if (selectedRepos.some((item) => item.path === repo.path)) {
    return
  }
  setSelectedRepos([...selectedRepos, repo])
}

function removeRepo(path: string, selectedRepos: RepoCandidate[], setSelectedRepos: (value: RepoCandidate[]) => void) {
  setSelectedRepos(selectedRepos.filter((item) => item.path !== path))
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
