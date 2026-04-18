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
      <div className="flex min-w-[760px] items-center gap-2">
        {stageOrder.map((stageID, index) => {
          const stage = stages.find((item) => item.id === stageID)!
          const selected = stage.id === activeStageID
          return (
            <div className="flex items-center gap-2" key={stage.id}>
              <button
                className={`min-w-[112px] rounded-[18px] border px-3 py-3 text-left transition ${
                  selected
                    ? 'border-[#c96442] bg-[#fff6ee] shadow-[0_0_0_1px_rgba(201,100,66,0.24)] dark:border-[#c77b61] dark:bg-[#2a211b]'
                    : 'border-[#e8e6dc] bg-[#f5f4ed] hover:bg-[#f1ede4] dark:border-[#30302e] dark:bg-[#232220] dark:hover:bg-[#292825]'
                }`}
                onClick={() => onSelect(stage.id)}
                type="button"
              >
                <div className="text-[11px] uppercase tracking-[0.25em] text-[#87867f] dark:text-[#b0aea5]">{String(index + 1).padStart(2, '0')}</div>
                <div className="mt-2 text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{stage.label}</div>
                <div className={`mt-2 inline-flex rounded-full border px-3 py-1 text-xs ${stageTone(stage.status)}`}>{stage.status}</div>
              </button>
              {index < stageOrder.length - 1 ? <div className="h-px w-6 bg-[#d9d3c8] dark:bg-[#3a3937]" /> : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}
