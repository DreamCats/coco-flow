import { useMemo, useState } from 'react'

type StageID = 'input' | 'refine' | 'design' | 'plan' | 'code' | 'archive'
type StageState = 'todo' | 'active' | 'done' | 'blocked'

type StageDetail = {
  id: StageID
  label: string
  summary: string
  status: StageState
  actions: string[]
  notePlaceholder: string
  previewTitle: string
  previewBody: string
  graphTitle?: string
  graphBody?: string
  repos?: Array<{
    name: string
    status: 'ready' | 'running' | 'blocked' | 'done' | 'failed'
    note: string
    path: string
    buildResult: string
    branch: string
    worktree: string
    nextExecutable?: boolean
  }>
}

type TaskPreview = {
  id: string
  title: string
  source: string
  updatedAt: string
  overall: string
  currentStage: StageID
  stages: StageDetail[]
}

const stageOrder: StageID[] = ['input', 'refine', 'design', 'plan', 'code', 'archive']

const tasks: TaskPreview[] = [
  {
    id: 'task-2417',
    title: '统一商品规则定义口径',
    source: '飞书 PRD',
    updatedAt: '今天 14:20',
    overall: '待设计',
    currentStage: 'refine',
    stages: [
      {
        id: 'input',
        label: 'Input',
        summary: '已收集 PRD 原文和研发补充说明。',
        status: 'done',
        actions: ['查看原文', '继续补充'],
        notePlaceholder: '继续补充背景、约束或参考材料',
        previewTitle: 'source package',
        previewBody:
          '来源：飞书文档\n补充说明：\n- 本轮重点是统一规则定义，不直接重构所有消费侧。\n- 已知风险是旧字段映射分散。',
      },
      {
        id: 'refine',
        label: 'Refine',
        summary: '提炼需求目标、边界 case 和风险项。',
        status: 'active',
        actions: ['开始提炼', '人工补充'],
        notePlaceholder: '补充遗漏边界、风险或待确认问题',
        previewTitle: 'prd-refined.md',
        previewBody:
          '核心目标：统一规则口径，降低跨端定义偏差。\n非目标：本轮不改底层存储。\n风险项：历史配置兼容性、消费侧字段不一致。',
      },
      {
        id: 'design',
        label: 'Design',
        summary: '设计方案前先绑定仓库，补齐代码调研上下文。',
        status: 'todo',
        actions: ['绑定仓库', '生成设计'],
        notePlaceholder: '补充必须兼容的上下游或技术限制',
        previewTitle: 'design.md',
        previewBody: '当前还未生成设计稿。\n\n进入 Design 前需要先绑定相关仓库，以便补齐代码调研和上下游信息。',
      },
      {
        id: 'plan',
        label: 'Plan',
        summary: '拆执行任务与验证顺序。',
        status: 'todo',
        actions: ['生成计划'],
        notePlaceholder: '补充优先级、风险或验证方法',
        previewTitle: 'plan.md',
        previewBody: '当前还未生成计划。',
        graphTitle: '任务依赖关系',
        graphBody: '需求提炼\n   ↓\n绑定仓库并完成设计\n   ↓\n生成执行计划\n   ↓\n进入实现',
      },
      {
        id: 'code',
        label: 'Code',
        summary: '基于 Design 和 Plan 的结果进入实现与验证。',
        status: 'todo',
        actions: ['开始实现'],
        notePlaceholder: '补充最小验证方式或优先推进 repo',
        previewTitle: 'repo execution',
        previewBody: '等待 Design 和 Plan 完成后进入实现。',
        repos: [
          {
            name: '商品主仓',
            status: 'ready',
            note: '推荐先实现规则定义与兼容字段。',
            path: '/Users/bytedance/workspace/product-core',
            buildResult: '待生成',
            branch: '尚未创建',
            worktree: '尚未创建',
            nextExecutable: true,
          },
          {
            name: '消费侧仓库',
            status: 'blocked',
            note: '依赖主仓字段和设计边界先稳定。',
            path: '/Users/bytedance/workspace/product-consumer',
            buildResult: '待生成',
            branch: '尚未创建',
            worktree: '尚未创建',
          },
        ],
      },
      {
        id: 'archive',
        label: 'Archive',
        summary: '沉淀结果、验证结论与后续事项。',
        status: 'todo',
        actions: ['生成归档摘要'],
        notePlaceholder: '补充上线说明或残留风险',
        previewTitle: 'archive summary',
        previewBody: '当前还未进入归档阶段。',
      },
    ],
  },
  {
    id: 'task-2409',
    title: '直播间指标看板收口',
    source: '粘贴文本',
    updatedAt: '今天 11:05',
    overall: '计划已完成',
    currentStage: 'plan',
    stages: [
      {
        id: 'input',
        label: 'Input',
        summary: '输入材料已收全。',
        status: 'done',
        actions: ['查看原文'],
        notePlaceholder: '继续补充背景信息',
        previewTitle: 'source package',
        previewBody: '原文与补充材料已归档到输入包。',
      },
      {
        id: 'refine',
        label: 'Refine',
        summary: '需求提炼已完成。',
        status: 'done',
        actions: ['查看提炼稿'],
        notePlaceholder: '补充边界情况',
        previewTitle: 'prd-refined.md',
        previewBody: '提炼稿已确认，主要风险为指标口径差异和历史字段兼容。',
      },
      {
        id: 'design',
        label: 'Design',
        summary: '方案设计已完成。',
        status: 'done',
        actions: ['查看设计', '切换仓库'],
        notePlaceholder: '补充设计说明',
        previewTitle: 'design.md',
        previewBody: '已绑定 dashboard-web 和 metrics-service。\n\n采用配置汇总层承接指标口径，再逐步迁移消费端。',
      },
      {
        id: 'plan',
        label: 'Plan',
        summary: '当前处于计划确认阶段。',
        status: 'active',
        actions: ['生成计划', '细化拆解'],
        notePlaceholder: '补充依赖关系或验证顺序',
        previewTitle: 'plan.md',
        previewBody:
          '1. 先统一 schema。\n2. 再改 dashboard 读取逻辑。\n3. 最后回放历史数据并人工验证关键页面。',
        graphTitle: '任务依赖关系',
        graphBody: 'schema 统一\n   ↓\ndashboard-web\n   ↓\nmetrics-service\n   ↓\n回放验证',
      },
      {
        id: 'code',
        label: 'Code',
        summary: '等待仓库实现。',
        status: 'todo',
        actions: ['开始实现'],
        notePlaceholder: '补充优先落地仓库',
        previewTitle: 'repo execution',
        previewBody: '已具备进入 Code 的条件，但尚未开始执行。',
        repos: [
          {
            name: 'dashboard-web',
            status: 'ready',
            note: '优先落地展示层字段兼容。',
            path: '/Users/bytedance/workspace/dashboard-web',
            buildResult: '待生成',
            branch: '尚未创建',
            worktree: '尚未创建',
            nextExecutable: true,
          },
          {
            name: 'metrics-service',
            status: 'ready',
            note: '随后补聚合逻辑和验证。',
            path: '/Users/bytedance/workspace/metrics-service',
            buildResult: '待生成',
            branch: '尚未创建',
            worktree: '尚未创建',
          },
        ],
      },
      {
        id: 'archive',
        label: 'Archive',
        summary: '等待代码结果。',
        status: 'todo',
        actions: ['生成归档摘要'],
        notePlaceholder: '补充结论或风险',
        previewTitle: 'archive summary',
        previewBody: '归档区待后续产出。',
      },
    ],
  },
  {
    id: 'task-2398',
    title: '导出链路兼容治理',
    source: '飞书 PRD',
    updatedAt: '昨天 19:40',
    overall: '实现受阻',
    currentStage: 'code',
    stages: [
      {
        id: 'input',
        label: 'Input',
        summary: '输入已完成。',
        status: 'done',
        actions: ['查看原文'],
        notePlaceholder: '继续补充背景',
        previewTitle: 'source package',
        previewBody: '输入材料已齐备。',
      },
      {
        id: 'refine',
        label: 'Refine',
        summary: '需求提炼已完成。',
        status: 'done',
        actions: ['查看提炼稿'],
        notePlaceholder: '补充边界问题',
        previewTitle: 'prd-refined.md',
        previewBody: '提炼阶段已完成。',
      },
      {
        id: 'design',
        label: 'Design',
        summary: '设计稿已确认。',
        status: 'done',
        actions: ['查看设计', '切换仓库'],
        notePlaceholder: '补充设计说明',
        previewTitle: 'design.md',
        previewBody: '已绑定 export-gateway 和 schema-service，设计稿已确认。',
      },
      {
        id: 'plan',
        label: 'Plan',
        summary: '计划已生成。',
        status: 'done',
        actions: ['查看计划'],
        notePlaceholder: '补充计划说明',
        previewTitle: 'plan.md',
        previewBody: '计划阶段已确认，按仓库顺序推进。',
        graphTitle: '任务依赖关系',
        graphBody: 'schema-service\n   ↓\nexport-gateway\n   ↓\n导出验证\n   ↓\n归档',
      },
      {
        id: 'code',
        label: 'Code',
        summary: '当前有一个依赖阻塞，需要先处理上游仓库。',
        status: 'blocked',
        actions: ['查看阻塞原因', '切换仓库'],
        notePlaceholder: '记录阻塞原因或人工处理决定',
        previewTitle: 'repo execution',
        previewBody:
          '状态：blocked\n原因：export-gateway 依赖 schema-service 先完成字段兼容。\n建议：先切到上游仓库推进。',
        repos: [
          {
            name: 'schema-service',
            status: 'ready',
            note: '上游仓库，建议先推进字段兼容。',
            path: '/Users/bytedance/workspace/schema-service',
            buildResult: '待生成',
            branch: '尚未创建',
            worktree: '尚未创建',
            nextExecutable: true,
          },
          {
            name: 'export-gateway',
            status: 'blocked',
            note: '依赖 schema-service 完成后再继续。',
            path: '/Users/bytedance/workspace/export-gateway',
            buildResult: '待生成',
            branch: '尚未创建',
            worktree: '尚未创建',
          },
        ],
      },
      {
        id: 'archive',
        label: 'Archive',
        summary: '等待实现收口。',
        status: 'todo',
        actions: ['生成归档摘要'],
        notePlaceholder: '补充结论',
        previewTitle: 'archive summary',
        previewBody: '尚未归档。',
      },
    ],
  },
]

export function WorkflowPreviewPage() {
  const [activeTaskID, setActiveTaskID] = useState(tasks[0]!.id)
  const activeTask = useMemo(() => tasks.find((task) => task.id === activeTaskID) ?? tasks[0]!, [activeTaskID])
  const [activeStageID, setActiveStageID] = useState<StageID>(activeTask.currentStage)
  const [activeDetailTab, setActiveDetailTab] = useState<'artifact' | 'notes' | 'graph' | 'repos'>('artifact')
  const [selectedRepoName, setSelectedRepoName] = useState('')
  const [showCreateDrawer, setShowCreateDrawer] = useState(false)

  const currentStage = activeTask.stages.find((stage) => stage.id === activeStageID) ?? activeTask.stages[0]!
  const currentRepos = currentStage.id === 'code' ? currentStage.repos ?? [] : []
  const selectedRepo = currentRepos.find((repo) => repo.name === selectedRepoName) ?? currentRepos[0] ?? null

  function selectTask(taskID: string) {
    const nextTask = tasks.find((task) => task.id === taskID)
    if (!nextTask) {
      return
    }
    setActiveTaskID(taskID)
    setActiveStageID(nextTask.currentStage)
    setActiveDetailTab('artifact')
    setSelectedRepoName('')
  }

  function selectStage(stageID: StageID) {
    setActiveStageID(stageID)
    setActiveDetailTab('artifact')
    setSelectedRepoName('')
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-3 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
        <div className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] px-4 py-4 dark:border-[#30302e] dark:bg-[#232220]">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Preview</div>
              <h2 className="mt-2 text-[28px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                任务推进草图
              </h2>
            </div>
            <button
              className="inline-flex h-10 w-10 items-center justify-center rounded-[12px] border border-[#c96442] bg-[#c96442] text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]"
              onClick={() => setShowCreateDrawer(true)}
              title="新建任务"
              type="button"
            >
              <PlusIcon />
            </button>
          </div>
          <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
            左边选任务，右边看 6 步流水线。点击流水线后，只在下方展示这一步的详情和动作。
          </p>
        </div>

        <div className="mt-3 space-y-2">
          {tasks.map((task) => {
            const active = task.id === activeTask.id
            return (
              <button
                className={`w-full rounded-[20px] border px-4 py-4 text-left transition ${
                  active
                    ? 'border-[#c96442] bg-[#fff6ee] shadow-[0_0_0_1px_rgba(201,100,66,0.24)] dark:border-[#c77b61] dark:bg-[#2a211b]'
                    : 'border-[#e8e6dc] bg-[#faf9f5] hover:bg-[#f5f1e8] dark:border-[#30302e] dark:bg-[#1f1e1c] dark:hover:bg-[#262523]'
                }`}
                key={task.id}
                onClick={() => selectTask(task.id)}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{task.title}</div>
                    <div className="mt-1 text-xs text-[#87867f] dark:text-[#b0aea5]">
                      {task.id} · {task.source}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <TaskOverallBadge label={task.overall} />
                    <button
                      className="inline-flex h-6 w-6 items-center justify-center rounded-full text-[#87867f] transition hover:bg-[#f1ece4] hover:text-[#4d4c48] dark:text-[#8f8a82] dark:hover:bg-[#24221f] dark:hover:text-[#f1ede4]"
                      onClick={(event) => event.stopPropagation()}
                      title="删除任务"
                      type="button"
                    >
                      <CloseIcon />
                    </button>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between text-xs text-[#5e5d59] dark:text-[#b0aea5]">
                  <span>当前：{labelForStage(task.currentStage)}</span>
                  <span>{task.updatedAt}</span>
                </div>
              </button>
            )
          })}
        </div>
      </aside>

      <section className="space-y-4">
        <header className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Current Task</div>
              <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                {activeTask.title}
              </h3>
              <p className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                横条只表达阶段状态；真正的说明、产物和动作都放到下方单步骤详情里。
              </p>
            </div>
            <div className="rounded-full border border-[#e8e6dc] bg-[#f5f4ed] px-3 py-1.5 text-xs text-[#5e5d59] dark:border-[#30302e] dark:bg-[#232220] dark:text-[#b0aea5]">
              {activeTask.id} · {activeTask.overall}
            </div>
          </div>

          <div className="mt-5 overflow-x-auto">
            <div className="flex min-w-[760px] items-center gap-2">
              {stageOrder.map((stageID, index) => {
                const stage = activeTask.stages.find((item) => item.id === stageID)!
                const selected = stage.id === currentStage.id
                return (
                  <div className="flex items-center gap-2" key={stage.id}>
                    <button
                      className={`min-w-[112px] rounded-[18px] border px-3 py-3 text-left transition ${
                        selected
                          ? 'border-[#c96442] bg-[#fff6ee] shadow-[0_0_0_1px_rgba(201,100,66,0.24)] dark:border-[#c77b61] dark:bg-[#2a211b]'
                          : 'border-[#e8e6dc] bg-[#f5f4ed] hover:bg-[#f1ede4] dark:border-[#30302e] dark:bg-[#232220] dark:hover:bg-[#292825]'
                      }`}
                      onClick={() => selectStage(stage.id)}
                      type="button"
                    >
                      <div className="text-[11px] uppercase tracking-[0.25em] text-[#87867f] dark:text-[#b0aea5]">{String(index + 1).padStart(2, '0')}</div>
                      <div className="mt-2 text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{stage.label}</div>
                      <div className="mt-2">
                        <StageStatusBadge status={stage.status} />
                      </div>
                    </button>
                    {index < stageOrder.length - 1 ? (
                      <div className="h-px w-6 bg-[#d9d3c8] dark:bg-[#3a3937]" />
                    ) : null}
                  </div>
                )
              })}
            </div>
          </div>
        </header>

        <div className="rounded-[24px] border border-[#e8e6dc] bg-[#faf9f5] p-5 shadow-[0_0_0_1px_rgba(240,238,230,0.92)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_0_0_1px_rgba(48,48,46,0.98)]">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Stage Detail</div>
              <h4 className="mt-2 text-[28px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                {currentStage.label}
              </h4>
              <p className="mt-2 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{currentStage.summary}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {currentStage.actions.map((action, index) => (
                <button
                  className={
                    index === 0
                      ? 'rounded-[12px] border border-[#c96442] bg-[#c96442] px-3 py-1.5 text-xs text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]'
                      : 'rounded-[12px] border border-[#d1cfc5] bg-[#faf9f5] px-3 py-1.5 text-xs text-[#4d4c48] transition hover:bg-[#efeae0] dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]'
                  }
                  key={action}
                  type="button"
                >
                  {action}
                </button>
              ))}
              <StageStatusBadge status={currentStage.status} />
            </div>
          </div>

          <div className="mt-5">
            <div className="inline-flex rounded-[16px] border border-[#e8e6dc] bg-[#f5f4ed] p-1 dark:border-[#30302e] dark:bg-[#232220]">
              <button
                className={`rounded-[12px] px-4 py-2 text-sm transition ${
                  activeDetailTab === 'artifact'
                    ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                    : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                }`}
                onClick={() => setActiveDetailTab('artifact')}
                type="button"
              >
                产物与查看
              </button>
              <button
                className={`rounded-[12px] px-4 py-2 text-sm transition ${
                  activeDetailTab === 'notes'
                    ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                    : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                }`}
                onClick={() => setActiveDetailTab('notes')}
                type="button"
              >
                补充说明
              </button>
              {currentStage.id === 'plan' ? (
                <button
                  className={`rounded-[12px] px-4 py-2 text-sm transition ${
                    activeDetailTab === 'graph'
                      ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                      : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                  }`}
                  onClick={() => setActiveDetailTab('graph')}
                  type="button"
                >
                  关系图
                </button>
              ) : null}
              {currentStage.id === 'code' ? (
                <button
                  className={`rounded-[12px] px-4 py-2 text-sm transition ${
                    activeDetailTab === 'repos'
                      ? 'bg-[#ffffff] text-[#141413] shadow-[0_0_0_1px_rgba(240,238,230,0.95)] dark:bg-[#141413] dark:text-[#faf9f5] dark:shadow-[0_0_0_1px_rgba(48,48,46,1)]'
                      : 'text-[#5e5d59] hover:text-[#141413] dark:text-[#b0aea5] dark:hover:text-[#faf9f5]'
                  }`}
                  onClick={() => setActiveDetailTab('repos')}
                  type="button"
                >
                  仓库
                </button>
              ) : null}
            </div>

            {activeDetailTab === 'artifact' ? (
              <section className="mt-4 rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
                <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
                  <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{currentStage.previewTitle}</div>
                  <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                    {currentStage.previewBody}
                  </pre>
                </div>
              </section>
            ) : activeDetailTab === 'graph' && currentStage.id === 'plan' ? (
              <section className="mt-4 rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
                <div className="rounded-[18px] border border-[#ece6da] bg-[#fffdf9] px-4 py-4 dark:border-[#383632] dark:bg-[#151412]">
                  <div className="text-sm font-medium text-[#141413] dark:text-[#faf9f5]">{currentStage.graphTitle ?? '关系图'}</div>
                  <pre className="mt-3 overflow-x-auto whitespace-pre-wrap text-xs leading-7 text-[#5e5d59] dark:text-[#b0aea5]">
                    {currentStage.graphBody ?? '当前暂无关系图。'}
                  </pre>
                </div>
              </section>
            ) : activeDetailTab === 'repos' && currentStage.id === 'code' ? (
              <section className="mt-4 rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
                <div className="space-y-5">
                  <div className="rounded-[22px] border border-[#e8e0d5] bg-[#fffaf2] px-4 py-4 shadow-[0_0_0_1px_rgba(255,250,242,0.88)] dark:border-[#393632] dark:bg-[#201e1a] dark:shadow-[0_0_0_1px_rgba(32,30,26,1)]">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-[10px] uppercase tracking-[0.45em] text-[#8d7766] dark:text-[#ad9f8f]">Repo Execution Lane</div>
                        <div className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                          多仓执行链路
                        </div>
                        <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                          只做三件事：选一个仓库、看它的详情、点开始实现。
                        </p>
                      </div>
                      <RepoStageBadge status={currentStage.status === 'blocked' ? 'blocked' : currentRepos.length > 0 ? 'ready' : 'failed'} />
                    </div>
                  </div>

                  <div className="overflow-x-auto">
                    <div className="flex min-w-[720px] items-center gap-5">
                      {currentRepos.map((repo, index) => {
                        const active = selectedRepo?.name === repo.name
                        return (
                          <div className="flex items-center gap-5" key={repo.name}>
                            <button
                              className={`w-[300px] rounded-[22px] border px-4 py-4 text-left transition ${
                                active
                                  ? 'border-[#d56b45] bg-[#fff3ee] shadow-[0_0_0_1px_rgba(213,107,69,0.28)] dark:border-[#c77b61] dark:bg-[#2a211b]'
                                  : 'border-[#e7d8c0] bg-[#fffaf2] hover:bg-[#fff6ea] dark:border-[#4a4033] dark:bg-[#211d18] dark:hover:bg-[#29241e]'
                              }`}
                              onClick={() => setSelectedRepoName(repo.name)}
                              type="button"
                            >
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex items-center gap-3">
                                  <div className="inline-flex h-12 w-12 items-center justify-center rounded-full border border-[#dbc9b3] text-[28px] text-[#7c5d3d] dark:border-[#5a4a38] dark:text-[#d7c2a6]">
                                    {index + 1}
                                  </div>
                                  <div>
                                    <div className="text-[18px] font-medium text-[#5a3a28] dark:text-[#f3e5d6]">{repo.name}</div>
                                    <div className="mt-2 text-sm text-[#8a7a67] dark:text-[#b8ae9e]">{repo.note}</div>
                                  </div>
                                </div>
                                <LegendPill label={repo.status} tone={repo.status} />
                              </div>

                              <div className="mt-6 rounded-[16px] border border-[#e4d8c9] bg-[#fff9f1] px-4 py-3 text-sm tracking-[0.18em] text-[#8a6c48] dark:border-[#4a4033] dark:bg-[#1b1814] dark:text-[#cfbb9c]">
                                {repo.nextExecutable ? '选择后可立即实现' : '等待上游稳定后再实现'}
                              </div>
                            </button>
                            {index < currentRepos.length - 1 ? <div className="h-px w-14 bg-[#d7d1c7] dark:bg-[#3a3937]" /> : null}
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {selectedRepo ? (
                    <div className="rounded-[22px] border border-[#e8e0d5] bg-[#fffdf8] px-4 py-4 dark:border-[#393632] dark:bg-[#181714]">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <div className="text-[10px] uppercase tracking-[0.35em] text-[#8d7766] dark:text-[#ad9f8f]">Selected Repo</div>
                          <div className="mt-3 text-[28px] leading-none font-medium text-[#141413] dark:text-[#faf9f5]">{selectedRepo.name}</div>
                        </div>
                        <LegendPill label={selectedRepo.status} tone={selectedRepo.status} />
                      </div>

                      <div className="mt-4 flex flex-wrap gap-2">
                        <MetaPill label="仓库标识" value={selectedRepo.name} />
                        <MetaPill label="构建结果" value={selectedRepo.buildResult} />
                        <MetaPill label="分支" value={selectedRepo.branch} />
                        <MetaPill label="工作区" value={selectedRepo.worktree} />
                      </div>

                      <div className="mt-4 rounded-[18px] border border-[#ece6da] bg-[#fffaf2] px-4 py-4 text-sm text-[#8a7a67] dark:border-[#383632] dark:bg-[#11100f] dark:text-[#b8ae9e]">
                        {selectedRepo.path}
                      </div>

                      <div className="mt-4 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">{selectedRepo.note}</div>

                      <button
                        className="mt-6 rounded-[16px] border border-[#d56b45] bg-[#d56b45] px-6 py-3 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(213,107,69,1)] transition hover:bg-[#df7b57]"
                        type="button"
                      >
                        {selectedRepo.status === 'blocked' ? '等待可实现' : '开始实现'}
                      </button>
                    </div>
                  ) : null}
                </div>
              </section>
            ) : (
              <section className="mt-4 rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
                <div className="min-h-[220px] rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-6 text-[#87867f] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#8f8a82]">
                  {currentStage.notePlaceholder}
                </div>
              </section>
            )}
          </div>
        </div>
      </section>

      {showCreateDrawer ? (
        <div
          className="fixed inset-0 z-50 bg-[rgba(20,20,19,0.2)] backdrop-blur-sm dark:bg-[rgba(20,20,19,0.58)]"
          onClick={() => setShowCreateDrawer(false)}
        >
          <div
            className="absolute left-1/2 top-1/2 flex max-h-[calc(100vh-48px)] w-[min(720px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-[28px] border border-[#e8e6dc] bg-[#faf9f5] shadow-[0_24px_64px_rgba(20,20,19,0.18)] dark:border-[#30302e] dark:bg-[#1d1c1a] dark:shadow-[0_24px_64px_rgba(0,0,0,0.38)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-4 border-b border-[#e8e6dc] px-6 py-5 dark:border-[#30302e]">
              <div>
                <div className="text-[10px] uppercase tracking-[0.5px] text-[#87867f] dark:text-[#b0aea5]">Create Task</div>
                <h3 className="mt-2 text-[30px] leading-[1.08] font-medium text-[#141413] [font-family:Georgia,serif] dark:text-[#faf9f5]">
                  新建任务
                </h3>
                <p className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                  这里只收两类信息：需求原文，以及研发视角下的补充说明。
                </p>
              </div>
              <button
                className="inline-flex h-9 w-9 items-center justify-center rounded-full text-[#87867f] transition hover:bg-[#f1ece4] hover:text-[#4d4c48] dark:text-[#8f8a82] dark:hover:bg-[#24221f] dark:hover:text-[#f1ede4]"
                onClick={() => setShowCreateDrawer(false)}
                title="关闭"
                type="button"
              >
                <CloseIcon />
              </button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
              <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
                <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">输入内容</div>
                <div className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                  填 PRD 内容，或者直接贴飞书文档链接。
                </div>
                <div className="mt-4 min-h-[240px] rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-7 text-[#8a7a67] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#8f8a82]">
                  请输入 PRD 原文，或粘贴飞书文档链接。
                  <br />
                  <br />
                  示例：
                  <br />
                  https://bytedance.feishu.cn/docx/...
                </div>
              </section>

              <section className="rounded-[20px] border border-[#e8e6dc] bg-[#f5f4ed] p-4 dark:border-[#30302e] dark:bg-[#232220]">
                <div className="text-[10px] uppercase tracking-[0.45em] text-[#87867f] dark:text-[#b0aea5]">补充说明</div>
                <div className="mt-3 text-sm leading-6 text-[#5e5d59] dark:text-[#b0aea5]">
                  研发视角下补充理解、风险、约束，或者贴参考材料。
                </div>
                <div className="mt-4 min-h-[180px] rounded-[18px] border border-dashed border-[#d8d3c8] bg-[#fffdf9] px-4 py-4 text-sm leading-7 text-[#8a7a67] dark:border-[#3a3937] dark:bg-[#151412] dark:text-[#8f8a82]">
                  例如：
                  <br />
                  - 我理解这次主要是统一规则定义。
                  <br />
                  - 风险是旧链路字段兼容。
                  <br />
                  - 可参考历史需求或知识库文档。
                </div>
              </section>
            </div>

            <div className="flex flex-wrap gap-2 border-t border-[#e8e6dc] px-6 py-4 dark:border-[#30302e]">
              <button
                className="rounded-[14px] border border-[#c96442] bg-[#c96442] px-5 py-3 text-sm text-[#faf9f5] shadow-[0_0_0_1px_rgba(201,100,66,1)] transition hover:bg-[#d97757]"
                type="button"
              >
                创建任务
              </button>
              <button
                className="rounded-[14px] border border-[#d1cfc5] bg-[#faf9f5] px-5 py-3 text-sm text-[#4d4c48] transition hover:bg-[#efeae0] dark:border-[#3a3937] dark:bg-[#191816] dark:text-[#f1ede4] dark:hover:bg-[#24221f]"
                onClick={() => setShowCreateDrawer(false)}
                type="button"
              >
                取消
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function labelForStage(stageID: StageID) {
  const labels: Record<StageID, string> = {
    input: 'Input',
    refine: 'Refine',
    design: 'Design',
    plan: 'Plan',
    code: 'Code',
    archive: 'Archive',
  }
  return labels[stageID]
}

function TaskOverallBadge({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-[#d9cec0] bg-[#fffaf2] px-3 py-1 text-xs text-[#8d7766] dark:border-[#46423e] dark:bg-[#191816] dark:text-[#bcae9f]">
      {label}
    </span>
  )
}

function StageStatusBadge({ status }: { status: StageState }) {
  const tone =
    status === 'done'
      ? 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]'
      : status === 'active'
        ? 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]'
        : status === 'blocked'
          ? 'border-[#efbbb6] bg-[#ffe7e4] text-[#9f3d34] dark:border-[#75423f] dark:bg-[#3a1f1d] dark:text-[#f5b6b0]'
          : 'border-[#d7d2c8] bg-[#f2efe9] text-[#655d52] dark:border-[#4a4640] dark:bg-[#26231f] dark:text-[#d9d2c6]'

  const label =
    status === 'done' ? 'done' : status === 'active' ? 'active' : status === 'blocked' ? 'blocked' : 'todo'

  return <span className={`rounded-full border px-3 py-1 text-xs ${tone}`}>{label}</span>
}

function LegendPill({
  label,
  tone,
}: {
  label: string
  tone: 'ready' | 'running' | 'blocked' | 'done' | 'failed'
}) {
  return <span className={`rounded-full border px-4 py-2 text-sm ${legendTone(tone)}`}>{label}</span>
}

function MetaPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="inline-flex items-center gap-3 rounded-full border border-[#e2d8cb] bg-[#fffaf2] px-4 py-3 text-sm dark:border-[#3d3934] dark:bg-[#11100f]">
      <span className="text-[#9a9185] dark:text-[#8f8a82]">{label}</span>
      <span className="text-[#141413] dark:text-[#faf9f5]">{value}</span>
    </div>
  )
}

function legendTone(tone: 'ready' | 'running' | 'blocked' | 'done' | 'failed') {
  switch (tone) {
    case 'ready':
      return 'border-[#e2c36f] bg-[#fff4cf] text-[#8d6714] dark:border-[#7a6030] dark:bg-[#352a17] dark:text-[#f2cb77]'
    case 'running':
      return 'border-[#bcd7f2] bg-[#e7f2ff] text-[#3d638f] dark:border-[#456180] dark:bg-[#1d2937] dark:text-[#a5ccf5]'
    case 'blocked':
      return 'border-[#dfc289] bg-[#fff2dc] text-[#89601b] dark:border-[#725738] dark:bg-[#342717] dark:text-[#efc98b]'
    case 'done':
      return 'border-[#c8e0cc] bg-[#ebf7ed] text-[#43624a] dark:border-[#4d6654] dark:bg-[#1d2d21] dark:text-[#b9dcbd]'
    case 'failed':
      return 'border-[#efc3c1] bg-[#ffeceb] text-[#9b4b47] dark:border-[#754643] dark:bg-[#341e1d] dark:text-[#f0b5b1]'
  }
}

function PlusIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="18" viewBox="0 0 18 18" width="18">
      <path d="M9 3.75v10.5M3.75 9h10.5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </svg>
  )
}

function RepoStageBadge({ status }: { status: 'ready' | 'blocked' | 'done' | 'failed' }) {
  return (
    <span
      className={`rounded-full border px-3 py-1 text-xs ${
        status === 'done'
          ? 'border-[#b8dfcf] bg-[#e3f6ee] text-[#1f6d53] dark:border-[#395d51] dark:bg-[#183229] dark:text-[#8cdabf]'
          : status === 'blocked'
            ? 'border-[#efbbb6] bg-[#ffe7e4] text-[#9f3d34] dark:border-[#75423f] dark:bg-[#3a1f1d] dark:text-[#f5b6b0]'
            : status === 'failed'
              ? 'border-[#efc3c1] bg-[#ffeceb] text-[#9b4b47] dark:border-[#754643] dark:bg-[#341e1d] dark:text-[#f0b5b1]'
            : 'border-[#f0c38b] bg-[#fff1dd] text-[#9a5f16] dark:border-[#6f5330] dark:bg-[#3a2a18] dark:text-[#f1c98c]'
      }`}
    >
      {status}
    </span>
  )
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" fill="none" height="14" viewBox="0 0 14 14" width="14">
      <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
    </svg>
  )
}
