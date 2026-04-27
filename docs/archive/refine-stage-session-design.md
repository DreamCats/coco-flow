# Refine Stage Session Design

本文记录 `Refine` 引擎后续学习 Claude Code 式交互编排时，关于 session 复用、角色隔离和 skills 注入的设计判断。

## 目标

当前 `Refine` 已经是 manual-first：

- Python 编排层读取 Input 产物。
- 本地规则解析“人工提炼范围”。
- 本地生成 `refine-brief.draft.json` 和 `refine-source.excerpt.md`。
- native executor 再让 agent 生成 refined PRD，并让另一个 agent 校验结果。

下一步希望学习的不是“把 prompt 写得更长”，而是 Claude Code 的核心上下文工程：

- 阶段开始时先注入稳定协议。
- 固定上下文只注入一次。
- task-specific 指令后续只发差量。
- skills 先以索引/摘要形式进入上下文，正文按需读取。
- 事实状态通过 artifact 传递，不依赖聊天记忆。

## 设计结论

`Refine` 不应该把 generate 和 verify 放在同一个对话历史里。裁决角色如果看到 generate 的推理过程，容易被上一轮自我解释污染。

更合理的形态是 stage-scoped dual sessions：

```text
Generate Session:
  bootstrap prompt
  generate prompt

Verify Session:
  inline bootstrap + verify prompt
```

两条 session 共享同一份 bootstrap，但不共享工作历史。
`Verify` 当前把 bootstrap 内联进 verify task 的同一次 prompt，避免底层 ACP 对第二条 session 的 bootstrap-only prompt 偶发超时。

## Bootstrap 内容

bootstrap prompt 应该只放稳定上下文：

- coco-flow 的阶段协议。
- Refine 的 artifact contract。
- manual-first 的优先级规则。
- 可用 skills 的索引和简短说明。
- 读写文件约束。
- 输出和 diagnosis 的基本契约。

bootstrap 不应该放整份原始 PRD、整份 skill body 或 generate/verify 的具体任务说明。

## Generate Session

Generate Session 的职责是把本地 controller 产出的事实源写成需求确认书：

```text
bootstrap
  -> read refine-manual-extract.json
  -> read refine-brief.draft.json
  -> read refine-source.excerpt.md
  -> edit template
```

约束：

- 人工提炼范围优先级最高。
- 只能补洞和润色，不能扩大 in_scope。
- 最终状态必须落盘到模板或目标 artifact。
- 不把上一轮自然语言解释作为事实源。

## Verify Session

Verify Session 的职责是独立裁决结果是否偏离 brief：

```text
bootstrap
  -> read refine-brief.draft.json
  -> read generated/refined markdown
  -> edit verify JSON template
```

约束：

- 只以 artifact 为准。
- 不读取 Generate Session 的聊天历史。
- 不采信 generate 的口头解释。
- 输出结构化 verify payload，供 diagnosis 和 gate 消费。

## 当前 ACP Client 能力评估

`CocoACPClient.run_agent(...)` 仍保留原有 `fresh_session` 参数：

- 可以复用 daemon 和 `coco acp serve` 进程。
- session pool key 是 `coco_bin + cwd + mode + query_timeout`。
- `fresh_session=False` 时，会复用 pooled session 内部保存的默认 `_session_id`。
- `fresh_session=True` 时，每次 prompt 前都会 `session/new`，再用新 `sessionId` 发送 `session/prompt`。

当前 ACP wrapper 已补充显式 session handle：

- `CocoACPClient.new_agent_session(...)`
- `CocoACPClient.prompt_agent_session(...)`
- `CocoACPClient.close_agent_session(...)`
- daemon request type: `session_new`
- daemon request type: `session_prompt`
- daemon request type: `session_close`

这已经可以表达：

```text
generate_session = new_session(role="refine_generate")
prompt(generate_session, bootstrap)
prompt(generate_session, generate)

verify_session = new_session(role="refine_verify")
prompt(verify_session, bootstrap)
prompt(verify_session, verify)
```

当前已完成：

- `build_refine_bootstrap_prompt(...)` 已抽出。
- `Refine` native 已接入 dual sessions。
- `refine.log` 已记录 session role 和 bootstrap prompt。

当前仍未完成：

- `CocoCliClient` 的 `-p --json` 路径天然不支持多轮 session。
- `session_close` 当前是本地 handle 丢弃；底层 ACP 没有显式 close 单个 session 的封装。

## 目标接口

`Refine` 层当前使用两个 role session：

```python
generate_session = client.new_agent_session(..., role="refine_generate")
verify_session = client.new_agent_session(..., role="refine_verify")

client.prompt_agent_session(generate_session, bootstrap_prompt)
client.prompt_agent_session(generate_session, generate_prompt)

client.prompt_agent_session(verify_session, inline_bootstrap_plus_verify_prompt)
```

关键是不要把 role session 变成 pool 的默认 reusable session。

## 落地顺序

1. 已完成：扩展 ACP daemon protocol，支持显式 `session_new` / `session_prompt` / `session_close`。
2. 已完成：在 `CocoACPClient` 增加显式 session handle API。
3. 已完成：抽出 `build_refine_bootstrap_prompt(...)`。
4. 已完成：将 refine native 改为 dual sessions：
   - bootstrap + generate
   - inline bootstrap + verify
5. 已完成：在 `refine.log` 记录 session role 和 bootstrap prompt。
6. 保留 local verify/repair 作为最终稳定兜底。

## 判断

这个方向值得做，但不应该简单把现有两处 `fresh_session=True` 改成 `False`。

粗暴复用匿名默认 session 会让 rerun 和不同角色互相污染。正确目标是：稳定上下文复用，角色工作历史隔离，事实状态通过 artifact 传递。
