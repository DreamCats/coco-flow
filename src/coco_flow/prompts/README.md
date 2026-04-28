# Prompts 使用情况

本目录存放各阶段给 native agent 使用的 prompt builder。本文记录当前运行时代码里的实际引用情况，避免旧多阶段 schema prompt 被误认为仍在主链路上。

判断口径：

- 算作“在用”：被 `src/coco_flow/engines/` 或服务运行时代码直接 import 并调用。
- 不算作“在用”：只被 `tests/test_prompts.py` 覆盖，或只在 `prompts/*/__init__.py` 中聚合导出。

## 当前在用

### Code

- `code/execute.py`
  - `build_code_execute_prompt`
  - 调用点：`src/coco_flow/engines/code/execute.py`
- `code/retry.py`
  - `build_code_retry_prompt`
  - 调用点：`src/coco_flow/engines/code/execute.py`

### Refine

- `refine/bootstrap.py`
  - `build_refine_bootstrap_prompt`
  - 调用点：`src/coco_flow/engines/refine/generate.py`
- `refine/generate.py`
  - `build_refine_generate_agent_prompt`
  - 调用点：`src/coco_flow/engines/refine/generate.py`
- `refine/verify.py`
  - `build_refine_verify_agent_prompt`
  - 调用点：`src/coco_flow/engines/refine/generate.py`
- `refine/shared.py`
  - 被 `refine/generate.py` 和 `refine/verify.py` 内部复用。

### Design

- `design/bootstrap.py`
  - `build_design_bootstrap_prompt`
  - 调用点：`src/coco_flow/engines/design/runtime/agent.py`
- `design/search_hints.py`
  - `build_search_hints_prompt`
  - `build_search_hints_template_json`
  - 调用点：`src/coco_flow/engines/design/discovery/search_hints.py`
- `design/writer.py`
  - 当前只有 `build_doc_only_design_prompt` 在用。
  - 调用点：`src/coco_flow/engines/design/writer/markdown.py`

### Plan

- `plan/bootstrap.py`
  - `build_plan_bootstrap_prompt`
  - 调用点：`src/coco_flow/engines/plan/runtime/agent.py`
- `plan/generate.py`
  - 当前只有 `build_doc_only_plan_prompt` 和 `build_plan_template_markdown` 在用。
  - 调用点：`src/coco_flow/engines/plan/writer/markdown.py`

### Shared

- `core.py`
  - `PromptDocument`
  - `PromptSection`
  - `render_prompt`
  - 被多个仍在用的 prompt builder 复用。

## 当前看起来没用

这些文件或函数不在运行时主链路中使用，主要是旧 Design/Plan 多角色、多阶段 schema 流程遗留。后续如果删除，需要同步清理对应 `__init__.py` 导出和 `tests/test_prompts.py` 里的旧测试。

### Design 旧 schema prompt

- `design/architect.py`
- `design/gate.py`
- `design/revision.py`
- `design/skeptic.py`
- `design/shared.py`
- `design/writer.py`
  - 其中 `build_writer_prompt` 没有运行时调用；同文件里的 `build_doc_only_design_prompt` 仍在用，不能直接删整个文件。

### Plan 旧 schema prompt

- `plan/graph.py`
- `plan/review.py`
- `plan/task_outline.py`
- `plan/validation.py`
- `plan/verify.py`
- `plan/shared.py`
- `sections.py`
- `plan/generate.py`
  - 其中 `build_plan_generate_agent_prompt` 和 `build_plan_writer_agent_prompt` 没有运行时调用；同文件里的 `build_doc_only_plan_prompt` 和 `build_plan_template_markdown` 仍在用，不能直接删整个文件。

## 结论

当前主链路已经是 doc-only Design / doc-only Plan：Design 只保留 bootstrap、search hints、doc-only writer；Plan 只保留 bootstrap、doc-only writer 和 Markdown 模板。旧的 Design architect/skeptic/revision/gate，以及旧的 Plan planner/scheduler/validation/skeptic/revision/verify 这套 schema prompt 已经不在运行时使用。
