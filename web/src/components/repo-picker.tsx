import { useEffect, useMemo, useState } from 'react'
import {
  listRecentRepos,
  listRemoteDirs,
  listRemoteRoots,
  validateRepo,
  type RemoteDirEntry,
  type RemoteRoot,
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
  const [roots, setRoots] = useState<RemoteRoot[]>([])
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
        setRoots(rootList)
        const initialPath = recent[0]?.path || rootList[0]?.path || ''
        if (initialPath) {
          await loadBrowser(initialPath, cancelled)
        } else {
          setLoadingBrowser(false)
        }
      } catch {
        if (!cancelled) {
          setRecentRepos([])
          setRoots([])
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
      <div className="text-xs font-semibold uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">已选仓库</div>

      <div className="space-y-2">
        {selectedRepos.length > 0 ? (
          selectedRepos.map((repo) => (
            <div
              className="flex items-start justify-between gap-3 rounded-[18px] border border-stone-200 bg-stone-50 px-3 py-3 dark:border-white/10 dark:bg-white/5"
              key={repo.path}
            >
              <div className="min-w-0">
                <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{repo.displayName}</div>
                <div className="mt-1 break-all font-mono text-xs leading-5 text-stone-500 dark:text-stone-400">{repo.path}</div>
              </div>
              <button
                className="rounded-full border border-stone-200 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500 transition hover:border-stone-300 hover:text-stone-900 dark:border-white/10 dark:text-stone-400 dark:hover:border-white/20 dark:hover:text-stone-100"
                onClick={() => removeRepo(repo.path)}
                type="button"
              >
                移除
              </button>
            </div>
          ))
        ) : (
          <div className="rounded-[18px] border border-dashed border-stone-300 bg-stone-50 px-4 py-4 text-sm text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
            还没有选择仓库。可以从最近使用中挑选，或在右侧浏览服务器目录。
          </div>
        )}
      </div>

      {pickerError ? <div className="text-sm text-rose-600">{pickerError}</div> : null}

      <div className="grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
        <section className="rounded-[20px] border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/6">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">最近使用</div>
            <input
              className="w-44 rounded-full border border-stone-200 px-3 py-2 text-xs text-stone-700 outline-none focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-200 dark:placeholder:text-stone-500 dark:focus:border-white/20"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索仓库"
              type="text"
              value={query}
            />
          </div>
          <div className="mt-3 space-y-2">
            {loadingRecent ? (
              <div className="rounded-[18px] border border-dashed border-stone-300 bg-stone-50 px-3 py-4 text-sm text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
                正在加载最近使用的仓库...
              </div>
            ) : filteredRecent.length > 0 ? (
              filteredRecent.map((repo) => (
                <button
                  className={`flex w-full items-start justify-between gap-3 rounded-[18px] border px-3 py-3 text-left transition ${
                    selectedPaths.has(repo.path)
                      ? 'border-emerald-300 bg-emerald-50/80 dark:border-emerald-300/30 dark:bg-emerald-400/10'
                      : 'border-stone-200 bg-stone-50 hover:border-stone-300 hover:bg-stone-100 dark:border-white/10 dark:bg-white/5 dark:hover:border-white/20 dark:hover:bg-white/10'
                  }`}
                  key={repo.path}
                  onClick={() => addRepo(repo)}
                  type="button"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{repo.displayName}</div>
                    <div className="mt-1 break-all font-mono text-xs leading-5 text-stone-500 dark:text-stone-400">{repo.path}</div>
                  </div>
                  <div className="shrink-0 text-right text-[11px] uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">
                    {repo.taskCount ? `${repo.taskCount} 个任务` : '最近使用'}
                    {repo.lastSeenAt ? <div className="mt-1 normal-case tracking-normal">{repo.lastSeenAt}</div> : null}
                  </div>
                </button>
              ))
            ) : (
              <div className="rounded-[18px] border border-dashed border-stone-300 bg-stone-50 px-3 py-4 text-sm text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
                {query ? '没有找到匹配的仓库。' : '暂时还没有最近使用的仓库。'}
              </div>
            )}
          </div>
        </section>

        <section className="rounded-[20px] border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">远程目录</div>
            <div className="flex flex-wrap gap-2">
              {roots.map((root) => (
                <button
                  className={`rounded-full border px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] transition ${
                    browserPath === root.path
                      ? 'border-stone-900 bg-stone-900 text-white dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
                      : 'border-stone-200 text-stone-500 hover:border-stone-300 hover:text-stone-900 dark:border-white/10 dark:text-stone-400 dark:hover:border-white/20 dark:hover:text-stone-100'
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

          <div className="mt-3 rounded-[18px] border border-stone-200 bg-stone-50 px-3 py-3 dark:border-white/10 dark:bg-white/5">
            <div className="text-[11px] uppercase tracking-[0.18em] text-stone-500 dark:text-stone-400">当前位置</div>
            <div className="mt-2 break-all font-mono text-xs text-stone-700 dark:text-stone-300">{browserPath || '-'}</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {breadcrumbs.map((item) => (
                <button
                  className={`rounded-full border px-3 py-2 text-xs transition ${
                    browserPath === item.path
                      ? 'border-stone-900 bg-stone-900 text-white dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
                      : 'border-stone-200 bg-white text-stone-600 hover:border-stone-300 hover:text-stone-900 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-300 dark:hover:border-white/20 dark:hover:text-stone-100'
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
                className="rounded-full border border-stone-200 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-500 transition hover:border-stone-300 hover:text-stone-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:text-stone-400 dark:hover:border-white/20 dark:hover:text-stone-100"
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
              className="min-w-0 flex-1 rounded-2xl border border-stone-200 px-3 py-3 font-mono text-sm text-stone-900 outline-none focus:border-stone-400 dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-200 dark:placeholder:text-stone-500 dark:focus:border-white/20"
              onChange={(event) => setManualPath(event.target.value)}
              placeholder="输入仓库路径"
              type="text"
              value={manualPath}
            />
            <button
              className="rounded-2xl bg-stone-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={validating || !manualPath.trim()}
              onClick={() => void addManualRepo()}
              type="button"
            >
              {validating ? '校验中...' : '校验并加入'}
            </button>
          </div>
          <div className="mt-2 text-xs leading-5 text-stone-500 dark:text-stone-400">
            这里浏览的是运行 `coco-ext ui serve` 那台机器上的目录。
          </div>

          <div className="mt-4 max-h-72 space-y-2 overflow-y-auto pr-1">
            {loadingBrowser ? (
              <div className="rounded-[18px] border border-dashed border-stone-300 bg-stone-50 px-3 py-4 text-sm text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
                正在加载目录...
              </div>
            ) : entries.length > 0 ? (
              entries.map((entry) => (
                <div
                  className={`flex items-center justify-between gap-3 rounded-[18px] border px-3 py-3 ${
                    selectedPaths.has(entry.path)
                      ? 'border-emerald-300 bg-emerald-50/80 dark:border-emerald-300/30 dark:bg-emerald-400/10'
                      : 'border-stone-200 bg-stone-50 dark:border-white/10 dark:bg-white/5'
                  }`}
                  key={entry.path}
                >
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => void loadBrowser(entry.path)}
                    type="button"
                  >
                    <div className="text-sm font-semibold text-stone-950 dark:text-stone-50">{entry.name}</div>
                    <div className="mt-1 break-all font-mono text-xs leading-5 text-stone-500 dark:text-stone-400">{entry.path}</div>
                  </button>
                  {entry.isGitRepo ? (
                    <button
                      className="shrink-0 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700 transition hover:border-emerald-300 hover:bg-emerald-100"
                      onClick={() => addBrowserRepo(entry)}
                      type="button"
                    >
                      加入
                    </button>
                  ) : (
                    <div className="shrink-0 rounded-full border border-stone-200 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500 dark:border-white/10 dark:text-stone-400">
                      目录
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="rounded-[18px] border border-dashed border-stone-300 bg-stone-50 px-3 py-4 text-sm text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
                当前目录下没有可用子目录。
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
