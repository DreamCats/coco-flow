export type SkillTreeNode = {
  name: string
  path: string
  nodeType: 'directory' | 'file'
  children: SkillTreeNode[]
}

export type SkillTreeResponse = {
  rootPath: string
  nodes: SkillTreeNode[]
}

export type SkillFile = {
  path: string
  content: string
}

export type SkillPackage = {
  name: string
  rootPath: string
  skillPath: string
}
