# Daemon Streaming Notes

本文记录 daemon streaming 的当前结论和后续讨论分阶段方向。Web UI 展示方式暂不定稿，后续继续细化。

## 当前结论

- `coco acp serve` 到 daemon 内部支持流式 chunk。
- 当前 daemon 对外不支持流式，只在 ACP 返回完成后一次性返回最终 `content`。
- ACP chunk 类型来自 `session/update`，其中 `sessionUpdate == "agent_message_chunk"`。
- 现有调用方仍以同步字符串为主，Refine / Design / Plan / Code 都依赖最终完整内容。

相关代码：

- `src/coco_flow/clients/acp_client.py`
  - `_ACPProcess.prompt()` 发送 `session/prompt`，循环等待消息。
  - `_consume_prompt_update()` 消费 `agent_message_chunk` 并 append 到 `chunks`。
  - 当前最终通过 `"".join(chunks).strip()` 返回完整字符串。
- `src/coco_flow/daemon/server.py`
  - `_handle_prompt()` 和 `_handle_session_prompt()` 等待 pool 返回完整内容后 `_write_json()` 一次。
- `src/coco_flow/daemon/client.py`
  - `send_request()` 只读取一行 JSON 响应。
  - `run_prompt_via_daemon()` 和 `prompt_session_via_daemon()` 都返回 `str`。

## 阶段 1：Daemon Socket 对外流式

目标：在不破坏现有同步接口的前提下，新增 daemon socket streaming 能力。

建议范围：

- 在 ACP 层新增 streaming 入口，例如 `prompt_stream()` 或给 `prompt()` 增加 `on_chunk` callback。
- 在 session pool 层新增 `run_prompt_stream()` / `prompt_session_stream()`。
- 在 daemon server 新增请求类型，例如 `prompt_stream` / `session_prompt_stream`。
- socket 响应用 NDJSON，多行事件直到 `done` 或 `error`。
- daemon client 新增 iterator 版本，例如 `stream_request()`，保留当前 `send_request()` 不变。

建议事件格式：

```json
{"type":"chunk","content":"..."}
{"type":"done","content":"完整最终内容"}
{"type":"error","error":"..."}
```

注意点：

- `done.content` 是否返回完整内容需要确认。返回完整内容能兼容审计和最终落盘，但会重复传输。
- streaming 期间 session pool 锁会保持占用，这与当前单 session 串行语义一致。
- 超时、ACP 进程退出、空响应都要有明确 `error` 事件。

## 阶段 2：FastAPI 对外流式

目标：让 API 可以把 daemon streaming 转成 HTTP streaming。

候选方案：

- `StreamingResponse` + NDJSON。
- `StreamingResponse` + SSE。

建议先用 NDJSON 做内部 API，SSE 可作为 Web UI 展示层适配。原因是 daemon socket 本身更适合 NDJSON，错误和最终内容事件也更直接。

需要确认：

- 是否新增独立 endpoint，避免改变现有 `POST /api/tasks/...` 行为。
- 流式内容是 agent 文本，还是任务阶段事件。
- 是否需要把 chunk 同步写入阶段日志或 sidecar。

## 阶段 3：Web UI 展示

目标：在任务详情中实时展示 agent 输出或阶段输出。

当前只确认方向，不定稿 UI：

- 前端可以用 fetch stream 或 EventSource 消费 API streaming。
- 展示内容需要区分两类信息：
  - agent 文本 chunk：模型正在生成的正文。
  - workflow 进度事件：阶段开始、验证、失败、完成等。
- 初版可以只展示 agent 文本流，最终仍以 `prd-refined.md` / `design.md` / `plan.md` artifact 为准。

待讨论：

- 是否要在 Stage Detail Panel 内直接显示实时正文。
- 是否要把实时输出落到现有 `*.log`。
- 用户离开页面后再回来，是否需要恢复 streaming 状态或只读 artifact/log。

## 阶段 4：Workflow 语义整合

目标：把 streaming 从“传输能力”变成稳定产品语义。

需要设计：

- Refine / Design / Plan 的 streaming 输出分别代表什么。
- Code 阶段 streaming 是 agent 输出、验证日志，还是 repo 级进度。
- streaming 与 task status、`code-progress.json`、阶段日志之间的关系。
- 多 repo Code 时，事件里需要带 `repo_id`。

## 成本判断

- 只做 daemon socket streaming：低到中等。
- 透到 FastAPI：中等。
- 做完整 Web UI 展示和 workflow 语义：中等偏上。

建议拆成两步：

1. 先打通 daemon socket streaming，并保留同步接口。
2. 再基于真实 UI 交互确认 API 和 Web UI 展示协议。
