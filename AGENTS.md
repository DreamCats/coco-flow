# AGENTS.md

本文件面向在 `coco-flow` 仓库内协作的 AI agent。目标是先给出当前仓库的事实性上下文，再约束默认工作方式，避免继续沿用 `coco-ext` 的过时假设。

如本文与代码不一致，以代码为准，并在完成改动后同步更新本文。

## 仓库上下文

- 项目名称：`coco-flow`
- Python 包名：`coco-flow`
- Python 版本：`>=3.13`
- 维护人：Maifeng `<maifeng@bytedance.com>`
- CLI 入口：[`src/coco_flow/cli.py`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/cli.py)
- Web API 入口：[`src/coco_flow/api/app.py`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/api/app.py)
- 技术栈：Python + `uv`、Typer、FastAPI、Vite/React
- 交互语言：默认中文

## 先读什么

处理任务前，优先阅读以下文件，而不是凭记忆推断：

- [`README.md`](/Users/bytedance/Work/tools/bytedance/coco-flow/README.md)
- [`pyproject.toml`](/Users/bytedance/Work/tools/bytedance/coco-flow/pyproject.toml)
- [`src/coco_flow/cli.py`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/cli.py)
- 与当前改动直接相关的 `src/coco_flow/services/`、`src/coco_flow/api/`、`web/src/` 文件

如果发现本文过时，修代码时顺手修正文档，不要把错误上下文继续传给下一个 agent。

## 常用命令

```bash
# 安装依赖
uv sync

# 查看 CLI
uv run coco-flow --help

# 启动本地 API
uv run coco-flow api serve --host 127.0.0.1 --port 4318

# 单命令启动 UI + API
uv run coco-flow ui serve

# 查看任务
uv run coco-flow tasks roots
uv run coco-flow tasks list
uv run coco-flow prd list

# 推进任务
uv run coco-flow tasks refine <task_id>
uv run coco-flow tasks plan <task_id>
uv run coco-flow tasks code <task_id>
uv run coco-flow tasks reset <task_id>
uv run coco-flow tasks archive <task_id>

# 迁移友好的 prd 入口
uv run coco-flow prd refine --prd "需求描述"
uv run coco-flow prd plan --task <task_id>
uv run coco-flow prd code --task <task_id>
uv run coco-flow prd run -i "需求描述"

# daemon
uv run coco-flow daemon start
uv run coco-flow daemon status
uv run coco-flow daemon stop
```

前端调试：

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow/web
npm install
npm run build
```

定向校验：

```bash
uv run python -m py_compile src/coco_flow/engines/refine.py
uv run python -m py_compile src/coco_flow/engines/plan.py
uv run python -m py_compile src/coco_flow/services/tasks/plan.py
uv run python -m py_compile src/coco_flow/services/tasks/code.py
uv run python -m unittest discover -s tests -v
```

## 目录与架构

当前建议按四层理解：CLI / API 层 `src/coco_flow/cli.py`、`src/coco_flow/api/` → workflow 壳 `src/coco_flow/services/tasks/` → 推理引擎 `src/coco_flow/engines/` → 外部依赖与运行时（`clients/`、`daemon/`、`services/runtime/`、git、`lark-cli`）。

关键目录：

- [`src/coco_flow/api/`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/api)：FastAPI app factory 与路由
- [`src/coco_flow/engines/`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/engines)：`refine` / `plan` 的核心推理与编排引擎
- [`src/coco_flow/services/`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/services)：按 `tasks/`、`queries/`、`runtime/` 拆分 workflow 壳、查询拼装与运行时状态逻辑
- [`src/coco_flow/clients/`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/clients)：ACP client 抽象
- [`src/coco_flow/daemon/`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/daemon)：daemon client / server / protocol / paths
- [`src/coco_flow/models/`](/Users/bytedance/Work/tools/bytedance/coco-flow/src/coco_flow/models)：API response model
- [`web/`](/Users/bytedance/Work/tools/bytedance/coco-flow/web)：本地 Web UI

## 核心流程

### task create

- 统一存储在 `~/.config/coco-flow/tasks/`
- `POST /api/tasks` 当前支持三种输入：
  - 纯文本
  - 本地文件路径
  - 飞书文档链接（`/wiki/TOKEN`、`/docx/TOKEN`）
- 创建后默认后台异步启动 `refine`
- CLI 层当前同时保留两套入口：
  - `tasks ...`：底层 task 入口
  - `prd ...`：对齐 `coco-ext` 的迁移入口

### refine

- `refine` 支持 `native` 和 `local`
- `native` 通过 `coco acp serve` 执行 prompt-only refine
- `local` 生成结构化兜底稿
- `refine` 当前已支持业务记忆降级模式：
  - 默认优先读取 repo 下 `.livecoding/context/`
  - 若未找到可用上下文，显式降级为 `source_only`
  - 若只找到部分上下文，标记为 `partial_grounded`
- 飞书文档若暂时拉不到正文，会生成 pending refine 占位稿，状态保持 `initialized`
- `refine.log` 当前会记录：
  - `=== REFINE START === / === REFINE END ===`
  - `task_id / task_dir / executor`
  - `context_mode / business_memory_provider / business_memory_used`
  - `source_type / source_path / source_url / source_doc_token`
  - `source_length`
  - `prompt_start / prompt_ok`
  - `fallback_local_refine` 或 pending 信息

### plan

- `plan` 支持 `native` 和 `local`
- `native` 通过 ACP 的 readonly/explorer 模式生成 `design.md` 和 `plan.md`
- `local` 会基于 refined PRD、本地 context 和代码调研生成本地方案
- 当前 `plan` 已支持多 repo research：
  - 对 task 绑定的每个 repo 分别读取 `.livecoding/context`
  - 分别提取 glossary 命中、未命中术语、candidate files / dirs
  - 在 `design.md`、`plan.md`、prompt 和 `plan.log` 中按 repo 聚合
- `plan.log` 当前会记录：
  - `repo_count`
  - 每个 repo 的 `repo_research`
  - glossary hits / unmatched terms / candidate files / complexity

### code

- `code` 当前统一走后台异步模型
- 单 repo task 可直接推进；多 repo task 支持：
  - `POST /api/tasks/{task_id}/code?repo=<repo_id>`
  - `POST /api/tasks/{task_id}/code-all`
- `native code` 通过 ACP agent 模式在隔离 worktree 内执行
- worktree 根目录：
  - `<repo-parent>/.coco-flow-worktree/`
- 当前已支持：
  - repo 级 `code-result.json` / `code.log` / diff summary / diff patch
  - 最小验证
    - Go：默认按受影响目录执行 `go build ./dir/...`
    - Go：默认不跑 `go test`；如确实需要，可通过 `COCO_FLOW_ENABLE_GO_TEST_VERIFY=1` 显式开启，并且仅在受影响 package 存在 `*_test.go` 时才执行
    - Python：`python3 -m py_compile`
  - 验证失败后 follow-up 重试
  - 自动 commit
- `code.log` 当前会记录：
  - `=== CODE START === / === CODE END ===`
  - `repo_start / repo_attempt / repo_verify_output / repo_verify_failed / repo_verify_ok / repo_done`

### reset / archive / artifact

- `reset` / `archive` 已支持 repo 级操作
- `GET /api/tasks/{task_id}/artifact?name=...&repo=...` 支持读取 task 级或 repo 级 artifact
- 当前 task 级可编辑 artifact：
  - `prd.source.md`
  - `prd-refined.md`
  - `design.md`
  - `plan.md`
- 当前 task 级非编辑 artifact 还包括：
  - `refine-result.json`

### daemon / ACP

- 当前默认不是每次命令都冷启动 `coco acp serve`
- `coco-flow daemon` 使用 Unix socket 驱动本地 daemon，daemon 内维护 ACP session pool
- 当前复用维度主要基于：
  - `cwd`
  - `mode`
  - `query_timeout`
- 默认空闲超时：
  - daemon 进程：`3600` 秒（`1h`）
  - ACP session：`600` 秒（`10m`）
- 可通过环境变量覆盖：
  - `COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS`
  - `COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS`

## 当前 API 入口

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
- `GET /api/tasks/{task_id}/artifact?name=...&repo=...`
- `PUT /api/tasks/{task_id}/artifact?name=...`
- `DELETE /api/tasks/{task_id}`
- `GET /api/repos/recent`
- `POST /api/repos/validate`
- `GET /api/fs/roots`
- `GET /api/fs/list?path=...`

## 关键约定

- task 根目录：`~/.config/coco-flow/tasks/`
- daemon pid：`~/.config/coco-flow/daemon.pid`
- daemon socket：`~/.config/coco-flow/daemon.sock`
- daemon log：`~/.config/coco-flow/daemon.log`
- worktree 根目录：`<repo-parent>/.coco-flow-worktree/`
- 同步到 worktree 的 task 目录：`.coco-flow/tasks/<task_id>/`
- context 目录：`.livecoding/context/`

## 本仓库的默认协作方式

- 优先做最小范围验证。默认不要跑全量测试；优先 `py_compile`、定向 smoke、前端 `npm run build`。
- 修改 API 行为时，同时检查 README / AGENTS / UI 是否需要同步。
- 修改 `refine / plan / code` 时，要额外关注：
  - task 状态流转
  - 后台线程行为
  - 日志格式
  - repo 级 artifact 是否仍可读
- 修改 `task_plan.py` 时，优先保留现有 `coco-ext` 对齐思路，不要退回成单 repo 简化版。
- 修改 `task_code.py` 时，不要破坏：
  - 后台异步模型
  - repo 级结果模型
  - 最小验证 + 重试链路
- 修改 `task_create.py` / `task_refine.py` 时，不要破坏：
  - text / file / lark_doc 三种输入来源
  - pending refine 占位模式

## 迁移目标

这个仓库的目标不是重新发明一套流程，而是尽量平滑承接 `coco-ext` 的 workflow product 层能力。

默认原则：

- **优先对齐外部行为**
  - UI 交互
  - 状态流转
  - 日志格式
  - task / artifact 语义
- **允许底层实现不同**
  - Python
  - FastAPI
  - ACP daemon 实现细节
- **如果必须偏离 `coco-ext`**
  - 先在代码里说明原因
  - 同步更新 README / AGENTS
