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

卸载：

```bash
uv tool uninstall coco-flow
rm -rf ~/.local/share/coco-flow

# 可选：删除本地 task 和 knowledge 数据
rm -rf ~/.config/coco-flow
```

直接使用示例：

```bash
coco-flow --help

coco-flow version
coco-flow install --path .
coco-flow update --path .

coco-flow start
coco-flow start --detach
coco-flow start --api-only
coco-flow status
coco-flow stop

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

coco-flow remote add dev --host 10.37.122.5 --user maifeng
coco-flow remote list
coco-flow remote connect dev
coco-flow remote status
coco-flow remote disconnect dev
```

远程机安装脚本：

```bash
source ./install.sh
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
```

## 远程开发机连接

现在 `coco-flow` 已支持把“远程开发机启动服务，本地电脑通过 SSH 隧道访问”的流程包装成正式 CLI。

常见用法：

```bash
# 先保存一个远程开发机配置
coco-flow remote add dev --host 10.37.122.5 --user maifeng

# 查看已保存的远程配置
coco-flow remote list

# 在本地电脑连接远程开发机
coco-flow remote connect dev

# 查看当前由 coco-flow 管理的隧道状态
coco-flow remote status

# 断开本地隧道
coco-flow remote disconnect dev
```

如果你不想先保存配置，也可以直接按 SSH alias 或 IP 连接：

```bash
coco-flow remote connect dev
coco-flow remote connect 10.37.122.5 --user maifeng
```

`remote connect` 的行为是：

- 尽量复用已经健康的本地隧道
- 先检查远程 `coco-flow` 是否已经可用
- 只有在远程服务不健康时才启动远程 `coco-flow`
- 只有在本地隧道缺失或失效时才重建 SSH 隧道
- 默认自动在本地打开 `http://127.0.0.1:<local-port>`，可用 `--no-open` 关闭

常用选项：

```bash
coco-flow remote connect dev --no-open
coco-flow remote connect dev --restart
coco-flow remote connect dev --reconnect-tunnel
coco-flow remote status dev --json
coco-flow remote disconnect
```

说明：

- 如果你的 `~/.ssh/config` 已经配置了 `User`，通常不需要再显式传 `--user`
- `remote connect` 现在会对比本地 build fingerprint 和远程运行中服务的 fingerprint；如果不一致，会明确提示并建议 `--restart`
- `coco-flow update` 现在会一并重建 bundled Web UI；`coco-flow start` 和 `coco-flow ui serve` 也会在检测到 `web/dist` 过期时自动重建
- `remote disconnect` 目前只会断开本地 SSH 隧道，不会停止远程开发机上的 `coco-flow`
- 已保存的 remote 配置会落在 `~/.config/coco-flow/remote/`

## 工作流行为

### Input

- task 默认存储在 `~/.config/coco-flow/tasks/`
- `POST /api/tasks` 支持三类输入：
  - 纯文本
  - 本地文件路径
  - 飞书文档链接
- 纯文本和本地文件会同步落盘，状态进入 `input_ready`
- 飞书文档链接先进入 `input_processing`，正文拉取完成后异步继续
- Input 现在要求先填写人工提炼范围。Web UI 会预填服务端模板，至少补齐“本次范围”和“人工提炼改动点”后，才允许进入 Refine。
- Input 阶段会生成 `input.json` 和 `input.log`

### Refine

- `refine` 支持 `native` 和 `local`
- 当前 refine 是 `manual-first`：以 Input 阶段的“人工提炼范围”为主输入，收敛成结构化 implementation brief。
- `local` 直接基于规则生成的 brief 渲染文档。
- `native` 现在走 `AGENT_MODE`：controller 先准备 `manual_extract / brief draft / source excerpt`，再由可读写 agent 填充 markdown 模板，并用第二个 agent 做 verify。
- 常见产物包括 `refine-brief.json`、兼容用的 `refine-intent.json`、`prd-refined.md`、`refine-verify.json`、`refine-result.json`

### Design 与 Plan

- `design` 是独立阶段，CLI 和 API 都已暴露
- Design 会在 `design-decision.json` 中记录 repo 级 producer / consumer 依赖，并派生到 `design-repo-binding.json` 的 `depends_on` 与 `design-sections.json` 的 `system_dependencies`
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
- 默认监听 `0.0.0.0:4318`
- 同时提供静态页面和 API；同机访问可直接打开 `http://127.0.0.1:4318`

如果你是在远程开发机上运行 `coco-flow start`，想在本地电脑打开 Web：

- 如果开发机 IP 和端口对你本机可直连，直接打开 `http://<dev-machine-ip>:4318`
- 如果不方便直连，优先用 SSH 端口转发：

```bash
ssh -fN -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 \
  -L 4318:127.0.0.1:4318 \
  <user>@<dev-machine>
```

然后在本地浏览器打开 `http://127.0.0.1:4318`。

常用选项：

```bash
coco-flow start --no-build
coco-flow start --detach
coco-flow start --web-dir /absolute/path/to/dist
coco-flow start --api-only
coco-flow status
coco-flow stop
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
- `GET /api/meta`
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
└── cli/            # Typer 入口与命令模块

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
