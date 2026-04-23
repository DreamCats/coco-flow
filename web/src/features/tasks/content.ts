const manualExtractHeading = '## 人工提炼范围'
const legacyManualExtractHeadings = ['## 研发补充说明']
const requiredManualExtractSectionTitles = ['本次范围', '人工提炼改动点'] as const
const manualExtractSectionBodies = {
  本次范围: '- [必填] 这次只做什么，先用一句话收敛范围。',
  人工提炼改动点: '- [必填] 按“场景 / 状态 / 改动”逐条列出服务端改动点。',
  明确不做: '- 如无可写：无',
  '前置条件 / 待确认项': '- 如有实验命中条件、接口依赖、跨端协同点，请写这里；如无可写：无',
} as const

export const manualExtractTemplate = [
  '## 本次范围',
  manualExtractSectionBodies.本次范围,
  '',
  '## 人工提炼改动点',
  manualExtractSectionBodies.人工提炼改动点,
  '',
  '## 明确不做',
  manualExtractSectionBodies.明确不做,
  '',
  '## 前置条件 / 待确认项',
  manualExtractSectionBodies['前置条件 / 待确认项'],
].join('\n')

export function composeCreateTaskInput(source: string, supplement: string) {
  const normalizedSource = source.trim()
  const normalizedSupplement = supplement.trim()
  if (!normalizedSupplement) {
    return normalizedSource
  }
  return `${normalizedSource}\n\n${manualExtractHeading}\n\n${normalizedSupplement}\n`
}

export function extractSourceSections(artifactContent: string) {
  const content = artifactContent.split('\n---\n', 2)[1] ?? artifactContent
  const split = splitSourceAndManualExtract(content)
  return {
    source: split.source.trim(),
    supplement: split.manualExtract.trim(),
  }
}

export function replaceSourceSections(
  artifactContent: string,
  next: {
    source: string
    supplement: string
  },
) {
  const [header, originalBody] = artifactContent.split('\n---\n', 2)
  const normalizedSource = next.source.trim()
  const normalizedSupplement = next.supplement.trim()
  const bodyLines = [normalizedSource]
  if (normalizedSupplement) {
    bodyLines.push('', manualExtractHeading, '', normalizedSupplement)
  }
  const nextBody = bodyLines.join('\n').trim()
  if (!originalBody) {
    return `${nextBody}\n`
  }
  return `${header.trimEnd()}\n\n---\n\n${nextBody}\n`
}

export function validateManualExtract(value: string) {
  const trimmed = value.trim()
  if (!trimmed) {
    return '人工提炼范围不能为空，请先按模板补齐“本次范围”和“人工提炼改动点”。'
  }
  const sections = parseManualExtractSections(trimmed)
  const missing = requiredManualExtractSectionTitles.filter((title) => !hasMeaningfulSectionContent(sections[title] ?? '', title))
  if (missing.length > 0) {
    return `人工提炼范围未填写完整，请至少补齐：${missing.join('、')}。`
  }
  return ''
}

export function hasValidManualExtract(value: string) {
  return validateManualExtract(value) === ''
}

function splitSourceAndManualExtract(content: string) {
  const matches = [manualExtractHeading, ...legacyManualExtractHeadings]
    .map((heading) => ({ heading, index: content.indexOf(heading) }))
    .filter((item) => item.index >= 0)
    .sort((left, right) => left.index - right.index)
  if (matches.length === 0) {
    return { source: content, manualExtract: '' }
  }
  const first = matches[0]!
  return {
    source: content.slice(0, first.index),
    manualExtract: content.slice(first.index + first.heading.length),
  }
}

function parseManualExtractSections(content: string) {
  const sections: Record<string, string[]> = {}
  let currentTitle = ''
  for (const rawLine of content.trim().split('\n')) {
    const line = rawLine.trimEnd()
    const matched = /^##\s+(.+?)\s*$/.exec(line.trim())
    if (matched) {
      currentTitle = matched[1]!.trim()
      sections[currentTitle] ||= []
      continue
    }
    if (!currentTitle) {
      continue
    }
    sections[currentTitle]!.push(line)
  }
  return Object.fromEntries(Object.entries(sections).map(([title, lines]) => [title, lines.join('\n').trim()]))
}

function hasMeaningfulSectionContent(body: string, title: keyof typeof manualExtractSectionBodies) {
  const entries = normalizeEntries(body)
  if (entries.length === 0) {
    return false
  }
  if (entries.every((entry) => ['无', '暂无', '待补充', 'todo', 'tbd', 'n/a', 'na'].includes(entry.toLowerCase()))) {
    return false
  }
  return JSON.stringify(entries) !== JSON.stringify(normalizeEntries(manualExtractSectionBodies[title]))
}

function normalizeEntries(body: string) {
  return body
    .split('\n')
    .map((line) => line.trim())
    .map((line) => line.replace(/^(?:[-*+]\s+|\d+\.\s+|\[\s?[xX]?\s?\]\s*)/, ''))
    .map((line) => line.replace(/^\[必填\]\s*/, ''))
    .filter(Boolean)
}
