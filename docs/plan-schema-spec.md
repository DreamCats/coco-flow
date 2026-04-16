# Plan Schema Spec

本文把当前讨论过的目标产物结构进一步收敛成字段级 schema，作为后续重构 `refine -> plan -> code` 链路的契约草案。

如果本文与代码不一致，以代码为准。

## 这份文档的定位

这不是实现细节文档，而是字段级契约文档。

它主要回答：

- 新版 `refine` 应该向 `plan` 提供什么结构
- `design.md` 背后应该对应什么结构对象
- `plan.md` 背后应该对应什么结构对象
- `code` 阶段最少应该从 `plan.md` 中消费哪些字段

## 设计原则

这套 schema 建议遵循 4 条原则：

1. 文档标题和内部字段分离  
   对人看的标题可以稳定，对程序消费的字段也要稳定，但两者不必一一同名。

2. 先结构化，再渲染  
   `design.md` 和 `plan.md` 都不应由 prompt 直接生成最终 Markdown，而应先生成结构对象，再统一 renderer 落盘。

3. 给人和给机器同时可用  
   同一份对象既要让研发读得懂，也要让后续 `code` 阶段稳定消费。

4. 先满足主链路，再补专项字段  
   P0 先保证 `refine -> design -> plan -> code` 主链路跑通；协议、实验、QA、人力评估等字段允许后续逐步补强。

## 一、新版 `RefinedSections`

这是 `plan` 的正式输入结构。

### 字段定义

```python
@dataclass
class RefinedSections:
    change_scope: list[str]
    non_goals: list[str]
    key_constraints: list[str]
    acceptance_criteria: list[str]
    open_questions: list[str]
    raw: str
```

### 字段含义

- `change_scope`
  当前需求明确要改什么。这里是后续 design / plan 的主输入。

- `non_goals`
  当前需求明确不改什么。这里直接约束 design 边界和 plan 任务边界。

- `key_constraints`
  当前需求里的强约束，包括业务规则、兼容性、默认行为、限制条件。

- `acceptance_criteria`
  从需求角度定义“改完怎么算对”。

- `open_questions`
  当前仍未决、不能脑补的点。

- `raw`
  原始 refined Markdown，保留给 trace、降级和人工兜底使用。

### 兼容映射

为了兼容旧版 refined 文档，建议在过渡期保留映射：

- `summary + features` -> `change_scope`
- `boundaries` -> `non_goals`
- `business_rules` -> `key_constraints`
- 旧版没有稳定字段 -> `acceptance_criteria` 先留空或从旧章节弱提取
- `open_questions` -> `open_questions`

这里最需要补强的是：

- `non_goals`
- `acceptance_criteria`

## 二、`DesignSections`

这是 `design.md` 背后的正式结构对象。

### 字段定义

```python
@dataclass
class DesignSections:
    system_change_points: list[str]
    solution_overview: str
    system_changes: list["SystemChange"]
    system_dependencies: list["SystemDependency"]
    critical_flows: list["CriticalFlow"]
    protocol_changes: list["ProtocolChange"]
    storage_config_changes: list["StorageConfigChange"]
    experiment_changes: list["ExperimentChange"]
    qa_inputs: list[str]
    staffing_estimate: "StaffingEstimate | None"
```

### 章节映射

- `系统改造点` -> `system_change_points`
- `方案设计`
  - `solution_overview`
  - `system_changes`
  - `system_dependencies`
  - `critical_flows`
- `多端协议是否有变更` -> `protocol_changes`
- `存储&&配置是否有变更` -> `storage_config_changes`
- `是否有实验，实验怎么涉及` -> `experiment_changes`
- `给 QA 的输入` -> `qa_inputs`
- `人力评估` -> `staffing_estimate`

## 三、`SystemChange`

这是 `方案设计` 中最核心的结构。

### 字段定义

```python
@dataclass
class SystemChange:
    system_id: str
    system_name: str
    serves_change_points: list[int]
    responsibility: str
    planned_changes: list[str]
    upstream_inputs: list[str]
    downstream_outputs: list[str]
    touched_repos: list[str]
```

### 设计意图

这组字段要明确回答：

- 这个系统承担什么职责
- 它服务于哪些系统改造点
- 具体要做什么改动
- 它依赖哪些上游
- 它给哪些下游提供什么结果

它是 `design` 和 `plan` 之间最重要的桥梁对象。

## 四、`SystemDependency`

这不是代码 import 依赖，而是实施依赖。

### 字段定义

```python
@dataclass
class SystemDependency:
    upstream_system_id: str
    downstream_system_id: str
    dependency_type: str  # strong | weak | parallel_friendly
    reason: str
```

### 设计意图

它用于支撑：

- `design.md` 中的系统依赖关系
- `plan.md` 中的执行顺序
- 后续 `PlanTaskSpec.depends_on`

## 五、`CriticalFlow`

用于承接“关键链路说明”。

### 字段定义

```python
@dataclass
class CriticalFlow:
    name: str
    trigger: str
    steps: list[str]
    state_changes: list[str]
    fallback_or_error_handling: list[str]
```

### 设计意图

它解决的是：

- 系统改动点写了
- 分系统改造写了
- 但读者仍然串不起主链路

## 六、专项变更对象

### `ProtocolChange`

```python
@dataclass
class ProtocolChange:
    boundary_name: str
    changed: bool
    summary: str
    impacted_systems: list[str]
    compatibility_notes: list[str]
```

用于承接：

- 大前端接口变化
- RPC / IDL 变化
- 请求/响应字段变化

### `StorageConfigChange`

```python
@dataclass
class StorageConfigChange:
    category: str  # storage | config | tcc
    changed: bool
    summary: str
    affected_items: list[str]
    rollout_notes: list[str]
```

### `ExperimentChange`

```python
@dataclass
class ExperimentChange:
    changed: bool
    experiment_name: str
    traffic_scope: str
    affected_flows: list[str]
    rollout_notes: list[str]
    rollback_notes: list[str]
```

## 七、`StaffingEstimate`

这个字段不是技术主链路核心，但既然设计文档保留了该章节，建议结构化。

```python
@dataclass
class StaffingEstimate:
    summary: str
    frontend: str
    backend: str
    qa: str
    coordination_notes: list[str]
```

如果当前阶段难稳定生成，可以允许为 `None`。

## 八、`PlanExecutionSections`

这是 `plan.md` 背后的正式结构对象。

### 字段定义

```python
@dataclass
class PlanExecutionSections:
    execution_strategy: list[str]
    tasks: list["PlanTaskSpec"]
    execution_order: list[str]
    verification_plan: list[str]
    blockers_and_risks: list[str]
```

### 章节映射

- `实施策略` -> `execution_strategy`
- `任务拆分` -> `tasks`
- `执行顺序` -> `execution_order`
- `验证计划` -> `verification_plan`
- `阻塞项与风险` -> `blockers_and_risks`

## 九、`PlanTaskSpec`

这是后续 `code` 阶段最关键的消费对象。

### 字段定义

```python
@dataclass
class PlanTaskSpec:
    id: str
    title: str
    target_system_or_repo: str
    serves_change_points: list[int]
    goal: str
    depends_on: list[str]
    parallelizable_with: list[str]
    change_scope: list[str]
    actions: list[str]
    done_definition: list[str]
    verify_rule: list[str]
```

### 字段含义

- `id`
  稳定任务标识，如 `T1`、`T2`。

- `title`
  面向研发阅读的任务标题。

- `target_system_or_repo`
  当前任务主要落在哪个系统或仓库。

- `serves_change_points`
  这个任务服务于哪些“系统改造点”。

- `goal`
  一句话说明这个任务为什么存在。

- `depends_on`
  强依赖任务。

- `parallelizable_with`
  可并行任务。没有也可以为空。

- `change_scope`
  任务预计影响的目录、package、文件或模块范围。

- `actions`
  实施动作列表。

- `done_definition`
  任务完成定义。

- `verify_rule`
  默认建议是“受影响 package 编译通过”。

## 十、`code` 阶段最少消费哪些字段

如果后续 `code` 阶段要稳定消费 `plan.md`，最少建议消费这些字段：

- `PlanTaskSpec.id`
- `PlanTaskSpec.target_system_or_repo`
- `PlanTaskSpec.depends_on`
- `PlanTaskSpec.change_scope`
- `PlanTaskSpec.actions`
- `PlanTaskSpec.done_definition`
- `PlanTaskSpec.verify_rule`

换句话说，后续 `code` 不应该依赖整篇 prose，而应依赖 `PlanTaskSpec`。

## 十一、推荐迁移顺序

### 阶段 1：先把输入和产物模型定住

1. 切换 `RefinedSections`
2. 新增 `DesignSections`
3. 新增 `PlanExecutionSections`
4. 新增 `PlanTaskSpec`

### 阶段 2：让 renderer 围绕结构对象工作

5. `build_design()` 改为消费 `DesignSections`
6. `build_plan()` 改为消费 `PlanExecutionSections`

### 阶段 3：再重写 generator / verifier

7. generator 输出结构化对象
8. verifier 分拆成 design verifier 和 execution verifier

### 阶段 4：最后补专项信号抽取

9. research 层补协议、配置、实验、QA、人力评估信号

## 一句话结论

后续真正应该稳定下来的，不是 `design.md` 和 `plan.md` 这两份 Markdown 本身，而是：

- `RefinedSections`
- `DesignSections`
- `PlanExecutionSections`
- `PlanTaskSpec`

Markdown 只是这些对象的渲染结果。

如果要继续落到第一批代码实施切分，另见
[`docs/plan-implementation-slices.md`](docs/plan-implementation-slices.md)。
