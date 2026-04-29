# Design 质量优化任务列表

目标：优化 Design 阶段产物质量，让 `design.md` 面向人类评审，机器所需的完整代码证据和候选文件进入 sidecar，避免后续 Plan/Code 被噪音和错误仓库归因误导。

## 当前问题

- `design.md` 堆了大量代码搜索线索、搜索命中原因和机器证据，可读性差。
- repo 职责只有“需要代码改造/不需要”，无法表达“条件改”。
- PRD 的非目标没有反向约束候选文件，导致“不改购物袋”时仍把 bag helper 写进主方案。
- Design 复述需求较多，真正的方案决策较弱。
- 需求存在冲突时，仍可能输出“当前无待确认项”。
- Plan 目前主要读 `design.md`，缺少机器可消费的实现提示 sidecar。

## 实施顺序

### 1. Design 文档瘦身

状态：已实施。

改造点：

- 修改 doc-only Design writer prompt。
- 修改 local fallback 的 `design.md` 模板。
- `design.md` 不再渲染完整候选文件列表、搜索命中原因和机器证据。
- 允许保留少量对研发评审有帮助的“涉及模块/文件”，用于表达方案落点。
- 保留面向研发评审的自然语言方案。

建议改动文件：

- `src/coco_flow/prompts/design/writer.py`
- `src/coco_flow/engines/design/writer/markdown.py`

验收：

- 新生成的 `design.md` 不出现大段“代码线索”列表、搜索命中原因或 `confidence/kind/core_evidence` 等机器字段。
- 如需说明方案落点，可保留少量涉及模块/文件，但不展开成搜索结果清单。
- 文档能清楚说明用户可见变化、方案设计、影响范围、风险与待确认。

### 2. 新增 `design-implementation-hints.json`

状态：已实施。

改造点：

- 新增 Design sidecar，承载机器消费的信息。
- 把候选文件、排除文件、函数/模块线索、仓库职责、实现提示放入 sidecar。
- `design.md` 只引用必要结论，不直接展开 sidecar 内容。

建议改动文件：

- `src/coco_flow/engines/design/types.py`
- `src/coco_flow/engines/design/pipeline.py`
- `src/coco_flow/services/tasks/design.py`
- `src/coco_flow/services/tasks/design_sync.py`

验收：

- Design 完成后生成 `design-implementation-hints.json`。
- sidecar 至少包含 repo 级职责、候选文件、排除原因、待确认项。
- 编辑并同步 Design 时，不丢失或误覆盖用户编辑后的 `design.md`。

### 3. 仓库职责分级

状态：已实施。

改造点：

- 将 repo 工作类型从当前粗粒度标签改成更明确的职责分级。
- 支持：
  - `required`
  - `conditional`
  - `reference_only`
  - `not_needed`
  - `unknown`
- writer 根据职责分级输出人类可读结论。

建议改动文件：

- `src/coco_flow/engines/design/evidence/research.py`
- `src/coco_flow/engines/design/writer/markdown.py`

验收：

- 多仓任务中，公共仓可被标为“条件改”，而不是一律“需要代码改造”。
- `design.md` 能说明条件，例如“仅当缺少实验字段时改 live_common”。

### 4. 非目标反向约束候选文件

状态：待实施。

改造点：

- 从 `prd-refined.md` 的“非目标/明确不做”提取排除信号。
- 研究阶段对命中排除信号的文件降权或标为 excluded。
- writer 不把 excluded 文件写成主方案落点。
- 当前先在 research payload 中输出 `excluded_files`；后续任务 2 再落到 `design-implementation-hints.json`。

建议改动文件：

- `src/coco_flow/engines/design/evidence/research.py`
- 可新增：`src/coco_flow/engines/design/evidence/scope_guard.py`

验收：

- PRD 写“不改购物袋”时，bag/list/refresh 相关文件不会进入主改造方案。
- sidecar 中能看到被排除文件及原因。
- `design.md` 能说明关键边界，但不展开冗余搜索结果。

### 5. Design 写业务层设计

状态：已实施。

改造点：

- 强制 writer 输出“方案设计”而非搜索摘要。
- 每个仓库只写：
  - 职责
  - 是否改造
  - 改造层级
  - 与非目标的隔离方式
  - 回退策略
- 完整候选文件、函数细节和搜索证据进入 sidecar；`design.md` 仅保留必要方案落点。

建议改动文件：

- `src/coco_flow/prompts/design/writer.py`
- `src/coco_flow/engines/design/writer/markdown.py`

验收：

- `design.md` 可以直接给研发评审。
- 文档不会因为没有候选文件列表而失去方案判断。

### 6. 待确认项质量检查

状态：已实施。

改造点：

- 识别 refined PRD 中的明显冲突表达。
- 如果存在冲突，Design 必须写入“风险与待确认”。
- 禁止在有冲突时输出“当前无待确认项”。
- 当前已覆盖通用格式尾随 0 口径冲突；后续任务 8 再扩展为完整质量 gate。

建议改动文件：

- 可新增：`src/coco_flow/engines/design/quality.py`
- `src/coco_flow/engines/design/pipeline.py`

验收：

- 当 PRD 同时出现“`12.50` 保持不变”和“所有尾随 0 都去掉”时，Design 会写待确认。
- 待确认项只保留影响实现判断的问题。

### 7. 多仓误判修正

状态：待实施。

改造点：

- 对公共仓、配置仓、协议仓增加更保守的职责判断。
- 搜到 AB 字段不等于该仓必改。
- 只有存在新增字段、协议变更或公共能力改造证据时，才标为 `required`。

建议改动文件：

- `src/coco_flow/engines/design/evidence/research.py`
- `src/coco_flow/engines/design/writer/markdown.py`

验收：

- `live_common` 这类仓在“只需确认实验字段”时标为 `conditional` 或 `reference_only`。
- `design.md` 不误导 Plan 把条件改当成必改。

### 8. Design 质量 gate 与自动 repair

状态：待实施。

改造点：

- 生成 `design.md` 后执行质量检查。
- 对低风险问题自动 repair 一轮。
- 严重问题写入 `design-quality.json`，供 UI/Plan 判断。

建议改动文件：

- 可新增：`src/coco_flow/engines/design/quality.py`
- `src/coco_flow/engines/design/pipeline.py`
- `src/coco_flow/services/tasks/design.py`

建议检查项：

- 是否堆搜索线索。
- 是否违背非目标。
- 是否误判仓库职责。
- 是否遗漏冲突待确认。
- 是否缺实验命中/未命中/回退策略。
- 是否缺明确不做。

验收：

- 低质量 Design 不会静默进入 `designed`。
- 自动 repair 后的 `design.md` 更短、更聚焦、更适合人审。

### 9. Plan 消费 sidecar

状态：待实施。

改造点：

- Plan 继续以 `design.md` 作为人类方案事实源。
- Plan 同时读取 `design-implementation-hints.json` 获取候选文件、排除文件和职责分级。
- Plan 不再从 `design.md` 中解析代码线索。

建议改动文件：

- `src/coco_flow/engines/plan/input/__init__.py`
- `src/coco_flow/engines/plan/source.py`
- `src/coco_flow/prompts/plan/generate.py`

验收：

- `design.md` 即使不含候选文件列表，Plan 仍能生成可执行任务。
- Plan 不会把 sidecar 中 excluded 的文件当成主改造目标。

## 推荐里程碑

### Milestone 1：先让 Design 文档可读

- 完成任务 1、3、5。
- 验证目标：新 Design 不再堆代码线索，仓库职责表述更准确。

### Milestone 2：引入 sidecar 和 scope guard

- 完成任务 2、4、7。
- 验证目标：代码证据进入 sidecar，非目标能反向约束候选文件。

### Milestone 3：质量闭环

- 完成任务 6、8、9。
- 验证目标：低质量 Design 能被发现并修复，Plan 能消费 sidecar。

## 测试样例

优先用 task `20260428-193046-00` 回归：

- PRD：实验组竞拍讲解卡整数金额隐藏尾部 `.00`
- 预期 Design：
  - `live_pack` 必改
  - `live_common` 条件改或仅确认
  - 不把购物袋 helper 写成主方案
  - 明确待确认 `.00` vs trailing zero 冲突
- `design.md` 不展开代码搜索命中列表；允许保留少量方案落点文件
