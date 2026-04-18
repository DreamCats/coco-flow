# coco-flow

英文说明见：[README.md](README.md)

`coco-flow` 是一个独立的 workflow product，聚焦：

- PRD task 编排
- 基于 worktree 的代码执行
- 本地 Web UI / API 工作台

当前技术形态：

- 产品名：`coco-flow`
- 技术栈：Python + `uv`
- 运行方式：Typer CLI + FastAPI 本地服务

## 深入阅读

- [`docs/refine-v2-design.md`](docs/refine-v2-design.md)：当前 Refine 设计，基于 Input 产物、知识筛选和多步 Prompt
- [`docs/plan-engine.md`](docs/plan-engine.md)：解释 `plan` 引擎怎样做 repo research、scope 收敛、方案生成与验证
- [`docs/knowledge-generation-engine.md`](docs/knowledge-generation-engine.md)：解释知识草稿生成链路

## 当前能力范围

当前版本已经具备一条可用的主链路：

- `coco-flow tasks list` 查看 task 摘要
- `coco-flow tasks roots` 查看当前 task 根目录
- `coco-flow prd list` 查看 PRD workflow tasks
- `coco-flow tasks refine <task_id>` 生成 `prd-refined.md`
- `coco-flow tasks plan <task_id>` 生成 `design.md` 和 `plan.md`
- `coco-flow tasks code <task_id>` 执行 code 阶段
- `coco-flow prd refine --prd ...` / `plan --task ...` / `code --task ...`
- `coco-flow prd run -i ...` 一键执行 `refine -> plan -> code`
- `coco-flow tasks reset <task_id>` 回退 code 结果
- `coco-flow tasks archive <task_id>` 归档任务
- `coco-flow api serve` 启动本地 FastAPI 服务
- `POST /api/tasks` 从文本、本地文件或飞书文档创建 task
- `POST /api/tasks/{task_id}/code-all` 顺序推进剩余 repo
- `GET /api/tasks/{task_id}/artifact?name=diff.patch&repo=...` / `diff.json` 查看 repo 级 diff artifact
- `POST /api/knowledge/drafts` 默认生成 `flow` 知识草稿，也可按需补 `domain` 草稿，并写出 trace 中间产物

默认 task 目录：

- `~/.config/coco-flow/tasks`

## 快速开始

```bash
uv sync
uv run coco-flow --help

uv run coco-flow tasks roots
uv run coco-flow tasks list
uv run coco-flow knowledge list
uv run coco-flow prd list

uv run coco-flow prd refine --prd "需求描述"
uv run coco-flow prd plan --task <task_id>
uv run coco-flow prd code --task <task_id>
uv run coco-flow prd run -i "需求描述"
uv run coco-flow knowledge generate -d "竞拍讲解卡表达层" --path /path/to/repo

uv run coco-flow api serve --host 127.0.0.1 --port 4318
uv run coco-flow ui serve
```

## Web UI

前端目录在：[web](web/)

最简单的本地启动方式：

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow
uv sync
uv run coco-flow ui serve
```

这个命令会：

- 构建 `web/` 前端
- 启动 FastAPI
- 用同一个端口托管静态资源和 API

默认访问地址：

- `http://127.0.0.1:4318`

可选参数：

```bash
uv run coco-flow ui serve --no-build
uv run coco-flow ui serve --web-dir /absolute/path/to/dist
```

当前 UI 已支持：

- 创建 task
- 执行 refine / plan / code
- 编辑 `prd.source.md` / `prd-refined.md` / `design.md` / `plan.md`
- 查看 repo 级 code result / diff
- reset / archive

## 执行模式

当前支持两种执行模式：

- `native`：默认，走本地 `coco` / `coco acp serve`
- `local`：本地兜底实现

切换方式：

```bash
export COCO_FLOW_COCO_BIN=/path/to/coco
export COCO_FLOW_KNOWLEDGE_EXECUTOR=local
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
```

当前行为说明：

- `refine` / `plan` 默认优先 `native`，失败时回退到本地模板
- `knowledge` 支持 `native / local`；当前 `native` 会提升 repo research 和正文 synthesis，结构化输出失败时会自动回退到 `local`
- `refine` 支持：
  - 纯文本
  - 本地文件路径
  - 飞书文档链接
- 飞书文档如果暂时无法拉到正文，会生成 pending refine 占位稿，而不是直接创建失败
- `refine` 现在会额外产出 `refine-result.json`，记录 `context_mode`、业务记忆是否命中、风险提示；当没有业务记忆可用时会显式降级为 `source_only`
- `refine` 的详细编排和设计动机见 [`docs/refine-v2-design.md`](docs/refine-v2-design.md)
- `plan` 的详细编排和设计动机见 [`docs/plan-engine.md`](docs/plan-engine.md)
- `plan` 现在会额外产出 `plan-scope.json`、`plan-execution.json`、`plan-verify.json`；其中 native plan 已拆成 scope、design、execution 三段内部编排
- `code=native` 走 `coco acp serve`
- `code` 会做最小范围验证，并在 build 失败后进行一到两轮修复重试

## API

当前主要接口：

- `GET /`
- `GET /healthz`
- `GET /api/workspace`
- `GET /api/knowledge`
- `GET /api/knowledge/{document_id}`
- `GET /api/knowledge/jobs/{job_id}`
- `GET /api/knowledge/traces/{trace_id}`
- `POST /api/knowledge/drafts`
- `PUT /api/knowledge/{document_id}`
- `DELETE /api/knowledge/{document_id}`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/refine`
- `POST /api/tasks/{task_id}/plan`
- `POST /api/tasks/{task_id}/code`
- `POST /api/tasks/{task_id}/code-all`
- `POST /api/tasks/{task_id}/reset`
- `POST /api/tasks/{task_id}/archive`
- `GET /api/tasks/{task_id}/artifact?name=...`
- `PUT /api/tasks/{task_id}/artifact?name=...`

## Knowledge Draft

`POST /api/knowledge/drafts` 现在会先启动后台 knowledge generation job，再按
[`docs/knowledge-generation-engine.md`](docs/knowledge-generation-engine.md)
的第一阶段实现运行：

- 根据 `title + description + selected_paths + kinds` 做 intent normalize
- 在 discovery 前先做术语映射，把用户语言对齐到 repo 内真实术语
- 对选中路径执行轻量 repo discovery，读取 `AGENTS.md`、`.livecoding/context/`、目录结构、文件名、符号命中和最近提交标题
- 在 repo research 前再做一轮锚点筛选，提炼 `strongest_terms / entry_files / business_symbols / discarded_noise`
- repo research 和 knowledge synthesis 通过 `COCO_FLOW_KNOWLEDGE_EXECUTOR` 执行；`native` 分别走 readonly ACP 与 prompt-only synthesis，`local` 保持规则兜底
- 生成草稿、执行静态校验，并把 trace 写到本地 knowledge 目录

接口返回的是带 `stage/status/progress` 的 job。
前端或脚本可通过 `GET /api/knowledge/jobs/{job_id}` 轮询进度和最终结果。

为了兼容现有 UI，请求体同时支持新的 `selected_paths` 和旧的 `repos` 字段。
trace 默认落盘到 `~/.config/coco-flow/knowledge/trace/<trace_id>/`。

## 目录结构

```text
src/coco_flow/
├── api/            # FastAPI app factory
├── engines/        # refine / plan 推理引擎
├── models/         # 共享模型
├── services/       # workflow 壳、查询拼装与 runtime helper
├── cli.py          # Typer 入口
└── config.py       # 配置与默认目录

web/
├── src/App.tsx     # 本地 workflow workbench
├── src/api.ts      # 浏览器 API client
└── src/index.css   # 页面样式
```

## 当前对齐目标

这个仓库的目标不是重新设计一套新 workflow，而是尽量平滑承接 `coco-ext` 的 workflow product 层能力。

当前优先级：

- 优先对齐外部行为
  - CLI 语义
  - task 状态流转
  - 日志格式
  - UI 体验
- 底层实现允许不同
  - Python
  - FastAPI
  - ACP daemon

## 后续方向

- 继续优化 `plan` 的 repo grouping 和 task 拆分
- 继续打磨 pending Lark refine 的 UI 恢复提示
- 增加 background task / multi-repo workflow 的自动化测试
