import type { TaskRecord } from '../../../api'
import { useState } from 'react'
import { ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

export function ArchiveStage({ task }: { task: TaskRecord }) {
  const [tab, setTab] = useState<'artifact' | 'notes'>('artifact')
  const summary = task.status === 'archived' ? '任务已归档，可回看最终结果。' : task.status === 'coded' ? '当前可以进入归档收口。' : '当前还未进入归档阶段。'

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
        {tab === 'artifact' ? <ArtifactPanel content={summary} title="archive summary" /> : <NotePanel content={task.nextAction || summary} />}
      </div>
    </SectionCard>
  )
}
