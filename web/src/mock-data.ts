export type TaskStatus =
  | 'initialized'
  | 'refined'
  | 'planning'
  | 'planned'
  | 'coding'
  | 'partially_coded'
  | 'coded'
  | 'archived'

export type RepoTaskStatus = 'pending' | 'planned' | 'coding' | 'coded' | 'failed' | 'archived'
export type SourceType = 'text' | 'file' | 'lark_doc'

export type TaskArtifactName =
  | 'prd.source.md'
  | 'prd-refined.md'
  | 'refine.log'
  | 'design.md'
  | 'plan.md'
  | 'plan.log'
  | 'code-result.json'

export type TaskTimelineItem = {
  label: string
  state: 'done' | 'current' | 'pending'
  detail: string
}

export type RepoResult = {
  id: string
  displayName: string
  path: string
  status: RepoTaskStatus
  branch?: string
  worktree?: string
  commit?: string
  build?: 'passed' | 'failed' | 'n/a'
  filesWritten?: string[]
}

export type TaskRecord = {
  id: string
  title: string
  status: TaskStatus
  sourceType: SourceType
  updatedAt: string
  owner: string
  complexity: '简单' | '中等' | '复杂'
  nextAction: string
  primaryRepo: string
  repos: RepoResult[]
  summary?: string
  timeline: TaskTimelineItem[]
  artifacts: Record<TaskArtifactName, string>
}

export const tasks: TaskRecord[] = [
  {
    id: '20260411-103200-auction-observability-multi-repo',
    title: '竞拍链路观测收敛：业务仓与 SDK 仓同步降噪',
    status: 'partially_coded',
    sourceType: 'lark_doc',
    updatedAt: '2026-04-11 10:46',
    owner: 'Maifeng',
    complexity: '中等',
    nextAction: 'coco-ext prd code --task 20260411-103200-auction-observability-multi-repo --repo live_sdk',
    primaryRepo: 'live_pack',
    repos: [
      {
        id: 'live_pack',
        displayName: 'Live Pack',
        path: '/home/maifeng/go/src/code.byted.org/ttec/live_pack',
        status: 'coded',
        branch: 'prd_20260411-103200-auction-observability-multi-repo',
        worktree:
          '/home/maifeng/go/src/code.byted.org/ttec/.coco-ext-worktree/live_pack-f3d8368d/20260411-103200-auction-observability-multi-repo',
        commit: 'ab12cd3',
        build: 'passed',
        filesWritten: ['utils/metric_v4/auction_metric.go', 'dal/tcc/auction_config.go'],
      },
      {
        id: 'live_sdk',
        displayName: 'Live SDK',
        path: '/home/maifeng/go/src/code.byted.org/ttec/live_sdk',
        status: 'planned',
        branch: 'prd_20260411-103200-auction-observability-multi-repo',
        build: 'n/a',
      },
    ],
    summary:
      '这个 task 同时涉及业务仓和 SDK 仓。业务仓已经完成代码实现并编译通过，SDK 仓仍停留在 planned 阶段，说明 task 的真实归属对象已经不再适合只绑定单仓。',
    timeline: [
      { label: 'Refine', state: 'done', detail: '已生成结构化需求文档' },
      { label: 'Plan', state: 'done', detail: '计划已明确拆分到 live_pack 与 live_sdk 两个仓库' },
      { label: 'Code', state: 'current', detail: 'live_pack 已完成，live_sdk 仍待执行' },
      { label: 'Archive', state: 'pending', detail: '需全部关联仓库完成后才能归档' },
    ],
    artifacts: {
      'prd.source.md': `# PRD Source

本需求目标是降低竞拍链路里的观测噪音，但改动会落到两个仓库：

- live_pack：业务日志级别调整与调用点收敛
- live_sdk：公共观测 SDK 的默认策略与 helper 行为调整

希望两个仓库协同落地，但保持最小改动范围。
`,
      'prd-refined.md': `# PRD Refined

## 需求概述

竞拍观测链路中存在过量 Error 日志，需要在业务仓和公共 SDK 仓协同降噪。

## 功能点

- 业务仓：将可容忍退化场景的 Error 日志降级
- SDK 仓：统一 helper 的默认日志级别和包装策略

## 验收标准

- 两个仓库各自最小编译通过
- 业务行为不变
- 日志噪音显著下降
`,
      'refine.log': `2026-04-11 10:32:00 === REFINE START ===
2026-04-11 10:32:00 task_id: 20260411-103200-auction-observability-multi-repo
2026-04-11 10:32:00 generator_init: begin (session timeout=5m0s)
2026-04-11 10:32:02 prompt_start: timeout=3m0s
2026-04-11 10:32:03 first_chunk_received: 128 bytes
2026-04-11 10:32:08 validate_ok: true
2026-04-11 10:32:08 status: refined
2026-04-11 10:32:08 duration: 8s
2026-04-11 10:32:08 === REFINE END ===
`,
      'design.md': `# Design

## 总体方案

- task 级产物统一描述需求、设计和计划
- code 阶段按 repo 拆分执行
- 每个 repo 各自记录 branch / worktree / commit / code result

## repo 拆分

- live_pack：改调用点与业务日志级别
- live_sdk：改 helper 与默认观测策略
`,
      'plan.md': `# Plan

## 拟改仓库

- live_pack
- live_sdk

## repo: live_pack

- utils/metric_v4/auction_metric.go：降低观测错误日志级别
- dal/tcc/auction_config.go：降低配置读取错误日志级别

## repo: live_sdk

- sdk/observability/logger.go：统一默认级别
- sdk/observability/helper.go：补齐可容忍退化策略
`,
      'plan.log': `2026-04-11 10:32:10 === PLAN START ===
2026-04-11 10:32:10 task_id: 20260411-103200-auction-observability-multi-repo
2026-04-11 10:32:10 generator_mode: explorer(readonly)
2026-04-11 10:32:12 first_chunk_received: 684 bytes
2026-04-11 10:32:15 status: planned
2026-04-11 10:32:15 duration: 5s
2026-04-11 10:32:15 === PLAN END ===
`,
      'code-result.json': `{
  "status": "partially_coded",
  "task_id": "20260411-103200-auction-observability-multi-repo",
  "primary_repo": "live_pack",
  "repos": [
    {
      "id": "live_pack",
      "status": "coded",
      "branch": "prd_20260411-103200-auction-observability-multi-repo",
      "worktree": "/home/maifeng/go/src/code.byted.org/ttec/.coco-ext-worktree/live_pack-f3d8368d/20260411-103200-auction-observability-multi-repo",
      "commit": "ab12cd3",
      "build_ok": true
    },
    {
      "id": "live_sdk",
      "status": "planned"
    }
  ]
}`,
    },
  },
  {
    id: '20260411-094220-product-card-experiment',
    title: '新增商品卡实验开关与回退策略',
    status: 'planned',
    sourceType: 'text',
    updatedAt: '2026-04-11 09:58',
    owner: 'Maifeng',
    complexity: '中等',
    nextAction: 'coco-ext prd code --task 20260411-094220-product-card-experiment',
    primaryRepo: 'live_pack',
    repos: [
      {
        id: 'live_pack',
        displayName: 'Live Pack',
        path: '/home/maifeng/go/src/code.byted.org/ttec/live_pack',
        status: 'planned',
        branch: 'prd_20260411-094220-product-card-experiment',
        build: 'n/a',
      },
    ],
    timeline: [
      { label: 'Refine', state: 'done', detail: '已从自然语言生成 refined PRD' },
      { label: 'Plan', state: 'done', detail: '已完成 explorer 调研和实施计划' },
      { label: 'Code', state: 'current', detail: '尚未执行，等待进入隔离 code 阶段' },
      { label: 'Archive', state: 'pending', detail: '等待代码结果确认' },
    ],
    artifacts: {
      'prd.source.md': `# PRD Source

给商品卡新增实验开关，支持按端和流量开关灰度，并提供回退逻辑。
`,
      'prd-refined.md': `# PRD Refined

## 需求概述

希望为商品卡逻辑新增实验能力，支持灰度、开关和回退。
`,
      'refine.log': `2026-04-11 09:42:20 === REFINE START ===
2026-04-11 09:42:20 task_id: 20260411-094220-product-card-experiment
2026-04-11 09:42:20 generator_init: begin (session timeout=5m0s)
2026-04-11 09:42:24 prompt_start: timeout=3m0s
2026-04-11 09:42:29 validate_ok: true
2026-04-11 09:42:29 status: refined
2026-04-11 09:42:29 duration: 9s
2026-04-11 09:42:29 === REFINE END ===
`,
      'design.md': `# Design

- 扩展现有实验配置读取层
- 避免在 handler 中散落实验判断
- 以 converter / config facade 收敛逻辑
`,
      'plan.md': `# Plan

## repo: live_pack

- app/experiment/product_card.go：新增实验配置读取
- service/product_card_service.go：接入实验判断
- converter/product_card_converter.go：处理回退逻辑
`,
      'plan.log': `2026-04-11 09:42:31 === PLAN START ===
2026-04-11 09:42:31 task_id: 20260411-094220-product-card-experiment
2026-04-11 09:42:31 generator_mode: explorer(readonly)
2026-04-11 09:42:34 first_chunk_received: 512 bytes
2026-04-11 09:42:38 status: planned
2026-04-11 09:42:38 duration: 7s
2026-04-11 09:42:38 === PLAN END ===
`,
      'code-result.json': `{
  "status": "planned"
}`,
    },
  },
  {
    id: '20260410-221030-review-trigger-cleanup',
    title: 'push 后 review/lint 异步触发链路收敛',
    status: 'archived',
    sourceType: 'file',
    updatedAt: '2026-04-10 23:12',
    owner: 'Maifeng',
    complexity: '中等',
    nextAction: 'task 已归档，无后续操作',
    primaryRepo: 'coco-ext',
    repos: [
      {
        id: 'coco-ext',
        displayName: 'coco-ext',
        path: '/Users/bytedance/go/src/coco-ext',
        status: 'archived',
        branch: 'prd_20260410-221030-review-trigger-cleanup',
        commit: '7fa22bc',
        build: 'passed',
        filesWritten: ['cmd/push.go', 'cmd/review.go', 'cmd/lint.go'],
      },
    ],
    summary: '统一 push 成功后的异步 review 和 lint 触发时机，减少 pre-push 干扰。',
    timeline: [
      { label: 'Refine', state: 'done', detail: '已完成' },
      { label: 'Plan', state: 'done', detail: '已完成' },
      { label: 'Code', state: 'done', detail: '已完成并提交' },
      { label: 'Archive', state: 'done', detail: '已清理分支和 worktree' },
    ],
    artifacts: {
      'prd.source.md': '# Source\n\n已归档 task，源文档略。',
      'prd-refined.md': '# PRD Refined\n\n已归档 task，refined 文档略。',
      'refine.log': '2026-04-10 22:10:30 === REFINE START ===\n2026-04-10 22:10:37 status: refined\n2026-04-10 22:10:37 === REFINE END ===\n',
      'design.md': '# Design\n\n已归档 task，设计文档略。',
      'plan.md': '# Plan\n\n已归档 task，实施计划略。',
      'plan.log': '2026-04-10 22:10:39 === PLAN START ===\n2026-04-10 22:10:46 status: planned\n2026-04-10 22:10:46 === PLAN END ===\n',
      'code-result.json': `{
  "status": "success",
  "task_id": "20260410-221030-review-trigger-cleanup",
  "primary_repo": "coco-ext",
  "repos": [
    {
      "id": "coco-ext",
      "status": "archived",
      "branch": "prd_20260410-221030-review-trigger-cleanup",
      "commit": "7fa22bc",
      "build_ok": true
    }
  ]
}`,
    },
  },
]

export const workspaceSummary = {
  repoRoot: '/home/maifeng/go/src/code.byted.org/ttec/live_pack',
  tasksRoot: '~/.config/coco-ext/tasks',
  contextRoot: '.livecoding/context',
  worktreeRoot: '/home/maifeng/go/src/code.byted.org/ttec/.coco-ext-worktree',
  activeBranches: [
    'main',
    'codex-prd-skill',
    'prd_20260411-103200-auction-observability-multi-repo',
  ],
  reposInvolved: ['live_pack', 'live_sdk', 'coco-ext'],
}

export function getTask(taskId: string) {
  return tasks.find((task) => task.id === taskId)
}
