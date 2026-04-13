export type DiffLineKind = 'context' | 'add' | 'delete' | 'meta'

export type ParsedDiffLine = {
  kind: DiffLineKind
  text: string
  oldLine: number | null
  newLine: number | null
}

export type ParsedDiffHunk = {
  header: string
  lines: ParsedDiffLine[]
}

export type ParsedDiffFile = {
  path: string
  rawLines: string[]
  additions: number
  deletions: number
  hunks: ParsedDiffHunk[]
}

export type ParsedPatch = {
  headerLines: string[]
  files: ParsedDiffFile[]
}

export type SplitDiffCell = {
  kind: DiffLineKind
  text: string
  lineNumber: number | null
}

export type SplitDiffRow = {
  left: SplitDiffCell
  right: SplitDiffCell
}

export type ContextBlock<T> =
  | { kind: 'items'; items: T[] }
  | { kind: 'collapsed'; hiddenCount: number; hiddenItems: T[]; visibleHead: T[]; visibleTail: T[] }

export function parsePatch(patch: string): ParsedPatch {
  if (!patch.trim()) {
    return { headerLines: [], files: [] }
  }

  const lines = patch.split('\n')
  const files: ParsedDiffFile[] = []
  const headerLines: string[] = []
  let currentFile: ParsedDiffFile | null = null
  let currentHunk: ParsedDiffHunk | null = null
  let oldLine = 0
  let newLine = 0

  for (const line of lines) {
    if (line.startsWith('diff --git ')) {
      if (currentFile) {
        files.push(currentFile)
      }
      currentFile = {
        path: extractDiffPath(line),
        rawLines: [line],
        additions: 0,
        deletions: 0,
        hunks: [],
      }
      currentHunk = null
      oldLine = 0
      newLine = 0
      continue
    }

    if (!currentFile) {
      headerLines.push(line)
      continue
    }

    currentFile.rawLines.push(line)

    if (line.startsWith('@@')) {
      currentHunk = { header: line, lines: [] }
      currentFile.hunks.push(currentHunk)
      const positions = extractHunkPositions(line)
      oldLine = positions.oldLine
      newLine = positions.newLine
      continue
    }

    if (!currentHunk) {
      continue
    }

    if (!line.startsWith('+++') && line.startsWith('+')) {
      currentFile.additions += 1
      currentHunk.lines.push({
        kind: 'add',
        text: line.slice(1),
        oldLine: null,
        newLine,
      })
      newLine += 1
      continue
    }

    if (!line.startsWith('---') && line.startsWith('-')) {
      currentFile.deletions += 1
      currentHunk.lines.push({
        kind: 'delete',
        text: line.slice(1),
        oldLine,
        newLine: null,
      })
      oldLine += 1
      continue
    }

    if (line.startsWith('\\ No newline at end of file')) {
      currentHunk.lines.push({
        kind: 'meta',
        text: line,
        oldLine: null,
        newLine: null,
      })
      continue
    }

    const contextText = line.startsWith(' ') ? line.slice(1) : line
    currentHunk.lines.push({
      kind: 'context',
      text: contextText,
      oldLine,
      newLine,
    })
    oldLine += 1
    newLine += 1
  }

  if (currentFile) {
    files.push(currentFile)
  }

  return { headerLines, files }
}

function extractDiffPath(line: string) {
  const parts = line.trim().split(' ')
  const bPath = parts[3] ?? ''
  if (bPath.startsWith('b/')) {
    return bPath.slice(2)
  }
  return bPath || 'unknown'
}

function extractHunkPositions(header: string) {
  const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(header)
  if (!match) {
    return { oldLine: 0, newLine: 0 }
  }

  return {
    oldLine: Number(match[1] ?? 0),
    newLine: Number(match[2] ?? 0),
  }
}

export function diffLineTone(kind: DiffLineKind) {
  if (kind === 'add') {
    return 'bg-emerald-500/12 text-emerald-200'
  }
  if (kind === 'delete') {
    return 'bg-rose-500/12 text-rose-200'
  }
  if (kind === 'meta') {
    return 'bg-sky-500/10 text-sky-200'
  }
  return 'text-stone-200'
}

export function buildSplitRows(lines: ParsedDiffLine[]): SplitDiffRow[] {
  const rows: SplitDiffRow[] = []

  for (let index = 0; index < lines.length; index += 1) {
    const current = lines[index]
    if (!current) {
      continue
    }

    if (current.kind === 'delete') {
      const next = lines[index + 1]
      if (next?.kind === 'add') {
        rows.push({
          left: buildSplitCell(current),
          right: buildSplitCell(next),
        })
        index += 1
        continue
      }

      rows.push({
        left: buildSplitCell(current),
        right: emptySplitCell(),
      })
      continue
    }

    if (current.kind === 'add') {
      rows.push({
        left: emptySplitCell(),
        right: buildSplitCell(current),
      })
      continue
    }

    const cell = buildSplitCell(current)
    rows.push({
      left: cell,
      right: cell,
    })
  }

  return rows
}

function buildSplitCell(line: ParsedDiffLine): SplitDiffCell {
  return {
    kind: line.kind,
    text: line.text,
    lineNumber: line.oldLine ?? line.newLine,
  }
}

function emptySplitCell(): SplitDiffCell {
  return {
    kind: 'context',
    text: '',
    lineNumber: null,
  }
}

export function collapseContextBlocks<T>(items: T[], isContext: (item: T) => boolean, visibleCount = 3): ContextBlock<T>[] {
  const blocks: ContextBlock<T>[] = []
  let index = 0

  for (; index < items.length; ) {
    if (!isContext(items[index]!)) {
      blocks.push({ kind: 'items', items: [items[index]!] })
      index += 1
      continue
    }

    let end = index
    for (; end < items.length && isContext(items[end]!); end += 1) {
      // continue
    }

    const contextItems = items.slice(index, end)
    if (contextItems.length <= visibleCount * 2 + 2) {
      blocks.push({ kind: 'items', items: contextItems })
    } else {
      blocks.push({
        kind: 'collapsed',
        hiddenCount: contextItems.length - visibleCount * 2,
        hiddenItems: contextItems.slice(visibleCount, -visibleCount),
        visibleHead: contextItems.slice(0, visibleCount),
        visibleTail: contextItems.slice(-visibleCount),
      })
    }
    index = end
  }

  return mergeAdjacentItemBlocks(blocks)
}

function mergeAdjacentItemBlocks<T>(blocks: ContextBlock<T>[]) {
  const merged: ContextBlock<T>[] = []
  for (const block of blocks) {
    const previous = merged[merged.length - 1]
    if (block.kind === 'items' && previous?.kind === 'items') {
      previous.items = previous.items.concat(block.items)
      continue
    }
    merged.push(block)
  }
  return merged
}
