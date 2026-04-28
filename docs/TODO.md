# TODO

## Lark Token 过期后错误提示与降级路径

状态：待实施。

背景：

- 当前 `lark-cli` 用户 token 过期后，会自动退回 `bot` 身份。
- 如果 bot 对目标文档没有权限，`docs +fetch` 会返回 `forBidden`。
- 现状里 task 侧只会看到“拉取文档失败”或下游阶段失败，问题不够直观。

需要做：

- 在 Input / Source 阶段识别 `lark-cli auth status` 中的用户 token 过期状态。
- 如果实际请求身份退回到 `bot`，在日志和 `source.json` / `prd.source.md` 里明确写出：
  - 用户 token 已过期
  - 当前使用的是 `bot` 身份
  - `bot` 对该文档无权限或权限待确认
- 给出明确修复建议：
  - 先执行 `lark-cli auth login`
  - 必要时用 `--as user` 重试
  - 如仍 `forBidden`，检查文档是否对当前用户 / app 授权
- 避免把这类问题误判为“网络暂时异常”。

验收：

- 用户 token 过期时，日志能明确看到“token expired -> fallback to bot identity”。
- 文档无权限时，错误提示能明确区分“未登录/登录过期”和“已登录但无文档权限”。
- 用户看到错误后，不需要再翻源码才能知道下一步该执行什么命令。

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
