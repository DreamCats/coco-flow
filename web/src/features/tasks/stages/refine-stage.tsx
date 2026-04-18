import type { TaskRecord } from '../../../api'
import { useState } from 'react'
import { ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

export function RefineStage({ task }: { task: TaskRecord }) {
  const [tab, setTab] = useState<'artifact' | 'notes'>('artifact')

  return (
    <SectionCard title="阶段详情">
      <div className="inline-flex rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
        <TabButton active={tab === 'artifact'} onClick={() => setTab('artifact')}>
          产物与查看
        </TabButton>
        <TabButton active={tab === 'notes'} onClick={() => setTab('notes')}>
          补充说明
        </TabButton>
      </div>
      <div className="mt-4">
        {tab === 'artifact' ? (
          <ArtifactPanel content={task.artifacts['prd-refined.md'] || ''} title="prd-refined.md" />
        ) : (
          <NotePanel content={task.artifacts['refine.log'] || task.nextAction || '当前没有额外说明。'} />
        )}
      </div>
    </SectionCard>
  )
}
