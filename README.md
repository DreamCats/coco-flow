# coco-flow

中文说明见：[README.zh-CN.md](README.zh-CN.md)

`coco-flow` is a local workflow product for PRD-driven task orchestration. It combines a Typer CLI, a FastAPI service, a local Web UI, and worktree-based code execution around one task model.

## At A Glance

- Product: `coco-flow`
- Package: `coco-flow`
- Python: `>=3.13`
- Stack: Python, `uv`, Typer, FastAPI, Vite/React
- Default interaction language: Chinese

Current task flow:

```text
Input -> Refine -> Design -> Plan -> Code
```

## Quickstart

```bash
uv sync
uv run coco-flow --help
```

Common CLI commands:

```bash
uv run coco-flow tasks roots
uv run coco-flow tasks list
uv run coco-flow knowledge list
uv run coco-flow prd list

uv run coco-flow prd refine --prd "需求描述"
uv run coco-flow prd design --task <task_id>
uv run coco-flow prd plan --task <task_id>
uv run coco-flow prd code --task <task_id>
uv run coco-flow prd run -i "需求描述"

uv run coco-flow api serve --host 127.0.0.1 --port 4318
uv run coco-flow ui serve

uv run coco-flow daemon start
uv run coco-flow daemon status
uv run coco-flow daemon stop
```

## Workflow Behavior

### Input

- Tasks are stored under `~/.config/coco-flow/tasks/`.
- `POST /api/tasks` and `prd refine --prd ...` accept plain text, local file paths, and Lark doc links.
- Plain text and local files are stored immediately and enter `input_ready`.
- Lark doc links enter `input_processing`, then finish asynchronously after the document body is fetched.
- The Input stage writes `input.json` and `input.log`.

### Refine

- `refine` supports `native` and `local`.
- `native refine` runs a staged flow around intent extraction, knowledge selection, knowledge brief generation, draft generation, and verification.
- `local refine` produces a structured fallback draft.
- Typical artifacts include `prd-refined.md`, `refine-intent.json`, `refine-knowledge-selection.json`, `refine-knowledge-brief.md`, `refine-verify.json`, and `refine-result.json`.

### Design And Plan

- `design` is a standalone stage exposed in both CLI and API.
- `plan` supports `native` and `local`.
- `native plan` runs staged scope extraction, generation, and verification.
- Typical artifacts include `design.md`, `plan.md`, `plan-scope.json`, `plan-execution.json`, `plan-verify.json`, `plan-knowledge-selection.json`, and `plan-knowledge-brief.md`.

### Code

- `code` runs asynchronously.
- Single-repo tasks can be advanced directly; multi-repo tasks support `code?repo=...` and `code-all`.
- `native code` runs repo batches in isolated worktrees and writes task-level and repo-level result artifacts.
- Minimal verification is built in:
  - Go: `go build` on affected directories by default
  - Go tests: opt in with `COCO_FLOW_ENABLE_GO_TEST_VERIFY=1`
  - Python: `python3 -m py_compile`

## Web UI

The Web UI lives in [`web/`](web/).

The simplest local startup flow is:

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow
uv sync
uv run coco-flow ui serve
```

This command will:

- build `web/`
- start the FastAPI app
- serve static assets and API together on `http://127.0.0.1:4318`

Useful options:

```bash
uv run coco-flow ui serve --no-build
uv run coco-flow ui serve --web-dir /absolute/path/to/dist
```

Current UI capabilities:

- create tasks
- run `refine`, `design`, `plan`, and `code`
- browse and edit knowledge documents
- edit `prd.source.md`, `prd-refined.md`, `design.md`, and `plan.md`
- reset, archive, and inspect task artifacts

## Execution Modes

Executors:

- `native`: default, backed by local `coco` and ACP
- `local`: built-in fallback implementation

Common environment variables:

```bash
export COCO_FLOW_COCO_BIN=/path/to/coco
export COCO_FLOW_KNOWLEDGE_EXECUTOR=local
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
export COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS=86400
export COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS=86400
```

Default idle timeouts:

- daemon: `3600` seconds
- ACP session: `600` seconds

## API

Current endpoints:

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

## Project Layout

```text
src/coco_flow/
├── api/            # FastAPI app factory and routes
├── clients/        # ACP client abstraction
├── daemon/         # Local daemon and session management
├── engines/        # Input / Refine / Design / Plan / Code engines
├── models/         # Shared response models
├── services/       # Workflow shells, queries, runtime helpers
└── cli.py          # Typer entrypoint

web/
├── src/App.tsx
├── src/api.ts
└── src/index.css
```

## Verification

Targeted checks:

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

Frontend build:

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow/web
npm install
npm run build
```

## Deep Dives

- [`docs/refine-v2-design.md`](docs/refine-v2-design.md)
- [`docs/design-v2-design.md`](docs/design-v2-design.md)
- [`docs/plan-engine.md`](docs/plan-engine.md)
- [`docs/code-v2-design.md`](docs/code-v2-design.md)
