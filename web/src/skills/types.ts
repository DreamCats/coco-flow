export type SkillTreeNode = {
  name: string
  path: string
  nodeType: 'directory' | 'file'
  children: SkillTreeNode[]
}

export type SkillTreeResponse = {
  rootPath: string
  sourceId: string
  nodes: SkillTreeNode[]
}

export type SkillFile = {
  path: string
  sourceId: string
  content: string
}

export type SkillSourceStatus = {
  id: string
  name: string
  sourceType: 'git'
  enabled: boolean
  url: string
  branch: string
  localPath: string
  status: string
  message: string
  isGitRepo: boolean
  currentBranch: string
  commit: string
  remoteUrl: string
  dirty: boolean
  ahead: number
  behind: number
  packageCount: number
}

export type SkillSourcesResponse = {
  sources: SkillSourceStatus[]
}

export type SkillSourceActionResponse = {
  source: SkillSourceStatus
  output: string
}
