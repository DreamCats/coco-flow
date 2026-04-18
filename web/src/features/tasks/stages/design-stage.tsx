import type { TaskRecord } from '../../../api'
import { useState } from 'react'
import { ArtifactPanel, NotePanel, SectionCard, TabButton } from '../ui'

export function DesignStage({ task }: { task: TaskRecord }) {
  const [tab, setTab] = useState<'artifact' | 'notes'>('artifact')
  const notes = task.repos.length > 0 ? `已绑定仓库：${task.repos.map((repo) => repo.displayName).join('、')}` : '当前还没有绑定仓库。后续会补一版正式的仓库绑定服务。'

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
        {tab === 'artifact' ? <ArtifactPanel content={task.artifacts['design.md'] || ''} title="design.md" /> : <NotePanel content={notes} />}
      </div>
    </SectionCard>
  )
}
