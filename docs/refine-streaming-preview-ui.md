# Refine Streaming Preview UI

本文记录 Refine 阶段 streaming preview 的 Web UI 方向。当前分支只落地 daemon socket streaming；本文用于后续 API / Web UI 分支继续设计，不在当前阶段直接实现。

## 背景

已确认：

- daemon socket 已支持 `prompt_stream` / `session_prompt_stream`。
- Web UI 当前布局不是重新设计的工作台，而是现有 Task Stage Detail Panel。
- Refine 当前在 `web/src/features/tasks/stages/refine-stage.tsx` 内使用三类内容：
  - `产物与查看`
  - `补充说明`
  - `日志`
- 产物展示当前读取 `prd-refined.md`，日志展示 `refine.log`。

因此 streaming preview 应适配现有 Refine Stage 布局，不重做整页信息架构。

## UI 结论

Refine 运行中，默认仍停留在 `产物与查看` tab。

`产物与查看` 的内容区域从正式 artifact viewer 临时切换为只读 streaming preview：

```text
阶段详情 / Refine

[产物与查看] [补充说明] [日志]

prd-refined.md        Streaming
正在生成中，完成后会自动切换为保存后的正式产物。

# 需求提炼

正在流式生成的 markdown...
|
```

关键约束：

- `Streaming` 是状态 pill，不是按钮，也不是可点击 tab。
- preview 是只读区域，不支持边生成边编辑。
- 完成后自动刷新 task detail，并展示保存后的 `prd-refined.md`。
- `补充说明` 和 `日志` tab 保持现有交互。
- 初版不做刷新页面后的断线续看；刷新后读取 artifact / log 即可。

## 为什么不做成按钮或可点击标签

- 看生成过程不是一个用户命令，不应该要求用户额外点击。
- Refine 初版只有一个正文 preview，不需要单独增加 tab。
- 如果做成新 tab，容易让用户误以为 streaming preview 是一种可长期访问的 artifact。
- 状态 pill 足够表达“当前内容来自实时流，而不是已落盘文件”。

## 与当前布局的关系

当前 Refine Stage 已有进度条和步骤卡片。Streaming preview 不替代这些状态组件。

建议关系：

- 顶部进度条继续表达阶段进展。
- `产物与查看` tab 表达当前产物正文。
- `日志` tab 表达执行事件和诊断信息。
- streaming preview 只接管 `产物与查看` tab 的正文区域。

## 最小实现范围

后续 Refine streaming UI 的 MVP 应包括：

- 后端提供 Refine 专用 streaming endpoint。
- 前端在触发 Refine 后消费 streaming。
- `task.status === "refining"` 时显示只读 markdown preview。
- 收到 `chunk` 时追加到 preview。
- 收到 `done` 时刷新 task detail，切回正式 `prd-refined.md`。
- 收到 `error` 时保留已收到 preview，并显示错误状态。

不包括：

- Design / Plan streaming UI。
- Code repo 级 streaming。
- 页面刷新后的 stream 恢复。
- 与 artifact 编辑器合并。
- 全局 floating console。

## 视觉要求

- 沿用当前 `RefineStage` 的 SectionCard / tab / artifact panel 风格。
- preview 的 header 可沿用 artifact panel 标题区域，右侧放非点击状态 pill。
- 内容区域使用 markdown 渲染或接近 artifact viewer 的排版。
- running 状态下不显示“编辑原文”按钮，避免用户边生成边编辑。

## 待定问题

- Refine streaming endpoint 使用 NDJSON 还是 SSE。
- preview 内容是否需要同步写入临时 sidecar，便于刷新后短暂恢复。
- `refine.log` 是否要记录 chunk 事件，还是只记录阶段事件。
- 如果用户切到日志 tab，是否继续在后台消费 stream 并更新 preview。
