# Design Engine Agentic Redesign

本文定义下一轮 `Design` 引擎的大改方向：从规则流水线转向“证据收集 + 多角色 LLM 裁决 + 对抗校验 + 阶段化 artifact”的 agentic workflow。

如果这套模式验证有效，`Refine` 和 `Plan` 后续也应学习同一类架构：编排层只负责上下文、状态、产物和 gate，核心判断交给职责明确的 agent 角色。

## 背景判断

当前 `Design` 引擎已经具备完整阶段产物，但复杂度主要堆在规则上：

- change point、repo assignment、research、matrix、binding、sections、generate 串成线性流水线。
- 文件候选、repo 职责、接口变更、风险边界里有大量启发式规则。
- native 失败后可能 fallback 到 local，local 结果更像模板填空。
- verify 主要检查契约和格式一致性，较少判断设计方案是否真的解决 refined PRD。

这些规则能让产物稳定成形，但会降低真实设计判断质量。`Design` 的核心价值不是把前序 JSON 拼成文档，而是判断：

- 改动范围是否找准。
- 哪些仓库真的要改，哪些只是验证或参考。
- 关键实现落点和系统边界是否有证据。
- 当前信息不足时是否应该停下来让人确认。

`OpenHarness` 的启发是：它的代码并不复杂，复杂度在角色协议上。planner、worker、verifier、coordinator 各自职责明确，通过自然语言和工具形成内部评审闭环。`coco-flow` 不能照搬无限人机对话，但可以把这种“内部对话”产品化为有限轮次的阶段工作流。

## 设计原则

### 1. 编排层不替模型做设计判断

Python 引擎负责：

- 读取稳定输入。
- 组织 repo / skills / task artifacts。
- 分发只读调研任务。
- 收集和归档 agent 结果。
- 执行 schema 校验、状态流转、诊断和 gate。

Python 引擎不再负责：

- 用硬编码关键词判断某个仓库是否必须修改。
- 用固定分数裁定候选文件优先级。
- 用规则推断复杂设计结论。
- 把 local 模板稿包装成高质量设计稿。

### 2. Design 是有限轮内部评审，不是无限对话

`coco-flow` 的产品目标是阶段式异步处理。用户可以启动任务后去做别的事，回来看到：

- 当前阶段产物。
- 当前裁决依据。
- 当前风险和不确定项。
- 下一步动作。

因此 `Design` 内部可以多 agent 讨论，但必须有限、可复现、可落盘。默认最多 2 轮：

1. architect 生成裁决。
2. skeptic/verifier 挑刺。
3. architect 根据问题修订一次。
4. final gate 决定通过、降级、阻塞或等待人工确认。

### 3. Markdown 是表达，不是唯一事实源

最终目标仍然是高质量 `design.md`，但机器消费的事实源应该是结构化裁决。内部结构化产物可以保留 evidence / confidence / repo work type，供 gate、diagnosis 和 `Plan` 消费；`design.md` 不应该把这些内部标签直接暴露给研发。

- repo responsibilities
- candidate files
- design decisions
- risks
- unresolved questions
- verification notes

`design.md` 只是把裁决结果写成人能快速判断的工程设计文档。

### 4. 不确定性进入 diagnosis，不污染 design.md

研发读 `design.md` 时主要关心“该怎么改”，不关心哪些判断是 high confidence、哪些是 low confidence。置信度和证据强弱应该进入 JSON artifact、diagnosis 和 UI 状态，而不是成为 `design.md` 的主体内容。

不能为了流程顺滑强行生成“看似完整”的文档。遇到下面情况时，必须进入 `needs_human` 或 `degraded`：

- 多个 repo 都可能承担同一核心改造点，但证据不足。
- refined PRD 和 repo research 冲突。
- 关键候选文件无法定位。
- verifier 指出方案不能支撑 PRD。
- native agent 全部失败，只剩 local fallback。

## 目标产物

`Design` 完成后，研发看到 `design.md` 应该能判断：

- 本次核心改造点是什么。
- 各个仓库分别主要做什么事。
- 每个仓库的主要改点、候选文件和改动边界是什么。
- 本次明确不做什么。
- 风险和待确认项是什么。

研发不应该被迫理解 `主仓 / 次仓 / 协同仓 / validate_only / reference_only / confidence` 这些内部标签。引擎内部可以保留这些字段做机器消费，但 `design.md` 要用自然语言回答“哪个仓库做什么、为什么这个范围够用、风险是什么”。

下游 `Plan` 消费结构化 artifact，而不是重新理解一份散文。

## 输入契约

`Design` 的输入是一个 `DesignInputBundle`：

```text
prd-refined.md
input.json
refine-brief.json
refine-intent.json
refine-skills-selection.json
refine-skills-read.md
repos.json
skills brief
task metadata
```

输入规则：

- `prd-refined.md` 是需求基线。
- 用户绑定 repo 是搜索空间和强提示，不等于最终都要修改。
- skills/知识库提供稳定规则和领域词表，不得扩写成新需求。

## 新阶段流程

```text
prepare input bundle
  -> research plan
  -> parallel repo research
  -> evidence normalization
  -> architect adjudication
  -> skeptic review
  -> bounded revision
  -> final decision
  -> design.md writer
  -> semantic gate
```

### 1. Prepare Input Bundle

编排层统一准备输入摘要：

- refined scope
- manual change points
- bound repos
- repo paths
- selected skills
- constraints

输出：

- `design-input.json`
- `design-input.md`

### 2. Research Plan

一个轻量 planner 先决定要调研什么，而不是直接扫全仓：

- 每个 repo 的调研目标。
- 优先搜索的术语、目录、文件类型。
- 最大搜索预算。
- 需要回答的问题。

输出：

- `design-research-plan.json`

示例结构：

```json
{
  "repos": [
    {
      "repo_id": "live-pack",
      "questions": [
        "成功态状态在哪里定义或聚合？",
        "是否存在与 refined scope 直接对应的 converter/loader？"
      ],
      "search_terms": ["success", "auction", "status"],
      "preferred_paths": ["pkg/**", "biz/**"],
      "budget": {
        "max_files_read": 12,
        "max_search_commands": 8
      }
    }
  ]
}
```

### 3. Parallel Repo Research

按 repo 并发只读 subagent。每个 agent 必须：

- 只分析自己的 repo。
- 优先使用 research plan。
- 搜索相关代码，不读全仓。
- 输出证据，而不是只给结论。
- 明确 unknowns。

输出：

```text
design-research/<repo_id>.json
design-research-summary.json
```

`design-research/<repo_id>.json` 推荐结构：

```json
{
  "repo_id": "live-pack",
  "work_hypothesis": "requires_code_change",
  "confidence": "medium",
  "evidence": [
    {
      "path": "pkg/auction/status_converter.go",
      "line_hint": 42,
      "why_relevant": "这里聚合竞拍状态并影响卡片展示状态"
    }
  ],
  "candidate_files": [
    {
      "path": "pkg/auction/status_converter.go",
      "kind": "core_change",
      "confidence": "high",
      "reason": "直接承接状态聚合逻辑"
    }
  ],
  "boundaries": [
    "未发现需要修改对外 proto 的证据"
  ],
  "unknowns": [
    "是否还有下游 BFF 覆写成功态，需要跨仓确认"
  ]
}
```

### 4. Architect Adjudication

architect 读取所有 repo research，做跨仓裁决：

- change point 是否成立。
- repo 工作内容是否成立。
- 是否单仓可闭合。
- 每个仓库具体需要做什么。
- 哪些仓库只需要检查，不需要修改。
- 哪些候选文件是核心改点。
- 哪些风险需要人工确认。

输出：

- `design-adjudication.json`

该步骤是新的 `Design` 核心。它替代当前大量 hardcoded matrix / binding 规则。

### 5. Skeptic Review

skeptic/verifier 不负责润色文档，只负责反驳 architect：

- 是否误读 refined PRD。
- 是否把相关仓误判成需要修改代码。
- 是否遗漏关键仓。
- 候选文件是否有证据。
- 风险是否真实。
- 方案是否能支撑 `Plan`。

输出：

- `design-review.json`

示例：

```json
{
  "ok": false,
  "issues": [
    {
      "severity": "blocking",
      "failure_type": "repo_role_not_proven",
      "target": "repo_bindings.live-shopapi",
      "expected": "如果要求 live-shopapi 修改代码，必须有字段/接口变更证据",
      "actual": "research 只发现消费链路，没有发现必须修改接口的证据",
      "suggested_action": "改成只做联动检查，或补充接口变更证据"
    }
  ]
}
```

### 6. Bounded Revision

如果 skeptic 提出 blocking issue，architect 最多修订 1 次。修订必须：

- 明确接受或拒绝每个 issue。
- 拒绝时给出证据。
- 不得扩大 refined scope。

输出：

- `design-debate.json`
- `design-decision.json`

如果仍有 blocking issue，进入 `needs_human` 或 `failed`。

### 7. Design Writer

writer 只负责把 `design-decision.json` 写成 `design.md`。writer 不做新的 repo 裁决。

输出：

- `design.md`

要求：

- 自然语言表达，不暴露内部标签。
- 结论先行。
- 每个涉及仓库都要说明“主要做什么事、落在哪些文件或模块、边界是什么”。
- 待确认项只写会影响研发判断的问题，不写内部 confidence。
- 不把只需检查的仓库写成本次代码改造项。

### 8. Semantic Gate

最终 gate 包含两层：

1. contract gate：章节、schema、repo 覆盖、文件引用。
2. semantic gate：是否解决 refined PRD、各仓改动范围是否有证据、风险是否真实。

输出：

- `design-verify.json`
- `design-diagnosis.json`
- `design-result.json`

## Artifact 设计

新增或调整后的 artifact：

```text
design-input.json
design-input.md
design-research-plan.json
design-research/<repo_id>.json
design-research-summary.json
design-adjudication.json
design-review.json
design-debate.json
design-decision.json
design-repo-binding.json
design-sections.json
design.md
design-verify.json
design-diagnosis.json
design-result.json
design.log
```

兼容策略：

- 保留 `design-repo-binding.json`，由 `design-decision.json` 派生。
- 保留 `design-sections.json`，作为 `design.md` 和 `Plan` 的兼容输入。
- 旧的 `design-change-points.json`、`design-repo-assignment.json`、`design-repo-responsibility-matrix.json` 可以先继续生成，但逐步降级为 debug artifact。

## Gate 策略

`Design` 结果状态不再只有 pass/fail。

| 状态 | 含义 | 是否允许进入 Plan |
|------|------|-------------------|
| `passed` | native 完成，semantic gate 通过 | 允许 |
| `passed_with_warnings` | 有非阻塞风险 | 允许，UI 展示 warning |
| `needs_human` | 关键改动范围判断冲突或证据不足 | 不允许，等待人工确认 |
| `degraded` | native 失败，只得到 local/partial 草稿 | 默认不允许，人工确认后可继续 |
| `failed` | 引擎失败或产物不可用 | 不允许 |

local fallback 规则：

- local 可以生成调试草稿。
- local 不得自动写 `ok=true`。
- local 结果必须标记 `degraded`。
- `degraded` 进入 Plan 需要人工确认。

## Agent 角色协议

### Repo Research Agent

职责：

- 只读当前 repo。
- 按 research plan 搜索。
- 输出证据、候选文件、unknowns。

禁止：

- 修改文件。
- 读取无关大范围代码。
- 对其他 repo 下最终结论。

### Architect Agent

职责：

- 综合所有 repo research。
- 做最终设计裁决。
- 给出 repo binding、系统边界、风险、待确认项。

禁止：

- 引入 research 中完全没有证据的文件。
- 把“相关”直接等同于“必须改”。
- 为了让流程通过而隐藏需要人工确认的问题。

### Skeptic Agent

职责：

- 站在反方审查裁决。
- 寻找误选 repo、遗漏 repo、证据不足、PRD 未覆盖。
- 输出结构化 blocking/warning/info issues。

禁止：

- 重写方案。
- 只检查格式。
- 无证据地否定。

### Writer Agent

职责：

- 把 final decision 写成高质量 `design.md`。
- 改善表达、结构和可读性。

禁止：

- 新增裁决。
- 删除风险和待确认项。
- 把内部 JSON 字段直接暴露给用户。

## Search Budget

为了避免“读全仓”，每个 repo research 必须有预算。

默认建议：

- 最多 40 次搜索命令。
- 最多读取 30 个文件。
- 单文件最多截取关键片段。
- 优先读 refined scope 命中的术语附近代码。

超预算时，agent 必须停止并输出 unknowns，而不是继续扩大搜索。

## 迁移计划

### Phase 1：先修 gate 和 fallback

目标：停止把低质量 fallback 包装成通过。

- native design 失败后写 `degraded`。
- local design 不再自动 `ok=true`。
- `design-diagnosis.json` 明确提示人工确认。
- `Plan` 默认阻止消费 degraded design。

### Phase 2：引入 repo research agent artifact

目标：让调研结果以证据形式落盘。

- 增加 `design-research-plan.json`。
- 按 repo 并发生成 `design-research/<repo>.json`。
- 保留现有 binding 逻辑，但优先使用 repo research evidence。

### Phase 3：引入 architect + skeptic

目标：把 hardcoded matrix/binding 降级为 fallback。

- 新增 `design-adjudication.json`。
- 新增 `design-review.json`。
- blocking issue 触发 1 次 bounded revision。
- 输出 `design-decision.json`。

### Phase 4：writer 和 semantic gate

目标：让 `design.md` 成为 final decision 的高质量表达。

- writer 只读 `design-decision.json`。
- semantic verifier 检查 PRD 覆盖、证据和风险。
- contract verifier 继续保留。

### Phase 5：推广到 Refine / Plan

如果 Design V3 效果好：

- `Refine` 引入需求 skeptic，专门检查是否过度提炼或遗漏人工范围。
- `Plan` 引入 execution planner + plan verifier，对 work item 可执行性做对抗审查。
- 三阶段统一 diagnosis / gate / degraded 语义。

## 不做什么

本轮不建议：

- 继续扩大硬编码关键词表。
- 继续调阈值来修 design 质量。
- 让 generate prompt 承担所有设计判断。
- 用无限重试代替明确 gate。
- 把 OpenHarness 整套 coordinator runtime 搬进 `coco-flow`。

`coco-flow` 需要借鉴的是角色边界和评审闭环，不是交互形态本身。

## 成功标准

这次重构成功的标志：

- design.md 能清楚回答核心改造点、各仓库主要做什么、不做什么和风险。
- 改动范围证据不足时会主动停下来，而不是生成漂亮但错误的文档。
- 研发能从 design.md 快速判断这个方案是否能直接进入 plan。
- Plan 不再需要重新猜 design 意图。
- 引擎代码减少领域硬编码，新增复杂度主要集中在角色 prompt 和 artifact contract。

一句话目标：

> Design 引擎应该像一个可复现的内部架构评审会：先分头调研，再集中裁决，再有人挑刺，最后沉淀成可读、可执行、可追责的设计文档。
