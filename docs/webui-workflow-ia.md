# Task Workflow UI Information Architecture

本文定义当前 `coco-flow` WebUI 在 `task detail` 场景下的信息架构草图。目标不是重做一套通用控制台，而是把现有任务页收敛成一个真正的 `workflow workbench`。

如果本文与代码不一致，以代码为准。

当前相关代码：

- 路由入口：`web/src/routes/tasks.tsx`
- 主行动区：`web/src/components/task-primary-action.tsx`
- 阅读工作台：`web/src/components/task-workbench.tsx`
- 数据类型：`web/src/api.ts`

## 设计目标

当前任务页已经具备：

- task 列表
- 主行动区
- 文档 / 日志 / 结果 / diff 工作台
- repo 上下文面板

但它更像“artifact browser + action panel”，还不是“workflow 页面”。

这一版信息架构要解决 4 个问题：

1. 用户一眼看出 task 当前走到哪一步
2. 用户一眼看出下一步该做什么
3. 用户一眼看出为什么卡住
4. 多 repo 场景下，用户一眼看出哪个 repo 在跑、哪个 repo 被阻塞

非目标：

- 不做通用项目管理首页
- 不做多人协作面板
- 不做完整流程编排编辑器
- 不把所有 artifact 都升成一级信息

## 页面定位

`/tasks/:taskId` 应该被定义为：

- `Task Workflow Workbench`

不是：

- 文档查看页
- 日志查看页
- 仓库结果列表页

这里的核心原则是：

- 页面先表达“阶段”
- 再表达“动作”
- 最后才是“artifact”

## 一级信息架构

任务详情页建议固定为 5 个区块，从上到下：

1. `Task Header`
2. `Pipeline Strip`
3. `Current Stage CTA`
4. `Stage Workbench`
5. `Repo Execution Lane`

当前左侧任务列表继续保留，但详情页内部不再以“tab + artifact”作为第一心智。

## 页面草图

```text
+----------------------------------------------------------------------------------+
| Task Header                                                                      |
| title | task id | status | repo count | updated at                               |
+----------------------------------------------------------------------------------+
| Pipeline Strip                                                                   |
| Input -> Refine -> Design -> Plan -> Code -> Archive                             |
| each node: state / key artifact / updated at / blocked reason                    |
+--------------------------------------+-------------------------------------------+
| Current Stage CTA                    | Stage Summary                             |
| next action                          | current stage narrative                    |
| primary button                       | risk / blocker / next repo                 |
| reset / retry / archive              |                                           |
+--------------------------------------+-------------------------------------------+
| Stage Workbench                                                                  |
| stage-aware content, not generic artifact-first                                  |
| Refine: source vs refined                                                        |
| Design: design.md + plan.log                                                     |
| Plan: plan.md + structured tasks                                                 |
| Code: code.log + result + diff summary                                           |
+----------------------------------------------------------------------------------+
| Repo Execution Lane                                                              |
| repo-a done | repo-b running | repo-c blocked by repo-b | repo-d pending         |
| expandable repo cards with result / diff / retry / reset                         |
+----------------------------------------------------------------------------------+
```

## 区块职责

### 1. `Task Header`

职责：

- 提供 task 全局身份信息
- 提供最小但稳定的顶部概览

展示内容：

- `title`
- `task_id`
- `status`
- `repo_count`
- `updated_at`
- `source_type`

不放什么：

- 不放大按钮
- 不放文档 tab
- 不放 repo 明细

建议组件：

- `TaskHeaderCard`

依赖数据：

- `TaskRecord.id`
- `TaskRecord.title`
- `TaskRecord.status`
- `TaskRecord.updatedAt`
- `TaskRecord.repos`

### 2. `Pipeline Strip`

职责：

- 把 task 进度从“状态字段”变成“可感知流程”
- 明确当前节点、已完成节点、失败节点、阻塞节点

建议节点：

1. `Input`
2. `Refine`
3. `Design`
4. `Plan`
5. `Code`
6. `Archive`

说明：

- 后端命令虽然还是 `tasks plan`
- 但 UI 上应拆成 `Design` 和 `Plan` 两个节点，因为当前产物已经是 `design.md + plan.md`

每个节点展示：

- 节点名
- `pending / running / done / failed / blocked`
- 对应关键 artifact
- 最近更新时间
- 如有阻塞，展示一句原因

建议组件：

- `TaskPipelineStrip`
- `PipelineNode`

依赖数据：

- `TaskRecord.status`
- `TaskRecord.timeline`
- `TaskRecord.nextAction`
- `TaskRecord.artifacts`
- repo failure 信息

### 3. `Current Stage CTA`

职责：

- 只回答一个问题：现在该做什么

展示内容：

- 当前阶段标题
- 当前阶段简述
- 主按钮
- 次按钮
- 阻塞信息
- 推荐下一步

按钮策略：

- `Refine` 阶段：重新 refine / 编辑 `prd.source.md`
- `Design/Plan` 阶段：开始或重跑 plan
- `Code` 阶段：
  - 单 repo：开始实现 / 重试实现
  - 多 repo：推进下一个可执行 repo / 依次推进剩余 repo
- `Archive` 阶段：归档

建议组件：

- 由现有 `TaskPrimaryAction` 演化成 `CurrentStageActionCard`

当前组件映射：

- 可复用现有 `TaskPrimaryAction`
- 但职责要从“全局动作台”收敛成“当前阶段动作台”

依赖数据：

- `TaskRecord.status`
- `TaskRecord.nextAction`
- `TaskRecord.repoNext`
- `TaskRecord.repos`

### 4. `Stage Workbench`

职责：

- 展示当前阶段最相关的信息
- artifact 仍可切换，但默认视角必须由阶段驱动

原则：

- 不再让用户先想“我要点 docs 还是 logs”
- 而是先看“当前阶段应该默认给我什么”

#### Refine 视图

默认内容：

- `prd.source.md`
- `prd-refined.md`
- `refine.log`

推荐布局：

- 左：原始需求
- 右：refine 后结果
- 下：log / verify 摘要

建议组件：

- `RefineWorkbench`

#### Design 视图

默认内容：

- `design.md`
- `plan.log` 中与 design 相关的最新过程

建议组件：

- `DesignWorkbench`

#### Plan 视图

默认内容：

- `plan.md`
- 结构化任务拆分摘要
- 执行顺序摘要

建议组件：

- `PlanWorkbench`

后续增强：

- 直接消费 `plan-execution.json`
- 不只展示 markdown

#### Code 视图

默认内容：

- `code.log`
- `code-result.json`
- `diff.json`
- `diff.patch`

建议组件：

- `CodeWorkbench`

当前组件映射：

- 由现有 `TaskWorkbench` 演化
- 但 `docs / logs / result / diff` 从一级心智降级成次级切换

### 5. `Repo Execution Lane`

职责：

- 在多 repo 场景下，把 code 阶段从“多个仓库卡片”升级成“执行流水线”

展示内容：

- repo 顺序
- repo 状态
- `blocked by ...`
- `depends_on`
- 当前可执行前缀
- 每个 repo 的主动作

推荐状态：

- `pending`
- `ready`
- `running`
- `done`
- `failed`
- `blocked`

推荐表达：

```text
repo-a  done
repo-b  running
repo-c  blocked by repo-b
repo-d  pending
```

建议组件：

- `RepoExecutionLane`
- `RepoExecutionNode`
- `RepoExecutionDetailsDrawer`

当前组件映射：

- 现有 `RepoContextPanel` 适合保留
- 但它应降级成“选中 repo 的详情区”
- 不再承担“表达 repo 执行顺序”的职责

依赖数据：

- `TaskRecord.repos`
- `TaskRecord.repoNext`
- repo `failureType / failureHint / failureAction`
- 后续建议直接补 `planExecution` typed data 给前端

## 左侧任务列表建议

左侧列表仍保留，但卡片信息建议更 workflow 化。

每条 task 卡片建议固定展示：

- `title`
- `task_id`
- 当前阶段
- `repo progress`
- 是否 `blocked`
- 是否 `failed`
- 推荐下一步

建议视觉摘要：

```text
竞拍讲解卡状态提示
Code · 2/4 repos done · blocked
next: 先完成 live-api
```

建议组件：

- 当前 `TaskListItemCard` 保留
- 补充 `stage label / repo progress / blocked hint`

## 组件分层建议

建议按 3 层组织：

### 路由容器层

职责：

- 拉取 task 数据
- 控制轮询
- 控制用户动作和刷新

组件：

- `TaskDetailPage`

### workflow 表达层

职责：

- 只表达任务阶段、repo 阶段、下一步

组件：

- `TaskHeaderCard`
- `TaskPipelineStrip`
- `CurrentStageActionCard`
- `RepoExecutionLane`

### workbench 层

职责：

- 展示当前阶段的 artifact 和结果

组件：

- `RefineWorkbench`
- `DesignWorkbench`
- `PlanWorkbench`
- `CodeWorkbench`
- `RepoExecutionDetailsDrawer`

## 数据契约建议

当前前端已经有：

- `TaskRecord.status`
- `TaskRecord.nextAction`
- `TaskRecord.repoNext`
- `TaskRecord.timeline`
- `TaskRecord.repos`
- `TaskRecord.artifacts`

这足够先做第一版 workflow UI。

但为了把 `Plan` 和 `Code` 真正做成流水线，建议后续 API 增加 typed 字段：

- `taskStage`
- `designStatus`
- `planStatus`
- `codeStatus`
- `repoExecution`
- `planExecution`

其中最关键的是：

- `planExecution`
  直接暴露 `plan-execution.json` 的结构化视图

这样前端就不用反复从 markdown 和 repo failure 中反推流程。

## 落地顺序

建议按 4 步推进，不要一次性全改。

### 第一批

- task detail 顶部新增 `Pipeline Strip`
- 保留现有 workbench 和 repo panel

### 第二批

- 把 `TaskPrimaryAction` 改造成 `Current Stage CTA`
- 让按钮和文案完全围绕当前阶段组织

### 第三批

- 把 `TaskWorkbench` 改造成 stage-aware workbench
- 默认视图由阶段驱动，而不是由 artifact 类型驱动

### 第四批

- 增加 `Repo Execution Lane`
- 让多 repo `Code` 阶段真正表现成流水线

## 最终判断

对于当前 `coco-flow`，WebUI 最合理的方向不是继续强化“artifact 阅读器”，而是转成：

- `Task Workflow Workbench`

也就是：

- 顶部看阶段
- 中间看当前节点
- 底部看 repo 执行链路

文档、日志、结果、diff 仍然存在，但它们应该成为 workflow 的支撑材料，而不是页面的第一心智。
