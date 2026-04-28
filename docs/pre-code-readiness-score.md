# Pre-Code Readiness Score

Pre-Code Readiness Score, 简称 PCRS，用来评估一个 task 在未进入 Code 阶段前，Design 和 Plan 是否已经足够支撑代码实现。

这个指标的前提是：对多数业务改动，真正的 Code 阶段不一定最难；更关键的是 Design / Plan 是否已经把需求、边界、仓库职责、跨仓依赖、任务拆解和验证方式讲清楚。PCRS 衡量的是“进入 Code 前的确定性”，不是最终代码质量。

## 总分公式

```text
PCRS = 100 * (
  0.35 * DesignQuality
+ 0.45 * PlanExecutability
+ 0.10 * GateCorrectness
+ 0.10 * NoiseControl
)
```

取值范围是 `0 ~ 100`。所有子项都归一化到 `0 ~ 1`。

建议阈值：

```text
PCRS >= 85        可以进入 Code
70 <= PCRS < 85  需要人工快速 review 后再进入 Code
PCRS < 70         回到 Design / Plan 修正
```

## 一级变量

### DesignQuality

DesignQuality 衡量 `design.md` 是否把“为什么这么做、哪些仓负责、边界是什么、跨仓契约是什么”讲清楚。

```text
DesignQuality =
  0.25 * RequirementCoverage
+ 0.20 * BoundaryCoverage
+ 0.20 * RepoResponsibilityClarity
+ 0.20 * ContractCompleteness
+ 0.15 * RiskResolution
```

变量含义：

- `RequirementCoverage`
  - refined PRD 中的验收标准有多少被映射到 Design / Plan。
  - 计算：`已映射验收标准数 / refined PRD 验收标准总数`。

- `BoundaryCoverage`
  - 非目标、边界条件、fallback 是否被 Design 明确保留。
  - 计算：`已体现边界数 / refined PRD 边界总数`。

- `RepoResponsibilityClarity`
  - 每个绑定仓是否有明确职责，例如 producer / consumer / validate-only。
  - 可按仓库打分：职责明确为 `1`，只列候选文件但无裁决为 `0.5`，无职责说明为 `0`。

- `ContractCompleteness`
  - 跨仓字段、接口、配置、实验参数等契约是否完整。
  - 应至少包含 producer、consumer、字段或接口名、默认值 / 兼容策略、消费方式。

- `RiskResolution`
  - 待确认项是否被处理成明确结论，或者被保留为真实 blocker。
  - “已确认：...”不应阻断 Code；真正缺字段名、key、枚举值、协议判断时才应阻断。

为什么 DesignQuality 权重是 `0.35`：

Design 是 Plan 和 Code 的事实基础，但它不是直接执行清单。Design 错会导致后续全错，所以权重较高；但最终能否执行，更多由 Plan 决定，因此低于 PlanExecutability。

### PlanExecutability

PlanExecutability 衡量 `plan.md`、`plan-work-items.json`、`plan-repos/*.md` 是否能直接交给 Code 阶段执行。

```text
PlanExecutability =
  0.25 * TaskCoverage
+ 0.20 * FileSpecificity
+ 0.20 * StepActionability
+ 0.15 * DependencyCorrectness
+ 0.10 * ValidationMapping
+ 0.10 * CodeGatePass
```

变量含义：

- `TaskCoverage`
  - Design 中每个 must-change repo 是否都有 work item。
  - 计算：`已生成 work item 的 must-change repo 数 / must-change repo 总数`。

- `FileSpecificity`
  - work item 是否有明确文件、目录或模块落点。
  - 计算：`包含明确 change_scope 的 work item 数 / work item 总数`。

- `StepActionability`
  - step 是否是可执行动作，而不是证据句或泛化句。
  - 计算：`可执行 step 数 / step 总数`。
  - 可执行 step 应满足：有动作、有对象、有条件或结果。
  - 示例：`读取实验字段 X`、`命中实验时拼接 Auction 标识`。
  - 非示例：`代码证据：xxx 包含 getAuctionTitle`、`在 xxx.go 中：`、`完成相关改动`。

- `DependencyCorrectness`
  - 跨仓执行顺序是否正确。
  - 计算：`正确依赖边数 / 应存在依赖边数`。
  - 例如实验字段由 `live_common` 生产、`live_pack` 消费时，应有 `live_common -> live_pack`。

- `ValidationMapping`
  - 验收标准是否映射到对应 work item 的验证项。
  - 计算：`已映射验收标准数 / refined PRD 验收标准总数`。

- `CodeGatePass`
  - Plan gate 是否允许进入 Code。
  - `code_allowed=true` 为 `1`，否则为 `0`。

为什么 PlanExecutability 权重是 `0.45`：

Plan 是 Code 阶段的直接输入。即使 Design 合理，如果 Plan 中任务不可执行、依赖错误、验证缺失，Code 阶段也会跑偏。因此它是最高权重。

### GateCorrectness

GateCorrectness 衡量系统是否正确判断“能不能进入 Code”。

```text
GateCorrectness =
  1 - GateErrorRate
```

常见 gate 错误：

- 把“已确认：...”误判为 blocker。
- 有真实待确认项却允许进入 Code。
- design / plan 已编辑但结构化 sidecar 未同步，却允许进入 Code。
- 多仓依赖未确认却允许并行执行。

为什么 GateCorrectness 权重是 `0.10`：

Gate 不是内容质量本身，但它决定是否错误放行或错误阻断。它权重不宜超过 Design / Plan 内容，但必须单独评估。

### NoiseControl

NoiseControl 衡量 Design / Plan 中是否混入会干扰 Code agent 的噪音。

```text
NoiseControl = 1 - min(1, NoiseCount / max(1, TotalPlanItems))
```

噪音包括：

- 证据句进入 task steps。
- 重复文件路径，例如完整路径和 basename 同时出现。
- 悬空标题句，例如 `在 regular_auction_converter.go 中：`。
- 泛化句，例如 `完成相关改动`、`按 Design 实现`。
- 非目标被误写成任务。
- 已确认项仍作为 blocker。

为什么 NoiseControl 权重是 `0.10`：

噪音通常不改变方向，但会降低 Code agent 的执行稳定性，增加误改和绕路概率。它适合作为扣分项，而不是主评价项。

## 计算示例

假设某个 task：

- refined PRD 有 4 条验收，Plan 覆盖 4 条：`RequirementCoverage = 1.0`
- 有 4 条边界，Design 覆盖 4 条：`BoundaryCoverage = 1.0`
- 2 个仓职责都明确：`RepoResponsibilityClarity = 1.0`
- 有 1 条跨仓实验字段契约且完整：`ContractCompleteness = 1.0`
- 3 个待确认项都变成已确认结论：`RiskResolution = 1.0`
- 2 个 must-change repo 都有 work item：`TaskCoverage = 1.0`
- 2 个 work item 都有文件落点：`FileSpecificity = 1.0`
- 10 个 step 中 8 个可执行、2 个是证据句：`StepActionability = 0.8`
- 应有 1 条依赖边，生成正确：`DependencyCorrectness = 1.0`
- 验收都映射到验证：`ValidationMapping = 1.0`
- code gate passed：`CodeGatePass = 1.0`
- 12 个 Plan item 中有 2 个噪音：`NoiseControl = 1 - 2/12 = 0.83`
- gate 无误判：`GateCorrectness = 1.0`

则：

```text
DesignQuality = 1.0
PlanExecutability = 0.25*1 + 0.20*1 + 0.20*0.8 + 0.15*1 + 0.10*1 + 0.10*1 = 0.96
PCRS = 100 * (0.35*1 + 0.45*0.96 + 0.10*1 + 0.10*0.83) = 96.5
```

这个结果表示：虽然 Plan 有少量噪音，但总体已经可以进入 Code。

## 使用建议

PCRS 最适合用在以下场景：

- 比较不同 executor、prompt、SOP 版本生成的 Design / Plan 质量。
- 在不跑 Code 的情况下做批量回归评估。
- 判断一个 task 是否可以自动进入 Code。
- 定位质量问题主要来自 Design、Plan、Gate 还是噪音。

不建议把 PCRS 用作唯一上线指标。最终仍需要结合 Code 阶段的编译、测试、diff review 和人工验收。
