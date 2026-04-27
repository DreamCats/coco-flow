# Design Stage Session Design

本文记录 Design 引擎接入 ACP session 分层 prompt 的目标形态和当前落地状态。

## 背景

Refine 已验证了一个更接近 Claude Code 的工作方式：阶段开始时先建立稳定协议，再把具体 generate / verify 任务作为后续 prompt 送入对应 session。这个模式的价值不是“省 token”，而是把固定协议、角色边界、artifact 契约和具体任务拆开，让后续任务 prompt 更短、更稳定。

Design V3 当前已经是 agentic workflow：

- prepare input bundle
- research plan
- parallel repo research
- architect adjudication
- skeptic review
- bounded decision
- writer
- semantic gate

其中多个角色不能共享同一段聊天历史，否则 Architect 的假设、Writer 的表述或 Gate 的裁决容易互相污染。因此 Design 不能简单复用一个大 session，而应该按角色隔离。

## 目标

Design 阶段应把固定协议放进 bootstrap prompt，把角色 prompt 收窄为“本次任务 + artifact 路径 + 输出契约”。

需要稳定注入的内容包括：

- coco-flow 产品与 Design 阶段定位
- Design 只做技术设计裁决，不写 plan，不改代码
- refined PRD、repo research、skills brief、design decision 等 artifact 的事实优先级
- 证据优先的 repo 判定规则
- skills 只提供稳定规则和领域约束，不作为新需求或 must_change 证据
- 角色隔离策略
- 文件读写契约

## Session 拓扑

当前运行时拓扑：

```text
Architect Session
  bootstrap -> adjudication -> bounded revision

Skeptic Session
  inline bootstrap + review

Writer Session
  inline bootstrap + write design.md

Decision/Gate Session
  inline bootstrap + semantic gate
```

说明：

- Architect 是 Design 阶段最长的推理链，适合 standalone bootstrap，然后连续执行 adjudication 和 bounded revision。
- Skeptic 必须独立审查 Architect 的产物，不能共享 Architect session。
- Writer 只消费最终 decision，不应继承 Architect / Skeptic 的聊天过程。
- Gate 必须以 artifact 为事实源做最终裁决，不应继承 Writer 的润色倾向。

## ACP 经验约束

Refine 实测过“第二个 session 先 standalone bootstrap 再进入 verify”可能触发 ACP 长时间无响应或 Internal error。因此 Design 后续运行时应采用保守策略：

- 长生命周期角色可以使用 standalone bootstrap。
- 短生命周期角色优先使用 inline bootstrap，即 bootstrap 文本和任务 prompt 合并发送。
- 所有角色都以 artifact 传递事实，不依赖聊天历史传递事实。
- 日志必须记录 `session_role`、`bootstrap_prompt`、`agent_prompt_start/done/failed`。
- 任一 agent 失败后的降级产物必须标记为 `degraded` 或 `needs_human`，不能包装成通过。

## Artifact 契约

Design session 只应读取当前任务 prompt 明确列出的 artifact。主要机器事实源：

- `design-input.json`
- `design-research-plan.json`
- `design-research/<repo_id>.json`
- `design-research-summary.json`
- `design-adjudication.json`
- `design-review.json`
- `design-debate.json`
- `design-decision.json`

兼容与展示产物：

- `design-repo-binding.json`
- `design-sections.json`
- `design.md`
- `design-verify.json`
- `design-diagnosis.json`
- `design-result.json`

角色之间只通过这些 artifact 传递信息。聊天回复只允许简短确认完成，不粘贴完整产物。

## 落地状态

已完成：

- 新增 Design bootstrap prompt。
- 将 Architect / Skeptic / Writer / Gate / Revision prompt 收窄为任务 prompt。
- 运行时接入 Architect standalone session，并让 bounded revision 复用 Architect session。
- Skeptic / Writer / Gate 使用短 session + inline bootstrap。
- 日志记录 `session_role`、`bootstrap_prompt`、`agent_prompt_start/done/failed`。
- 阶段结束显式关闭 Design session。

待继续补强：

- 将 native agent 局部失败的 degraded 状态进一步结构化到 `design-result.json`，避免只依赖日志判断。
- 结合真实 ACP 运行结果继续调短 session bootstrap 策略。
