import type { TaskRecord } from '../../../api'
import { useMemo, useState } from 'react'
import { extractSourceSections } from '../content'
import { ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

export function InputStage({ task }: { task: TaskRecord }) {
  const [tab, setTab] = useState<'artifact' | 'notes'>('artifact')
  const sections = useMemo(() => extractSourceSections(task.artifacts['prd.source.md'] || ''), [task.artifacts])

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
          <ArtifactPanel content={sections.source || task.artifacts['prd.source.md'] || ''} title="prd.source.md" />
        ) : (
          <NotePanel content={sections.supplement || '当前没有额外补充说明。'} />
        )}
      </div>
    </SectionCard>
  )
}
