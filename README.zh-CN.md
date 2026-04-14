# coco-flow

英文说明见：[README.md](/Users/bytedance/Work/tools/bytedance/coco-flow/README.md)

`coco-flow` 是一个独立的 workflow product，聚焦：

- PRD task 编排
- 基于 worktree 的代码执行
- 本地 Web UI / API 工作台

当前技术形态：

- 产品名：`coco-flow`
- 技术栈：Python + `uv`
- 运行方式：Typer CLI + FastAPI 本地服务

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

默认 task 目录：

- `~/.config/coco-flow/tasks`

## 快速开始

```bash
uv sync
uv run coco-flow --help

uv run coco-flow tasks roots
uv run coco-flow tasks list
uv run coco-flow prd list

uv run coco-flow prd refine --prd "需求描述"
uv run coco-flow prd plan --task <task_id>
uv run coco-flow prd code --task <task_id>
uv run coco-flow prd run -i "需求描述"

uv run coco-flow api serve --host 127.0.0.1 --port 4318
uv run coco-flow ui serve
```

## Web UI

前端目录在：[web](/Users/bytedance/Work/tools/bytedance/coco-flow/web)

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
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
```

当前行为说明：

- `refine` / `plan` 默认优先 `native`，失败时回退到本地模板
- `refine` 支持：
  - 纯文本
  - 本地文件路径
  - 飞书文档链接
- 飞书文档如果暂时无法拉到正文，会生成 pending refine 占位稿，而不是直接创建失败
- `code=native` 走 `coco acp serve`
- `code` 会做最小范围验证，并在 build 失败后进行一到两轮修复重试

## API

当前主要接口：

- `GET /`
- `GET /healthz`
- `GET /api/workspace`
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

## 目录结构

```text
src/coco_flow/
├── api/            # FastAPI app factory
├── models/         # 共享模型
├── services/       # task/workflow/repo 业务逻辑
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
