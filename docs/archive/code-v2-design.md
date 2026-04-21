# Code V2 Design

本文定义 `coco-flow` 下一版正式 `Code` 阶段。

本文建立在以下前提上：

- `Input` 已完成独立重构
- `Refine` 已完成独立重构
- `Design` 已完成独立重构
- `Plan` 已完成 V2 重构，并正式产出 `plan-work-items.json`、`plan-execution-graph.json`、`plan-validation.json`

如果本文与代码不一致，以代码为准；如果后续按本文实施，落地时应同步移除旧 `code` 逻辑和旧 `plan-execution.json` 假设。

## Executive Summary

- `Code` 是独立于 `Plan` 的执行阶段，不再兼容当前旧 `code.py` 的单文件混合逻辑。
- `Code` 的唯一上游基线是 `Design Bundle + Plan Bundle`，而不是 `plan.md + plan-execution.json` 的旧组合。
- `Code` 的正式职责是：
  - 基于 `Plan` work items 生成可执行 repo batch
  - 驱动 worktree 内实现 / 验证
  - 记录 repo 级结果、diff、验证结论和失败原因
  - 向 Web UI 暴露稳定的进度与结果契约
- `Code` 采用与 `Refine / Design / Plan` 对齐的组织方式：
  - `engine` 归一化输入与执行编排
  - `prompts` 管理 agent prompt
  - `artifacts` 记录结构化过程和结果
- `code.log` 和 `code-result.json` 不再是唯一真相源；`code-dispatch.json`、`code-progress.json`、repo 级结果文件才是正式 source of truth。

## Goals

`Code` 需要回答的问题是：

1. 这次应先执行哪些 repo batch，哪些 repo 只做验证？
2. 每个 repo 当前对应哪些 work items？
3. 哪些 batch 可立即运行，哪些被依赖阻塞？
4. agent 应该基于哪些结构化输入执行？
5. 每个 repo 的验证结果、diff、失败原因、建议动作是什么？
6. Web UI 该如何稳定展示 Code 阶段的执行进度？

一句话：

- `Plan` owns execution truth
- `Code` owns execution runtime truth

## Non-Goals

`Code` 不应该：

- 重新做 repo discovery
- 重新判定 repo 是否 in scope
- 重新拆 work items
- 重新推导 repo 间依赖顺序
- 依赖 `plan.md` 自由文本去猜执行边界
- 继续以旧 `plan-execution.json` 作为主要输入
- 把 Web UI 的“repo 卡片”当成后端真实执行模型

## Why Old Code Must Be Replaced

当前旧实现存在几个根本问题：

1. 输入契约错误
   - 仍主要消费 `plan-execution.json`
   - 无法正式接住 `Plan V2` 的 work items / graph / validation

2. 执行模型过粗
   - 当前基本是 repo 级 `start code`
   - 但真正的上游 truth 已经是 work item graph

3. service 与 engine 混在一起
   - `src/coco_flow/services/tasks/code.py` 同时承担：
     - 状态流转
     - 输入解析
     - worktree 创建
     - agent prompt
     - verify
     - diff/commit 持久化
   - 这与 `Refine / Design / Plan` 的阶段化结构不一致

4. Web UI 无稳定 typed contract
   - 前端主要靠 `repo.status`、`code.log`、`code-result.json`
   - 无法稳定表达批次、阻塞、验证、verify-only repo 等状态

因此 `Code V2` 的目标不是“在旧 code.py 上继续叠逻辑”，而是直接定义新的阶段契约和新 engine 结构。

## Stage Positioning

正式责任切分应当是：

1. `Input`
   - 落原始输入

2. `Refine`
   - 澄清需求与边界

3. `Design`
   - 明确 repo / system truth

4. `Plan`
   - 形成 execution truth

5. `Code`
   - 消费 execution truth，形成 runtime truth

6. `Archive`
   - 汇总与收口

短版定义：

- `Plan` decides what should run
- `Code` records what actually ran

## Plan -> Code Boundary

这是本阶段最重要的边界。

### `Plan` 的终点

`Plan` 结束时，系统必须已经明确：

- 哪些 work items 存在
- 每个 work item 属于哪个 repo
- work item 之间的依赖关系
- 每个 work item 的 change scope
- 每个 work item 的 done definition
- 每个 work item 的 verification steps

这些问题在 `Code` 里不能重新 adjudicate。

### `Code` 的起点

`Code` 的起点应该是：

- work items 已归一化
- execution graph 已归一化
- validation contract 已归一化
- repo binding 已完成

`Code` 只需要继续回答：

- 当前有哪些 runnable batches
- 执行结果如何
- 是否通过验证
- 失败类型是什么
- 下一步建议动作是什么

### 明确禁止的行为

`Code` 禁止做以下事情：

- 因为 agent 想改某个文件，就把 work item 边界扩大
- 因为验证不通过，就在 `Code` 阶段偷偷改 `Plan` graph
- 因为 repo 方便操作，就忽略 `validate_only` / `reference_only` 语义
- 以 repo 级 diff 反向覆盖 `Plan` 的 work item truth

如果 `Code` 发现 `Plan` artifact 明显不完整，正确做法是：

- 在 `code-result.json` 与 `code-progress.json` 中记录结构化错误
- 将任务标记为 `failed`
- 要求返回 `Plan` 修复

而不是在 `Code` 阶段自行补 plan truth。

## Input Contract

`Code` 消费的是 `Code Bundle`。

### Required Inputs

最小必需输入：

1. `design-repo-binding.json`
2. `plan-work-items.json`
3. `plan-execution-graph.json`
4. `plan-validation.json`
5. `plan-result.json`
6. `repos.json`
7. `task title`

### Strongly Recommended Inputs

强推荐输入：

1. `design.md`
2. `plan.md`
3. `prd-refined.md`
4. `task.json`

这些输入仅作为辅助上下文，不是 primary truth。

### Inputs That Must Be Treated As Primary Truth

以下输入是 `Code` 的 primary truth：

1. `design-repo-binding.json`
2. `plan-work-items.json`
3. `plan-execution-graph.json`
4. `plan-validation.json`

### Inputs That Must Not Become The Main Baseline

以下内容不能成为 `Code` 主基线：

- 旧 `plan-execution.json`
- 旧 `plan-scope.json`
- `plan.md` 自由文本
- `design.md` 自由文本
- 本地 heuristics 推出来的 task order

## Code Bundle

推荐的 `Code Bundle` 为：

```text
Code Bundle
├── title
├── task metadata
├── design_repo_binding_payload
├── plan_work_items_payload
├── plan_execution_graph_payload
├── plan_validation_payload
├── plan_result_payload
├── repos_runtime_payload
├── design_markdown
├── plan_markdown
└── refined_markdown
```

controller 先把这些输入读入并归一化，再进入 dispatch / execute / verify 步骤。

## Execution Model

`Code` 内部正式执行单元不应该是“裸 repo”，而应该是 `repo execution batch`。

### 为什么不是 work item 直接执行

worktree、branch、commit、diff、最小构建验证都天然是 repo 级。

因此：

- 上游 execution truth 以 work item 为中心
- `Code` runtime truth 应归一化为 repo batch

### Repo Execution Batch

每个 batch 需要回答：

- `repo_id`
- `mode`
  - `apply`
  - `verify_only`
- `work_item_ids`
- `depends_on_batches`
- `change_scope`
- `verify_rules`
- `done_definition`
- `is_runnable`
- `blocked_by`

### Batch 归一化规则

建议规则：

1. `must_change` / `co_change` repo
   - 生成 `apply` batch

2. `validate_only` repo
   - 默认生成 `verify_only` batch

3. `reference_only` repo
   - 不生成 runnable batch
   - 仅作为上下文 reference

4. 一个 repo 下多个 work items
   - 默认合并为一个 repo batch
   - `work_item_ids` 保留细粒度引用

5. batch 依赖
   - 由 graph 中跨 repo 的 work item dependency 归一化而来

## Output Contract

`Code` 正式输出三类 truth：

1. dispatch truth
2. runtime progress truth
3. repo execution result truth

### `code-dispatch.json`

这是 `Code` 阶段启动时归一化后的正式 dispatch 结果。

建议结构：

```json
{
  "batches": [
    {
      "id": "B1",
      "repo_id": "demo",
      "mode": "apply",
      "scope_tier": "must_change",
      "work_item_ids": ["W1", "W2"],
      "depends_on_batches": [],
      "blocked_by_batches": [],
      "change_scope": ["main.go"],
      "verify_rules": ["go build ./..."],
      "done_definition": ["实现 two sum", "最小构建通过"],
      "status": "ready"
    }
  ]
}
```

### `code-progress.json`

这是 Web UI 的主要 typed 数据源。

建议结构：

```json
{
  "task_id": "2026...",
  "status": "coding",
  "current_batch_id": "B1",
  "completed_batches": ["B0"],
  "failed_batches": [],
  "blocked_batches": [],
  "repo_progress": [
    {
      "repo_id": "demo",
      "batch_id": "B1",
      "mode": "apply",
      "status": "running",
      "work_item_ids": ["W1", "W2"],
      "failure_type": "",
      "last_event": "repo_verify_ok"
    }
  ]
}
```

### `code-result.json`

这是 task 级收口结果。

建议至少包含：

- `status`
- `task_id`
- `batch_count`
- `completed_batch_count`
- `failed_batch_count`
- `repo_results`
- `next_actions`

### Repo-Level Artifacts

每个 repo 推荐产出：

- `code-results/<repo>.json`
- `code-logs/<repo>.log`
- `code-verify/<repo>.json`
- `diffs/<repo>.json`
- `diffs/<repo>.patch`

其中：

- `code-results/<repo>.json` 记录 repo 最终结果
- `code-verify/<repo>.json` 记录验证详情与 verify-only 结果
- diff artifacts 继续保留

## Engine Structure

建议新目录：

```text
src/coco_flow/engines/code/
├── __init__.py
├── source.py
├── models.py
├── dispatch.py
├── execute.py
├── verify.py
├── persist.py
├── prompts.py
└── pipeline.py

src/coco_flow/prompts/code/
├── __init__.py
├── execute.py
└── retry.py
```

### 模块职责

- `source.py`
  - 构建 `CodePreparedInput`
- `models.py`
  - batch、progress、result 数据模型
- `dispatch.py`
  - 从 plan artifacts 归一化出 repo batches
- `execute.py`
  - native/local 执行与 worktree 准备
- `verify.py`
  - 语言相关最小验证
- `persist.py`
  - task / repo artifact 落盘
- `pipeline.py`
  - controller 主流程

## Pipeline

建议 pipeline：

1. `prepare`
   - 读取 Code Bundle

2. `dispatch`
   - 归一化出 repo batches
   - 写入 `code-dispatch.json`

3. `select runnable batches`
   - 过滤掉 blocked batches
   - 生成初始 `code-progress.json`

4. `execute repo batch`
   - `apply` batch：准备 worktree、执行 agent、收集 changed files
   - `verify_only` batch：执行验证，不要求产出代码 diff

5. `verify`
   - 基于 batch verify rules 执行最小验证

6. `persist`
   - 写 repo result / repo log / repo verify / diff
   - 更新 `code-progress.json`

7. `finalize`
   - 写 `code-result.json`
   - 同步 task/repo status

## Status Model

task 级状态仍可保持：

- `planned`
- `coding`
- `partially_coded`
- `coded`
- `failed`
- `archived`

但 `Code` 内部 batch 状态需要更细：

- `ready`
- `blocked`
- `running`
- `verify_running`
- `completed`
- `failed`
- `skipped`

repo 级状态映射规则：

- 有 runnable batch 正在执行 -> `coding`
- repo batch 全完成 -> `coded`
- repo batch 失败 -> `failed`
- 仅有 `verify_only` batch 且验证通过 -> `coded`

## Web UI Contract

`Code` 页不应再只是“仓库列表 + code.log”。

建议拆成四块：

1. `Code Progress`
   - 总 batch 数
   - 当前波次
   - 已完成 / 失败 / 阻塞

2. `Repo Queue`
   - repo、mode、scope_tier、当前状态、阻塞原因

3. `Execution Detail`
   - 当前 repo 对应的 work items
   - change scope
   - done definition
   - verify rules

4. `Result Tabs`
   - `结果`
   - `验证`
   - `Diff`
   - `日志`

### UI Action Rules

建议按钮语义：

- `推进下一波`
- `执行当前 repo`
- `执行验证`
- `重试`
- `归档`

其中：

- `validate_only` repo 显示 `执行验证`
- `reference_only` repo 不显示执行按钮

## Migration Strategy

推荐按以下顺序落地：

1. 新建 `docs/code-v2-design.md`
2. 落 `engines/code/` 与 `prompts/code/`
3. 将 `services/tasks/code.py` 改为薄壳
4. 停止 `Code` 消费旧 `plan-execution.json`
5. 给 `task_detail` 增加 typed `code_progress` / `code_batches`
6. 重做 Web UI `Code` Stage
7. 删除旧 code 内联 prompt / 旧调度假设

## Removal Scope

这次重构后，以下旧假设应被移除：

- `load_plan_execution_artifact()` 只读旧 `plan-execution.json`
- `select_repo_tasks()` 以旧 task 列表驱动 code
- 基于旧 `target_system_or_repo` 的 repo 排序
- Web UI 只靠 `repo.status` 猜 code 阶段
- `local code` 仅“准备 worktree”的伪 fallback

## Open Questions

本次落地建议先明确以下决策：

1. `Code` 是否支持一次只执行一个 runnable batch
   - 建议：支持

2. `code-all` 是否保留
   - 建议：保留，但其语义变为“依次推进当前 runnable batches，遇错停止”

3. `verify_only` repo 是否允许生成 commit
   - 建议：不允许；默认只记录验证结果

4. `local code` 是否保留完整 fallback
   - 建议：先保留最小结构化 fallback，但不要再只是 prepare worktree

## Final Position

`Code V2` 的核心不是“让 agent 去改代码”，而是：

- 让 `Code` 正式消费 `Plan V2`
- 让 repo 级执行与 work item truth 接上
- 让 Web UI 有稳定的 progress/result contract

只有这样，`Design -> Plan -> Code` 才能真正形成一条结构化流水线，而不是在 `Code` 阶段重新退回自由文本和 repo 级 heuristics。
