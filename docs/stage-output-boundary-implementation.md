# 阶段产物边界调整 — 实施计划

本文档是 `stage-output-boundary-design.md` 的实施方案，包含具体改动点、排期和预期收益。

---

## 实施概览

### 改动规模评估

| 阶段 | 涉及文件 | 改动类型 | 预估工作量 |
|------|---------|---------|-----------|
| Refine | 7 个文件 | 模型扩展 + prompt 重写 + renderer 重写 + verify 调整 | 2-3 天 |
| Design | 6 个文件 | prompt 重写 + renderer 大幅删减重写 + 模型裁剪 | 2-3 天 |
| Plan | 6 个文件 | prompt 重写 + renderer 重写 + 模型扩展 | 2-3 天 |
| Code | 2 个文件 | 模型小幅扩展 + goal 字段透传 | 0.5 天 |
| 联调 & 回归 | - | 端到端验证 + 历史 case 回归 | 2 天 |
| **总计** | **~21 个文件** | | **9-12 天** |

---

## 一、Refine 阶段实施

### 1.1 改动清单

| 文件 | 改动内容 |
|------|---------|
| `engines/refine/models.py` | `RefineIntent` 增加 `acceptance_criteria: list[str]` 字段 |
| `engines/refine/intent.py` | intent 提取逻辑增加验收标准抓取（关键词: 验收/标准/应该/必须/当...时）|
| `prompts/refine/intent.py` | agent prompt 的 JSON 模板增加 `acceptance_criteria` 字段 |
| `prompts/refine/generate.py` | 模板从 `# PRD Refined` + 5 旧 section 改为 `# 需求确认书` + 5 新 section |
| `prompts/refine/verify.py` | verify 检查项改为新 section 名称 + 新质量规则 |
| `engines/refine/generate.py` | `_REQUIRED_SECTIONS` 更新；`build_local_refined_markdown()` 完全重写 |
| `engines/refine/pipeline.py` | 无改动（pipeline 编排不变，只是产物格式变了）|

### 1.2 关键设计决策

**Q: `discussion_seed` + `risks_seed` 如何合并为结构化"待确认项"？**

方案：保留 `discussion_seed` 和 `risks_seed` 在 intent 模型中不变（它们是中间抓取结果），在 renderer 层合并渲染。renderer 为每条 seed 自动填充：
- question = seed 原文
- assumption = "待确认"（LLM 生成时可以更具体）
- impact = 从 change_points 关联推导，或标"待评估"

这样 intent 抓取逻辑不需要大改，新格式在 renderer 和 LLM generate prompt 中约束即可。

**Q: 三段式变更点（场景/当前/期望）如何实现？**

方案：`change_points` 在 intent 模型中保持 `list[str]`（向后兼容），但 generate prompt 明确要求 LLM 输出三段式格式。local fallback 时，如果原始 change_point 不是三段式，用启发式拆分或保留为单段。

### 1.3 实施顺序

```
Day 1:
  1. 修改 RefineIntent 模型，增加 acceptance_criteria 字段
  2. 修改 intent prompt 模板，增加 acceptance_criteria 提取
  3. 修改 intent.py 的 local 提取逻辑和 native parse 逻辑

Day 2:
  4. 重写 generate prompt 模板（新 section 结构 + 三段式 + 结构化待确认项）
  5. 重写 build_local_refined_markdown()
  6. 更新 _REQUIRED_SECTIONS 和相关校验逻辑

Day 3:
  7. 更新 verify prompt（新 section 名称 + 新质量检查规则）
  8. 端到端测试：local 模式 + native 模式各跑 1-2 个 case
  9. 清理废弃代码：_normalize_risks(), _ensure_discussion_tags()
```

---

## 二、Design 阶段实施

### 2.1 改动清单

| 文件 | 改动内容 |
|------|---------|
| `prompts/design/generate.py` | 模板从 12 section 裁剪为 6 section（含接口协议变更）|
| `prompts/design/verify.py` | verify 检查项更新到新 section 结构 |
| `engines/design/generate.py` | `generate_local_design_markdown()` 完全重写（从 ~110 行削减到 ~70 行）；`build_design_sections_payload()` 裁剪废弃字段，保留 protocol_changes 用于接口协议变更 section，增加 risk_boundaries；`collect_design_contract_issues()` 更新 section 检查 |
| `engines/design/models.py` | `DesignEngineResult` 无需改动（产物字段不变，只是 markdown 格式变了）|
| `engines/shared/models.py` | 删除 `StorageConfigChange`, `ExperimentChange`, `StaffingEstimate` 三个 dataclass；保留 `ProtocolChange`（重命名为 `InterfaceChange`）；`DesignAISections` 和 `DesignSections` 裁剪字段 |
| `prompts/design/responsibility_matrix.py` | 无改动（矩阵是中间产物，不影响最终文档）|

### 2.2 关键设计决策

**Q: validate_only 仓库在"分仓库方案"中怎么展示？**

方案：所有 in_scope 仓库统一在 `## 分仓库方案` 下列出，用 `scope_tier` 标注角色：
- `must_change` → 详细展示（职责 + 改动 + 候选文件 + 理由）
- `co_change` → 中等展示（职责 + 主要改动 + 理由）
- `validate_only` → 简要展示（职责 + 验证要点）

这样研发一眼能看到全貌，同时不会被 validate_only 的细节干扰。

**Q: 仓库依赖关系的类型如何分类？**

方案：在 `design-sections.json` 的 `system_dependencies` 条目中增加 `dependency_kind` 字段，取值：
- `interface` — A 调用 B 的 RPC/HTTP 接口
- `data` — A 读 B 写入的存储
- `config` — A 读 B 管理的配置/AB 实验

分类逻辑：优先从 research 结果推断（import 关系 → interface，数据库/缓存共用 → data，config center → config），兜底为 `interface`。

**Q: 接口协议变更 section 的内容怎么来？**

方案：保留现有的 `ProtocolChange` 模型（重命名为 `InterfaceChange`），重新定义字段含义为服务端视角：
- `interface`：变更的接口名
- `field`：新增/修改的字段
- `change_type`：`add` / `modify` / `deprecate`
- `consumer`：下游消费方（前端 / 其他服务 / 客户端）
- `need_alignment`：是否需要和下游对齐（bool）
- `description`：变更说明

数据来源：
1. Design research 阶段 agent 探索仓库时，识别 proto/thrift/IDL 文件变更 → 自动提取
2. Change points 中涉及"下发"、"透传"、"新增字段"等关键词 → LLM 判断
3. 如果都没命中，默认输出"本次需求不涉及对外接口协议变更"

### 2.3 实施顺序

```
Day 1:
  1. 裁剪 plan_models.py：删除 4 个废弃 dataclass，精简 DesignAISections/DesignSections
  2. 裁剪 build_design_sections_payload()：删除 5 个废弃字段
  3. 重写 design generate prompt 模板（5 新 section）

Day 2:
  4. 重写 generate_local_design_markdown()（大幅删减，约 60 行）
  5. 更新 collect_design_contract_issues()
  6. 更新 verify prompt

Day 3:
  7. 增加 dependency_kind 字段和分类逻辑
  8. 端到端测试：local + native 各 1-2 case
  9. 确认 plan 阶段能正常消费新格式的 design.md（回归）
```

---

## 三、Plan 阶段实施

### 3.1 改动清单

| 文件 | 改动内容 |
|------|---------|
| `engines/plan/models.py` | `PlanWorkItem` 增加 `specific_steps: list[str]` 字段 |
| `prompts/plan/task_outline.py` | task outline 模板增加 `specific_steps` 字段 + prompt 要求步骤级描述 |
| `engines/plan/task_outline.py` | local 构建逻辑增加 specific_steps 推导 |
| `prompts/plan/generate.py` | 模板从 7 section 裁剪为 4 section |
| `engines/plan/generate.py` | `generate_local_plan_markdown()` 重写（删除实施策略/并发与协同/交付边界，合并执行顺序+并行信息）|
| `prompts/plan/verify.py` | verify 检查项更新 |

### 3.2 关键设计决策

**Q: `specific_steps` 的颗粒度如何把控？**

方案：在 task_outline prompt 中明确约束：
- 每个任务 2-5 步
- 每步格式："在 {模块/文件} 中 {动作} {对象}"
- 不到代码行，但到模块+接口+字段级别
- 示例："在 auction_service/handler.go 的 GetAuctionCard 方法中增加 auction_hint 字段的填充逻辑"

local fallback 时，从 design research 的 candidate_files 和 change_summary 推导步骤。

**Q: 执行顺序如何展示？**

方案：合并当前的"执行顺序"和"并发与协同"为一个 section：
```
T1 → T2（T1 完成后 T2 才能启动：T2 依赖 T1 产出的接口定义）
T3, T4 可并行（无依赖）
```
只展示有约束的关系，纯顺序执行的不需要额外标注。

### 3.3 实施顺序

```
Day 1:
  1. PlanWorkItem 模型增加 specific_steps 字段
  2. 修改 task_outline prompt 模板（增加 specific_steps + 颗粒度约束）
  3. 修改 task_outline.py 的 local 构建逻辑

Day 2:
  4. 重写 plan generate prompt 模板（4 新 section）
  5. 重写 generate_local_plan_markdown()
  6. 更新 verify prompt

Day 3:
  7. 端到端测试
  8. 确认 code 阶段能正常消费新格式的 plan artifacts（回归）
```

---

## 四、Code 阶段实施

### 4.1 改动清单

| 文件 | 改动内容 |
|------|---------|
| `engines/code/source.py` | `_parse_work_items()` 增加 `goal` 字段提取；从 `specific_steps` 拼接为 goal text |
| `engines/code/models.py` | `CodeWorkItem` 增加 `goal: str` 字段 |

### 4.2 实施顺序

```
Day 1 (0.5 天):
  1. CodeWorkItem 增加 goal 字段
  2. _parse_work_items() 从 plan payload 提取 goal + specific_steps
  3. code-batch.md 渲染时展示 goal
  4. 快速验证 code agent 能正确读取新字段
```

---

## 五、联调 & 回归验证

### 5.1 验证策略

| 验证维度 | 方法 | 通过标准 |
|---------|------|---------|
| 格式正确性 | 用 2-3 个历史 case 跑完整 pipeline | 新格式的 section 结构完整，无 `__FILL__` 残留 |
| 内容质量 | 人工 review 产出文档 | 研发能看懂，信息密度 > 旧版 |
| 下游兼容 | design 能消费新 prd-refined，plan 能消费新 design.md，code 能消费新 plan artifacts | 无报错，产物合理 |
| Local fallback | 切换到 local executor 跑全流程 | 与 native 产出的结构一致（内容质量允许差异）|
| 旧数据兼容 | 已有 task 数据目录不被破坏 | 不影响已有 task 的 status 和 artifacts |

### 5.2 兼容性处理

**旧 task 数据兼容**: 已有 task 的 `prd-refined.md` / `design.md` / `plan.md` 是旧格式。新代码在 **读取** 旧产物时需要做兼容：
- Plan 阶段读取 design.md：用 heading 检测来判断是新格式还是旧格式
- 如果检测到旧格式，走旧解析路径（向后兼容 6 个月后移除）

**新 task 数据**: 所有新创建的 task 一律使用新格式。

---

## 六、排期建议

### 方案 A: 三阶段分批上线（推荐）

```
第 1 周: Refine 阶段改造
  - Day 1-3: 开发 + 自测
  - Day 4: 联调验证 (refine 产物能被现有 design 正常消费)
  - Day 5: 合入主干

第 2 周: Design 阶段改造
  - Day 1-3: 开发 + 自测
  - Day 4: 联调验证 (新 design 产物能被现有 plan 正常消费)
  - Day 5: 合入主干

第 3 周: Plan + Code 阶段改造 + 全量回归
  - Day 1-2: Plan 开发
  - Day 3: Code 阶段 goal 透传
  - Day 4-5: 全流程端到端回归
```

优势：每周一个阶段，风险可控，每次只影响一个引擎。

### 方案 B: 并行开发一次上线

```
第 1 周:
  - Day 1-2: 模型层改动（全阶段的 dataclass 变更一次性完成）
  - Day 3-5: 三个引擎并行改造 prompt + renderer

第 2 周:
  - Day 1-2: verify 和 contract 校验更新
  - Day 3-5: 全流程联调 + 回归
```

优势：总工期短（~10 天），但风险集中，联调问题可能较多。

### 推荐：方案 A

理由：
1. 每个阶段可独立验证，避免"改了上游导致下游全挂"
2. 每周有明确交付物，进度可见
3. 如果某阶段出问题，不影响其他阶段的已上线部分

---

## 七、预期收益

### 7.1 用户体验收益

| 维度 | 旧版 | 新版 | 提升 |
|------|------|------|------|
| 文档可读性 | 12 section 的 design 混杂技术/管理信息 | 5 section 聚焦技术方案 | 研发 review 时间 -40% |
| 信息密度 | 大量"当前未发现明确变更信号"的空 section | 移除无信息量 section | 有效信息占比从 ~60% 提升到 ~90% |
| 可操作性 | "讨论点"仅列问题 | "待确认项"含假设+影响，可直接找产品对齐 | 需求锁定周期缩短 |
| 颗粒度一致性 | plan 任务描述粗泛 | plan 任务到模块+接口级别 | code agent 执行准确性提升 |

### 7.2 流程效率收益

| 维度 | 改善 | 原因 |
|------|------|------|
| 研发 review 效率 | +30-50% | section 更少、信息更聚焦、边界更清晰 |
| 需求返工率 | -20-30% | "待确认项"驱动提前对齐，减少开发中途发现需求不清晰 |
| Code agent 输出质量 | +10-20% | plan 的 specific_steps 提供更具体的执行指导 |
| 文档一致性 | 显著提升 | 三个文档有明确的信息流转关系，不重复不遗漏 |

### 7.3 工程维护收益

| 维度 | 改善 | 原因 |
|------|------|------|
| Prompt 维护成本 | -30% | Design prompt 从 12 section 降到 5 section，约束规则大幅减少 |
| Model 复杂度 | -20% | 删除 4 个废弃 dataclass + 5 个废弃字段 |
| 测试负担 | -20% | 更少的 section 意味着更少的边界条件需要验证 |
| 新人上手成本 | -30% | 文档职责清晰，不再有"这个 section 到底该写什么"的困惑 |

### 7.4 核心收益总结

1. **研发真正能用起来**: 文档从"系统产出的技术产物"变成"研发工作流的输入"，每个文档有明确的 review 目标和后续动作。
2. **需求锁定提前**: "待确认项"的结构化设计驱动研发在编码前就和产品对齐，减少返工。
3. **Code agent 更准**: plan 的 specific_steps 给 agent 更具体的执行指导，减少 agent 猜测。
4. **维护更轻**: 删除大量冗余代码和废弃模型，prompt 约束更简洁。

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Prompt 格式变化导致 LLM 输出质量下降 | 中 | 每个阶段改完后在 2-3 个真实 case 上验证质量，对比新旧版产出 |
| 旧 task 数据兼容问题 | 低 | 下游读取时做 heading 检测，旧格式走旧解析路径 |
| specific_steps 颗粒度不稳定 | 中 | 在 prompt 中加入 2 个 few-shot 示例约束颗粒度 |
| 验收标准提取困难（PRD 原文缺少） | 中 | 当 PRD 无明确验收标准时，LLM 从变更点反推；local fallback 标记"[待补充]" |
| 三段式变更点对简单需求过于冗余 | 低 | prompt 明确：当需求简单时可以用单句描述，三段式仅用于复杂变更 |
