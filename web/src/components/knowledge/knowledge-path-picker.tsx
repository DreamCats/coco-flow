import { useEffect, useMemo, useState } from 'react'
import { listRemoteDirs, listRemoteRoots, validateRepo, type RemoteDirEntry, type RemoteRoot, type RepoCandidate } from '../../api'

type KnowledgePathPickerProps = {
  open: boolean
  selectedPaths: string[]
  onAddPath: (repo: RepoCandidate) => void
  onClose: () => void
}

export function KnowledgePathPicker({ open, selectedPaths, onAddPath, onClose }: KnowledgePathPickerProps) {
  const [roots, setRoots] = useState<RemoteRoot[]>([])
  const [browserPath, setBrowserPath] = useState('')
  const [parentPath, setParentPath] = useState('')
  const [entries, setEntries] = useState<RemoteDirEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [candidate, setCandidate] = useState<RepoCandidate | null>(null)
  const [validating, setValidating] = useState(false)

  useEffect(() => {
    if (!open) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        setLoading(true)
        setError('')
        const rootList = (await listRemoteRoots()).filter((root) => root.label.toLowerCase() !== 'cwd')
        if (cancelled) {
          return
        }
        setRoots(rootList)
        const initialPath = rootList[0]?.path || ''
        if (initialPath) {
          await loadBrowser(initialPath, cancelled)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载路径失败')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
      setCandidate(null)
    }
  }, [open])

  const breadcrumbs = useMemo(() => {
    if (!browserPath) {
      return []
    }
    const normalized = browserPath.replace(/\/+$/, '') || '/'
    const parts = normalized.split('/').filter(Boolean)
    if (parts.length === 0) {
      return [{ label: '/', path: '/' }]
    }
    const items: Array<{ label: string; path: string }> = [{ label: '/', path: '/' }]
    let current = ''
    for (const part of parts) {
      current += `/${part}`
      items.push({ label: part, path: current })
    }
    return items
  }, [browserPath])

  async function loadBrowser(path: string, cancelled = false) {
    try {
      setLoading(true)
      setError('')
      const response = await listRemoteDirs(path)
      if (cancelled) {
        return
      }
      setBrowserPath(response.path)
      setParentPath(response.parentPath)
      setEntries(response.entries)
    } catch (err) {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : '加载目录失败')
      }
    } finally {
      if (!cancelled) {
        setLoading(false)
      }
    }
  }

  async function selectRepo(path: string) {
    try {
      setValidating(true)
      setError('')
      const repo = await validateRepo(path)
      setCandidate(repo)
    } catch (err) {
      setError(err instanceof Error ? err.message : '选择路径失败')
    } finally {
      setValidating(false)
    }
  }

  function commitSelection(closeAfterCommit: boolean) {
    if (!candidate) {
      return
    }
    if (!selectedPaths.includes(candidate.path)) {
      onAddPath(candidate)
    }
    if (closeAfterCommit) {
      onClose()
      return
    }
    setCandidate(null)
  }

  if (!open) {
    return null
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-[rgba(20,20,19,0.48)] p-4 backdrop-blur-sm">
      <div className="max-h-[min(820px,calc(100vh-32px))] w-full max-w-[900px] overflow-hidden rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_24px_80px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a]">
        <div className="border-b border-[#e8e6dc] px-5 py-4 dark:border-[#30302e]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Path Picker</div>
              <h4 className="mt-2 text-[28px] leading-[1.15] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">选择路径</h4>
            </div>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#e8e6dc] text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
              onClick={onClose}
              type="button"
            >
              ×
            </button>
          </div>
        </div>

        <div className="grid gap-0 md:grid-cols-[0.9fr_1.1fr]">
          <section className="border-b border-[#e8e6dc] px-5 py-4 md:border-r md:border-b-0 dark:border-[#30302e]">
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">已选路径</div>
            <div className="mt-3 space-y-2">
              {selectedPaths.length === 0 ? (
                <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-4 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                  还没有选择路径。
                </div>
              ) : (
                selectedPaths.map((path) => (
                  <div
                    className="rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 font-mono text-xs leading-5 text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]"
                    key={path}
                  >
                    {path}
                  </div>
                ))
              )}
            </div>

            <div className="mt-5 text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">候选路径</div>
            <div className="mt-3 rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 dark:border-[#30302e] dark:bg-[#232220]">
              {candidate ? (
                <>
                  <div className="text-sm font-semibold text-[#141413] dark:text-[#faf9f5]">{candidate.displayName}</div>
                  <div className="mt-1 break-all font-mono text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{candidate.path}</div>
                </>
              ) : (
                <div className="text-sm text-[#87867f] dark:text-[#b0aea5]">先从右侧目录中选择一个 git 仓库路径。</div>
              )}
            </div>
          </section>

          <section className="px-5 py-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">远程目录</div>
              <div className="flex flex-wrap gap-2">
                {roots.map((root) => (
                  <button
                    className={`rounded-[12px] border px-3 py-2 text-xs uppercase tracking-[0.5px] transition ${
                      browserPath === root.path
                        ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
                        : 'border-[#d1cfc5] bg-[#e8e6dc] text-[#4d4c48] hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]'
                    }`}
                    key={root.path}
                    onClick={() => void loadBrowser(root.path)}
                    type="button"
                  >
                    {root.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-[#87867f] dark:text-[#b0aea5]">
              {breadcrumbs.map((crumb, index) => (
                <button
                  className="rounded-[10px] px-2 py-1 hover:bg-[#f5f4ed] dark:hover:bg-[#232220]"
                  key={`${crumb.path}-${index}`}
                  onClick={() => void loadBrowser(crumb.path)}
                  type="button"
                >
                  {crumb.label}
                </button>
              ))}
              {browserPath && parentPath && parentPath !== browserPath ? (
                <button
                  className="rounded-[10px] border border-[#e8e6dc] px-2 py-1 text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
                  onClick={() => void loadBrowser(parentPath)}
                  type="button"
                >
                  返回上级
                </button>
              ) : null}
            </div>

            {error ? <div className="mt-3 text-sm text-[#b53333]">{error}</div> : null}

            <div className="mt-4 max-h-[420px] overflow-y-auto space-y-2 pr-1">
              {loading ? (
                <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-4 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                  正在加载目录...
                </div>
              ) : entries.length === 0 ? (
                <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-4 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                  当前目录下没有可用子目录。
                </div>
              ) : (
                entries.map((entry) => (
                  <div
                    className="flex items-start justify-between gap-3 rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 shadow-[0_0_0_1px_rgba(240,238,230,0.84)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]"
                    key={entry.path}
                  >
                    <button className="min-w-0 text-left" onClick={() => void loadBrowser(entry.path)} type="button">
                      <div className="text-[16px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{entry.name}</div>
                      <div className="mt-1 break-all font-mono text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{entry.path}</div>
                    </button>
                    <div className="shrink-0">
                      {entry.isGitRepo ? (
                        <button
                          className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-3 py-2 text-xs font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:opacity-50"
                          disabled={validating}
                          onClick={() => void selectRepo(entry.path)}
                          type="button"
                        >
                          选中
                        </button>
                      ) : (
                        <span className="rounded-[12px] border border-[#e8e6dc] px-3 py-2 text-[11px] uppercase tracking-[0.18em] text-[#87867f] dark:border-[#30302e] dark:text-[#b0aea5]">
                          目录
                        </span>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#e8e6dc] px-5 py-4 dark:border-[#30302e]">
          <button
            className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
            onClick={onClose}
            type="button"
          >
            取消
          </button>
          <div className="flex flex-wrap gap-3">
            <button
              className="rounded-[12px] border border-[#e8e6dc] px-4 py-2 text-sm text-[#5e5d59] transition hover:text-[#141413] disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#30302e] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]"
              disabled={!candidate}
              onClick={() => commitSelection(false)}
              type="button"
            >
              选择下一个
            </button>
            <button
              className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-2 text-sm font-semibold text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!candidate}
              onClick={() => commitSelection(true)}
              type="button"
            >
              完成选择
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
