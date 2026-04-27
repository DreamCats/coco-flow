# Design Engine Guide

这个目录负责把 `prd-refined.md`、绑定仓库、Skills/SOP 和代码调研证据整理成 `design.md`。

Design 比 Plan 更复杂，原因是它不是简单生成文档，而是要回答：

- 这个需求会影响哪些仓库？
- 每个仓库大概率改哪些文件？
- 哪些判断来自 PRD，哪些判断来自 Skills/SOP，哪些判断来自真实代码证据？
- 是否存在风险、边界或待确认项？

当前 Design 是 doc-only：最终主要落 `design.md` 和 `design.log`，并额外写轻量 sidecar：
`design-skills.json` 给 Plan 继承业务 Skills/SOP，`design-contracts.json` 给 Plan 消费跨仓契约，
`design-sync.json` 记录 Markdown 与结构化契约是否同步；不再落旧 schema 中间产物。

## 建议阅读顺序

1. `__init__.py`
   看对外导出和阶段定位。

2. `pipeline.py`
   看主流程。这个文件是最重要的入口。

3. `types.py`
   看 `DesignInputBundle` 里到底传了哪些输入材料。

4. `input/source.py`
   看 Design 从 task 目录读取了哪些文件。

5. `knowledge/skills.py`
   看 Skills/SOP 怎么被选中，并渲染成可渐进式加载的文件索引。

6. `discovery/search_hints.py`
   看 native/local 如何生成搜索线索。

7. `evidence/research.py`
   看本地仓库调研、候选文件、git evidence 怎么产生。

8. `writer/markdown.py`
   看最终 `design.md` 如何生成，native 失败时如何 fallback。

## 当前架构层

```text
design/
  __init__.py              对外入口，导出状态、日志、主编排
  pipeline.py              主编排：input -> knowledge -> discovery -> evidence -> writer
  types.py                 DesignInputBundle / DesignEngineResult / 状态常量

  input/                   输入层：读取 refined PRD、repos、兼容旧 refine 产物
  knowledge/               知识层：选择 Skills/SOP，生成文件索引和 local fallback excerpt
  discovery/               搜索线索层：从需求里提取搜索词、符号、路径模式
  evidence/                证据层：在本地 repo 做 rg、路径扫描、git evidence、候选文件排序
  writer/                  写作层：生成 design.md，native 失败则用本地草稿
  runtime/                 运行时层：ACP session 和 design.log
  support/                 跨层轻量工具函数
```

## 主流程

`pipeline.run_design_engine()` 是主入口：

1. `input.prepare_design_input()`
   读取：
   - `prd-refined.md`
   - `input.json`
   - `repos.json`
   - 兼容旧 refine 的 `refine-brief.json`、`refine-intent.json`、`refine-skills-*`

   输出 `DesignInputBundle`。

2. `knowledge.build_design_skills_bundle()`
   从 Skills Store 中选中相关业务知识，生成：
   - `design_skills_selection_payload`
   - `design_skills_index_markdown`
   - `design_skills_fallback_markdown`
   - `design_selected_skill_ids`

   native agent 主要消费 `design_skills_index_markdown` 中的完整文件路径，并按需读取
   `SKILL.md` 与 `references/*.md`。`design_skills_fallback_markdown` 只作为 local fallback，
   不作为 native 的完整事实源。
   阶段完成后，selection payload 会持久化为 `design-skills.json`，Plan 只能继承它，
   不再重新选择业务范围类 Skills。

3. `discovery.build_search_hints()`
   生成 repo research 用的搜索线索：
   - `search_terms`
   - `likely_symbols`
   - `likely_file_patterns`
   - `negative_terms`

   native 可用时让 agent 从需求和 Skills 中提取；失败时走本地启发式。

4. `evidence.build_research_plan()`
   把搜索线索扩展成每个 repo 的调研计划，包括搜索词、路径模式、预算和问题列表。

5. `evidence.run_parallel_repo_research()`
   并发调研每个仓库，核心逻辑在 `evidence/research.py` 的 `research_single_repo()`：
   - 用 `rg` 搜索关键词
   - 按路径模式扫描文件
   - 用 git history/co-change 补充证据
   - 排序 candidate files / related files
   - 生成 evidence、boundaries、unknowns

6. `evidence.build_research_summary()`
   汇总多仓调研结果，给 writer 使用。

7. `writer.write_doc_only_design_markdown()`
   先生成本地草稿，再在 native 可用时让 writer agent 编辑 Markdown。
   native 失败时保留本地草稿。

8. `shared.contracts.build_design_contracts_payload()`
   从最终 `design.md` 中提取跨仓字段、接口或配置契约，持久化为 `design-contracts.json`。
   这一步是程序规则，不调用 LLM。

## LLM 和程序规则的边界

使用 LLM 的地方：

- `discovery/search_hints.py`
  native 模式下，LLM 只提取搜索线索，不直接读取仓库、不直接决定最终方案。

- `writer/markdown.py`
  native 模式下，LLM 只编辑 `design.md` Markdown。

使用程序规则的地方：

- `input/source.py`
  文件读取和输入归一化。

- `knowledge/skills.py`
  Skills/SOP 的通用召回、native semantic selector、文件索引渲染，以及 local fallback excerpt 渲染。

- `evidence/research.py`
  本地代码搜索、git evidence、候选文件排序、边界和未知项。

- `pipeline.py`
  阶段顺序、fallback、日志事件。

- `shared/contracts.py`
  从 `design.md` 提取跨仓契约，并被 Design 生成和 Plan 编译共同使用。

当前设计理念是：程序规则负责“召回候选 skill 与收集代码证据”，LLM 负责“从候选 skill
中做语义选择、读取完整 skill 内容后的理解和文档表达”。程序不提前压缩 native agent 的主要上下文。

## 文件职责细分

### `input/source.py`

输入层。只做读取和归一化，不做判断。

常见改动：

- 新增 Design 输入文件
- 修改前置校验
- 从 task metadata 增加字段

### `knowledge/skills.py`

知识层。负责先用 `SKILL.md` 入口文本召回候选 skill；native 可用时再用受控 JSON
selector 从候选中选择真正需要读取的 skill，并输出渐进式加载索引。

常见改动：

- 调整 skill 打分规则
- 调整 native selector 输入、输出和 fallback 条件
- 调整 selected skill 数量
- 调整索引里暴露哪些路径和命中原因
- 调整 local fallback excerpt

不建议在这里写具体 repo 改动判断。Skills 是背景知识，不是代码证据。

### `discovery/search_hints.py`

发现层。负责把需求转成 repo research 的搜索入口。

常见改动：

- 调整搜索词提取
- 调整 likely symbol / file pattern 规则
- 调整 native search hints prompt 的输入输出

这里的输出只是“搜索线索”，不是最终设计结论。

### `evidence/research.py`

证据层。当前最复杂，也最容易看不懂。

它主要分四段：

1. `build_research_plan()`
   为每个 repo 生成调研计划。

2. `run_parallel_repo_research()`
   并发跑多个 repo。

3. `research_single_repo()`
   单仓调研主逻辑。

4. 后面的 helper
   包括 `rg` 搜索、路径扫描、git evidence、candidate ranking、excerpt 读取。

常见改动：

- 调整搜索预算
- 调整 candidate file 排序
- 增加/减少 git evidence
- 调整排除目录
- 改善 unknowns / boundaries 表达

### `writer/markdown.py`

写作层。负责最终 `design.md`。

常见改动：

- 调整本地 fallback 草稿结构
- 调整 writer prompt 输入
- 调整 native 输出校验

注意：writer 可以解释证据，但不应该凭空发明 repo 证据。

### `runtime/agent.py`

运行时适配层。只放 ACP session / agent 调用细节。

除非改 native agent 调用方式，否则不要把业务规则放这里。

## 判断改动放哪里

- “Design 要多读一个上游产物” -> `input/`
- “业务 skill 命中不准” -> `knowledge/`
- “搜索不到相关文件” -> `discovery/` 或 `evidence/`
- “候选文件排序不准” -> `evidence/`
- “design.md 结构不好读” -> `writer/`
- “native agent 调用失败/复用 session 有问题” -> `runtime/`
- “阶段顺序、日志事件、fallback 策略” -> `pipeline.py`
- “落盘、状态流转、API 行为” -> `services/tasks/design.py`

## 当前主要技术债

- `evidence/research.py` 仍然过大，里面同时包含搜索、git evidence、ranking、excerpt 读取。
  后续可以继续拆成 `evidence/search.py`、`evidence/git.py`、`evidence/ranking.py`。

- `discovery/` 和 `evidence/` 的边界需要保持清晰：
  前者只产搜索入口，后者才产证据。

- `types.py` 里还保留一些兼容旧 refine schema 的字段。
  当前是为了平滑迁移，后续如果确定不会再用旧产物，可以继续瘦身。
