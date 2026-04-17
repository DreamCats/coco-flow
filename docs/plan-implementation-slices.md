# Plan Implementation Slices

本文把 `docs/plan-schema-spec.md` 进一步落成“实施切分”，明确第一批代码先改哪些文件、按什么顺序改，以及哪些改动属于第一阶段必须完成的硬切分。

如果本文与代码不一致，以代码为准。

## 先给结论

当前最合理的推进方式是：

- `plan` 命令不拆
- 引擎内部先拆
- 第一批先改模型和 renderer
- 第二批再改 generator / verifier
- 第三批再补 research 和 `code` 消费

换句话说，先把“产物契约”落地，再提升“内容质量”。

## 命令策略

当前不建议把外部命令拆成 `design` 和 `plan` 两个 stage。

建议保持：

- `coco-flow tasks plan <task_id>`

内部再逐步拆成：

- design generation
- execution planning

原因：

- 避免先触发 task 状态机、API、UI 和 `prd run` 的连锁改动
- 先把引擎内部契约稳定下来
- 等设计层和执行层真正成熟后，再决定是否暴露额外入口

## 实施总顺序

建议按 5 个 slice 推进：

1. `输入 schema 切换`
2. `renderer 重构`
3. `plan 内部模型落地`
4. `generator / verifier 重构`
5. `research / code 消费补齐`

## Slice 1：输入 schema 切换

### 目标

让 `plan` 正式消费新版 `RefinedSections`，同时保留旧结构兼容映射。

### 主要文件

- [src/coco_flow/engines/plan_models.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_models.py)
- [src/coco_flow/engines/plan_research.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_research.py)
- [src/coco_flow/engines/plan_knowledge.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_knowledge.py)
- [src/coco_flow/engines/plan_render.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_render.py)
- [src/coco_flow/engines/plan.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan.py)

### 具体改动

1. 在 `plan_models.py` 中替换 `RefinedSections`
2. 在 `plan_research.py` 中重写 `parse_refined_sections(...)`
3. 在 `plan_research.py` 中把 `research_codebase(...)`、`infer_search_terms(...)`、`score_complexity(...)` 改成消费：
   - `change_scope`
   - `non_goals`
   - `key_constraints`
   - `acceptance_criteria`
   - `open_questions`
4. 在 `plan_knowledge.py` 中把 knowledge 召回术语的输入切到新字段
5. 在 `plan_render.py` 中把所有直接依赖旧字段的 helper 改成新字段

### 为什么先做这一步

因为如果输入还停在旧 schema，后面的 `design` / `plan` 新结构只能继续搭在旧字段之上，最后会出现“文档章节换了，内部语义没换”的假升级。

## Slice 2：renderer 重构

### 目标

先让 `design.md` 和 `plan.md` 的最终章节骨架对齐目标结构，即使内容暂时仍然部分依赖旧 research / AI 输出。

### 主要文件

- [src/coco_flow/engines/plan_render.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_render.py)

### 具体改动

1. 重写 `build_design(...)`
2. 重写 `build_plan(...)`
3. 补出新的 renderer helper，围绕下面两套结构：

`design.md`
- 系统改造点
- 方案设计
- 多端协议是否有变更
- 存储&&配置是否有变更
- 是否有实验，实验怎么涉及
- 给 QA 的输入
- 人力评估

`plan.md`
- 实施策略
- 任务拆分
- 执行顺序
- 验证计划
- 阻塞项与风险

4. 去掉当前以中间视角为主的章节骨架依赖：
   - `Plan Scope`
   - `Knowledge Brief`
   - `实现概要`
   - `拟改文件`
   - `验证建议`

### 为什么这一步在 generator 之前

因为 renderer 决定最终对外契约。  
先把输出章节定住，后面 generator 和 verifier 才有稳定目标，不然 prompt 还会继续围绕旧文档形态优化。

## Slice 3：plan 内部模型落地

### 目标

把 `DesignSections`、`PlanExecutionSections`、`PlanTaskSpec` 这些结构真正落到代码里，结束“所有信息都塞在 `PlanBuild + PlanAISections` 里”的状态。

### 主要文件

- [src/coco_flow/engines/plan_models.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_models.py)
- [src/coco_flow/engines/plan.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan.py)
- [src/coco_flow/engines/plan_render.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_render.py)

### 具体改动

1. 在 `plan_models.py` 中新增：
   - `DesignSections`
   - `PlanExecutionSections`
   - `PlanTaskSpec`
   - `SystemChange`
   - `SystemDependency`
   - `CriticalFlow`
   - `ProtocolChange`
   - `StorageConfigChange`
   - `ExperimentChange`
   - `StaffingEstimate`
2. 让 `PlanEngineResult` 继续只暴露 Markdown，但内部构建先走结构对象
3. 把当前 `PlanTask` 过渡为 `PlanTaskSpec`
4. 在 `plan.py` 中增加面向结构对象的 build 组装步骤

### 这一步的重点

不是一次把所有字段都高质量填满，而是先让类型系统承接这些对象，让 renderer 和后续 generator 都有正式挂点。

## Slice 4：generator / verifier 重构

### 目标

把 native plan 从“一个 generator 输出 5 段文本”升级成“设计层 + 执行层”的双阶段生成。

### 主要文件

- [src/coco_flow/engines/plan_generate.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_generate.py)
- [src/coco_flow/engines/plan.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan.py)
- [src/coco_flow/engines/plan_models.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_models.py)

### 具体改动

1. 缩小 `PlanAISections` 的角色，最终用新的结构对象替代
2. 把当前：
   - `build_plan_scope_prompt`
   - `build_plan_prompt`
   - `build_plan_verify_prompt`
   拆成更明确的两组：
   - design 生成 / 校验
   - execution plan 生成 / 校验
3. 让 verifier 不再只检查：
   - summary
   - steps
   - risks
   - candidate_files
   而是检查：
   - design 章节是否齐
   - 系统改造点与分系统改造是否对齐
   - 依赖关系是否自洽
   - `PlanTaskSpec` 是否具备最少执行字段

### 为什么不是第一批先改 prompt

因为 prompt 是最容易反复重写的层。  
在模型和 renderer 还没稳定前，先重写 prompt，后面基本还要再来一轮。

## Slice 5：research / code 消费补齐

### 目标

让新结构真正可持续产出，而不是只靠 LLM 临场发挥。

### 主要文件

- [src/coco_flow/engines/plan_research.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_research.py)
- [src/coco_flow/engines/plan_knowledge.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_knowledge.py)
- [src/coco_flow/services/tasks/code.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/services/tasks/code.py)

### 具体改动

1. `plan_research.py` 增加系统级 research 信号：
   - system / repo responsibilities
   - upstream / downstream clues
   - protocol / config / experiment hints
2. `plan_knowledge.py` 更偏向输出：
   - 系统边界
   - 稳定规则
   - 验证要点
3. `code.py` 后续逐步从 prose 依赖切到 `PlanTaskSpec`

### 这一阶段的意义

前四个 slice 解决的是“结构和主链路”。  
这一阶段解决的是“内容稳定性”和“下游真正消费结构对象”。

## 第一批最小落地集合

如果只做第一批、且希望尽快看到结果，我建议最小集合是：

1. `plan_models.py`
   改 `RefinedSections`，新增目标对象 skeleton
2. `plan_research.py`
   改 `parse_refined_sections(...)` 和关键消费点
3. `plan_render.py`
   重写 `build_design(...)` / `build_plan(...)`
4. `plan.py`
   调整 `prepare_plan_build(...)` 和 build 流程接线

先不动：

- `services/tasks/plan.py`
- API
- UI
- 命令入口
- `code.py` 的正式消费改造

这是最小闭环，因为：

- 输入换了
- 输出换了
- 主流程还能继续跑
- 外部接口不变

## 推荐的具体顺序

更细一点，建议按这个顺序动代码：

1. [plan_models.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_models.py)
2. [plan_research.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_research.py)
3. [plan_knowledge.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_knowledge.py)
4. [plan_render.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_render.py)
5. [plan.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan.py)
6. [plan_generate.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines/plan_generate.py)
7. [services/tasks/code.py](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/services/tasks/code.py)

这里的原则是：

- 先改静态模型
- 再改本地解析与 research
- 再改 renderer
- 最后改 AI 生成和下游消费

## 一句话结论

第一批不要先改 prompt，也不要先改命令。

第一批最该改的是：

- `plan_models.py`
- `plan_research.py`
- `plan_render.py`
- `plan.py`

也就是先把“输入 schema + 输出骨架 + 主流程接线”定住。
