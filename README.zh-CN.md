# coco-flow

英文说明见：[README.md](README.md)

`coco-flow` 是一个本地 workflow product，用一套 task 模型把 PRD 驱动的需求流转、Typer CLI、FastAPI、本地 Web UI 和基于 worktree 的代码执行串起来。

## 概览

- 产品名：`coco-flow`
- Python 包：`coco-flow`
- Python 版本：`>=3.13`
- 技术栈：Python、`uv`、Typer、FastAPI、Vite/React
- 默认交互语言：中文

当前 task 主流程：

```text
Input -> Refine -> Design -> Plan -> Code
```

## 快速开始

先安装一次，之后直接用 `coco-flow`：

```bash
source ./install.sh
coco-flow version
coco-flow start
```

也可以一条命令安装：

```bash
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash -s -- --no-ui
```

如果不用 `source`，第一次安装后需要重开 shell，或者按脚本输出把 tool bin 目录加到当前 `PATH`。

直接使用示例：

```bash
coco-flow --help

coco-flow version
coco-flow install --path .
coco-flow update --path .

coco-flow start
coco-flow start --api-only

coco-flow tasks roots
coco-flow tasks list
coco-flow knowledge list

coco-flow tasks refine <task_id>
coco-flow tasks design <task_id>
coco-flow tasks plan <task_id>
coco-flow tasks code <task_id>
coco-flow tasks reset <task_id>
coco-flow tasks archive <task_id>

coco-flow daemon start
coco-flow daemon status
coco-flow daemon stop
```

远程机安装脚本：

```bash
source ./install.sh
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
```

## 工作流行为

### Input

- task 默认存储在 `~/.config/coco-flow/tasks/`
- `POST /api/tasks` 支持三类输入：
  - 纯文本
  - 本地文件路径
  - 飞书文档链接
- 纯文本和本地文件会同步落盘，状态进入 `input_ready`
- 飞书文档链接先进入 `input_processing`，正文拉取完成后异步继续
- Input 阶段会生成 `input.json` 和 `input.log`

### Refine

- `refine` 支持 `native` 和 `local`
- `native refine` 采用 intent、knowledge selection、knowledge brief、draft generate、verify 的多步编排
- `local refine` 负责结构化兜底
- 常见产物包括 `prd-refined.md`、`refine-intent.json`、`refine-knowledge-selection.json`、`refine-knowledge-brief.md`、`refine-verify.json`、`refine-result.json`

### Design 与 Plan

- `design` 是独立阶段，CLI 和 API 都已暴露
- `plan` 支持 `native` 和 `local`
- `native plan` 采用 scope 提取、生成、验证的分段编排
- 常见产物包括 `design.md`、`plan.md`、`plan-scope.json`、`plan-execution.json`、`plan-verify.json`、`plan-knowledge-selection.json`、`plan-knowledge-brief.md`

### Code

- `code` 统一按后台异步执行
- 单 repo task 可直接推进；多 repo task 支持 `code?repo=...` 和 `code-all`
- `native code` 会在隔离 worktree 里跑 repo batch，并写回 task 级和 repo 级结果产物
- 内置最小验证：
  - Go：默认对受影响目录执行 `go build`
  - Go test：通过 `COCO_FLOW_ENABLE_GO_TEST_VERIFY=1` 显式开启
  - Python：`python3 -m py_compile`

## Web UI

前端目录在 [`web/`](web/)。

最简单的本地启动方式：

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow
source ./install.sh
coco-flow start
```

这个命令会：

- 构建 `web/`
- 启动 FastAPI
- 在 `http://127.0.0.1:4318` 同时提供静态页面和 API

常用选项：

```bash
coco-flow start --no-build
coco-flow start --web-dir /absolute/path/to/dist
coco-flow start --api-only
```

当前 UI 能力：

- 创建 task
- 执行 `refine`、`design`、`plan`、`code`
- 浏览和编辑 knowledge 文档
- 编辑 `prd.source.md`、`prd-refined.md`、`design.md`、`plan.md`
- reset、archive、查看 task artifact

## 执行模式

执行器：

- `native`：默认，依赖本地 `coco` 和 ACP
- `local`：内置兜底实现

常用环境变量：

```bash
export COCO_FLOW_COCO_BIN=/path/to/coco
export COCO_FLOW_KNOWLEDGE_EXECUTOR=local
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
export COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS=86400
export COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS=86400
```

默认空闲超时：

- daemon：`3600` 秒
- ACP session：`600` 秒

## API

当前接口：

- `GET /`
- `GET /healthz`
- `GET /api/workspace`
- `GET /api/knowledge`
- `POST /api/knowledge`
- `GET /api/knowledge/{document_id}`
- `PUT /api/knowledge/{document_id}`
- `PUT /api/knowledge/{document_id}/content`
- `DELETE /api/knowledge/{document_id}`
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `PUT /api/tasks/{task_id}/repos`
- `DELETE /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/refine`
- `POST /api/tasks/{task_id}/design`
- `POST /api/tasks/{task_id}/plan`
- `POST /api/tasks/{task_id}/code`
- `POST /api/tasks/{task_id}/code-all`
- `POST /api/tasks/{task_id}/reset`
- `POST /api/tasks/{task_id}/archive`
- `GET /api/tasks/{task_id}/artifact?name=...&repo=...`
- `PUT /api/tasks/{task_id}/artifact?name=...`
- `GET /api/repos/recent`
- `POST /api/repos/validate`
- `GET /api/fs/roots`
- `GET /api/fs/list?path=...`

## 目录结构

```text
src/coco_flow/
├── api/            # FastAPI app factory 与路由
├── clients/        # ACP client 抽象
├── daemon/         # 本地 daemon 与 session 管理
├── engines/        # Input / Refine / Design / Plan / Code 引擎
├── models/         # 共享响应模型
├── services/       # workflow 壳、查询拼装、runtime helper
└── cli.py          # Typer 入口

web/
├── src/App.tsx
├── src/api.ts
└── src/index.css
```

## 校验

定向校验：

```bash
uv run python -m py_compile src/coco_flow/engines/refine/__init__.py
uv run python -m py_compile src/coco_flow/engines/plan.py
uv run python -m py_compile src/coco_flow/engines/plan_generate.py
uv run python -m py_compile src/coco_flow/engines/plan_models.py
uv run python -m py_compile src/coco_flow/engines/plan_knowledge.py
uv run python -m py_compile src/coco_flow/engines/plan_research.py
uv run python -m py_compile src/coco_flow/engines/plan_render.py
uv run python -m py_compile src/coco_flow/services/tasks/plan.py
uv run python -m py_compile src/coco_flow/services/tasks/code.py
uv run python -m unittest discover -s tests -v
```

前端构建：

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow/web
npm install
npm run build
```

## 深入阅读

- [`docs/refine-v2-design.md`](docs/refine-v2-design.md)
- [`docs/design-v2-design.md`](docs/design-v2-design.md)
- [`docs/plan-engine.md`](docs/plan-engine.md)
- [`docs/code-v2-design.md`](docs/code-v2-design.md)
