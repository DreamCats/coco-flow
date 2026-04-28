import { startTransition, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import YAML from 'yaml'
import { addSkillSource, cloneSkillSource, getSkillFile, getSkillSources, getSkillsTree, pullSkillSource, removeSkillSource } from '../api'
import { PanelMessage } from '../components/ui-primitives'
import type { SkillFile, SkillSourceStatus, SkillTreeNode } from '../skills/types'

type PreviewMode = 'rendered' | 'source'

export function SkillsPage() {
  const [sources, setSources] = useState<SkillSourceStatus[]>([])
  const [selectedSourceId, setSelectedSourceId] = useState('')
  const [rootPath, setRootPath] = useState('')
  const [nodes, setNodes] = useState<SkillTreeNode[]>([])
  const [expandedPaths, setExpandedPaths] = useState<string[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedFile, setSelectedFile] = useState<SkillFile | null>(null)
  const [previewMode, setPreviewMode] = useState<PreviewMode>('rendered')
  const [loadingSources, setLoadingSources] = useState(true)
  const [loadingTree, setLoadingTree] = useState(false)
  const [loadingFile, setLoadingFile] = useState(false)
  const [actionSourceId, setActionSourceId] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)
  const [newSourceName, setNewSourceName] = useState('')
  const [newSourceUrl, setNewSourceUrl] = useState('')
  const [newSourceBranch, setNewSourceBranch] = useState('')
  const [addingSource, setAddingSource] = useState(false)
  const [error, setError] = useState('')

  const selectedSource = sources.find((source) => source.id === selectedSourceId) || null
  const fileContent = selectedFile?.content || ''
  const selectedFileName = selectedFile?.path.split('/').pop() || ''
  const isMarkdown = selectedFileName.endsWith('.md') || selectedFileName.endsWith('.markdown')
  const parsedFile = useMemo(() => parseMarkdownSource(fileContent), [fileContent])
  const metadataEntries = useMemo(() => Object.entries(parsedFile.data), [parsedFile.data])
  const fileCount = useMemo(() => flattenFiles(nodes).length, [nodes])

  useEffect(() => {
    void loadSources()
  }, [])

  useEffect(() => {
    if (sources.length === 0) {
      setSelectedSourceId('')
      return
    }
    if (!selectedSourceId || !sources.some((source) => source.id === selectedSourceId)) {
      setSelectedSourceId(sources[0].id)
    }
  }, [sources, selectedSourceId])

  useEffect(() => {
    if (!selectedSourceId) {
      setNodes([])
      setRootPath('')
      setSelectedPath('')
      return
    }
    void loadTree(selectedSourceId)
  }, [selectedSourceId])

  useEffect(() => {
    const availableFiles = flattenFiles(nodes)
    if (availableFiles.length === 0) {
      setSelectedPath('')
      return
    }
    if (!selectedPath || !availableFiles.some((node) => node.path === selectedPath)) {
      setSelectedPath(pickDefaultFile(availableFiles)?.path || '')
    }
  }, [nodes, selectedPath])

  useEffect(() => {
    if (!selectedSourceId || !selectedPath) {
      setSelectedFile(null)
      return
    }
    let cancelled = false
    void (async () => {
      try {
        setLoadingFile(true)
        const file = await getSkillFile(selectedSourceId, selectedPath)
        if (cancelled) {
          return
        }
        setSelectedFile(file)
        setPreviewMode('rendered')
        setError('')
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载 skill 文件失败')
        }
      } finally {
        if (!cancelled) {
          setLoadingFile(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedSourceId, selectedPath])

  async function loadSources() {
    try {
      setLoadingSources(true)
      const response = await getSkillSources()
      startTransition(() => {
        setSources(response.sources)
        if (selectedSourceId && !response.sources.some((source) => source.id === selectedSourceId)) {
          setSelectedSourceId(response.sources[0]?.id || '')
        }
      })
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载 skills sources 失败')
    } finally {
      setLoadingSources(false)
    }
  }

  async function loadTree(sourceId: string) {
    try {
      setLoadingTree(true)
      const tree = await getSkillsTree(sourceId)
      startTransition(() => {
        setRootPath(tree.rootPath)
        setNodes(tree.nodes)
        setExpandedPaths([])
      })
      setError('')
    } catch (err) {
      setNodes([])
      setError(err instanceof Error ? err.message : '加载 skills 目录失败')
    } finally {
      setLoadingTree(false)
    }
  }

  function replaceSource(nextSource: SkillSourceStatus) {
    setSources((current) => current.map((source) => (source.id === nextSource.id ? nextSource : source)))
  }

  async function createSource() {
    if (!newSourceUrl.trim()) {
      setError('GitLab URL 不能为空')
      return
    }
    try {
      setAddingSource(true)
      const response = await addSkillSource({
        name: newSourceName,
        url: newSourceUrl,
        branch: newSourceBranch,
      })
      startTransition(() => {
        setSources((current) => [...current, response.source])
        setSelectedSourceId(response.source.id)
        setShowAddForm(false)
        setNewSourceName('')
        setNewSourceUrl('')
        setNewSourceBranch('')
      })
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '添加 skills source 失败')
    } finally {
      setAddingSource(false)
    }
  }

  async function runSourceAction(source: SkillSourceStatus) {
    try {
      setActionSourceId(source.id)
      const response = source.status === 'not_cloned' ? await cloneSkillSource(source.id) : await pullSkillSource(source.id)
      replaceSource(response.source)
      if (source.id === selectedSourceId) {
        await loadTree(source.id)
      }
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新 skills source 失败')
    } finally {
      setActionSourceId('')
    }
  }

  async function removeSource(source: SkillSourceStatus) {
    const confirmed = window.confirm(`移除 skills source「${source.name}」？\n\n只会从 coco-flow 配置中移除，不会删除本地目录。`)
    if (!confirmed) {
      return
    }
    try {
      setActionSourceId(source.id)
      await removeSkillSource(source.id)
      await loadSources()
      if (source.id === selectedSourceId) {
        setNodes([])
        setRootPath('')
        setSelectedPath('')
        setSelectedFile(null)
      }
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '移除 skills source 失败')
    } finally {
      setActionSourceId('')
    }
  }

  function toggleExpanded(path: string) {
    setExpandedPaths((current) => (current.includes(path) ? current.filter((item) => item !== path) : [...current, path]))
  }

  return (
    <div className="grid min-h-[760px] gap-4 lg:grid-cols-[260px_300px_minmax(0,1fr)]">
      <aside className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-2.5 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a]">
        <div className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-3 dark:border-[#30302e] dark:bg-[#232220]">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Skills</div>
              <h2 className="mt-2 text-[26px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">Skills Sources</h2>
              <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">管理 GitLab 来源，只读加载知识库。</div>
            </div>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#c96442] bg-[#c96442] text-[#faf9f5] transition hover:bg-[#d97757]"
              onClick={() => setShowAddForm((current) => !current)}
              title="添加 GitLab source"
              type="button"
            >
              <PlusIcon />
            </button>
          </div>

          {showAddForm ? (
            <div className="mt-3 space-y-3 rounded-[14px] border border-[#e8e6dc] bg-[#f5f4ed] p-3 dark:border-[#30302e] dark:bg-[#1d1c1a]">
              <TextInput label="Source Name" onChange={setNewSourceName} placeholder="live-team-skills" value={newSourceName} />
              <TextInput label="Git URL" onChange={setNewSourceUrl} placeholder="git@gitlab.xxx:team/coco-flow-skills.git" value={newSourceUrl} />
              <TextInput label="Branch" onChange={setNewSourceBranch} placeholder="main，可留空" value={newSourceBranch} />
              <div className="flex gap-2">
                <button
                  className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={addingSource}
                  onClick={() => void createSource()}
                  type="button"
                >
                  {addingSource ? '添加中...' : '添加来源'}
                </button>
                <button
                  className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
                  onClick={() => setShowAddForm(false)}
                  type="button"
                >
                  收起
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-3 space-y-2">
          {loadingSources ? (
            <SidebarMessage>正在加载 sources...</SidebarMessage>
          ) : sources.length === 0 ? (
            <SidebarMessage>还没有 skills source。</SidebarMessage>
          ) : (
            sources.map((source) => (
              <SourceCard
                busy={actionSourceId === source.id}
                key={source.id}
                onAction={runSourceAction}
                onRemove={removeSource}
                onSelect={setSelectedSourceId}
                selected={source.id === selectedSourceId}
                source={source}
              />
            ))
          )}
        </div>
      </aside>

      <aside className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-3 dark:border-[#30302e] dark:bg-[#1d1c1a]">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Package Tree</div>
          <h3 className="mt-2 truncate text-xl font-semibold text-[#141413] dark:text-[#faf9f5]">{selectedSource?.name || '未选择 source'}</h3>
          <div className="mt-2 break-all rounded-[14px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-3 font-mono text-xs text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
            {rootPath || '无本地目录'}
          </div>
          <div className="mt-3 text-xs text-[#87867f] dark:text-[#b0aea5]">{fileCount} 文件</div>
        </div>

        <div className="mt-3 max-h-[640px] overflow-y-auto pr-1">
          {loadingTree ? (
            <SidebarMessage>正在加载 package tree...</SidebarMessage>
          ) : selectedSource?.status === 'not_cloned' ? (
            <SidebarMessage>该 Git source 尚未初始化，先点击左侧初始化。</SidebarMessage>
          ) : nodes.length === 0 ? (
            <SidebarMessage>当前 source 没有可识别的 skill package。</SidebarMessage>
          ) : (
            <div className="space-y-1">
              {nodes.map((node) => (
                <SkillTreeItem
                  expandedPaths={expandedPaths}
                  key={node.path}
                  node={node}
                  onSelect={setSelectedPath}
                  onToggle={toggleExpanded}
                  selectedPath={selectedPath}
                />
              ))}
            </div>
          )}
        </div>
      </aside>

      <main className="min-w-0">
        {!selectedFile ? (
          <PanelMessage>{loadingFile ? '正在加载文件...' : '先从中间选择一个 skill 文件。'}</PanelMessage>
        ) : (
          <section className="min-w-0 rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a]">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e8e6dc] pb-4 dark:border-[#30302e]">
              <div className="min-w-0 flex-1">
                <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Read Only Skill File</div>
                <h3 className="mt-2 truncate text-[30px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]" title={selectedFile.path}>
                  {selectedFileName}
                </h3>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 font-mono dark:border-[#30302e] dark:bg-[#232220]">{selectedFile.sourceId}</span>
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 font-mono dark:border-[#30302e] dark:bg-[#232220]">{selectedFile.path}</span>
                  <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 dark:border-[#30302e] dark:bg-[#232220]">{countLines(fileContent)} 行</span>
                </div>
              </div>
              <div className="inline-flex rounded-[14px] bg-[#e8e6dc] p-1 dark:bg-[#30302e]">
                <ToggleButton active={previewMode === 'rendered'} label="预览" onClick={() => setPreviewMode('rendered')} />
                <ToggleButton active={previewMode === 'source'} label="源码" onClick={() => setPreviewMode('source')} />
              </div>
            </div>

            {error ? <div className="mt-4 rounded-[16px] border border-[#e1c1bf] bg-[#fbf1f0] px-4 py-3 text-sm text-[#b53333] dark:border-[#7a3b3b] dark:bg-[#362020] dark:text-[#efb3b3]">{error}</div> : null}

            {isMarkdown ? (
              <MetadataCard
                entries={metadataEntries}
                frontmatter={parsedFile.frontmatter}
                hasFrontmatter={parsedFile.hasFrontmatter}
                parseError={parsedFile.parseError}
              />
            ) : null}

            <div className="mt-4 min-w-0">
              {renderFileContent({
                content: fileContent,
                isMarkdown,
                parsedContent: parsedFile.content,
                previewMode,
              })}
            </div>
          </section>
        )}
      </main>
    </div>
  )
}

function SourceCard({
  source,
  selected,
  busy,
  onSelect,
  onAction,
  onRemove,
}: {
  source: SkillSourceStatus
  selected: boolean
  busy: boolean
  onSelect: (sourceId: string) => void
  onAction: (source: SkillSourceStatus) => Promise<void>
  onRemove: (source: SkillSourceStatus) => Promise<void>
}) {
  const canSync = source.sourceType === 'git' && source.status !== 'dirty' && source.status !== 'not_git'
  const actionLabel = source.status === 'not_cloned' ? '初始化' : '更新'
  return (
    <div className={`rounded-[16px] border p-3 transition ${selected ? 'border-[#c96442] bg-[#fff7f2] dark:border-[#d97757] dark:bg-[#3a2620]' : 'border-[#e8e6dc] bg-[#faf9f5] dark:border-[#30302e] dark:bg-[#232220]'}`}>
      <button className="w-full text-left" onClick={() => onSelect(source.id)} type="button">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">{source.name}</div>
            <div className="mt-1 truncate font-mono text-[11px] text-[#87867f] dark:text-[#b0aea5]">{source.id}</div>
          </div>
          <StatusBadge source={source} />
        </div>
        <div className="mt-2 truncate text-xs text-[#87867f] dark:text-[#b0aea5]">{source.url || source.localPath}</div>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[#87867f] dark:text-[#b0aea5]">
          <span>{source.sourceType}</span>
          <span>{source.currentBranch || source.branch || 'no branch'}</span>
          <span>{source.commit || 'no commit'}</span>
          <span>{source.packageCount} packages</span>
        </div>
      </button>
      <div className="mt-3 flex gap-2">
        <button
          className="flex-1 rounded-[12px] border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-2 text-sm font-semibold text-[#141413] transition hover:border-[#c96442] disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#faf9f5]"
          disabled={busy || !canSync}
          onClick={() => void onAction(source)}
          title={source.status === 'dirty' ? '存在本地改动，请先在终端处理' : undefined}
          type="button"
        >
          {busy ? '执行中...' : actionLabel}
        </button>
        <button
          className="rounded-[12px] border border-[#e1c1bf] px-3 py-2 text-sm font-semibold text-[#9d3328] transition hover:bg-[#fbf1f0] disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#7a3b3b] dark:text-[#efb3b3] dark:hover:bg-[#362020]"
          disabled={busy}
          onClick={() => void onRemove(source)}
          type="button"
        >
          移除
        </button>
      </div>
    </div>
  )
}

function StatusBadge({ source }: { source: SkillSourceStatus }) {
  const label = source.message || source.status
  const tone = source.status === 'clean' || source.status === 'ready' ? 'text-[#1f7a4d] bg-[#e8f5ee] border-[#b7dfc8]' : source.status === 'behind' ? 'text-[#8a5b00] bg-[#fff4d6] border-[#e5c86e]' : 'text-[#9d3328] bg-[#fbf1f0] border-[#e1c1bf]'
  return <span className={`shrink-0 rounded-full border px-2 py-1 text-[11px] ${tone}`}>{label}</span>
}

function TextInput({ label, value, placeholder, onChange }: { label: string; value: string; placeholder: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <div className="mb-1 text-[11px] uppercase tracking-[0.18em] text-[#87867f] dark:text-[#b0aea5]">{label}</div>
      <input
        className="w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5]"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type="text"
        value={value}
      />
    </label>
  )
}

function SkillTreeItem({
  node,
  selectedPath,
  expandedPaths,
  onToggle,
  onSelect,
  depth = 0,
}: {
  node: SkillTreeNode
  selectedPath: string
  expandedPaths: string[]
  onToggle: (path: string) => void
  onSelect: (path: string) => void
  depth?: number
}) {
  const isDirectory = node.nodeType === 'directory'
  const isExpanded = expandedPaths.includes(node.path)
  const paddingLeft = 12 + depth * 18

  return (
    <div>
      <button
        className={`flex w-full items-center gap-2 rounded-[14px] px-3 py-2 text-left transition ${
          selectedPath === node.path
            ? 'bg-[#fff7f2] text-[#141413] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:bg-[#3a2620] dark:text-[#faf9f5]'
            : 'text-[#5e5d59] hover:bg-[#faf9f5] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:bg-[#232220] dark:hover:text-[#faf9f5]'
        }`}
        onClick={() => {
          if (isDirectory) {
            onToggle(node.path)
            return
          }
          onSelect(node.path)
        }}
        style={{ paddingLeft }}
        type="button"
      >
        <span className="w-4 text-center text-xs text-[#87867f] dark:text-[#8f8a82]">{isDirectory ? (isExpanded ? '▾' : '▸') : '·'}</span>
        <span className={`truncate ${isDirectory ? 'text-sm font-semibold' : 'font-mono text-xs'}`}>{node.name}</span>
      </button>
      {isDirectory && isExpanded ? (
        <div className="space-y-1">
          {node.children.map((child) => (
            <SkillTreeItem
              depth={depth + 1}
              expandedPaths={expandedPaths}
              key={child.path}
              node={child}
              onSelect={onSelect}
              onToggle={onToggle}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

function MetadataCard({
  entries,
  frontmatter,
  hasFrontmatter,
  parseError,
}: {
  entries: Array<[string, unknown]>
  frontmatter: string
  hasFrontmatter: boolean
  parseError: string
}) {
  const summary = metadataSummary({ entries, hasFrontmatter, parseError })

  return (
    <section className="mt-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] dark:border-[#30302e] dark:bg-[#232220]">
      <div className="px-4 py-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">Frontmatter</div>
        <div className="mt-1 text-sm text-[#5e5d59] dark:text-[#b0aea5]">{summary}</div>
      </div>
      {hasFrontmatter ? (
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
          <pre className="overflow-auto rounded-[16px] border border-[#e8e6dc] bg-[#141413] px-4 py-4 font-mono text-xs leading-6 text-[#faf9f5] dark:border-[#30302e]">
            <code>{frontmatter}</code>
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
          ? 'bg-[#ffffff] text-[#141413] dark:bg-[#141413] dark:text-[#faf9f5]'
          : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function renderFileContent({
  content,
  isMarkdown,
  parsedContent,
  previewMode,
}: {
  content: string
  isMarkdown: boolean
  parsedContent: string
  previewMode: PreviewMode
}) {
  if (previewMode === 'source' || !isMarkdown) {
    return (
      <pre className="min-h-[620px] overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#141413] px-4 py-4 font-mono text-xs leading-6 text-[#faf9f5] dark:border-[#30302e]">
        <code>{content || '暂无内容'}</code>
      </pre>
    )
  }
  return (
    <div className="overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#fdfcf9] px-5 py-5 dark:border-[#30302e] dark:bg-[#171615]">
      <MarkdownPreview content={parsedContent || '暂无内容'} />
    </div>
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

function parseMarkdownSource(source: string) {
  const normalized = source.trim() ? source : '\n'
  const extracted = extractLeadingFrontmatter(normalized)
  if (!extracted) {
    return {
      data: {},
      content: normalized.trim(),
      frontmatter: '',
      hasFrontmatter: false,
      parseError: '',
    }
  }
  try {
    const parsed = YAML.parse(extracted.block)
    return {
      data: isRecord(parsed) ? parsed : {},
      content: extracted.body.trim(),
      frontmatter: `---\n${extracted.block}\n---`,
      hasFrontmatter: true,
      parseError: '',
    }
  } catch (error) {
    return {
      data: {},
      content: extracted.body.trim(),
      frontmatter: `---\n${extracted.block}\n---`,
      hasFrontmatter: true,
      parseError: error instanceof Error ? error.message : 'unknown error',
    }
  }
}

function extractLeadingFrontmatter(source: string) {
  const normalized = source.replace(/\r\n/g, '\n')
  if (!normalized.startsWith('---\n')) {
    return null
  }
  const end = normalized.indexOf('\n---\n', 4)
  if (end === -1) {
    return null
  }
  return {
    block: normalized.slice(4, end).trim(),
    body: normalized.slice(end + 5),
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
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

function metadataSummary({
  entries,
  hasFrontmatter,
  parseError,
}: {
  entries: Array<[string, unknown]>
  hasFrontmatter: boolean
  parseError: string
}) {
  if (parseError) {
    return `frontmatter YAML 解析失败：${parseError}`
  }
  if (hasFrontmatter) {
    return `检测到 ${entries.length} 个字段`
  }
  return '当前文件没有 frontmatter'
}

function countLines(content: string) {
  return content.trim() ? content.split('\n').length : 0
}

function flattenFiles(nodes: SkillTreeNode[]): SkillTreeNode[] {
  const files: SkillTreeNode[] = []
  for (const node of nodes) {
    if (node.nodeType === 'file') {
      files.push(node)
      continue
    }
    files.push(...flattenFiles(node.children))
  }
  return files
}

function pickDefaultFile(files: SkillTreeNode[]) {
  const skillFile = files.find((node) => node.name === 'SKILL.md')
  return skillFile || files[0] || null
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 16 16">
      <path d="M8 3.333v9.334M3.333 8h9.334" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  )
}
