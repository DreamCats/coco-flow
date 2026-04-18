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
