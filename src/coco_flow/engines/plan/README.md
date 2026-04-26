# Plan Engine Guide

这个目录负责把 `prd-refined.md`、`design.md`、仓库绑定和 Skills/SOP 编译成 Code 阶段可执行的 Plan 契约。

如果只是想看懂代码，建议按这个顺序读：

1. `__init__.py`：先看整体架构说明。
2. `pipeline.py`：看主流程怎么串起来。
3. `types.py`：看 Plan 阶段内部传递的数据模型。
4. `compiler/structure.py`：看结构化产物如何生成和同步。
5. 需要排查 native writer 时再看 `writer/` 和 `runtime/`。

## 目录职责

```text
plan/
  __init__.py        包级入口和架构说明
  pipeline.py        主编排：input -> knowledge -> compiler -> writer
  types.py           Plan 数据模型、状态常量、executor 常量

  input/             读取 task 目录，解析 refined/design/repos
  knowledge/         选择 Skills/SOP，生成完整文件路径索引和 local fallback brief
  writer/            生成任务级 plan.md，native 失败时走 local fallback
  compiler/          程序规则生成结构化 JSON、repo plan、Sync Plan
  runtime/           ACP session 和 plan.log 这类运行时适配
```

## 主流程

`pipeline.run_plan_engine()` 是主入口：

1. `input.prepare_plan_input()`
   读取 `prd-refined.md`、`design.md`、`input.json`、`repos.json`，生成 `PlanPreparedInput`。

2. `knowledge.build_plan_skills_bundle()`
   挑选本次 Plan 相关的 Skills/SOP，生成 writer 可渐进式加载的完整文件路径索引。
   native writer 读取完整 skill 文件；brief 只作为 local fallback。

3. `compiler.build_structured_plan_artifacts()`
   用程序规则生成结构化契约：
   - `plan-work-items.json`
   - `plan-execution-graph.json`
   - `plan-validation.json`
   - `plan-result.json`
   - `plan-repos/<repo>.md`

4. `compiler.validate_plan_artifacts()`
   做最低限度的结构校验，避免缺仓、缺任务、依赖指向不存在任务。

5. `writer.generate_doc_only_plan_markdown()`
   生成任务级 `plan.md`。native writer 只负责写人看的 Markdown；结构化 JSON 不直接信 LLM。

6. `services.tasks.plan`
   不在本目录内。它是 workflow 壳，负责状态流转、落盘、日志生命周期和 repo 状态同步。

## Sync Plan

用户在 UI 中编辑 `plan.md` 或 `plan-repos/<repo>.md` 后，`plan-sync.json` 会变成 `synced: false`。

此时 Code 阶段会被阻断，因为 Code 消费的是结构化 JSON，而不是 Markdown。

用户点击“同步执行契约”时，会走：

```text
services.tasks.plan_sync.sync_plan_task()
  -> input.prepare_plan_input()
  -> compiler.build_structured_plan_artifacts_from_repo_markdowns()
  -> compiler.validate_plan_artifacts()
  -> 写回结构化 JSON 和 plan-sync.json
```

Sync Plan 不覆盖用户编辑后的 Markdown，只刷新 Code 会消费的 JSON。

## LLM 和程序规则的边界

LLM 只用于 `writer/`：

- native executor 下通过 ACP writer 生成任务级 `plan.md`
- 负责自然语言表达，不作为 Code gate 的唯一来源

程序规则负责 `compiler/`：

- 拆分 work items
- 推断依赖图
- 生成 repo plan markdown
- 生成 validation 和 result gate
- 从用户编辑后的 repo markdown 同步结构化 JSON

这个边界的原因是：Plan 的关键不是生成一篇长文，而是稳定回答“每个仓做什么、谁依赖谁、能不能进入 Code”。

## 常改文件

- `pipeline.py`
  调整 Plan 主流程顺序时改这里。

- `compiler/structure.py`
  调整任务拆分、依赖推断、repo plan 格式、Sync Plan 解析时改这里。

- `writer/markdown.py`
  调整 `plan.md` 生成策略、native/local fallback 时改这里。

- `input/source.py`
  调整 Plan 输入材料或前置校验时改这里。

## 尽量少改文件

- `runtime/agent.py`
  只封装 ACP session。除非改 native agent 调用方式，否则不要把业务逻辑放进去。

- `runtime/logging.py`
  只负责追加 `plan.log`。

- `types.py`
  数据模型变更会影响多个层，改之前先确认下游 Code 是否消费这些字段。

## 判断改动放哪里

- “读取更多上游文件” -> `input/`
- “选择更多业务知识” -> `knowledge/`
- “让 plan.md 写得更好” -> `writer/`
- “让 Code 能稳定消费计划” -> `compiler/`
- “ACP / session / 日志问题” -> `runtime/`
- “阶段状态、落盘、API 调用” -> `services/tasks/plan.py` 或 `services/tasks/plan_sync.py`
