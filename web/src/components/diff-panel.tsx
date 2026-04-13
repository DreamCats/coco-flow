import { useDeferredValue, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { RepoResult } from '../api'
import { buildSplitRows, collapseContextBlocks, diffLineTone, parsePatch, type ParsedDiffFile, type DiffLineKind } from '../lib/diff'
import { FilterChip, KeyValue } from './ui-primitives'

export function DiffPanel({
  repos,
  selectedRepo,
  onSelectRepo,
}: {
  repos: RepoResult[]
  selectedRepo: string
  onSelectRepo: (repoId: string) => void
}) {
  const reposWithDiff = repos.filter((repo) => repo.diffSummary)
  const deferredSelectedRepo = useDeferredValue(selectedRepo)
  const activeRepo = reposWithDiff.find((repo) => repo.id === deferredSelectedRepo) ?? reposWithDiff[0]
  const parsedPatch = useMemo(() => parsePatch(activeRepo?.diffSummary?.patch ?? ''), [activeRepo?.diffSummary?.patch])
  const [viewMode, setViewMode] = useState<'split' | 'unified' | 'raw'>('split')
  const [selectedFile, setSelectedFile] = useState('')

  const fileButtons = useMemo(() => {
    if (parsedPatch.files.length > 0) {
      return parsedPatch.files
    }

    return (activeRepo?.diffSummary?.files ?? []).map<ParsedDiffFile>((path) => ({
      path,
      rawLines: [],
      additions: 0,
      deletions: 0,
      hunks: [],
    }))
  }, [activeRepo?.diffSummary?.files, parsedPatch.files])

  useEffect(() => {
    setSelectedFile(fileButtons[0]?.path ?? '')
  }, [activeRepo?.id, fileButtons])

  const activeFile = fileButtons.find((file) => file.path === selectedFile) ?? fileButtons[0]
  const unifiedAvailable = Boolean(activeFile?.hunks.length)
  const additionsValue = unifiedAvailable ? activeFile?.additions ?? 0 : activeRepo?.diffSummary?.additions ?? 0
  const deletionsValue = unifiedAvailable ? activeFile?.deletions ?? 0 : activeRepo?.diffSummary?.deletions ?? 0

  return (
    <section className="rounded-[24px] border border-stone-200 bg-white p-4 dark:border-white/10 dark:bg-white/6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500 dark:text-stone-400">变更对比</div>
          <h4 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950 dark:text-stone-50">提交差异回看</h4>
        </div>
        <div className="text-xs text-stone-500 dark:text-stone-400">按仓库查看本次提交的 patch</div>
      </div>

      {reposWithDiff.length === 0 ? (
        <div className="rounded-[18px] border border-dashed border-stone-300 bg-stone-50 px-4 py-6 text-sm leading-6 text-stone-500 dark:border-white/15 dark:bg-white/5 dark:text-stone-400">
          暂时还没有可查看的提交差异。生成提交后，这里会自动展示对应 patch。
        </div>
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            {reposWithDiff.map((repo) => (
              <button
                className={`rounded-full border px-3 py-2 text-sm font-medium transition ${
                  activeRepo?.id === repo.id
                    ? 'border-stone-900 bg-stone-900 text-white shadow-sm dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
                    : 'border-stone-200 bg-stone-50 text-stone-700 hover:border-stone-300 hover:bg-white dark:border-white/10 dark:bg-white/5 dark:text-stone-300 dark:hover:border-white/20 dark:hover:bg-white/10'
                }`}
                key={repo.id}
                onClick={() => onSelectRepo(repo.id)}
                type="button"
              >
                {repo.id}
              </button>
            ))}
          </div>

          {activeRepo?.diffSummary ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-2">
                <FilterChip label="文件数" value={`${fileButtons.length || activeRepo.diffSummary.files.length}`} />
                <FilterChip label="+ / -" value={`${additionsValue} / ${deletionsValue}`} />
              </div>

              <div className="rounded-[18px] border border-stone-200 bg-stone-50 px-3 py-3 dark:border-white/10 dark:bg-white/5">
                <div className="grid gap-3 md:grid-cols-4">
                  <KeyValue label="分支" mono value={activeRepo.diffSummary.branch || '-'} />
                  <KeyValue label="提交" mono value={activeRepo.diffSummary.commit || '-'} />
                  <KeyValue label="总新增" mono value={`${activeRepo.diffSummary.additions}`} />
                  <KeyValue label="总删除" mono value={`${activeRepo.diffSummary.deletions}`} />
                </div>
              </div>

              <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
                <div className="rounded-[18px] border border-stone-200 bg-white px-3 py-3 dark:border-white/10 dark:bg-white/5">
                  <div className="mb-2 text-[11px] uppercase tracking-[0.2em] text-stone-500 dark:text-stone-400">涉及文件</div>
                  <div className="space-y-2">
                    {fileButtons.map((file) => (
                      <button
                        className={`block w-full rounded-xl border px-3 py-2 text-left transition ${
                          activeFile?.path === file.path
                            ? 'border-stone-900 bg-stone-900 text-white dark:border-stone-100 dark:bg-stone-100 dark:text-stone-950'
                            : 'border-stone-200 bg-stone-50 text-stone-800 hover:border-stone-300 hover:bg-white dark:border-white/10 dark:bg-stone-950/70 dark:text-stone-200 dark:hover:border-white/20 dark:hover:bg-stone-900'
                        }`}
                        key={file.path}
                        onClick={() => setSelectedFile(file.path)}
                        type="button"
                      >
                        <div className="truncate font-mono text-xs">{file.path}</div>
                        <div className="mt-2 flex items-center gap-2 text-[11px]">
                          <span className="rounded-full bg-emerald-500/15 px-2 py-1 text-emerald-600 dark:text-emerald-300">
                            +{file.additions}
                          </span>
                          <span className="rounded-full bg-rose-500/15 px-2 py-1 text-rose-600 dark:text-rose-300">
                            -{file.deletions}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="overflow-hidden rounded-[18px] border border-stone-200 bg-[#0d1014] shadow-[0_12px_30px_rgba(17,24,39,0.08)]">
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 px-4 py-3 text-sm text-stone-300">
                    <div>
                      <div className="font-semibold text-stone-100">
                        {activeFile?.path ? `Diff · ${activeFile.path}` : '提交差异'}
                      </div>
                      <div className="mt-1 text-xs text-stone-500">优先展示当前文件的变更；需要时可切回原始 patch。</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                          viewMode === 'split'
                            ? 'bg-stone-100 text-stone-950'
                            : 'bg-white/5 text-stone-300 hover:bg-white/10'
                        }`}
                        onClick={() => setViewMode('split')}
                        type="button"
                      >
                        Split
                      </button>
                      <button
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                          viewMode === 'unified'
                            ? 'bg-stone-100 text-stone-950'
                            : 'bg-white/5 text-stone-300 hover:bg-white/10'
                        }`}
                        onClick={() => setViewMode('unified')}
                        type="button"
                      >
                        Unified
                      </button>
                      <button
                        className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                          viewMode === 'raw'
                            ? 'bg-stone-100 text-stone-950'
                            : 'bg-white/5 text-stone-300 hover:bg-white/10'
                        }`}
                        onClick={() => setViewMode('raw')}
                        type="button"
                      >
                        Raw Patch
                      </button>
                    </div>
                  </div>
                  <div className="max-h-[520px] overflow-auto">
                    {viewMode === 'split' ? (
                      unifiedAvailable && activeFile ? (
                        <SplitDiffView file={activeFile} />
                      ) : (
                        <div className="px-4 py-6 text-sm leading-6 text-stone-400">
                          当前产物里没有可解析的文件级 diff。你仍然可以切到 `Raw Patch` 查看原始内容。
                        </div>
                      )
                    ) : viewMode === 'unified' ? (
                      unifiedAvailable && activeFile ? (
                        <UnifiedDiffView file={activeFile} />
                      ) : (
                        <div className="px-4 py-6 text-sm leading-6 text-stone-400">
                          当前产物里没有可解析的文件级 diff。你仍然可以切到 `Raw Patch` 查看原始内容。
                        </div>
                      )
                    ) : (
                      <RawPatchView
                        lines={activeFile?.rawLines.length ? activeFile.rawLines : activeRepo.diffSummary.patch.split('\n')}
                        path={`diffs/${activeRepo.id}.patch`}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
  )
}

function SplitDiffView({ file }: { file: ParsedDiffFile }) {
  const [expandedBlocks, setExpandedBlocks] = useState<Record<string, boolean>>({})

  return (
    <div>
      <div className="grid grid-cols-2 border-b border-white/8 text-[11px] uppercase tracking-[0.18em] text-stone-500">
        <div className="grid grid-cols-[56px_16px_1fr] gap-3 border-r border-white/8 px-4 py-2">
          <span className="text-right">旧</span>
          <span />
          <span>Before</span>
        </div>
        <div className="grid grid-cols-[56px_16px_1fr] gap-3 px-4 py-2">
          <span className="text-right">新</span>
          <span />
          <span>After</span>
        </div>
      </div>
      {file.hunks.map((hunk, hunkIndex) => (
        <div className="border-b border-white/6 last:border-b-0" key={`${file.path}-${hunk.header}-${hunkIndex}`}>
          <div className="bg-sky-500/10 px-4 py-2 font-mono text-[11px] text-sky-200">{hunk.header}</div>
          {collapseContextBlocks(
            buildSplitRows(hunk.lines),
            (row) => row.left.kind === 'context' && row.right.kind === 'context',
          ).map((block, blockIndex) => {
            const blockKey = `${file.path}-${hunkIndex}-${blockIndex}`
            if (block.kind === 'items') {
              return renderSplitRows(block.items, blockKey)
            }

            if (expandedBlocks[blockKey]) {
              return (
                <ExpandedContextBlock
                  key={blockKey}
                  onCollapse={() => setExpandedBlocks((current) => ({ ...current, [blockKey]: false }))}
                >
                  {renderSplitRows([...block.visibleHead, ...block.hiddenItems, ...block.visibleTail], `${blockKey}-expanded`)}
                </ExpandedContextBlock>
              )
            }

            return (
              <div key={blockKey}>
                {renderSplitRows(block.visibleHead, `${blockKey}-head`)}
                <CollapsedContextRow hiddenCount={block.hiddenCount} onExpand={() => setExpandedBlocks((current) => ({ ...current, [blockKey]: true }))} />
                {renderSplitRows(block.visibleTail, `${blockKey}-tail`)}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function UnifiedDiffView({ file }: { file: ParsedDiffFile }) {
  const [expandedBlocks, setExpandedBlocks] = useState<Record<string, boolean>>({})

  return (
    <div>
      <div className="grid grid-cols-[64px_64px_16px_1fr] gap-3 border-b border-white/8 px-4 py-2 text-[11px] uppercase tracking-[0.18em] text-stone-500">
        <span className="text-right">旧</span>
        <span className="text-right">新</span>
        <span />
        <span>内容</span>
      </div>
      {file.hunks.map((hunk, hunkIndex) => (
        <div className="border-b border-white/6 last:border-b-0" key={`${file.path}-${hunk.header}-${hunkIndex}`}>
          <div className="bg-sky-500/10 px-4 py-2 font-mono text-[11px] text-sky-200">{hunk.header}</div>
          {collapseContextBlocks(hunk.lines, (line) => line.kind === 'context').map((block, blockIndex) => {
            const blockKey = `${file.path}-unified-${hunkIndex}-${blockIndex}`
            if (block.kind === 'items') {
              return renderUnifiedLines(block.items, blockKey)
            }

            if (expandedBlocks[blockKey]) {
              return (
                <ExpandedContextBlock
                  key={blockKey}
                  onCollapse={() => setExpandedBlocks((current) => ({ ...current, [blockKey]: false }))}
                >
                  {renderUnifiedLines([...block.visibleHead, ...block.hiddenItems, ...block.visibleTail], `${blockKey}-expanded`)}
                </ExpandedContextBlock>
              )
            }

            return (
              <div key={blockKey}>
                {renderUnifiedLines(block.visibleHead, `${blockKey}-head`)}
                <CollapsedContextRow hiddenCount={block.hiddenCount} onExpand={() => setExpandedBlocks((current) => ({ ...current, [blockKey]: true }))} />
                {renderUnifiedLines(block.visibleTail, `${blockKey}-tail`)}
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}

function UnifiedDiffLine({
  line,
}: {
  line: { kind: DiffLineKind; text: string; oldLine: number | null; newLine: number | null }
}) {
  return (
    <div className={`grid grid-cols-[64px_64px_16px_1fr] gap-3 px-4 py-1.5 text-[12px] leading-6 ${diffLineTone(line.kind)}`}>
      <span className="select-none text-right font-mono text-stone-500">{formatLineNumber(line.oldLine)}</span>
      <span className="select-none text-right font-mono text-stone-500">{formatLineNumber(line.newLine)}</span>
      <span className="select-none font-mono text-stone-500">{diffLineMarker(line.kind)}</span>
      <code className="whitespace-pre-wrap break-all">{line.text || ' '}</code>
    </div>
  )
}

function SplitCell({
  cell,
  side,
}: {
  cell: { kind: DiffLineKind; text: string; lineNumber: number | null }
  side: 'left' | 'right'
}) {
  const isEmpty = cell.lineNumber == null && cell.text === ''
  const sideBorder = side === 'left' ? 'border-r border-white/8' : ''
  const cellTone = splitCellTone(cell.kind, side)

  return (
    <div className={`grid grid-cols-[56px_16px_1fr] gap-3 px-4 py-1.5 text-[12px] leading-6 ${sideBorder} ${cellTone}`}>
      <span className="select-none text-right font-mono text-stone-500">{formatLineNumber(cell.lineNumber)}</span>
      <span className="select-none font-mono text-stone-500">
        {isEmpty ? '' : side === 'left' ? splitMarker(cell.kind, 'left') : splitMarker(cell.kind, 'right')}
      </span>
      <code className="whitespace-pre-wrap break-all">{isEmpty ? ' ' : cell.text || ' '}</code>
    </div>
  )
}

function RawPatchView({ lines, path }: { lines: string[]; path: string }) {
  return (
    <>
      <div className="flex items-center justify-end px-4 py-3 text-xs text-stone-500">
        <span className="font-mono">{path}</span>
      </div>
      <div className="border-t border-white/8 px-4 py-4 text-[12px] leading-6">
        {lines.map((line, index) => (
          <div className={`${rawPatchTone(line)} font-mono`} key={`${index}-${line}`}>
            <code>{line || ' '}</code>
          </div>
        ))}
      </div>
    </>
  )
}

function diffLineMarker(kind: 'context' | 'add' | 'delete' | 'meta') {
  if (kind === 'add') {
    return '+'
  }
  if (kind === 'delete') {
    return '-'
  }
  if (kind === 'meta') {
    return '@'
  }
  return ' '
}

function formatLineNumber(line: number | null) {
  return line == null ? '' : `${line}`
}

function rawPatchTone(line: string) {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff --git') || line.startsWith('@@')) {
    return 'text-sky-300'
  }
  if (line.startsWith('+')) {
    return 'text-emerald-300'
  }
  if (line.startsWith('-')) {
    return 'text-rose-300'
  }
  return 'text-stone-200'
}

function CollapsedContextRow({
  hiddenCount,
  onExpand,
}: {
  hiddenCount: number
  onExpand: () => void
}) {
  return (
    <button
      className="block w-full border-y border-white/6 bg-white/[0.03] px-4 py-2 text-left text-xs font-medium text-stone-400 transition hover:bg-white/[0.06] hover:text-stone-200"
      onClick={onExpand}
      type="button"
    >
      展开 {hiddenCount} 行未改内容
    </button>
  )
}

function ExpandedContextBlock({
  children,
  onCollapse,
}: {
  children: ReactNode
  onCollapse: () => void
}) {
  return (
    <>
      {children}
      <button
        className="block w-full border-y border-white/6 bg-white/[0.03] px-4 py-2 text-left text-xs font-medium text-stone-400 transition hover:bg-white/[0.06] hover:text-stone-200"
        onClick={onCollapse}
        type="button"
      >
        收起上下文
      </button>
    </>
  )
}

function renderSplitRows(
  rows: Array<{ left: { kind: DiffLineKind; text: string; lineNumber: number | null }; right: { kind: DiffLineKind; text: string; lineNumber: number | null } }>,
  keyPrefix: string,
) {
  return rows.map((row, rowIndex) => (
    <div className="grid grid-cols-2" key={`${keyPrefix}-${rowIndex}-${row.left.lineNumber}-${row.right.lineNumber}`}>
      <SplitCell side="left" cell={row.left} />
      <SplitCell side="right" cell={row.right} />
    </div>
  ))
}

function renderUnifiedLines(
  lines: Array<{ kind: DiffLineKind; text: string; oldLine: number | null; newLine: number | null }>,
  keyPrefix: string,
) {
  return lines.map((line, lineIndex) => <UnifiedDiffLine key={`${keyPrefix}-${lineIndex}-${line.oldLine}-${line.newLine}`} line={line} />)
}

function splitCellTone(kind: DiffLineKind, side: 'left' | 'right') {
  if (kind === 'delete' && side === 'left') {
    return 'bg-rose-500/12 text-rose-200'
  }
  if (kind === 'add' && side === 'right') {
    return 'bg-emerald-500/12 text-emerald-200'
  }
  if (kind === 'context') {
    return 'text-stone-200'
  }
  if (kind === 'meta') {
    return 'bg-sky-500/10 text-sky-200'
  }
  return 'bg-white/[0.03] text-stone-400'
}

function splitMarker(kind: DiffLineKind, side: 'left' | 'right') {
  if (kind === 'delete' && side === 'left') {
    return '-'
  }
  if (kind === 'add' && side === 'right') {
    return '+'
  }
  if (kind === 'meta') {
    return '@'
  }
  return ' '
}
