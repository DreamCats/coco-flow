import { stageOrder, stageTone, type TaskStage, type TaskStageID } from './model'

export function TaskStageTimeline({
  stages,
  activeStageID,
  onSelect,
}: {
  stages: TaskStage[]
  activeStageID: TaskStageID
  onSelect: (stageID: TaskStageID) => void
}) {
  return (
    <div className="mt-5 overflow-x-auto">
      <div className="inline-flex min-w-max items-center gap-1 rounded-[10px] border border-[#e8e6dc] bg-[#faf9f5] p-1 dark:border-[#30302e] dark:bg-[#232220]">
        {stageOrder.map((stageID, index) => {
          const stage = stages.find((item) => item.id === stageID)!
          const selected = stage.id === activeStageID
          return (
            <div className="flex items-center" key={stage.id}>
              <button
                className={`rounded-[8px] px-3 py-2 text-left transition ${
                  selected
                    ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                    : 'text-[#4d4c48] hover:bg-[#ffffff] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:bg-[#30302e] dark:hover:text-[#faf9f5]'
                }`}
                onClick={() => onSelect(stage.id)}
                type="button"
              >
                <div className="flex items-center gap-2">
                  <span className={`h-1.5 w-1.5 rounded-full ${stageDotTone(stage.status)}`} />
                  <span className="text-sm font-medium">{stage.label}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[11px] ${stageTone(stage.status)}`}>{stage.status}</span>
                </div>
              </button>
              {index < stageOrder.length - 1 ? <div className="mx-1 h-4 w-px bg-[#e8e6dc] dark:bg-[#30302e]" /> : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function stageDotTone(status: TaskStage['status']) {
  switch (status) {
    case 'done':
      return 'bg-[#4fa06d]'
    case 'current':
      return 'bg-[#c96442]'
    case 'failed':
      return 'bg-[#b53333]'
    case 'blocked':
      return 'bg-[#c96442]'
    default:
      return 'bg-[#b0aea5]'
  }
}
