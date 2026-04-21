# Engine 质量与效率优化计划

本文档基于对 Refine、Design、Plan 三个引擎的完整代码分析，给出质量提升和速度提升的具体优化思路与实施计划。

## 现状摘要

| 引擎 | Native 模式 LLM 调用数 | 并行度 | 反馈循环 | 复杂度 |
|------|----------------------|--------|---------|--------|
| Refine | 最多 5 次串行 (intent → shortlist×N → knowledge_read → generate → verify) | 无 | 无 (verify 只记录不回补) | 低 |
| Design | 最多 6+N 次 (change_points → research×N → matrix → binding → generate → verify) | 仅 repo research 并行 | 无 | 高 |
| Plan | 最多 3 次串行 (task_outline → generate → verify) | 无 | 无 | 中 |

三个引擎的共性问题：
1. **所有步骤严格串行**（Design 的 repo research 除外），即使部分步骤之间无数据依赖
2. **Verify 不闭环**：verify 发现问题只记录 JSON，不触发重新生成
3. **`fresh_session=True` 全局开启**：每次 LLM 调用都是冷启动，无法复用上下文
4. **Prompt 未利用结构化输出能力**：通过写临时文件 + `__FILL__` 占位符让 agent 编辑，效率低于直接 JSON schema 约束输出
5. **无增量计算**：重跑某步骤时所有后续步骤全部重算

---

## 一、质量优化

### 1.1 Verify → Regenerate 闭环 (影响: 高, 全引擎)

**现状问题**: 三个引擎的 verify 步骤仅产出 `{ok, issues, reason}` JSON，当 `ok=false` 时不做任何修正动作。这意味着 LLM 的自检能力被浪费了——发现了问题但不修。

**优化方案**: 在 verify 返回 `ok=false` 时，将 issues 和原始产物一起喂回 generate 步骤做定向修正，最多重试 1 次。

```
generate → verify → (ok=false?) → regenerate_with_issues → re-verify → 接受
```

**实施要点**:
- 在 `generate_design_markdown()`、`generate_native_refine()`、`generate_native_plan_markdown()` 三处增加条件重试逻辑
- 构建新 prompt 函数 `build_*_regenerate_prompt(original_output, verify_issues)`，在原 prompt 末尾追加 issues 约束
- 最多重试 1 次，避免死循环；第二次 verify 无论结果都接受
- 重试时复用同一 session（将 `fresh_session` 改为 `False`），利用上下文连续性

**预期收益**: design.md / plan.md 的结构完整性和一致性显著提升，尤其是"遗漏 must_change repo"、"section 缺失"等可机器检测的问题将被自动修正。

---

### 1.2 Change Points 质量加固 (影响: 高, Design)

**现状问题**: `build_design_change_points_payload()` 从 refined sections 提取改造点，但提取逻辑依赖 LLM 一次性输出，缺少与 refine-intent 的交叉验证。如果 LLM 遗漏某个改造点，后续所有步骤（assignment → research → binding → generate）都会缺失对应内容。

**优化方案**:
1. 提取后用 `refine-intent.json` 的 `change_points` 做覆盖率检查：refine 阶段识别的每个 change point 是否在 design change points 中被覆盖
2. 未覆盖的自动补入，标记 `source: "refine_intent_backfill"`
3. 对 LLM 提取的 change points 做去重合并（当前已有），但增加语义去重：标题相似度 > 0.8 的合并

**实施要点**:
- 在 `assignment.py` 的 `build_design_change_points_payload()` 返回前增加 `_backfill_from_refine_intent()` 调用
- 使用 refine intent 的 `change_points` 列表做 term overlap 比对
- 纯本地逻辑，不增加 LLM 调用

---

### 1.3 Research 质量提升: 引导式探索 (影响: 高, Design)

**现状问题**: repo research 的 agent 在目标仓库内自由探索，仅凭 prompt 约束。当仓库较大或改造点不明确时，agent 容易陷入无关代码，产出 `candidate_files` 和 `evidence` 质量不稳定。

**优化方案**: 改为"引导式探索" —— 基于 change points 和 local prefilter 的信号，先生成具体的探索路径（目录 + 文件模式），再让 agent 沿路径做深度验证。

```
当前: prompt(change_points + repo_hint) → agent 自由探索
优化: local_prefilter(candidate_dirs, candidate_files) → 构建 exploration_plan → agent 沿 plan 验证 + 补充发现
```

**实施要点**:
- 在 `_explore_repo_with_agent()` 中，将 `local_entry` 的 `candidate_dirs` 和 `candidate_files` 作为 "exploration plan" 注入 prompt
- prompt 调整为："先验证以下候选路径的相关性，再沿这些路径扩展搜索"
- 减少 agent 的自由探索空间，提高命中率

---

### 1.4 Responsibility Matrix 前置校验 (影响: 中, Design)

**现状问题**: 当前 responsibility matrix 在 binding 之前生成，binding 会通过 `_merge_matrix_priors()` 合并 matrix 的建议。但 matrix 本身的质量取决于 research 的质量，如果 research 对某 repo 的理解有误，matrix 会放大这个错误。

**优化方案**: 在 matrix 生成后增加一致性检查：
1. 如果某 repo 的 matrix 全为 `none`，但 research 标记为 `in_scope_candidate`，标记为异常
2. 如果某 repo 被 matrix 建议为 `must_change`，但 research 的 `confidence` 为 `low`，标记为需人工审查
3. 将异常点写入 `design-repo-responsibility-matrix.json` 的 `warnings` 字段

**实施要点**:
- 在 `matrix.py` 的 `build_design_responsibility_matrix_payload()` 返回前增加 `_validate_matrix_consistency()` 
- 纯本地规则检查，不增加 LLM 调用

---

### 1.5 Plan 工作项依赖准确性 (影响: 中, Plan)

**现状问题**: `build_plan_execution_graph()` 用 BFS 拓扑排序构建执行图，但工作项之间的依赖关系由 LLM 在 task_outline 中一次性给出，缺少基于代码结构的依赖推断。例如，如果 repo A 的改动会影响 repo B 的 API 契约，但 LLM 没有识别这个依赖，执行图就会错误地将两者标为可并行。

**优化方案**: 在 task_outline 后增加基于 design artifacts 的依赖交叉验证：
1. 从 `design-sections.json` 的 `system_dependencies` 提取结构化依赖
2. 与 task_outline 的 `depends_on` 比对
3. 自动补充缺失的硬依赖（`hard_dependency` 类型）
4. 对冲突的依赖关系（task_outline 说可并行，design 说有依赖）发出警告

**实施要点**:
- 在 `plan/pipeline.py` 的 `build_plan_work_items()` 后增加 `_cross_validate_dependencies(work_items, sections_payload)` 
- 纯本地逻辑

---

### 1.6 Prompt 工程优化 (影响: 中, 全引擎)

**现状问题**: 当前 prompt 结构规范（PromptDocument 标准化），但缺少以下被广泛验证有效的技术：
- 无 few-shot 示例：所有 prompt 都是 zero-shot，LLM 需要从头理解输出格式
- 无显式 chain-of-thought 引导：复杂判断（如 scope_tier 决策）直接要求输出结果，不要求中间推理
- 输出契约过于冗长：部分 prompt 的 requirements 超过 10 条，信息密度低

**优化方案**:
1. 为 design 的关键步骤（change_points、repo_binding、responsibility_matrix）增加 1-2 个 few-shot 示例
2. 在 repo_binding prompt 中增加 "先列出判断依据，再给出结论" 的 CoT 引导
3. 精简低信息量的 requirements 条目，将重复约束合并

**实施要点**:
- 在 `prompts/design/` 的对应模块增加 `EXAMPLE_*` 常量
- 修改 `PromptDocument` 增加 `examples` 字段（可选）
- few-shot 示例从已有的测试数据或高质量历史产物中提取

---

## 二、速度优化

### 2.1 步骤级并行: DAG 编排 (影响: 高, Design)

**现状问题**: Design 的 8 个步骤中，大部分被实现为严格串行，但实际依赖关系允许部分并行：

```
当前执行顺序 (串行):
prepare → knowledge_brief → change_points → repo_assignment → research → matrix → binding → generate+verify

实际依赖图:
prepare ──┬── knowledge_brief ──────────────────────────────────────┐
          ├── change_points → repo_assignment → research ──────────┤
          │                                            └── matrix ─┤── binding → generate → verify
          └── (可提前启动 local prefilter)                          │
```

**优化方案**: 将 pipeline 改为基于依赖图的并行编排：
1. `knowledge_brief` 和 `change_points` 在 `prepare` 完成后同时启动
2. `repo_assignment` 依赖 `change_points`，在其完成后立即启动
3. `research` 依赖 `repo_assignment`，但可以与 `knowledge_brief` 并行
4. `matrix` 依赖 `research`
5. `binding` 依赖 `matrix` + `knowledge_brief`
6. `generate` 依赖 `binding`

**预期收益**: 在典型 3-repo 场景下，Design 阶段耗时从 ~6 个 LLM 调用的串行等待减少到 ~4 个关键路径长度（prepare → change_points → repo_assignment → research 是关键路径，knowledge_brief 被并行掩盖）。

**实施要点**:
- 引入轻量 DAG 执行器（不引入第三方依赖，基于 `concurrent.futures` + `threading.Event`）
- 每个步骤封装为一个 `StepFn(inputs) -> output`，声明依赖
- 修改 `pipeline.py` 调用方式：从顺序调用改为 `dag.run(steps)`
- 保持现有的 `on_log` 回调接口不变

---

### 2.2 Session 复用策略 (影响: 高, 全引擎)

**现状问题**: 所有 native agent 调用都设置 `fresh_session=True`，每次调用都是完全冷启动。对于同一个 Design 流程中的 change_points → repo_assignment → matrix → binding 这条链路，前一步的输出就是后一步的输入，完全可以在同一个 session 中连续对话。

**优化方案**: 引入"session chain"概念：
1. 同一 pipeline 内的顺序依赖步骤共享 session（`fresh_session=False`）
2. 并行步骤各自使用独立 session（现有行为）
3. 跨 pipeline 步骤（如 refine → design）继续使用 fresh session

**Session 链路设计**:
```
Design:
  Chain A: change_points → matrix → binding (同一 session，模式 prompt_only)
  Chain B: research_repo_1 (独立 session，模式 agent)
  Chain C: research_repo_2 (独立 session，模式 agent)
  Chain D: generate → verify (同一 session，模式 agent)

Refine:
  Chain A: intent → generate → verify (同一 session)
  Chain B: shortlist → knowledge_read (同一 session)

Plan:
  Chain A: task_outline → generate → verify (同一 session)
```

**预期收益**: 
- 减少 ACP session 创建开销（每次约 2-3s）
- LLM 在后续调用中可利用前文上下文，减少 prompt 重复传递的 token 数
- 输出一致性提升（同一 session 内风格和术语更连贯）

**实施要点**:
- 在 `CocoACPClient` 上增加 `session_chain()` context manager，返回一个绑定到特定 session ID 的 client wrapper
- 修改引擎调用从 `client.run_agent(prompt, ..., fresh_session=True)` 改为 `with client.session_chain() as chain: chain.run_agent(prompt, ...)`
- 对 daemon 层不需要修改，session pool 已支持 session 复用

---

### 2.3 Knowledge Shortlist 批量化 (影响: 中, Refine)

**现状问题**: Refine 的 knowledge shortlisting 将 knowledge cards 按每 8 个一组分块，每组一次 LLM 调用。当 knowledge base 有 20+ 文档时，需要 3+ 次串行调用，每次都是独立判断，还可能产生不一致的评分标准。

**优化方案**: 改为单次调用 + token 优化：
1. 将每个 knowledge card 压缩为 1-2 行摘要（id + title + 关键词），而非完整 YAML card
2. 在单次调用中处理所有 cards，prompt 要求输出 `{selected: [id1, id2], rejected: [id3, ...]}`
3. 如果 card 数量超过 30（罕见），才回退到分块模式

**预期收益**: 大多数场景下将 2-3 次串行调用减少为 1 次，且评分标准全局一致。

**实施要点**:
- 修改 `refine/knowledge.py` 的 `_native_select()` 
- 新增 `_build_compact_card_list()` 将 YAML cards 压缩为行式摘要
- 调整 shortlist prompt 适配单次批量输入

---

### 2.4 Local Fallback 加速 (影响: 中, 全引擎)

**现状问题**: 当前 local fallback 作为 native 失败时的降级方案存在。但有些步骤的 local 实现已经足够好，不需要 LLM 调用。

**优化方案**: 对以下步骤默认使用 local 实现，省去 LLM 调用：
1. **Repo assignment** (`build_design_repo_assignment_payload`): 当前已经是纯启发式实现，无需调整
2. **Knowledge brief** (`build_design_knowledge_brief`): 当前是纯本地实现，确认无需调整
3. **Execution graph** (`build_plan_execution_graph`): 当前已是纯算法实现
4. **Plan validation** (`build_plan_validation`): 当前已是纯本地实现

**新增建议**:
- Design verify 在单 repo 场景下跳过（当前已实现）
- Refine verify 在 intent 提取质量分 > 阈值时跳过（新增）
- Plan verify 在工作项数 ≤ 3 时跳过（新增）

---

### 2.5 Prompt Token 压缩 (影响: 中, Design)

**现状问题**: Design generate 的 prompt 包含完整的 `refined_markdown`（可能数千字）、`repo_binding_payload`（JSON）、`sections_payload`（JSON）、`knowledge_brief_markdown`。总 token 数在复杂任务时可能接近模型上下文窗口的 1/3。

**优化方案**:
1. **Refined markdown 摘要化**: generate 步骤不需要完整的 refined PRD，只需要目标、改造点列表和关键约束。构建 `_summarize_refined_for_generate()` 提取核心段落。
2. **JSON payload 精简**: repo_binding 中的 `prefilter_reasons`、`notes` 等辅助字段在 generate 阶段已无用，传入时裁剪。
3. **Knowledge brief 条件传入**: 如果 knowledge brief 为空或 < 100 字，不作为 section 传入。

**预期收益**: generate 步骤的 prompt token 减少 30-50%，降低延迟和成本。

---

### 2.6 模板文件机制优化 (影响: 中, 全引擎)

**现状问题**: 当前 LLM 输出通过"写临时文件 → agent 编辑文件 → 读回文件"的方式实现。这要求 agent 具有文件编辑能力（AGENT_MODE），且增加了文件 I/O 和 agent tool-use 的往返开销。

**优化方案**: 对于不需要 agent 读取仓库文件的步骤（change_points、matrix、binding、verify），改为 `prompt_only` 模式 + 直接从 response text 解析输出：
1. 将 `run_agent()` 改为 `run_prompt_only()`
2. prompt 要求输出 ```json ... ``` 格式
3. 从 response text 中提取 JSON block

**适用步骤**:
| 引擎 | 步骤 | 当前模式 | 可改为 |
|------|------|---------|--------|
| Design | change_points | agent | prompt_only |
| Design | matrix | agent | prompt_only |
| Design | binding | agent | prompt_only |
| Design | verify | agent | prompt_only |
| Design | generate | agent | agent (需要写文件) |
| Design | research | agent | agent (需要读仓库) |
| Refine | intent | agent | prompt_only |
| Refine | shortlist | agent | prompt_only |
| Refine | verify | agent | prompt_only |
| Plan | task_outline | agent | prompt_only |
| Plan | verify | agent | prompt_only |

**预期收益**: 
- `prompt_only` 模式禁用所有工具，LLM 直接生成文本，省去 tool-use 的往返（每次 agent 模式的 tool-use 至少增加 1 次往返 = 2-5s）
- 消除临时文件的创建/读取/删除开销
- 减少 prompt 中 "必须编辑模板文件" 的指令 token

---

## 三、架构优化

### 3.1 统一 DAG Pipeline 框架 (影响: 高, 架构层)

**现状问题**: 三个引擎各自在 `pipeline.py` 中硬编码调用顺序，添加/调整步骤需要修改 pipeline 代码，且无法灵活组合并行/串行。

**优化方案**: 抽象出统一的 `EnginePipeline` 框架：

```python
@dataclass
class Step:
    name: str
    fn: Callable[[StepContext], StepResult]
    depends_on: list[str]  # 依赖的步骤名
    mode: Literal["native", "local", "auto"]  # auto = 尝试 native，失败回退 local

class EnginePipeline:
    def __init__(self, steps: list[Step], max_workers: int = 4): ...
    def run(self, initial_context: dict, on_log) -> dict[str, StepResult]: ...
```

**核心行为**:
- 自动计算拓扑排序
- 无依赖的步骤并行执行
- 步骤失败时根据 `mode` 决定是否 fallback
- `on_log` 在步骤开始/完成/失败时自动回调
- 中间产物通过 `StepContext` 传递，支持增量读取

**实施要点**:
- 新增 `engines/pipeline_framework.py`（约 150 行）
- 逐步迁移三个引擎的 pipeline.py（先 Plan 最简单，再 Refine，最后 Design）
- 保持向后兼容：新 pipeline 的对外接口与现有 `run_*_engine()` 完全一致

---

### 3.2 增量执行支持 (影响: 中, 架构层)

**现状问题**: 重新运行某个阶段时，所有步骤全部重算。例如修改了某个 knowledge 文档后重跑 Design，即使只有 knowledge_brief 受影响，仍然要重跑 change_points、research 等不受影响的步骤。

**优化方案**: 基于 input hash 的步骤级缓存：
1. 每个步骤记录 input 的 hash（依赖步骤的 output hash + 自身参数 hash）
2. 重跑时先检查 input hash 是否变化
3. 未变化的步骤直接读取上次产物，跳过执行
4. 变化的步骤正常执行，并失效所有下游步骤的缓存

**实施要点**:
- 在 `StepResult` 中增加 `input_hash` 和 `output_hash` 字段
- 在 task_dir 下增加 `.step-cache.json` 记录每步的 hash
- 增量执行作为 opt-in 功能（默认关闭），通过 `--incremental` flag 启用

---

### 3.3 Executor 配置细化 (影响: 低, 配置层)

**现状问题**: Design 和 Plan 共享 `COCO_FLOW_PLAN_EXECUTOR` 配置，无法单独控制 Design 的 executor 模式。

**优化方案**: 
1. 新增 `COCO_FLOW_DESIGN_EXECUTOR` 环境变量
2. 在 `Settings` 中增加 `design_executor` 属性
3. 修改 Design pipeline 使用 `settings.design_executor` 而非 `settings.plan_executor`
4. 向后兼容：如果未设置 `COCO_FLOW_DESIGN_EXECUTOR`，回退到 `COCO_FLOW_PLAN_EXECUTOR`

---

## 四、社区/前沿技术融合

### 4.1 Structured Output (JSON Schema) 替代模板文件

**背景**: 主流 LLM API（Claude、GPT-4）已支持 structured output / tool use 约束输出格式。相比当前的 `__FILL__` 模板文件方案，JSON schema 约束可以：
- 保证输出格式 100% 合规（无需 `__FILL__` 检测和失败重试）
- 减少 prompt 中关于格式的指令 token
- 允许在 `prompt_only` 模式下使用

**适用条件**: 需要 ACP 协议支持 structured output 参数传递。如果 `coco` binary 的 ACP 接口支持 `response_format` 或 `tool_use` 参数，可以直接使用。

**评估项**: 确认 `coco acp serve` 是否支持 `response_format` 参数。如果不支持，可在 `prompt_only` 模式下通过 prompt engineering 模拟（要求输出严格 JSON，然后做容错解析）。

---

### 4.2 Context Caching / Prompt Caching

**背景**: Anthropic 的 prompt caching 允许缓存长 prompt 前缀，后续调用只需传递变化部分。对于 Design 引擎中多个步骤共享大量相同上下文（refined_markdown、knowledge_brief）的场景，缓存可以显著减少 token 处理量和延迟。

**适用方式**:
1. 将 `refined_markdown` + `knowledge_brief_markdown` 作为 system prompt 的固定前缀
2. 每个步骤的特定指令作为 user message 的变化部分
3. 在同一 session chain 中，前缀自动被缓存

**与 Session 复用 (2.2) 的协同**: Session chain 天然提供了 prompt caching 的载体——同一 session 中前文自动保留在 context window 中。

---

### 4.3 Map-Reduce 模式用于大规模 Knowledge 处理

**背景**: 当 knowledge base 较大（>20 文档）时，当前的分块 shortlist 方案效率低且评分标准不一致。

**优化方案**: 采用 Map-Reduce 模式：
- **Map**: 并行为每个 knowledge doc 计算与当前 task 的相关性评分（可以用 local embedding 或轻量 LLM 调用）
- **Reduce**: 取 top-K 结果，由一次 LLM 调用做最终排序和筛选

**实施前提**: 需要评估是否值得引入 embedding 模型。如果 knowledge base 平均 < 15 篇，当前的 term overlap + 单次 batch shortlist（优化 2.3）已经足够。

---

### 4.4 Agent-as-Verifier: 对抗式验证

**背景**: 当前 verify 步骤由同一个 LLM session（或同一个 prompt 风格）执行生成和验证，存在 "自己检查自己" 的盲区。

**优化方案**: verify 步骤使用不同的 prompt 角色（"严格审查者"而非"生成者"），并在 prompt 中明确要求"寻找以下类型的错误"，提供 checklist：
- 是否有 must_change repo 未被提及？
- 是否有改造点没有对应的设计段落？
- 是否有依赖关系被遗漏？
- 是否有不在 binding 中的 repo 被提及？

这比当前的泛化 verify prompt 更有针对性。

---

## 五、实施计划

### Phase 1: 快速收益 (1-2 周)

| 优先级 | 项目 | 影响 | 工作量 |
|-------|------|------|--------|
| P0 | 2.6 模板文件机制优化 (prompt_only 模式) | 速度 +15-20% | 2-3 天 |
| P0 | 1.1 Verify → Regenerate 闭环 | 质量 ++ | 2 天 |
| P0 | 3.3 Design executor 独立配置 | 配置灵活性 | 0.5 天 |
| P1 | 2.3 Knowledge shortlist 批量化 | Refine 速度 | 1 天 |
| P1 | 1.2 Change points 质量加固 | Design 质量 | 1 天 |

### Phase 2: 核心架构 (2-3 周)

| 优先级 | 项目 | 影响 | 工作量 |
|-------|------|------|--------|
| P0 | 2.1 步骤级并行 (DAG 编排) | Design 速度 -30-40% | 3-4 天 |
| P0 | 2.2 Session 复用策略 | 全引擎速度 | 2-3 天 |
| P1 | 2.5 Prompt token 压缩 | Design 成本和延迟 | 1-2 天 |
| P1 | 1.3 Research 引导式探索 | Design 质量 | 2 天 |
| P1 | 1.4 Responsibility matrix 校验 | Design 质量 | 1 天 |

### Phase 3: 精细优化 (2-3 周)

| 优先级 | 项目 | 影响 | 工作量 |
|-------|------|------|--------|
| P1 | 3.1 统一 DAG Pipeline 框架 | 可维护性 | 3-4 天 |
| P1 | 1.6 Prompt 工程优化 (few-shot + CoT) | 全引擎质量 | 2-3 天 |
| P2 | 3.2 增量执行支持 | 重跑效率 | 2-3 天 |
| P2 | 1.5 Plan 依赖交叉验证 | Plan 质量 | 1-2 天 |
| P2 | 4.4 Agent-as-Verifier 对抗式验证 | 验证质量 | 1-2 天 |

### Phase 4: 前沿探索 (按需)

| 优先级 | 项目 | 前置条件 | 工作量 |
|-------|------|---------|--------|
| P2 | 4.1 Structured Output | ACP 支持 | 2-3 天 |
| P2 | 4.2 Context Caching | Session 复用先落地 | 1-2 天 |
| P3 | 4.3 Map-Reduce Knowledge | Knowledge base > 20 篇 | 3-4 天 |

---

## 预期总收益

| 维度 | 当前 | Phase 1 后 | Phase 2 后 | Phase 3 后 |
|------|------|-----------|-----------|-----------|
| Design 耗时 (3-repo) | ~12-15 min | ~10-12 min | ~7-9 min | ~6-8 min |
| Design 质量 (verify pass rate) | ~60-70% | ~80-85% | ~85-90% | ~90%+ |
| Refine 耗时 | ~4-6 min | ~3-4 min | ~2-3 min | ~2-3 min |
| Plan 耗时 | ~3-5 min | ~2-3 min | ~2-3 min | ~1.5-2 min |
| LLM 调用次数 (Design) | 6+N | 4+N | 4+N (并行) | 4+N (并行+cached) |
| Token 成本 (Design) | 基线 | -15% | -30% | -40% |

> 注：以上数字为基于当前代码结构的估算，实际收益取决于任务复杂度和 repo 数量。

---

## 风险与注意事项

1. **Session 复用的隔离性**: 共享 session 可能导致前一步的错误输出影响后续步骤。需要在 session chain 中增加 context 清理机制。
2. **DAG 并行的错误传播**: 并行步骤中某个失败时，需要决定是否取消其他并行步骤。建议采用"继续执行，在合并点检查"的策略。
3. **Prompt 变更的回归风险**: 修改 prompt 可能导致输出格式变化。每次 prompt 变更需要在 2-3 个历史 task 上回归验证。
4. **Local fallback 的一致性**: 当 native 和 local 路径都可用时，需要确保两者的输出格式完全兼容。
5. **增量执行的 hash 稳定性**: 确保 input hash 计算不依赖于文件修改时间等不稳定因素。
