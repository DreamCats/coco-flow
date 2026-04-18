const supplementHeading = '## 研发补充说明'

export function composeCreateTaskInput(source: string, supplement: string) {
  const normalizedSource = source.trim()
  const normalizedSupplement = supplement.trim()
  if (!normalizedSupplement) {
    return normalizedSource
  }
  return `${normalizedSource}\n\n${supplementHeading}\n\n${normalizedSupplement}\n`
}

export function extractSourceSections(artifactContent: string) {
  const content = artifactContent.split('\n---\n', 2)[1] ?? artifactContent
  const [source, supplement] = content.split(supplementHeading, 2)
  return {
    source: source.trim(),
    supplement: supplement?.trim() ?? '',
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
    bodyLines.push('', supplementHeading, '', normalizedSupplement)
  }
  const nextBody = bodyLines.join('\n').trim()
  if (!originalBody) {
    return `${nextBody}\n`
  }
  return `${header.trimEnd()}\n\n---\n\n${nextBody}\n`
}
