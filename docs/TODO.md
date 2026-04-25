# TODO

## Plan Open Harness Phase 5：Code 反馈闭环

状态：待实施。

目标：让 Code 阶段失败能反向沉淀到 Plan，而不是只留在 `code.log` / `code-result.json` 里。

需要做：

- Code 失败时输出可归因字段：
  - `plan_item_id`
  - `repo_id`
  - `failure_type`
  - `suggested_plan_fix`
- 汇总生成 `plan-code-feedback.json`，供下一次 Plan rerun 消费。
- Plan rerun 时把 Code feedback 注入 Planner / Skeptic 输入。
- 如果失败原因是任务过大，Planner 应拆小 work item。
- 如果失败原因是验证契约不合适，Validation Designer 应修正 validation contract。
- 如果失败原因是 Design 裁决冲突，Plan 应输出 `needs_design_revision`，不要自行改 Design artifacts。

建议 failure types：

```text
work_item_too_broad
validation_contract_invalid
code_input_missing
dependency_order_invalid
design_artifact_conflict
needs_design_revision
```

验收：

- Code 因任务过大失败后，Plan rerun 能拆小 work item。
- Code 因验证命令不合适失败后，Plan rerun 能修正 `plan-validation.json`。
- Code 因 Design 裁决错误失败后，Plan gate 输出 `needs_design_revision` 且不允许进入 Code。
