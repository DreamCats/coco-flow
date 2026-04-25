# Workflow Doc-Only MVP

本文记录当前第一版取舍：Refine / Design / Plan 阶段先移除阶段 schema，只保留 Markdown 文档。

核心判断：

- 准度优先来自人工提炼范围、Skills/SOP、业务地图、仓库地图和代码证据。
- 第一版不把模型中间判断沉淀成多份 JSON。
- 引擎只负责编排输入、Skills/SOP、必要代码调研和 LLM 写文档。
- Markdown 是人类可读、可编辑、可讨论的唯一阶段产物。

## 保留与移除

保留的运行时元数据：

- `task.json`
- `repos.json`
- `input.json`
- `source.json`
- 日志文件，例如 `refine.log`、`design.log`、`plan.log`

这些文件是工作台运行、状态流转和 repo 绑定所必需，不属于 Refine / Design / Plan 的推理 schema。

阶段产物只保留：

```text
Refine:
  prd-refined.md

Design:
  design.md

Plan:
  plan.md
```

第一版移除或不再持久化：

- `refine-brief.json`
- `refine-intent.json`
- `refine-verify.json`
- `refine-diagnosis.json`
- `refine-result.json`
- `design-input.json`
- `design-research-plan.json`
- `design-research-summary.json`
- `design-adjudication.json`
- `design-review.json`
- `design-debate.json`
- `design-decision.json`
- `design-repo-binding.json`
- `design-sections.json`
- `design-verify.json`
- `design-diagnosis.json`
- `design-result.json`
- `plan-work-items.json`
- `plan-execution-graph.json`
- `plan-validation.json`
- `plan-review.json`
- `plan-debate.json`
- `plan-decision.json`
- `plan-verify.json`
- `plan-diagnosis.json`
- `plan-result.json`

## Refine

输入：

- 原始 PRD
- 人工提炼范围
- 必要原文片段

输出：

- `prd-refined.md`

原则：

- 人工提炼范围优先级最高。
- 不生成 brief / intent / verify / diagnosis JSON。
- 校验、修复和 native 生成所需的中间对象只存在于内存或临时文件，不进入 task 目录。

## Design

输入：

- `prd-refined.md`
- `repos.json`
- repo research 结果
- Skills/SOP

输出：

- `design.md`

原则：

- 业务规则、仓库依赖、SOP 判断都写在 Skills/SOP 中，不写死在引擎。
- 引擎可以做代码调研，但 research summary 不再作为持久化 schema。
- Design 文档里直接写清仓库职责、依赖、候选代码线索、风险与待确认。
- 不再通过 `design-decision.json`、`design-repo-binding.json`、`design-sections.json` 传递事实。

## Plan

输入：

- `prd-refined.md`
- `design.md`
- `repos.json`
- Skills/SOP

输出：

- `plan.md`

原则：

- Plan 不再生成 work item schema、execution graph、validation JSON。
- 执行顺序、任务拆解、验证策略直接写入 `plan.md`。
- 如果 `design.md` 不可执行或自相矛盾，在 `plan.md` 的风险与阻塞项中写清楚。

## Code 兼容

Code 阶段暂时兼容两种输入：

- 如果旧结构化产物存在，继续消费旧产物。
- 如果结构化产物不存在，退回到 `repos.json`、`prd-refined.md`、`design.md`、`plan.md`。

这保证 doc-only Plan 不会阻断后续 Code 阶段。

## 取舍

优点：

- 降低引擎复杂度。
- 避免 Markdown 和 JSON 双事实源冲突。
- 人工编辑路径更自然。
- 业务定制沉淀在 Skills/SOP，不污染通用引擎。

代价：

- 下游自动化可消费的结构化信息减少。
- Code 阶段需要更多依赖文档理解。
- UI 暂时少了精细 gate / diagnosis 展示。

当前选择是先用简单版本验证 workflow 准度，再决定哪些 schema 值得加回来。

