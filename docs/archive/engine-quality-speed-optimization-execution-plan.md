# Engine 质量与效率优化执行版（v1）

配套研究稿见：[`docs/engine-quality-speed-optimization.md`](./engine-quality-speed-optimization.md)

这份文档不再重复“为什么值得做”，只回答四个问题：

1. 本轮到底做哪些项，不做哪些项
2. 每一项改哪些文件
3. 每一项完成后怎么验收
4. 如果效果不稳定，怎么快速回退

## 本轮目标

本轮目标不是一次性把三条引擎线都重写，而是在不破坏现有 task / artifact / log 语义的前提下，先拿到一轮确定性收益：

- 让 Design 和 Plan 的 native 路径少一些“明明能自修却直接失败”的情况
- 让 Design 的范围判断更稳，减少 change points 漏项带来的级联偏差
- 让 Refine 在 knowledge 较多时少走几次串行 LLM 调用
- 把 Design 的 executor 从 Plan 中解耦，给后续实验留出开关位

## 本轮硬约束

- 不改 task 状态流转语义
- 不改现有 artifact 文件名
- 不删现有日志字段；只能新增日志字段
- 不破坏 repo 级 artifact 可读性
- 默认只做最小范围验证，不引入全量回归测试作为前置门槛

## 这轮做完以后，收益是什么

这轮的收益分两类：

- 确定性收益：代码做完就一定能拿到，不依赖模型“发挥”
- 概率性收益：需要通过历史 task 回归验证，但方向明确

先看总览。

| 维度 | 当前 | 本轮后 | 收益类型 | 置信度 |
|------|------|--------|----------|--------|
| Design / Plan verify 失败处理 | 首次 verify 失败直接整阶段失败 | 首次 verify 失败后允许 1 次定向重试，再决定成败 | 确定性 | 高 |
| Design change points 漏项处理 | 依赖一次性提取，漏了就一路漏下去 | 增加基于 refine intent 的本地回填 | 确定性 | 高 |
| Matrix 风险可见性 | research 和 matrix 不一致时基本静默 | `design-repo-responsibility-matrix.json` 增加 warnings | 确定性 | 高 |
| Refine shortlist LLM 调用次数 | 常见场景按 8 篇一组串行调用 | 30 篇以内优先单次批量调用 | 确定性 | 高 |
| Design / Plan executor 开关粒度 | Design 跟 Plan 共用一个 executor 开关 | Design 可单独切换 / 回退 | 确定性 | 高 |
| Multi-repo research 命中率 | agent 自由探索，容易漂 | 改成沿 prefilter 路径做引导式探索 | 概率性 | 中 |
| 多 repo task 的整体成功率 | 容易因漏项或 verify 问题失败 | 预期更稳，但需回归验证 | 概率性 | 中 |

## 前后对比怎么理解

不是所有收益都应该用“总耗时减少多少分钟”来表达。本轮更像是三类收益叠加：

### 1. 直接少走弯路

- Refine shortlist：
  - 现状：`N` 篇文档大致需要 `ceil(N / 8)` 次 LLM 调用
  - 本轮后：当 `N <= 30` 时，优先 1 次调用
  - 典型对比：
    - 8 篇：`1 -> 1`
    - 12 篇：`2 -> 1`
    - 16 篇：`2 -> 1`
    - 20 篇：`3 -> 1`
    - 24 篇：`3 -> 1`
  - 这部分收益是最硬的，主要减少的是 shortlist 子步骤等待时间和评分标准分裂

### 2. 直接少失败

- Design / Plan verify：
  - 现状：第一次生成只要 verify 报错，就直接 fail
  - 本轮后：允许 1 次带 issues 的定向修复
  - 前后差异不是“必然更快”，而是把一部分“本来可以修一下就过”的 case 从失败拉回成功

- Design change points：
  - 现状：如果 LLM 漏掉一个关键 change point，后续 assignment / research / binding 都会一起偏
  - 本轮后：至少对 refine intent 里已经明确写出来的 change point，有一层本地回填兜底
  - 前后差异是“漏项从静默传播变成可补、可见”

### 3. 直接更好调参和回退

- executor 拆分：
  - 现状：想试验 Design local，只能连 Plan 一起受影响
  - 本轮后：可以只切 Design，不碰 Plan
  - 这不是速度收益，但会明显降低实验和回退成本

## 这轮的收益预估

以下数字是基于当前代码路径给出的预估，不是已验证结果。最终以后面的基线 task 对比为准。

| 指标 | 当前 | 本轮后预期 | 说明 |
|------|------|-----------|------|
| Refine shortlist 调用次数（12-24 篇知识文档） | 2-3 次 | 1 次 | 只统计 shortlist 子步骤，不含 knowledge read |
| Design / Plan 因 verify 首次失败直接退出的 case | 全部直接失败 | 其中一部分会被单次重试拉回 | 取决于问题是否可通过文本修正解决 |
| Design change points 漏项后的连锁偏差 | 漏项会一路传递 | refine intent 可覆盖的漏项可被回填 | 仅对“intent 中已明确出现”的点有效 |
| 多 repo research 漂移 | 偏高 | 预期下降 | 需要看 T2 回归样本，不先承诺绝对比例 |
| 配置回退粒度 | Design + Plan 绑定 | Design 单独回退 | 运维 / 调试收益，不是运行时收益 |

## 看收益时优先看什么

本轮最值得看的不是“总耗时”，而是下面几个前后对比：

1. `refine` 在 12-24 篇 knowledge 文档时，shortlist 子步骤是否从多次串行变成一次调用
2. `design` / `plan` 在首次 verify 失败时，是否有一部分 task 被单次 regenerate 拉回成功
3. `design-change-points.json` 里是否出现了以前会漏掉、现在被回填的条目
4. `design-repo-responsibility-matrix.json` 是否暴露出以前静默存在的 warnings
5. 切 `COCO_FLOW_DESIGN_EXECUTOR=local` 时，是否能做到只影响 Design，不波及 Plan

## 本轮不做

以下项目保留在 backlog，不进入这一轮：

- 统一 DAG Pipeline 框架
- 步骤级增量缓存
- 全链路 `prompt_only` 改造
- Refine 的 verify -> regenerate 闭环
- Session chain / context caching 框架化改造

原因很简单：这些项都值得做，但和本轮的高性价比 slice 耦合太深，混在一起会让定位回归变难。

## 开工前基线

每个 slice 开始前，先固定 3 组历史 task 作为对照样本。不要只看一个 case。

- T1：单 repo task，Design fast path 明确
- T2：多 repo task，Design research / binding 明显参与
- T3：Refine 阶段 knowledge 文档较多的 task

每轮记录以下指标即可，不要求上自动化平台：

- `refine` / `design` / `plan` 总耗时
- 是否发生 native -> local fallback
- verify 是否通过
- 关键 artifact 是否产出完整
- 日志里是否出现新增字段

建议把基线记录在 PR 描述或单独的 markdown 表格里，不需要先做额外平台建设。

## 执行顺序

### Slice 0: `design_executor` 独立配置

优先级：P0  
预计工作量：0.5-1 天  
目标：把 Design 从 `COCO_FLOW_PLAN_EXECUTOR` 中拆出来，但默认行为保持不变。

涉及文件：

- `src/coco_flow/config.py`
- `src/coco_flow/engines/design/assignment.py`
- `src/coco_flow/engines/design/research.py`
- `src/coco_flow/engines/design/matrix.py`
- `src/coco_flow/engines/design/binding.py`
- `src/coco_flow/engines/design/generate.py`
- `src/coco_flow/services/tasks/design.py`
- `src/coco_flow/services/tasks/background.py`
- `README.md`
- `AGENTS.md`

具体改动：

- 在 `Settings` 中新增 `design_executor`
- 环境变量读取顺序改为：
  - 优先 `COCO_FLOW_DESIGN_EXECUTOR`
  - 未设置时回退到 `COCO_FLOW_PLAN_EXECUTOR`
- Design 相关引擎全部改读 `settings.design_executor`
- `design.log` 和后台日志改打印 Design 自己的 executor
- README / AGENTS 补一行配置说明

预期收益：

- Design 和 Plan 的 executor 开关解绑，回退粒度更细
- 后续做 Design 实验时，不会顺手把 Plan 一起扰动
- 收益主要体现在调试效率和回退成本，不体现在运行耗时

验收标准：

- 未设置 `COCO_FLOW_DESIGN_EXECUTOR` 时，行为与当前一致
- 设置 `COCO_FLOW_DESIGN_EXECUTOR=local` 后，只影响 Design，不影响 Plan
- 日志里能明确看到 Design executor 的实际值

回退方式：

- 保留 `plan_executor` fallback 逻辑
- 出现异常时，去掉环境变量即可恢复旧行为

---

### Slice 1: Design change points 回填 + matrix warnings

优先级：P0  
预计工作量：1-1.5 天  
目标：先把最便宜的质量改进补上，不增加新的 LLM 调用。

涉及文件：

- `src/coco_flow/engines/design/source.py`
- `src/coco_flow/engines/design/models.py`
- `src/coco_flow/engines/design/assignment.py`
- `src/coco_flow/engines/design/matrix.py`

具体改动：

- `prepare_design_input()` 已经读入 `refine-intent.json`，直接消费 `prepared.refine_intent_payload`
- 在 `build_design_change_points_payload()` 的 native 结果和 local fallback 结果返回前，统一走一层 `_backfill_from_refine_intent()`
- 回填规则先做简单版本，不做语义 embedding：
  - 基于小写词项 overlap
  - 完全未覆盖的 refine change point 才补入
  - 回填项增加 `source: "refine_intent_backfill"`
- `build_local_design_change_points_payload()` 产物也补 `source` 字段，区分 `local` / `llm` / `refine_intent_backfill`
- 在 matrix 构建后增加 `_validate_matrix_consistency()`，仅输出 warning，不改主决策
- warning 以新增字段写入 `design-repo-responsibility-matrix.json`

预期收益：

- 把“change point 漏一项就一路漏下去”改成“至少有一层本地兜底”
- 把 matrix / research 不一致从静默问题变成显式 warning
- 这项收益主要体现为 scope 稳定性提升，不是耗时下降

验收标准：

- `design-change-points.json` 中能看出哪些点来自回填
- 当 refine 有 change point、但 design 漏掉时，回填后不再丢失
- `design-repo-responsibility-matrix.json` 新增 `warnings` 字段，但旧消费方不受影响
- 不新增任何 LLM 调用

回退方式：

- `_backfill_from_refine_intent()` 和 `_validate_matrix_consistency()` 都保持纯附加逻辑
- 一旦效果不好，可直接短路回原始 payload

---

### Slice 2: Refine knowledge shortlist 批量化

优先级：P0  
预计工作量：1 天  
目标：把大部分 refine shortlist 从多次串行改成一次批量判断。

涉及文件：

- `src/coco_flow/engines/refine/knowledge.py`
- `src/coco_flow/prompts/refine/*` 中 shortlist 相关 prompt

具体改动：

- 新增紧凑卡片构造函数，例如 `_build_compact_card_list()`
- 当 `len(cards) <= 30` 时，走单次 LLM 调用
- prompt 输出仍然保持当前 shortlist payload 结构，不改下游
- 当卡片数大于 30，或单次批量解析失败时，回退到现有 chunk 模式
- 新增日志字段：
  - `knowledge_shortlist_mode: llm_batch|llm_chunked|rule`
  - `knowledge_shortlist_card_count: N`

预期收益：

- 12-24 篇知识文档的常见场景里，shortlist 子步骤从 2-3 次 LLM 调用降到 1 次
- 评分标准更统一，不再按 chunk 分散判断
- 这项收益是本轮里最接近“直接提速”的一项

明确不做：

- 这一轮不引入 embedding
- 这一轮不改 knowledge read 阶段

验收标准：

- 20 篇以内 knowledge 文档时，native shortlist 只发生一次 LLM 调用
- 失败时仍能回退到 chunk / rule 路径，不阻塞 refine
- `refine-knowledge-selection.json` 结构不变

回退方式：

- 保留原有 chunk 路径作为 fallback
- 批量模式通过简单开关或条件判断可快速关闭

---

### Slice 3: Design / Plan verify 失败后单次重试

优先级：P0  
预计工作量：1.5-2 天  
目标：只做“verify 失败后带着 issues 再生成一次”，不把 session 优化混进来。

涉及文件：

- `src/coco_flow/engines/design/generate.py`
- `src/coco_flow/engines/plan/generate.py`
- `src/coco_flow/engines/plan/pipeline.py`
- `src/coco_flow/prompts/design/*`
- `src/coco_flow/prompts/plan/*`

具体改动：

- Design：
  - 首次 generate
  - contract / verify
  - 若失败，构建 regenerate prompt，把 `issues` 明确追加进去
  - 再 generate 一次
  - 再 verify 一次
  - 第二次仍失败时，保持当前失败语义，不偷偷接受
- Plan：
  - 逻辑同上
  - 第二次 verify 仍失败时，保持当前 `raise ValueError(...)` 语义
- 新增日志字段：
  - `design_regenerate_start`
  - `design_regenerate_ok`
  - `design_regenerate_failed`
  - `plan_regenerate_start`
  - `plan_regenerate_ok`
  - `plan_regenerate_failed`

这一步的边界要写死：

- 不改现有 artifact 文件名
- `design-verify.json` / `plan-verify.json` 仍然只保存最终一次 verify 结果
- 第一轮不把“第二次失败也接受”带进来

为什么这一轮不顺手做 session 复用：

- 当前实现里，`fresh_session=True` 并不会自然变成“后续默认沿用同一 session”的保证
- 在 `src/coco_flow/clients/acp_client.py` 里，fresh session 是临时拿一个新 session id 来跑，本轮先不把这个语义一起改掉
- 先把 regenerate 逻辑落地，等回归稳定后，再单独处理 session 策略

预期收益：

- 把一部分“首次 verify 有问题但其实可修”的 task 从直接失败拉回成功
- 减少 Design / Plan 因格式缺口、段落遗漏、repo 覆盖不全而直接失败的概率
- 这项收益更像“少失败”，不保证平均耗时下降

验收标准：

- verify 首次失败时，日志里能看到一次且仅一次 regenerate
- 第二次 verify 通过时，最终状态与正常路径一致
- 第二次 verify 失败时，状态仍按当前语义失败，不引入新的“半成功”状态

回退方式：

- 重试逻辑包在 native path 内，删除重试分支即可完全回退

---

### Slice 4: Design repo research 改为“引导式探索”

优先级：P1  
预计工作量：1-2 天  
目标：在不增加 LLM 调用数的情况下，提高 repo research 命中率。

涉及文件：

- `src/coco_flow/engines/design/research.py`
- `src/coco_flow/prompts/design/*` 中 repo research prompt

具体改动：

- 继续保留现有 local prefilter
- `_explore_repo_with_agent()` 的 prompt 改为先消费：
  - `candidate_dirs`
  - `candidate_files`
  - `primary_change_points`
  - `secondary_change_points`
- 明确要求 agent：
  - 先验证这些候选路径是否相关
  - 再沿这些路径扩展搜索
  - 如果脱离这些路径，要给出原因
- 新增日志字段：
  - `repo_research_prefilter_candidates`
  - `repo_research_guided_paths`

预期收益：

- 降低 agent 在大仓库里自由漂移的概率
- 提高 `candidate_files` / `evidence` 与 prefilter 信号的一致性
- 这项收益需要看 T2 多 repo 样本，不先承诺固定百分比

验收标准：

- 多 repo case 下，research 输出里的 `candidate_files` 更接近 local prefilter 命中的路径
- 不新增额外 agent 调用
- 原有 parallel research 逻辑保持不变

回退方式：

- 只改 prompt 组装，不改 research payload 结构
- 如果 prompt 效果差，可直接回退到旧 prompt

## 每个 slice 的统一验收动作

代码层最小校验：

```bash
uv run python -m py_compile src/coco_flow/config.py
uv run python -m py_compile src/coco_flow/engines/design/assignment.py
uv run python -m py_compile src/coco_flow/engines/design/matrix.py
uv run python -m py_compile src/coco_flow/engines/design/research.py
uv run python -m py_compile src/coco_flow/engines/design/generate.py
uv run python -m py_compile src/coco_flow/engines/plan/pipeline.py
uv run python -m py_compile src/coco_flow/engines/plan/generate.py
uv run python -m py_compile src/coco_flow/engines/refine/knowledge.py
```

行为层 smoke：

```bash
uv run coco-flow tasks refine <task_id>
uv run coco-flow tasks design <task_id>
uv run coco-flow tasks plan <task_id>
```

需要人工检查的点：

- `design-change-points.json`
- `design-repo-responsibility-matrix.json`
- `design-repo-binding.json`
- `design-verify.json`
- `refine-knowledge-selection.json`
- `plan-verify.json`

## 本轮结束标准

满足以下条件即可认为这一轮完成：

- Design executor 已独立可配，且默认行为不变
- change points 漏项能被本地回填兜住
- refine shortlist 在常见 case 下不再按 8 篇一组串行跑多次
- design / plan verify 失败时会自动重试一次
- research prompt 已改成引导式探索
- README / AGENTS 中与配置相关的说明已同步

## 下一轮再做什么

这一轮稳定后，再考虑进入第二轮：

- session 复用策略梳理
- 局部 `prompt_only` 化
- DAG 编排
- 增量缓存

顺序建议是：先 session 语义，再 prompt_only，再 DAG。不要反过来。
