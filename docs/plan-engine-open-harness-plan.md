# Plan Engine Open Harness 改造计划

本文定义把 `Plan` 引擎从当前 staged compiler pipeline 拉到 Open Harness 形态的阶段计划。

目标不是让 `Plan` 重新做 `Design` 的工作，而是把“执行拆解、依赖编排、验证契约、Code 可消费性”做成有限轮、多角色、artifact 驱动的内部评审闭环。

## 背景判断

当前 `Plan` 已经具备执行编译层的骨架：

- 读取 `design.md`、`design-repo-binding.json`、`design-sections.json`
- 生成 `plan-work-items.json`
- 构建 `plan-execution-graph.json`
- 生成 `plan-validation.json`
- 输出 `plan.md`
- 用 `plan-verify.json` 阻塞错误结果

但它还不是完整 Open Harness：

- agent 主要是局部生成器，不是清晰分工的角色系统。
- `graph` / `validation` 偏本地规则，缺少专门角色审查执行合理性。
- verify 只检查一致性和必要章节，还没有系统攻击“是否能交给 Code”。
- regenerate 是文档级修补，不是针对结构化 artifact 的 bounded revision。
- plan 发现上游 design 矛盾时，缺少正式回退到 Design 的诊断通道。

## 改造目标

Plan 完成后，`Code V2` 应能直接消费结构化 artifacts，而不是重新理解散文。

研发看到 `plan.md` 时，应能快速确认：

- work item 是否足够小。
- 每个 item 的输入、输出、写入范围是否清楚。
- repo 之间的依赖顺序是否合理。
- 并行组是否安全。
- 验证方案是否最小但足够。
- 哪些问题必须回到 Design 或人工确认。

## 边界原则

### Plan 不重做 Design 裁决

Plan 允许质疑 Design artifacts 的可执行性，但不允许擅自改写：

- repo 是否 in scope
- `scope_tier`
- candidate files
- critical flows
- non-goals

如果发现 Design 裁决不可执行，Plan 应产出 `needs_design_revision` 或 `needs_human` diagnosis，而不是在 Plan 内自行发明新 repo 或新设计。

### Markdown 只是投影

机器事实源优先级：

```text
plan-work-items.json
plan-execution-graph.json
plan-validation.json
plan-review.json
plan-decision.json
plan-verify.json
plan-diagnosis.json
plan.md
```

`plan.md` 只负责把最终结构化 Plan 转成人可读表达。

### Open Harness 必须有限

默认一轮评审、一轮修订：

```text
Planner -> Scheduler -> Validation Designer -> Skeptic -> Bounded Revision -> Writer -> Gate
```

不做无限对话。连续失败直接进入 diagnosis。

## 目标角色

### Planner

输入：

- `design-repo-binding.json`
- `design-sections.json`
- `design.md`
- `prd-refined.md`
- Plan skills brief

职责：

- 生成候选 work items。
- 保持 repo 和 scope tier 与 Design 一致。
- 把 `must_change` / `co_change` / `validate_only` 映射成 implementation / coordination / validation 任务。
- 给每个 item 写清输入、输出、写入范围、done definition。

输出：

- `plan-draft-work-items.json`

### Scheduler

职责：

- 只处理执行顺序、依赖、并行组、critical path。
- 不新增任务，不改变任务目标。
- 标出跨 repo coordination points。

输出：

- `plan-draft-execution-graph.json`
- `plan-dependency-notes.json`

### Validation Designer

职责：

- 为每个 work item 生成最小验证契约。
- 将 Design critical flows 和 refined acceptance criteria 绑定到具体任务。
- 区分 review、build、test、smoke、manual-check。
- 避免默认扩大成全仓回归。

输出：

- `plan-draft-validation.json`
- `plan-risk-check.json`

### Plan Skeptic

职责：

- 攻击 Plan 是否可执行。
- 检查 must_change repo 是否遗漏。
- 检查任务是否过大、依赖是否错、验证是否空泛。
- 检查是否越过 Design 边界。
- 识别需要回 Design 的问题。

输出：

- `plan-review.json`

建议 issue 类型：

```text
missing_must_change_repo
scope_tier_rewritten
work_item_too_broad
dependency_cycle_or_gap
validation_too_vague
code_input_missing
design_artifact_conflict
needs_design_revision
needs_human_confirmation
```

### Bounded Revision

职责：

- 只根据 `plan-review.json` 修订结构化 Plan artifacts。
- 对每个 issue 明确 accepted / rejected。
- 不改 Design artifacts。
- 不能修的问题进入 diagnosis。

输出：

- `plan-debate.json`
- `plan-decision.json`
- 最终版 `plan-work-items.json`
- 最终版 `plan-execution-graph.json`
- 最终版 `plan-validation.json`

### Writer

职责：

- 只把 `plan-decision.json` 和最终结构化 artifacts 写成 `plan.md`。
- 不新增任务、依赖或验证方案。
- 如果 `finalized=false`，必须在文档中说明不能进入 Code 的原因。

输出：

- `plan.md`

### Gate

职责：

- 判断 Plan 是否允许进入 Code。
- 同时检查结构化 artifacts 和 `plan.md` 是否一致。
- 产出可给 UI 展示和自动化处理的 diagnosis。

输出：

- `plan-verify.json`
- `plan-diagnosis.json`
- `plan-result.json`

Gate 状态建议：

```text
passed
passed_with_warnings
needs_human
needs_design_revision
degraded
failed
```

## 阶段拆解

### Phase 0：补齐契约，不改行为

目标：先把未来 Open Harness 的 artifact 契约写入代码边界，但保持现有 Plan 行为。

改动：

- 新增 Plan role prompt scaffold。
- 新增 artifact 名称常量或模型字段。
- 在 `plan-result.json` 中预留 `harness_version`、`gate_status`、`code_allowed`。
- 保持当前 `run_plan_engine` 输出兼容。

验收：

- 旧任务仍能生成当前 artifacts。
- UI 和 Code 不需要改。

### Phase 1：Planner 角色替换 task outline

目标：把 `build_plan_work_items` 从“agent 可选增强 + local fallback”升级为 Planner 角色。

改动：

- 新增 `plan-draft-work-items.json`。
- Planner 生成 draft。
- 现有 `normalize_plan_work_items` 继续作为 deterministic normalizer。
- local fallback 只能标记为 `degraded`，不能静默包装成高质量 native plan。

验收：

- `must_change` repo 必须被 work item 覆盖。
- `validate_only` repo 不应被默认转成 implementation。
- 不允许出现 Design artifacts 之外的 repo。

### Phase 2：Scheduler 和 Validation Designer 角色化

目标：让执行图和验证契约从纯规则派生，升级为“角色生成 + 本地校验归一化”。

改动：

- 新增 Scheduler prompt，生成 `plan-draft-execution-graph.json`。
- 新增 Validation Designer prompt，生成 `plan-draft-validation.json`。
- 保留当前本地 graph / validation 作为 fallback 和 schema repair。
- 增加 graph 校验：节点全覆盖、无非法依赖、无环、并行组不含硬依赖。
- 增加 validation 校验：每个 work item 至少一个具体 check。

验收：

- execution graph 覆盖全部 work items。
- validation 覆盖全部 work items。
- fallback 被明确记录到 `plan-diagnosis.json` 或 `plan-result.json`。

### Phase 3：Plan Skeptic + Bounded Revision

目标：建立 Plan 阶段自己的内部评审闭环。

改动：

- 新增 `plan-review.json`。
- 新增 `plan-debate.json`。
- 新增 `plan-decision.json`。
- Skeptic 读取 draft work items / graph / validation，输出 blocking / warning / info issues。
- Revision 只修订结构化 artifacts，不直接改 `plan.md`。
- blocking issue 修不掉时进入 `needs_human` 或 `needs_design_revision`。

验收：

- 对遗漏 must_change repo 的 Plan，Skeptic 必须 blocking。
- 对越界新增 repo 的 Plan，Skeptic 必须 blocking。
- 对验证空泛的 Plan，Skeptic 至少 warning，严重时 blocking。
- Revision 有逐条 issue resolution。

### Phase 4：Writer / Gate 分离

目标：让 `plan.md` 变成最终结构化 Plan 的只读投影，并让 Gate 成为进入 Code 的唯一判断点。

改动：

- Writer 只消费 `plan-decision.json` 和最终 artifacts。
- Gate 检查 `plan.md` 与结构化 artifacts 一致。
- `plan-result.json` 使用 `gate_status` 和 `code_allowed`。
- `services/tasks/plan.py` 根据 gate status 更新任务状态。

验收：

- `passed` / `passed_with_warnings` 才允许进入 Code。
- `needs_design_revision` 不应标记为 `planned`。
- `plan.md` 不能包含结构化 artifacts 中不存在的任务或 repo。

### Phase 5：Code 反馈闭环

目标：让 Code 阶段失败能反向沉淀到 Plan，而不是只留在 code log。

改动：

- Code 失败时输出可归因字段：`plan_item_id`、`failure_type`、`repo_id`、`suggested_plan_fix`。
- Plan rerun 可读取上一轮 `code-result.json` / `code-verify/*.json`。
- Planner / Skeptic 在 rerun 时把 Code 反馈作为约束。

验收：

- Code 因任务过大失败时，Plan rerun 能拆小 work item。
- Code 因验证命令不合适失败时，Plan rerun 能修正 validation contract。
- Code 因 Design 裁决错误失败时，Plan 输出 `needs_design_revision`。

## 推荐落地顺序

优先顺序：

1. Phase 0：契约与兼容字段。
2. Phase 1：Planner 替换 task outline。
3. Phase 3：先做 Skeptic，即使 graph / validation 仍是本地规则，也能立刻提升质量。
4. Phase 4：Writer / Gate 分离。
5. Phase 2：Scheduler / Validation Designer 深化。
6. Phase 5：Code 反馈闭环。

原因：

- Planner 和 Skeptic 是 Open Harness 味道最强的两步。
- Graph / Validation 当前本地规则已经可用，可以稍后角色化。
- Gate 分离是让 Plan 真正成为 Code 前置质量门的关键。

## 最小可交付切片

第一版可以只交付：

```text
Planner
  -> local graph
  -> local validation
  -> Plan Skeptic
  -> Bounded Revision
  -> Writer
  -> Gate
```

新增 artifacts：

```text
plan-draft-work-items.json
plan-review.json
plan-debate.json
plan-decision.json
```

保留 artifacts：

```text
plan-work-items.json
plan-execution-graph.json
plan-validation.json
plan-verify.json
plan-diagnosis.json
plan-result.json
plan.md
```

这能用较小改动把 Plan 从“生成 + verify”推进到“生成 + 审查 + 修订 + gate”。

## 风险点

### 角色过多导致慢

默认只启用 Planner / Skeptic / Writer / Gate。Scheduler 和 Validation Designer 可以后置或仅 native 模式启用。

### Plan 反向污染 Design

所有 prompt 必须写明：

- 不重新 adjudicate repo。
- 不新增 Design 未认可的 repo。
- 发现上游冲突时输出 diagnosis。

### Fallback 结果被误认为高质量

任何 local fallback 或 agent 失败后的部分产物都必须显式记录：

- `degraded: true`
- `degraded_reason`
- `fallback_stage`

如果 fallback 影响 Code 可执行性，Gate 不得 passed。

### 结构化 artifact 与 markdown 漂移

Writer 不再接受自由生成。Gate 必须检查：

- `plan.md` 的任务数与 `plan-work-items.json` 一致。
- repo id 一致。
- 依赖顺序一致。
- 验证策略不超出 `plan-validation.json`。

## 最终形态

目标流程：

```text
prepare input
  -> skills brief
  -> planner draft
  -> scheduler draft
  -> validation draft
  -> skeptic review
  -> bounded revision
  -> final decision
  -> writer
  -> gate
```

目标结果：

- Plan 能清楚继承 Design，而不是重做 Design。
- Plan 能被 Code 直接消费，而不是要求 Code 自己重新拆任务。
- Plan 失败时能说明是 Plan 自身问题、Design 上游问题，还是需要人工确认。
- Plan 的质量提升来自角色协议和 artifact gate，而不是单纯加长 prompt。
