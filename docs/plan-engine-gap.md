# Plan Engine Gap

本文记录当前 `plan` 引擎和目标 `design.md + plan.md` 结构之间的差距，以及建议的迁移顺序。

如果本文与代码不一致，以代码为准。

## 这是不是 spec

是，有明显的 `spec` 味道。

但更准确地说，这份内容不是“完整实现 spec”，而是两类东西的组合：

- 产物契约 spec
- 引擎迁移 spec

也就是说，它主要回答：

- `design.md` 和 `plan.md` 最终应该长成什么样
- 当前引擎为了产出这种结构，最少要改哪些硬点

它还没有细化到：

- 每个函数怎么改
- 每个 prompt 怎么写
- 每个数据结构逐字段的最终代码定义

所以它更像“目标契约和迁移蓝图”，而不是实现细案。

## 目标状态

当前目标已经基本明确：

### `design.md`

面向研发的目标章节：

1. `系统改造点`
2. `方案设计`
3. `多端协议是否有变更`
4. `存储&&配置是否有变更`
5. `是否有实验，实验怎么涉及`
6. `给 QA 的输入`
7. `人力评估`

其中 P0 核心是：

- `系统改造点`
- `方案设计`

### `plan.md`

面向研发和后续 `code` 阶段的目标章节：

1. `实施策略`
2. `任务拆分`
3. `执行顺序`
4. `验证计划`
5. `阻塞项与风险`

其中核心是：

- `任务拆分`
- `执行顺序`

## 当前 plan 引擎的现实状态

当前引擎更接近：

- 基于 refined PRD、repo research、candidate files 和 complexity
- 生成一份“方案摘要 + 文件候选 + 任务列表”的混合文档

它还不是：

- 一套显式区分 `design.md` 和 `plan.md` 职责的双产物引擎

这意味着当前不是“差几个标题”，而是差一层明确的 schema 和编排分工。

## 差距一：`refine -> plan` 的输入 schema 还是旧的

当前 `plan` 仍然围绕旧的 refined 结构工作：

- `summary`
- `features`
- `boundaries`
- `business_rules`
- `open_questions`

但当前目标 refine 结构已经收敛成：

- `变更范围`
- `非目标`
- `关键约束`
- `验收标准`
- `待确认项`

这意味着如果不先改输入层，后面的 `design` 和 `plan` 仍然会继续围绕旧字段构建。

### 需要的硬改动

至少需要：

- 替换 `RefinedSections` 的正式字段定义
- 保留一段新旧标题兼容映射期
- 让 research / complexity / render 都消费新结构

## 差距二：缺少 `design` 和 `plan` 的正式结构模型

当前 `PlanBuild` 是一份通用构建上下文，没有把设计产物和执行产物正式拆开。

这会导致：

- renderer 只能拼 Markdown
- generator 只能输出宽泛文本块
- verifier 只能做粗粒度校验

### 需要的硬改动

建议新增至少三类模型：

- `DesignSections`
- `PlanExecutionSections`
- `PlanTaskSpec`

必要时继续拆出：

- `SystemChange`
- `SystemDependency`
- `ProtocolChange`
- `StorageConfigChange`
- `ExperimentChange`

## 差距三：当前 AI 输出 schema 太薄

当前 native plan 的 AI 输出本质上只有 5 段文本：

- 实现概要
- 候选文件
- 实施步骤
- 风险说明
- 验证补充

这套 schema 只能支撑“混合型方案摘要”，支撑不了新的目标结构。

尤其装不下下面这些内容：

- 系统改造点
- 分系统改造
- 系统依赖关系
- 协议 / 存储 / 配置 / 实验专项判断
- QA 输入
- 人力评估
- 结构化任务拆分
- 执行顺序

### 需要的硬改动

要把 AI 输出从“多段 marker 文本”升级为“结构化 design / plan 对象”。

## 差距四：renderer 仍然围绕旧文档骨架

当前 `build_design()` 和 `build_plan()` 仍然围绕下面这些中间概念组织：

- 背景与目标
- Plan Scope
- Knowledge Brief
- 方案摘要
- 实现概要
- 拟改文件
- 任务列表
- 验证建议

这些内容本身不是错的，但它们并不等于当前确定的目标章节。

### 需要的硬改动

需要重写：

- `build_design()`
- `build_plan()`

让它们围绕新的目标章节直接渲染，而不是围绕中间调研视角组织内容。

## 差距五：任务拆分逻辑还是“按目录切”，不是“按实施依赖切”

当前任务生成逻辑更接近：

- 先找 candidate files
- 再按 repo / directory 归组
- 顺着 repo 或目录串依赖

这个策略在简单需求下可用，但它表达的是：

- 文件邻近关系

而不是：

- 系统职责关系
- 改造依赖关系
- 实施顺序关系

### 需要的硬改动

`PlanTaskSpec` 至少要显式承接这些字段：

- `target_system_or_repo`
- `serves_design_changes`
- `depends_on`
- `parallelizable_with`
- `change_scope`
- `actions`
- `done_definition`
- `verify_rule`

这才足以支撑后续 `code` 阶段稳定消费。

## 差距六：当前编排把 design 和 execution 混在一个 generator 里

当前 native 流程更像：

1. research
2. scope extraction
3. generator
4. verify
5. render

但目标状态已经很明确地要求拆成两层产物：

- 设计层
- 执行层

### 需要的硬改动

建议未来编排至少拆成：

1. `research`
2. `design scope`
3. `design generator`
4. `design verify`
5. `task planning generator`
6. `task planning verify`
7. `render`

这样才能避免 `design` 和 `plan` 长期混在一套宽泛 prompt 里互相污染。

## 差距七：专项变更信号还没有被正式建模

当前目标结构里，有几类章节是专项检查项：

- 多端协议变更
- 存储 / 配置变更
- 实验设计
- QA 输入
- 人力评估

这些内容目前没有独立 research 结果，也没有稳定字段承接。

### 需要的硬改动

至少需要两层补充：

- research 层增加专项信号抽取
- schema 层增加对应字段

否则这些章节只能继续靠 LLM 自由发挥，不会稳定。

## 建议迁移顺序

如果按务实顺序推进，建议这样拆：

### 第一阶段：先定输入和产物契约

1. 改 `refine -> plan` 输入 schema
2. 明确定义 `DesignSections` / `PlanExecutionSections` / `PlanTaskSpec`
3. 重写 renderer，让输出章节先对齐目标文档结构

这一步的目标不是“质量最优”，而是先把文档契约定住。

### 第二阶段：再改生成和验证

4. 重写 generator 输出 schema
5. 拆分 design verifier 和 task-plan verifier
6. 让 AI 输出围绕正式对象而不是宽泛文本块

这一步的目标是让质量和稳定性跟上新契约。

### 第三阶段：补系统级研究和专项信号

7. 增加系统职责 / 系统依赖 research
8. 增加协议 / 存储 / 配置 / 实验信号抽取
9. 增加 QA 输入和人力评估的稳定生成依据

这一步的目标是让文档从“结构对了”进化到“内容也稳”。

## 一句话结论

当前 `plan` 引擎离目标 `design.md + plan.md` 结构，差的不是几个标题，而是：

- 输入 schema
- 产物模型
- AI 输出契约
- renderer
- 任务拆分逻辑
- design / execution 分阶段编排
- 专项变更信号建模

这已经是一个小型迁移 spec 了，但仍然属于“契约与迁移层”的 spec，还不是最终实现细案。

如果要继续往前推到字段级契约，另见
[`docs/plan-schema-spec.md`](docs/plan-schema-spec.md)。

如果要继续往前推到第一批代码实施切分，另见
[`docs/plan-implementation-slices.md`](docs/plan-implementation-slices.md)。
