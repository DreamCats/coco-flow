# coco-flow Harness 化工程设计

本文定义如果从当前 `coco-flow` 现状继续推进，我会如何把它做成一个更稳定、更聪明、研发更愿意使用的需求到代码落地平台。

结论先行：

- `coco-flow` 已经具备 Harness 工程雏形：阶段、artifact、状态、日志、worktree、验证链路都已经存在。
- 下一步不应该继续单纯增强 prompt，而应该增强阶段契约、诊断式修复、分级 gate、人工接管和经验沉淀。
- 不建议使用 `while true` 无限重试。正确模式是有限次数的诊断式修复循环。
- 目标不是让流程永不失败，而是让失败变得可解释、可修复、可接管、可沉淀。

## 背景问题

Claude Code / Codex 这类工具天然是人机对话模式：

1. 人提出目标。
2. Agent 尝试执行。
3. 人看结果并纠偏。
4. Agent 带着纠偏继续推进。

这个模式的稳定性很大一部分来自人持续参与。

`coco-flow` 不一样。它是产品化 workflow，由程序控制上下文、状态流转和阶段编排。好处是流程可复现、可集成、可规模化；问题是中间一旦某个阶段失败，系统不能只说 `verify failed`，否则后续重试没有方向。

所以 `coco-flow` 要补上的不是“再问一次模型”，而是把人机对话里的纠偏能力产品化：

- 人指出哪里不对 -> verifier 输出结构化 issues
- 人要求只改某个点 -> repair engine 定点修复 artifact
- 人判断是否继续 -> gate policy 判断阻塞、警告、人工接管
- 人积累经验 -> feedback store / repo profile 沉淀失败原因和修复策略

## 产品目标

研发真正满意，不是因为文档长，而是因为系统能稳定回答三个问题。

### 1. 需求是否理解对

`Refine` 输出要让研发快速确认：

- 本次做什么
- 本次不做什么
- 验收标准是什么
- 哪些问题还没确认

### 2. 改动范围是否找准

`Design` 输出要让研发快速确认：

- 改哪些 repo
- 每个 repo 是主改、协同、验证还是参考
- 主要落在哪些模块或文件
- 为什么是这些地方
- 哪些判断不确定

### 3. 计划是否能交给 coding agent

`Plan` 输出要让研发快速确认：

- work item 是否足够小
- 每个 item 的输入、输出、写入范围是否清楚
- 依赖顺序是否合理
- 验证方式是否明确
- code 阶段能不能直接消费

一句话目标：

> 研发看完 `plan` 后，应觉得“这个任务我自己做也会这么拆”，而不是“AI 写了一堆分析，我还要重新判断”。

## 当前现状判断

### Refine

当前 `Refine` 已经基本符合 Harness 方向：

- manual-first
- 先解析人工提炼范围
- 生成 `refine-brief.json`
- 输出 `prd-refined.md`
- 写入 `refine-verify.json`
- native 走模板文件 + agent 填充 + verifier

主要短板：

- verify 结果还不够结构化，不足以支撑稳定 repair。
- verify 与 gate 的关系还不够硬，失败类型没有分级。
- 对“需求信息不足”的情况缺少正式 `needs_human` 分支。

### Design

当前 `Design` 是三阶段里最像 Harness 的阶段：

- 有 `design-change-points.json`
- 有 `design-repo-assignment.json`
- 有 `design-research.json`
- 有 `design-repo-responsibility-matrix.json`
- 有 `design-repo-binding.json`
- 有 `design-sections.json`
- native design 已有 contract check 和 regeneration

主要短板：

- local design 的 gate 强度弱于 native design。
- repo binding 的不确定性没有产品化展示。
- design repair 仍偏重新生成，而不是稳定定点修复。
- “把用户绑定仓库误解为全部都要改”是当前最大风险，需要更明确的人机接管点。

### Plan

当前 `Plan` 已经开始进入执行 Harness：

- 有 `plan-work-items.json`
- 有 `plan-execution-graph.json`
- 有 `plan-validation.json`
- 有 `plan-risk-check.json`
- 有 `plan-verify.json`
- verify 失败会阻塞进入 planned

主要短板：

- work item 仍有不少自然语言字段，不够像可执行工单。
- verification 仍常是“最小范围验证通过”这种描述，不够命令化。
- plan 发现 design 矛盾时，缺少明确“回到 Design 修复”的机制。
- code 阶段失败后的反馈还没有反向沉淀到 plan/design。

## 核心设计原则

### 1. Gate 分级，不一刀切

做硬不等于所有问题都阻塞。

建议把 verify issue 分成四类：

| 等级 | 含义 | 行为 |
|------|------|------|
| `blocking` | 继续会明显走错 | 阻塞下一阶段，尝试 repair |
| `warning` | 质量不足但可继续 | 允许继续，UI 显示风险 |
| `needs_human` | 信息不足或判断冲突 | 暂停，等待人工确认 |
| `info` | 仅记录观察结果 | 不影响流程 |

这样系统不会因为小问题频繁失败，也不会把关键错误吞掉。

### 2. Verifier 要输出可修复问题

不要只输出：

```json
{
  "ok": false,
  "reason": "verify failed"
}
```

应该输出：

```json
{
  "ok": false,
  "stage": "design",
  "severity": "blocking",
  "failure_type": "missing_candidate_files",
  "issues": [
    {
      "id": "D001",
      "artifact": "design.md",
      "path": "分仓库方案.live-pack",
      "expected": "必须说明 must_change 仓库的核心候选文件",
      "actual": "只描述了仓库职责，没有落到文件",
      "repair_hint": "从 design-repo-binding.json 的 candidate_files 中选择前 3 个文件补充到分仓库方案",
      "auto_repairable": true
    }
  ],
  "next_action": "repair"
}
```

这才是 Harness 能自动纠偏的基础。

### 3. Repair 优先于 Regenerate

失败后优先定点修，不要整份重写。

推荐顺序：

1. schema/format 问题：本地 deterministic repair
2. 缺 section / 缺字段：agent repair 指定 artifact 片段
3. 语义覆盖不足：agent repair 指定 issue
4. repo 选择冲突：进入 `needs_human`
5. 多次同类失败：停止自动重试

### 4. 循环必须有限

不要 `while true`。

建议默认策略：

| 问题类型 | 自动修复次数 |
|----------|--------------|
| JSON / markdown 格式 | 2 |
| 缺字段 / 缺 section | 2 |
| 语义覆盖不足 | 1 |
| 仓库执行职责不确定 | 0，直接人工确认 |
| 连续同类失败 | 立即停止 |

每次重试都必须带上：

- 上一版 artifact
- 结构化 issue
- repair hint
- 禁止扩大修改范围的约束

### 5. Artifact 是阶段 API

Markdown 给人看，JSON 给机器消费。

每个阶段至少应该形成这几类产物：

```text
stage-input.json       # 本阶段实际消费的输入摘要
stage-output.json      # 本阶段结构化结论
stage-verify.json      # 验证结果
stage-diagnosis.json   # 失败诊断和建议动作
stage-result.json      # 状态、产物列表、耗时、重试次数
stage.log              # 可读日志
```

不要求所有阶段马上改成统一文件名，但内部模型应该朝这个方向收敛。

### 6. 人工接管是正常分支

自动化不是永远不停。

当系统遇到这些情况，应主动停下来：

- 需求范围缺关键信息
- 用户绑定的多个 repo 都可能承担必须改动职责，但证据不足
- design 和 refine 自相矛盾
- plan 无法生成真实验证方式
- repair 连续失败

UI 不应该只显示“失败”，而应该显示：

- 为什么停
- 需要人确认什么
- 推荐选项是什么
- 选完后从哪个阶段继续

### 7. 失败要沉淀

每次失败都应该形成可复用数据：

- 哪类需求容易失败
- 哪个 repo 缺验证命令
- 哪个术语没有解释
- 哪个 verify rule 误伤
- 哪个 repair hint 有效

长期看，`coco-flow` 的聪明不只来自模型，而来自这些沉淀。

## 目标架构

### 阶段执行模型

每个阶段统一成下面的模型：

```text
prepare bundle
-> generate structured artifacts
-> render markdown
-> verify
-> if ok: commit stage result
-> if warning: commit with warnings
-> if auto_repairable: repair and verify again
-> if needs_human: pause with diagnosis
-> if exhausted: fail with diagnosis
```

### 诊断式修复循环

伪代码：

```python
attempt = 0
artifact = generate(bundle)

while attempt <= max_repair_attempts:
    verify = verify_artifact(bundle, artifact)
    diagnosis = diagnose(verify)

    if diagnosis.ok:
        return success(artifact, diagnosis)

    if diagnosis.next_action == "continue_with_warnings":
        return success_with_warnings(artifact, diagnosis)

    if diagnosis.next_action == "needs_human":
        return pause_for_human(artifact, diagnosis)

    if diagnosis.next_action != "repair":
        return failed(artifact, diagnosis)

    if attempt >= max_repair_attempts:
        return failed(artifact, diagnosis)

    artifact = repair_artifact(bundle, artifact, diagnosis)
    attempt += 1
```

注意这里虽然用了循环，但它是有限循环，且每轮都有诊断输入。

### 标准诊断模型

建议新增共享模型，供 refine/design/plan/code 复用：

```json
{
  "ok": false,
  "stage": "plan",
  "severity": "blocking",
  "failure_type": "missing_work_item_coverage",
  "next_action": "repair",
  "retryable": true,
  "attempt": 1,
  "max_attempts": 2,
  "issues": [
    {
      "id": "P001",
      "artifact": "plan-work-items.json",
      "path": "work_items",
      "repo_id": "live-pack",
      "expected": "must_change repo 必须至少有一个 implementation work item",
      "actual": "live-pack 没有对应 implementation work item",
      "repair_hint": "基于 design-repo-binding.json 为 live-pack 补一个 implementation item",
      "auto_repairable": true
    }
  ]
}
```

### Stage Result

每个阶段都应该写统一结果摘要，方便 UI 和后续阶段读取：

```json
{
  "task_id": "xxx",
  "stage": "design",
  "status": "designed",
  "ok": true,
  "warnings": [],
  "attempts": 1,
  "artifacts": [
    "design.md",
    "design-repo-binding.json",
    "design-sections.json",
    "design-verify.json"
  ],
  "updated_at": "..."
}
```

## 绑定仓库与执行职责

这是 Design 阶段最容易误解的边界。

用户绑定多个 repo，表达的是：

> 这些仓库和需求有关，应该纳入探索范围。

它不等于：

> 这些仓库都必须改代码。

因此 Design 不应该用“主仓 / 次仓”这种产品语言。这个说法容易让人误解为系统在给用户绑定的仓库排高低。更准确的口径是“仓库执行职责”。

建议统一成下面三层：

| 层级 | 含义 | 产物 |
|------|------|------|
| 用户绑定仓库 | 用户认为相关的探索范围 | `repos.json` |
| 仓库执行职责 | Design 判断每个仓库在本次需求中的参与方式 | `design-repo-binding.json` |
| 执行工单 | Plan 真正交给 Code 阶段执行的任务 | `plan-work-items.json` |

Design 阶段要做的不是质疑用户为什么绑定这些仓库，而是把这些仓库转成明确职责：

| 执行职责 | 含义 | 是否进入 Code 主执行 |
|----------|------|----------------------|
| `must_change` | 不改这个仓，需求无法完成 | 是 |
| `co_change` | 需要配合修改，通常依赖 `must_change` 的结果 | 是 |
| `validate_only` | 不默认改代码，只做联动验证、兼容性确认或风险检查 | 通常否 |
| `reference_only` | 只作为上下文参考，不进入执行计划 | 否 |

这条边界对产品体验很重要：

- 用户绑定仓库不应该被系统静默丢掉。
- 但 Code 阶段也不应该默认修改所有绑定仓库。
- Design 必须解释每个绑定仓库为什么是当前职责。
- 如果某个绑定仓库证据不足，也应该保留为 `validate_only` 或 `reference_only`，而不是硬判要改。
- 如果多个仓库都可能承担 `must_change`，且证据不足，应进入 `needs_human`，让用户确认执行职责。

一句话：

> 绑定仓库是探索范围；执行职责是 Design 结论；work item 才是真正进入 Code 的任务。

## 分阶段改造设计

### Phase 1: 统一诊断模型与观测，不改变主流程

目标：先让系统说清楚为什么失败。

任务：

1. 新增共享诊断模型
   - 建议位置：`src/coco_flow/engines/shared/diagnostics.py`
   - 定义 `DiagnosticIssue`、`StageDiagnosis`、`GateDecision`

2. 扩展现有 verify payload
   - `refine-verify.json`
   - `design-verify.json`
   - `plan-verify.json`
   - 保留旧字段 `ok/issues/reason`，新增 `severity/failure_type/next_action`

3. 写入 diagnosis artifact
   - `refine-diagnosis.json`
   - `design-diagnosis.json`
   - `plan-diagnosis.json`

4. API / UI 先只展示，不阻塞更多流程
   - 目标是观察真实失败类型
   - 避免一开始 gate 过硬导致体验变差

验收：

- 三阶段失败时都有结构化 diagnosis。
- UI 或 API 能读到 `next_action`。
- 旧任务兼容，不要求历史 artifact 重写。

### Phase 2: Refine 诊断式 repair

目标：让需求确认书失败时可自动修复，信息不足时可人工接管。

任务：

1. 强化 refine verifier
   - 缺 section
   - 缺 `in_scope`
   - 缺验收标准
   - 验收标准混入非目标
   - 模板占位未清理

2. 新增 refine repair
   - 格式问题走本地修
   - 内容缺失走 agent repair
   - repair 只允许改 `prd-refined.md` 和 `refine-brief.json`

3. 明确 `needs_human`
   - 人工提炼范围缺“本次范围”
   - 人工提炼范围缺“改动点”
   - source 内容和人工提炼明显冲突

4. UI 显示人工确认点
   - 展示当前假设
   - 允许用户编辑 Input supplement 或 `prd-refined.md`
   - 继续从 refine rerun

验收：

- 常见格式/section 问题最多 2 次自动修复。
- 信息不足不反复重试，直接进入人工确认。
- `refine-verify.ok=false` 且 severity 为 `blocking` 时，不进入 design。

### Phase 3: Design 仓库执行职责可信化

目标：把用户绑定仓库稳定转成执行职责，降低把所有绑定仓库都当成需要改代码的概率。

任务：

1. 调整产品语言和模板口径
   - 避免使用“主仓 / 次仓”
   - 统一使用“仓库执行职责”
   - 在 UI 中区分“已绑定仓库”和“进入执行计划的仓库”

2. 强化 design binding contract
   - 每个 `in_scope` repo 必须有 `scope_tier`
   - `must_change` 必须有候选文件或候选目录
   - `validate_only` 必须说明验证定位
   - `reference_only` 默认不进入主 design 文档

3. 增加 repo binding confidence
   - `high`: 单仓明确命中核心文件
   - `medium`: 候选文件合理但仍需确认
   - `low`: 多仓竞争或只有弱信号

4. 增加 design repair
   - 缺候选文件：从 `design-research.json` 和 binding 中补
   - 缺 scope_tier 说明：从 responsibility matrix 补
   - 缺风险项：从 refine open questions 补

5. 增加 human gate
   - 多个 repo 都可能是 `must_change`
   - `must_change` 职责 confidence 为 `low`
   - repo binding 和用户绑定 repo 明显冲突
   - 用户绑定多个仓，但系统无法判断哪些应进入 Code 主执行

验收：

- `design-repo-binding.json` 能解释每个绑定 repo 的执行职责。
- 低信心 `must_change` 职责不会静默进入 plan。
- `validate_only` / `reference_only` 仓库不会默认生成 implementation work item。
- design repair 不整份重写，优先修指定 issue。

### Phase 4: Plan work item 执行化

目标：让 `plan-work-items.json` 真正成为 code 阶段的执行工单。

任务：

1. 扩展 work item schema
   - `write_scope`
   - `read_context`
   - `expected_outputs`
   - `verification_commands`
   - `requires_human_confirmation`

2. 从 repo profile 生成验证命令
   - Python: `python3 -m py_compile`
   - Go: 受影响目录 `go build ./...`
   - Web: `npm run build`
   - 允许 `.livecoding/context` 或 repo profile 覆盖

3. 强化 plan verify
   - must_change repo 必须有 implementation item
   - 每个 implementation item 必须有 write scope
   - 每个 item 必须有 done definition
   - 能生成真实验证命令时，不允许只写泛化描述

4. plan 发现 design 矛盾时返回 design
   - 不在 plan 阶段偷偷改 repo binding
   - 生成 `plan-diagnosis.json`
   - `next_action=return_to_design`

验收：

- Code 阶段可以直接按 work item 读取 `repo_id/write_scope/verification_commands`。
- plan verify 能区分“plan 可修”和“design 要返工”。
- markdown `plan.md` 只是 work item 的人类可读投影。

### Phase 5: Code 失败反馈反向沉淀

目标：让 code 阶段的失败变成 refine/design/plan 的改进输入。

任务：

1. 结构化 code failure
   - 编译失败
   - 测试失败
   - 修改范围偏离
   - 找不到文件
   - agent 未按 work item 执行

2. 生成 feedback artifact
   - `code-feedback.json`
   - 记录失败对应的 work item、repo、命令、错误摘要、建议归因

3. 反馈到上游
   - 缺验证命令 -> repo profile
   - work item 太虚 -> plan repair rule
   - repo 选错 -> design diagnosis
   - 需求不清 -> refine open question

4. UI 展示失败归因
   - 不是只显示日志
   - 显示“这更像是 plan 不清 / design 选错 / code 执行失败”

验收：

- code 失败后能判断主要归因阶段。
- 后续同类任务能消费沉淀信息。
- 用户能从失败页选择回到 refine/design/plan/code 任一阶段。

### Phase 6: 经验库与 repo profile

目标：让系统越用越聪明。

任务：

1. 建立 repo profile
   - repo 类型
   - 常用验证命令
   - 关键目录
   - 常见入口文件
   - 常见风险

2. 建立 failure knowledge
   - failure_type
   - repair strategy
   - 成功率
   - 示例 task

3. 接入 `.livecoding/context`
   - glossary
   - architecture
   - patterns
   - gotchas
   - validation

4. 给用户提供维护入口
   - 从失败结果一键沉淀规则
   - 从 repo 页面编辑验证命令
   - 从 task 页面保存经验

验收：

- 新任务能复用历史 repo profile。
- 常见验证命令不需要每次重新推断。
- repair 成功率可观察。

## 研发体验设计

### 正常路径

```text
Input -> Refine -> Design -> Plan -> Code
```

用户看到的是：

- 每阶段核心结论
- 关键 artifact
- warnings
- 下一步动作

### 需要人工确认

```text
Design -> needs_human -> 用户确认仓库执行职责 -> Design repair -> Plan
```

UI 应展示：

- 候选 repo
- 每个 repo 的证据
- 系统推荐
- 不确定原因
- 用户确认入口

### 自动修复路径

```text
Plan generate -> verify failed -> repair missing work item -> verify passed
```

UI 应展示：

- 自动修复了什么
- 修复前后 artifact diff
- 是否仍有 warning

## 指标

建议跟踪这些指标：

| 指标 | 含义 |
|------|------|
| stage pass rate | 每阶段一次通过率 |
| repair success rate | 自动修复成功率 |
| human intervention rate | 人工接管率 |
| blocking false positive rate | gate 误伤率 |
| code success rate | code 阶段验证通过率 |
| plan-to-code failure attribution | code 失败归因分布 |
| average attempts per stage | 每阶段平均重试次数 |

这些指标决定后续该调 prompt、调 verifier、调 gate，还是补 repo profile。

## 推荐落地顺序

我会按这个顺序做：

1. **先做诊断模型和观测**
   - 不改变用户主流程
   - 先收集真实失败分布

2. **再做 Refine repair**
   - 范围最小
   - 风险最低
   - 能验证“诊断式修复”模式是否成立

3. **再做 Design repo binding gate**
   - 这里对 code 成败影响最大
   - 要重点解决把绑定仓库误判为都要改、执行职责不清的问题

4. **再做 Plan work item 执行化**
   - 让 code 阶段少重新理解需求
   - 为更稳定自动编码打基础

5. **最后做 feedback 和经验库**
   - 等诊断模型稳定后再沉淀
   - 避免把脏数据沉淀成规则

## 非目标

当前阶段不建议做：

- 无限自动重试
- 所有 verify 失败都阻塞
- 让 plan 重新 adjudicate repo
- 让 code 阶段自由解释整个需求
- 一开始就做复杂知识库
- 直接把所有 markdown 改成统一大 schema

## 最小可行版本

如果只做一个最小版本，我建议做：

1. 新增统一 diagnosis schema。
2. 三阶段 verify 都输出 `severity / failure_type / next_action / issues[]`。
3. `Plan` 阶段 blocking 时不再只报错，而是写 `plan-diagnosis.json`。
4. 对缺 section、缺 work item、缺 candidate files 做最多 1 次 repair。
5. 对仓库执行职责不确定直接进入 `needs_human`。

这个版本就能把系统从“失败后不知道怎么办”推进到“失败后知道该修哪里或该问谁”。

## 总结

`coco-flow` 的方向不是复制聊天式 Agent，而是把聊天式 Agent 里有效的纠偏机制工程化。

稳定性来自：

- 明确 artifact contract
- 分级 gate
- 结构化 diagnosis
- 有限 repair loop
- 人工接管分支

聪明来自：

- 更好的上下文 bundle
- repo binding 证据
- code 失败反馈
- repo profile 和历史经验

最终目标是：

> 让不稳定的模型，在稳定的工程外壳里，持续产出研发能信任、能接手、能验证的结果。
