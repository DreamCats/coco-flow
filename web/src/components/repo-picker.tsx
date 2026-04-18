import { useEffect, useMemo, useState } from 'react'
import {
  listRecentRepos,
  listRemoteDirs,
  listRemoteRoots,
  validateRepo,
  type RemoteDirEntry,
  type RepoCandidate,
} from '../api'

export function RepoPicker({
  selectedRepos,
  onChange,
}: {
  selectedRepos: RepoCandidate[]
  onChange: (repos: RepoCandidate[]) => void
}) {
  const [recentRepos, setRecentRepos] = useState<RepoCandidate[]>([])
  const [manualPath, setManualPath] = useState('')
  const [loadingRecent, setLoadingRecent] = useState(true)
  const [loadingBrowser, setLoadingBrowser] = useState(true)
  const [pickerError, setPickerError] = useState('')
  const [validating, setValidating] = useState(false)
  const [query, setQuery] = useState('')
  const [browserPath, setBrowserPath] = useState('')
  const [parentPath, setParentPath] = useState('')
  const [entries, setEntries] = useState<RemoteDirEntry[]>([])

  useEffect(() => {
    let cancelled = false
    async function loadInitial() {
      try {
        const [recent, rootList] = await Promise.all([listRecentRepos(), listRemoteRoots()])
        if (cancelled) {
          return
        }
        setRecentRepos(recent)
        const homeRoot = rootList.find((root) => root.label.toLowerCase() === 'home')
        const initialPath = homeRoot?.path || rootList[0]?.path || recent[0]?.path || ''
        if (initialPath) {
          await loadBrowser(initialPath, cancelled)
        } else {
          setLoadingBrowser(false)
        }
      } catch {
        if (!cancelled) {
          setRecentRepos([])
          setLoadingBrowser(false)
        }
      } finally {
        if (!cancelled) {
          setLoadingRecent(false)
        }
      }
    }
    void loadInitial()
    return () => {
      cancelled = true
    }
  }, [])

  const selectedPaths = useMemo(() => new Set(selectedRepos.map((repo) => repo.path)), [selectedRepos])

  const filteredRecent = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return recentRepos.filter((repo) => {
      if (selectedPaths.has(repo.path)) {
        return false
      }
      if (!keyword) {
        return true
      }
      return (
        repo.displayName.toLowerCase().includes(keyword) ||
        repo.id.toLowerCase().includes(keyword) ||
        repo.path.toLowerCase().includes(keyword)
      )
    })
  }, [query, recentRepos, selectedPaths])

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
      setLoadingBrowser(true)
      setPickerError('')
      const response = await listRemoteDirs(path)
      if (cancelled) {
        return
      }
      setBrowserPath(response.path)
      setParentPath(response.parentPath)
      setEntries(response.entries)
    } catch (err) {
      if (!cancelled) {
        setPickerError(err instanceof Error ? err.message : '加载远程目录失败')
      }
    } finally {
      if (!cancelled) {
        setLoadingBrowser(false)
      }
    }
  }

  async function addManualRepo() {
    try {
      setValidating(true)
      setPickerError('')
      const repo = await validateRepo(manualPath)
      if (selectedPaths.has(repo.path)) {
        setPickerError('该 repo 已加入列表')
        return
      }
      onChange([...selectedRepos, repo])
      setManualPath('')
      await loadBrowser(repo.path)
    } catch (err) {
      setPickerError(err instanceof Error ? err.message : '添加 repo 失败')
    } finally {
      setValidating(false)
    }
  }

  function addRepo(repo: RepoCandidate) {
    if (selectedPaths.has(repo.path)) {
      return
    }
    onChange([...selectedRepos, repo])
  }

  function addBrowserRepo(entry: RemoteDirEntry) {
    addRepo({
      id: entry.name,
      displayName: entry.name,
      path: entry.path,
    })
  }

  function removeRepo(path: string) {
    onChange(selectedRepos.filter((repo) => repo.path !== path))
  }

  return (
    <div className="space-y-4">
      <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">已选仓库</div>

      <div className="space-y-2">
        {selectedRepos.length > 0 ? (
          selectedRepos.map((repo) => (
            <div
              className="flex items-start justify-between gap-3 rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 shadow-[0_0_0_1px_rgba(240,238,230,0.88)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]"
              key={repo.path}
            >
              <div className="min-w-0">
                <div className="text-[17px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{repo.displayName}</div>
                <div className="mt-1 break-all font-mono text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{repo.path}</div>
              </div>
              <button
                className="rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-1.5 text-xs text-[#4d4c48] transition hover:bg-[#ddd9cc] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
                onClick={() => removeRepo(repo.path)}
                type="button"
              >
                移除
              </button>
            </div>
          ))
        ) : (
          <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-4 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
            还没有选择仓库。可以从最近使用中挑选，或在右侧浏览服务器目录。
          </div>
        )}
      </div>

      {pickerError ? <div className="text-sm text-[#b53333]">{pickerError}</div> : null}

      <div className="grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
        <section className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">最近使用</div>
            <input
              className="w-44 rounded-[12px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-2 text-xs text-[#5e5d59] outline-none shadow-[0_0_0_1px_rgba(240,238,230,0.86)] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索仓库"
              type="text"
              value={query}
            />
          </div>
          <div className="mt-3 space-y-2">
            {loadingRecent ? (
              <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-3 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                正在加载最近使用的仓库...
              </div>
            ) : filteredRecent.length > 0 ? (
              filteredRecent.map((repo) => (
                <button
                  className={`flex w-full items-start justify-between gap-3 rounded-[18px] border px-3 py-3 text-left transition ${
                    selectedPaths.has(repo.path)
                      ? 'border-[#ccd6c8] bg-[#f3f7f1] dark:border-[#425142] dark:bg-[#263126]'
                      : 'border-[#e8e6dc] bg-[#f5f4ed] shadow-[0_0_0_1px_rgba(240,238,230,0.84)] hover:bg-[#efede4] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:hover:bg-[#2a2927]'
                  }`}
                  key={repo.path}
                  onClick={() => addRepo(repo)}
                  type="button"
                >
                  <div className="min-w-0">
                    <div className="text-[17px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{repo.displayName}</div>
                    <div className="mt-1 break-all font-mono text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{repo.path}</div>
                  </div>
                  <div className="shrink-0 text-right text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">
                    {repo.taskCount ? `${repo.taskCount} 个任务` : '最近使用'}
                    {repo.lastSeenAt ? <div className="mt-1 normal-case tracking-normal">{repo.lastSeenAt}</div> : null}
                  </div>
                </button>
              ))
            ) : (
              <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-3 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                {query ? '没有找到匹配的仓库。' : '暂时还没有最近使用的仓库。'}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-[18px] border border-[#e8e6dc] bg-[#faf9f5] p-4 shadow-[0_0_0_1px_rgba(240,238,230,0.9)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
          <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">远程目录</div>

          <div className="mt-3 rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 shadow-[0_0_0_1px_rgba(240,238,230,0.86)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
            <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">当前位置</div>
            <div className="mt-2 break-all font-mono text-xs text-[#5e5d59] dark:text-[#b0aea5]">{browserPath || '-'}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {breadcrumbs.map((item) => (
                <button
                  className={`rounded-[12px] border px-3 py-2 text-xs transition ${
                    browserPath === item.path
                      ? 'border-[#c96442] bg-[#fff7f2] text-[#c96442] shadow-[0_0_0_1px_rgba(201,100,66,0.18)] dark:border-[#d97757] dark:bg-[#3a2620] dark:text-[#f0c0b0]'
                      : 'border-[#e8e6dc] bg-[#faf9f5] text-[#5e5d59] hover:text-[#141413] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                  }`}
                  key={item.path}
                  onClick={() => void loadBrowser(item.path)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <button
                className="rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-2 text-xs text-[#4d4c48] transition hover:bg-[#ddd9cc] disabled:cursor-not-allowed disabled:opacity-50 dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5] dark:hover:bg-[#3a3937]"
                disabled={!parentPath}
                onClick={() => void loadBrowser(parentPath)}
                type="button"
              >
                上一级
              </button>
            </div>
          </div>

          <div className="mt-3 flex gap-2">
            <input
              className="min-w-0 flex-1 rounded-[12px] border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-3 font-mono text-sm text-[#141413] outline-none shadow-[0_0_0_1px_rgba(240,238,230,0.86)] focus:border-[#3898ec] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)] dark:placeholder:text-[#87867f] dark:focus:border-[#3898ec]"
              onChange={(event) => setManualPath(event.target.value)}
              placeholder="输入仓库路径"
              type="text"
              value={manualPath}
            />
            <button
              className="rounded-[12px] border border-[#c96442] bg-[#c96442] px-4 py-3 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757] disabled:cursor-not-allowed disabled:opacity-60"
              disabled={validating || !manualPath.trim()}
              onClick={() => void addManualRepo()}
              type="button"
            >
              {validating ? '校验中...' : '校验并加入'}
            </button>
          </div>
          <div className="mt-2 text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">
            这里浏览的是运行 `coco-ext ui serve` 那台机器上的目录。
          </div>

          <div className="mt-4 max-h-72 space-y-2 overflow-y-auto pr-1">
            {loadingBrowser ? (
              <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-3 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                正在加载目录...
              </div>
            ) : entries.length > 0 ? (
              entries.map((entry) => (
                <div
                  className={`flex items-center justify-between gap-3 rounded-[18px] border px-3 py-3 ${
                    selectedPaths.has(entry.path)
                      ? 'border-[#ccd6c8] bg-[#f3f7f1] dark:border-[#425142] dark:bg-[#263126]'
                      : 'border-[#e8e6dc] bg-[#f5f4ed] shadow-[0_0_0_1px_rgba(240,238,230,0.84)] dark:border-[#30302e] dark:bg-[#232220] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]'
                  }`}
                  key={entry.path}
                >
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => void loadBrowser(entry.path)}
                    type="button"
                  >
                    <div className="text-[17px] leading-[1.2] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">{entry.name}</div>
                    <div className="mt-1 break-all font-mono text-xs leading-5 text-[#87867f] dark:text-[#b0aea5]">{entry.path}</div>
                  </button>
                  {entry.isGitRepo ? (
                    <button
                      className="shrink-0 rounded-[12px] border border-[#c96442] bg-[#c96442] px-3 py-2 text-xs text-[#faf9f5] transition hover:bg-[#d97757]"
                      onClick={() => addBrowserRepo(entry)}
                      type="button"
                    >
                      加入
                    </button>
                  ) : (
                    <div className="shrink-0 rounded-[12px] border border-[#d1cfc5] bg-[#e8e6dc] px-3 py-2 text-[10px] uppercase tracking-[0.5px] text-[#4d4c48] dark:border-[#30302e] dark:bg-[#30302e] dark:text-[#faf9f5]">
                      目录
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="rounded-[16px] border border-dashed border-[#d1cfc5] bg-[#f5f4ed] px-3 py-4 text-sm text-[#87867f] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
                当前目录下没有可用子目录。
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
