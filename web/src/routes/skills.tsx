import { startTransition, useEffect, useMemo, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import YAML from 'yaml'
import { createSkillPackage, getSkillFile, getSkillsTree, updateSkillFile } from '../api'
import { PanelMessage } from '../components/ui-primitives'
import type { SkillFile, SkillTreeNode } from '../skills/types'

type PreviewMode = 'rendered' | 'source'

export function SkillsPage() {
  const [rootPath, setRootPath] = useState('')
  const [nodes, setNodes] = useState<SkillTreeNode[]>([])
  const [expandedPaths, setExpandedPaths] = useState<string[]>([])
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedFile, setSelectedFile] = useState<SkillFile | null>(null)
  const [draftContent, setDraftContent] = useState('')
  const [previewMode, setPreviewMode] = useState<PreviewMode>('rendered')
  const [loadingTree, setLoadingTree] = useState(true)
  const [loadingFile, setLoadingFile] = useState(false)
  const [saving, setSaving] = useState(false)
  const [creating, setCreating] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newPackageName, setNewPackageName] = useState('')
  const [newPackageDescription, setNewPackageDescription] = useState('')
  const [newPackageDomain, setNewPackageDomain] = useState('')
  const [error, setError] = useState('')

  const parsedFile = useMemo(() => parseMarkdownSource(draftContent), [draftContent])
  const metadataEntries = useMemo(() => Object.entries(parsedFile.data), [parsedFile.data])

  useEffect(() => {
    void loadTree()
  }, [])

  useEffect(() => {
    const availableFiles = flattenFiles(nodes)
    if (availableFiles.length === 0) {
      if (selectedPath) {
        setSelectedPath('')
      }
      return
    }
    if (!selectedPath || !availableFiles.some((node) => node.path === selectedPath)) {
      setSelectedPath(pickDefaultFile(availableFiles)?.path || '')
    }
  }, [nodes, selectedPath])

  useEffect(() => {
    if (!selectedPath) {
      setSelectedFile(null)
      setDraftContent('')
      return
    }
    let cancelled = false
    void (async () => {
      try {
        setLoadingFile(true)
        const file = await getSkillFile(selectedPath)
        if (cancelled) {
          return
        }
        setSelectedFile(file)
        setDraftContent(file.content)
        setPreviewMode('rendered')
        setError('')
      } catch (err) {
        if (cancelled) {
          return
        }
        setError(err instanceof Error ? err.message : '加载 skill 文件失败')
      } finally {
        if (!cancelled) {
          setLoadingFile(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selectedPath])

  async function loadTree(nextSelectedPath = '') {
    try {
      setLoadingTree(true)
      const tree = await getSkillsTree()
      startTransition(() => {
        setRootPath(tree.rootPath)
        setNodes(tree.nodes)
        setExpandedPaths(collectDirectoryPaths(tree.nodes))
        if (nextSelectedPath) {
          setSelectedPath(nextSelectedPath)
        }
      })
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载 skills 目录失败')
    } finally {
      setLoadingTree(false)
    }
  }

  function toggleExpanded(path: string) {
    setExpandedPaths((current) => {
      if (current.includes(path)) {
        return current.filter((item) => item !== path)
      }
      return [...current, path]
    })
  }

  async function saveFile() {
    if (!selectedFile) {
      return
    }
    try {
      setSaving(true)
      const saved = await updateSkillFile(selectedFile.path, draftContent)
      setSelectedFile(saved)
      setDraftContent(saved.content)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存 skill 文件失败')
    } finally {
      setSaving(false)
    }
  }

  async function createPackage() {
    if (!newPackageName.trim()) {
      setError('skill package name 不能为空')
      return
    }
    try {
      setCreating(true)
      const created = await createSkillPackage({
        name: newPackageName,
        description: newPackageDescription,
        domain: newPackageDomain,
      })
      setShowCreateForm(false)
      setNewPackageName('')
      setNewPackageDescription('')
      setNewPackageDomain('')
      await loadTree(created.skillPath)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建 skill package 失败')
    } finally {
      setCreating(false)
    }
  }

  const selectedFileName = selectedFile?.path.split('/').pop() || ''
  const isMarkdown = selectedFileName.endsWith('.md')
  const fileContent = renderFileContent({
    draftContent,
    isMarkdown,
    parsedContent: parsedFile.content,
    previewMode,
    setDraftContent,
  })

  return (
    <div className="grid min-h-[760px] gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <aside className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-2.5 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.94)] lg:flex lg:min-h-0 lg:flex-col lg:overflow-hidden">
        <div className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Skills</div>
              <h2 className="mt-2 text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">Skills 工作台</h2>
              <div className="mt-2 text-sm text-[#87867f] dark:text-[#b0aea5]">左侧维护 skill package 文件树，右侧打开查看与编辑。</div>
            </div>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#c96442] bg-[#c96442] text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]"
              onClick={() => setShowCreateForm((current) => !current)}
              type="button"
            >
              <PlusIcon />
            </button>
          </div>

          <div className="mt-3 rounded-[14px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 text-xs text-[#87867f] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5]">
            <div className="font-semibold uppercase tracking-[0.18em]">Root</div>
            <div className="mt-2 break-all font-mono">{rootPath || '加载中...'}</div>
          </div>

          {showCreateForm ? (
            <div className="mt-3 space-y-3 rounded-[14px] border border-[#e8e6dc] bg-[#f5f4ed] p-3 dark:border-[#30302e] dark:bg-[#1d1c1a]">
              <label className="block">
                <div className="mb-1 text-[11px] uppercase tracking-[0.18em] text-[#87867f] dark:text-[#b0aea5]">Package Name</div>
                <input
                  className="w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5]"
                  onChange={(event) => setNewPackageName(event.target.value)}
                  placeholder="auction-popcard"
                  type="text"
                  value={newPackageName}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-[11px] uppercase tracking-[0.18em] text-[#87867f] dark:text-[#b0aea5]">Description</div>
                <input
                  className="w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5]"
                  onChange={(event) => setNewPackageDescription(event.target.value)}
                  placeholder="描述这个 skill 在什么场景下使用"
                  type="text"
                  value={newPackageDescription}
                />
              </label>
              <label className="block">
                <div className="mb-1 text-[11px] uppercase tracking-[0.18em] text-[#87867f] dark:text-[#b0aea5]">Domain</div>
                <input
                  className="w-full rounded-[12px] border border-[#e8e6dc] bg-[#faf9f5] px-3 py-2 text-sm text-[#141413] outline-none transition placeholder:text-[#87867f] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5]"
                  onChange={(event) => setNewPackageDomain(event.target.value)}
                  placeholder="auction_pop_card"
                  type="text"
                  value={newPackageDomain}
                />
              </label>
              <div className="flex gap-2">
                <button
                  className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={creating}
                  onClick={() => void createPackage()}
                  type="button"
                >
                  {creating ? '创建中...' : '创建 package'}
                </button>
                <button
                  className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
                  onClick={() => setShowCreateForm(false)}
                  type="button"
                >
                  收起
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="mt-3 flex items-center justify-between px-1">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">文件浏览器</div>
          <div className="text-xs text-stone-500 dark:text-stone-400">{flattenFiles(nodes).length} 文件</div>
        </div>

        <div className="mt-2 lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:pr-1">
          {loadingTree ? (
            <SidebarMessage>正在加载 skills 目录...</SidebarMessage>
          ) : nodes.length === 0 ? (
            <SidebarMessage>当前还没有 skill package，先创建一个。</SidebarMessage>
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

      {!selectedFile ? (
        <PanelMessage>{loadingFile ? '正在加载文件...' : '先从左侧选择一个 skill 文件。'}</PanelMessage>
      ) : (
        <section className="min-w-0 rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.92),0_4px_24px_rgba(20,20,19,0.05)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#e8e6dc] pb-4 dark:border-[#30302e]">
            <div className="min-w-0 flex-1">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Skill File</div>
              <h3 className="mt-2 truncate text-[32px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]" title={selectedFile.path}>
                {selectedFileName}
              </h3>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
                <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 font-mono dark:border-[#30302e] dark:bg-[#232220]">{selectedFile.path}</span>
                <span className="rounded-full border border-[#d1cfc5] bg-[#f5f4ed] px-3 py-1 dark:border-[#30302e] dark:bg-[#232220]">{countLines(draftContent)} 行</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-[14px] bg-[#e8e6dc] p-1 shadow-[0_0_0_1px_rgba(209,207,197,0.9)] dark:bg-[#30302e] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]">
                <ToggleButton active={previewMode === 'rendered'} label="预览" onClick={() => setPreviewMode('rendered')} />
                <ToggleButton active={previewMode === 'source'} label="源码" onClick={() => setPreviewMode('source')} />
              </div>
              <button
                className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={saving}
                onClick={() => void saveFile()}
                type="button"
              >
                {saving ? '保存中...' : '保存'}
              </button>
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
            {fileContent}
          </div>
        </section>
      )}
    </div>
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
    <section className="mt-4 rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.96)]">
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
          <pre className="overflow-auto rounded-[16px] border border-[#e8e6dc] bg-[#141413] px-4 py-4 font-mono text-xs leading-6 text-[#faf9f5] shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:border-[#30302e]">
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

function renderFileContent({
  draftContent,
  isMarkdown,
  parsedContent,
  previewMode,
  setDraftContent,
}: {
  draftContent: string
  isMarkdown: boolean
  parsedContent: string
  previewMode: PreviewMode
  setDraftContent: (value: string) => void
}) {
  if (previewMode === 'source') {
    return (
      <textarea
        className="min-h-[620px] w-full resize-y rounded-[18px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-4 font-mono text-xs leading-6 text-[#141413] outline-none transition focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#141413] dark:text-[#faf9f5] dark:focus:border-[#3898ec]"
        onChange={(event) => setDraftContent(event.target.value)}
        value={draftContent}
      />
    )
  }
  if (isMarkdown) {
    return (
      <div className="overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#fdfcf9] px-5 py-5 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#171615] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
        <MarkdownPreview content={parsedContent || '暂无内容'} />
      </div>
    )
  }
  return (
    <pre className="overflow-auto rounded-[18px] border border-[#e8e6dc] bg-[#141413] px-4 py-4 font-mono text-xs leading-6 text-[#faf9f5] shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:border-[#30302e]">
      <code>{draftContent || '暂无内容'}</code>
    </pre>
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

function collectDirectoryPaths(nodes: SkillTreeNode[]): string[] {
  const paths: string[] = []
  for (const node of nodes) {
    if (node.nodeType === 'directory') {
      paths.push(node.path)
      paths.push(...collectDirectoryPaths(node.children))
    }
  }
  return paths
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 16 16">
      <path d="M8 3.333v9.334M3.333 8h9.334" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </svg>
  )
}
