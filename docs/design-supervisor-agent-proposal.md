# Design Supervisor Agent 提案

本文沉淀一个后续新分支可验证的方向：在 Design 引擎中引入 `Supervisor Agent`，让它像 Tech Lead 一样审阅每一步中间产物，并基于明确理由调度子 agent 或程序工具重试。

当前 Design 引擎本身不是没有工具，而是缺少一个持续判断“这个中间结果是否可信”的总控层。固定流程可以跑完，但当 repo research 只找到弱相关文件、native writer 章节名不符合 gate、local fallback 输出模板化内容时，程序很难像人一样判断“这份设计是不是看起来像真的”。

## 命名

建议使用 `Supervisor Agent`。

原因：

- 比 `主 agent` 更具体，强调监督、审阅和纠偏。
- 比 `Orchestrator Agent` 更强调质量判断，而不只是流程编排。
- 比 `Review Agent` 更主动，因为它可以决定下一步调谁、是否重试、是否降级。

## 核心想法

现在的流程大致是程序固定编排：

```text
prepare input
  -> select skills
  -> repo research
  -> writer
  -> simple gate
  -> fallback
  -> output
```

目标形态是 Supervisor 驱动的有限闭环：

```text
Supervisor Agent
  -> 看输入和约束
  -> 决定调用哪些工具或子角色
  -> 审阅每一步返回结果
  -> 判断是否可信、是否足以进入下一步
  -> 不可信时给出原因和修正指令
  -> 最多重试有限轮
  -> 通过、降级或阻塞
```

这不是无限对话，而是有限轮次的内部评审循环。程序仍负责状态、落盘、超时、最大轮次和 artifact，Supervisor 负责判断和调度。

## 要解决的问题

以 `20260429-105926-auction` 暴露的问题为例：

- native writer 跑完了，但被 `_design_markdown_is_actionable()` 判为不合格。
- 当前日志只写 `design_writer_fallback: shallow_design_markdown`，没有说明具体缺哪类结构。
- fallback 尝试写文件落点时，容易把弱相关 candidate 写成看似精准的模块。
- 如果 fallback 完全不写文件落点，又会变成模板化设计。

这些问题靠继续堆硬编码规则收益有限。更合理的做法是让 Supervisor 判断：

- candidate file 是否真的支撑设计落点。
- 只是相关链路，还是可作为主改造点。
- native writer 是章节命名没命中 gate，还是内容确实不够。
- local fallback 应该输出“待补充设计”，还是可以给出明确方案。

## 角色划分

### Supervisor Agent

职责：

- 持有阶段目标和质量标准。
- 看每个步骤的返回结果。
- 决定是否继续、重试、补证据、降级或阻塞。
- 输出结构化评审结论。

不做：

- 不直接扫仓。
- 不直接写最终大段文档。
- 不替工具伪造证据。

### Research Tool / Research Agent

职责：

- 按 repo 做只读调研。
- 输出证据、候选文件、排除文件、unknowns。
- 明确哪些只是弱相关。

### Writer Agent

职责：

- 根据 Supervisor 认可的事实源写 `design.md`。
- 不新增需求、不伪造落点。
- 对不确定项写成待确认。

### Program Gate

职责：

- 做确定性校验。
- 负责超时、最大轮次、状态流转。
- 保存 rejected draft 和 quality report。

## 推荐流程

```text
prepare_design_input
  -> select_skills
  -> build_research_plan
  -> repo_research
  -> supervisor_review_research
      - evidence 是否足够？
      - 候选文件是否只是弱相关？
      - 是否需要补搜索词？
  -> writer_draft_design
  -> supervisor_review_design
      - 对象是否正确？
      - repo 职责是否可信？
      - 文件落点是否有证据？
      - 待确认项是否完整？
      - 是否违背非目标？
  -> bounded_repair_or_retry
  -> final_gate
  -> save design.md / quality report / contracts
```

## Supervisor Review 输出契约

建议输出 `design-supervisor-review.json`：

```json
{
  "passed": false,
  "decision": "repair_writer",
  "confidence": "medium",
  "blocking_issues": [
    {
      "type": "weak_candidate_promoted",
      "summary": "候选文件只证明相关链路，不能作为精准落点。",
      "evidence": ["repo research 中只命中对象词和实验词，未命中具体改造语义。"]
    }
  ],
  "repair_instructions": [
    "不要把弱相关 candidate 写成涉及模块/文件。",
    "将 live_pack 落点写为待补充定位，并列出需要确认的问题。"
  ],
  "next_action": "rewrite_design"
}
```

`decision` 可选值：

- `pass`
- `repair_writer`
- `redo_research`
- `degrade_design`
- `needs_human`
- `fail`

## 最大轮次

建议第一版只做小闭环：

- research review 最多 1 轮。
- writer repair 最多 1 轮。
- 总 native 调用不超过 3 次。

如果仍不通过：

- 不继续硬凑完整设计。
- 输出 `degraded` 质量状态。
- `design.md` 明确写“当前证据不足以确定精准落点”。
- `design-quality.json` 记录阻断项和下一步需要人工补的信息。

## Artifact 建议

新增或恢复以下 artifact：

- `design-supervisor-review.json`
- `design-quality.json`
- `design-writer-rejected.md`
- `design-research-summary.json`

用途：

- `design-supervisor-review.json`：解释 Supervisor 为什么通过或退回。
- `design-quality.json`：给 UI/Plan 判断质量状态。
- `design-writer-rejected.md`：保留 native writer 被 fallback 的原文，便于诊断。
- `design-research-summary.json`：让 research 证据可回放，而不是只存在 prompt 中。

## 第一阶段最小实现

当前分支已开始落地第一阶段：`quality/` 拆成独立程序规则层，`supervisor/` 新增 `supervisor_review_design()`；
随后 native Design 主链路已开始切到 Research Agent + Research Supervisor，旧程序化 repo research 只保留给 local executor；
native Research Agent 失败会显式写入 research gate，不能偷偷回落成旧 research 后通过。
Design 主流程会写 `design-quality.json`、`design-supervisor-review.json`、`design-research-summary.json`，
并在 native writer 草稿被退回时保留 `design-writer-rejected.md`。

第一阶段不需要重写整个引擎，只加一个 Supervisor review 点：

```text
repo_research
  -> writer
  -> supervisor_review_design
  -> repair_writer_once 或 degrade_design
```

具体改动：

- 保留 native writer 被拒稿件：`design-writer-rejected.md`。
- `_design_markdown_is_actionable()` 返回结构化失败原因，而不是 bool。
- 新增 `supervisor_review_design()`，让 agent 读取 PRD、research summary、draft design。
- 如果 Supervisor 指出可修复问题，把 critique 传回 writer 重写一次。
- 如果 Supervisor 判断证据不足，输出 degraded design，不写猜测落点。

## 与当前质量优化任务的关系

现有 `docs/design-quality-optimization-tasks.md` 仍然是短期修补路线。

本提案是下一阶段重构方向：

- 短期：修 fallback、补 post-check、改善日志。
- 中期：引入 Supervisor review。
- 长期：Supervisor 接管 Design 阶段有限闭环编排。

## 关键原则

- 程序不要用固定业务词表替代设计判断。
- 弱相关候选不能写成精准落点。
- 没有证据时要降级或待确认，不要生成看似确定的方案。
- native 被拒必须保留原文和失败原因。
- Supervisor 的每次退回都必须有明确原因，不能只说“不够好”。
