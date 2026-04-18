import type { TaskRecord } from '../../../api'
import { useMemo, useState } from 'react'
import { ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

export function PlanStage({ task }: { task: TaskRecord }) {
  const [tab, setTab] = useState<'artifact' | 'notes' | 'graph'>('artifact')
  const graphContent = useMemo(() => buildPlanGraph(task), [task])

  return (
    <SectionCard title="阶段详情">
      <div className="inline-flex rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
        <TabButton active={tab === 'artifact'} onClick={() => setTab('artifact')}>
          产物与查看
        </TabButton>
        <TabButton active={tab === 'notes'} onClick={() => setTab('notes')}>
          补充说明
        </TabButton>
        <TabButton active={tab === 'graph'} onClick={() => setTab('graph')}>
          关系图
        </TabButton>
      </div>
      <div className="mt-4">
        {tab === 'artifact' ? (
          <ArtifactPanel content={task.artifacts['plan.md'] || ''} title="plan.md" />
        ) : tab === 'graph' ? (
          <ArtifactPanel content={graphContent} renderAs="plain" title="执行关系" />
        ) : (
          <NotePanel content={task.artifacts['plan.log'] || task.nextAction || '当前没有额外说明。'} renderAs="plain" />
        )}
      </div>
    </SectionCard>
  )
}

function buildPlanGraph(task: TaskRecord) {
  const repos = task.repos.map((repo) => repo.displayName)
  if (repos.length === 0) {
    return '当前没有仓库绑定，后续计划会在绑定仓库后补齐关系图。'
  }
  if (repos.length === 1) {
    return `${repos[0]}\n  ↓\n验证与收口`
  }
  return repos.map((repo, index) => (index === repos.length - 1 ? repo : `${repo}\n  ↓`)).join('\n')
}
