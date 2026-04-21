# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`coco-flow` is a local workflow product for PRD-driven task orchestration. It wraps a local `coco` binary (an ACP-compatible agent) through a daemon process, exposing it via Typer CLI, FastAPI REST API, and a Vite/React web UI. The default interaction language is Chinese.

## Build & Run

```bash
# Install (editable, uses uv tool install)
source ./install.sh

# Verify
coco-flow version

# Start the full stack (builds web, starts FastAPI on 0.0.0.0:4318)
coco-flow start

# Start in background
coco-flow start --detach

# API only (no web build)
coco-flow start --api-only

# Status / stop
coco-flow status
coco-flow stop
```

### Verification & Tests

```bash
# Compile-check individual modules
uv run python -m py_compile src/coco_flow/engines/refine/__init__.py

# Run all tests
uv run python -m unittest discover -s tests -v

# Run a single test file
uv run python -m unittest tests/test_task_plan.py -v
```

### Frontend

```bash
cd web
npm install
npm run build    # tsc -b && vite build
npm run dev      # vite dev server on :5173
npm run lint     # eslint
```

## Architecture

### Task Flow Pipeline

Tasks progress through stages: **Input → Refine → Design → Plan → Code**. Each stage has an engine in `src/coco_flow/engines/` and a service shell in `src/coco_flow/services/tasks/`. The engine handles the core logic; the service shell handles status transitions and orchestration.

- **Input** (`engines/input/`): Accepts plain text, local files, or Lark doc links. Writes `input.json`, `source.json`, `task.json`, and `prd.source.md`.
- **Refine** (`engines/refine/`): Extracts intent, selects knowledge, generates refined PRD. Writes `prd-refined.md` and intermediate artifacts.
- **Design** (`engines/design/`): Produces `design.md` with change points and responsibility matrix.
- **Plan** (`engines/plan/`): Generates `plan.md` with execution batches and work items per repo.
- **Code** (`engines/code/`): Runs repo batches in isolated git worktrees. Verifies with `go build` or `python3 -m py_compile`. Writes per-repo results under `code-results/`.

### Layer Separation

```
cli.py          → Typer CLI commands (start, tasks, daemon, knowledge)
api/app.py      → FastAPI routes, calls service layer
services/tasks/ → Orchestration: status checks, background thread launch, error handling
engines/        → Pure pipeline logic for each stage (no HTTP or CLI awareness)
prompts/        → Prompt templates for each engine stage
clients/        → ACP client abstraction over the `coco` binary
daemon/         → Unix socket daemon that manages pooled ACP sessions
models/         → Pydantic models for API requests/responses
```

### ACP Client & Daemon

The `coco` binary speaks ACP (Agent Communication Protocol) over JSON-RPC on stdin/stdout. The daemon (`daemon/server.py`) is a Unix socket server that manages a pool of long-lived ACP sessions (`clients/acp_client.py`). Each session key is `(coco_bin, cwd, mode, query_timeout)`. Three modes exist:

- `prompt_only`: text generation only, all tool use disabled
- `explorer`: read-only agent (no Edit/Write/Replace)
- `agent`: full agent with all tools

### Executor Modes

Each engine stage supports `native` (uses `coco` via ACP) or `local` (built-in fallback). Controlled by env vars like `COCO_FLOW_REFINE_EXECUTOR`, `COCO_FLOW_PLAN_EXECUTOR`, `COCO_FLOW_CODE_EXECUTOR`.

### Data Storage

All task data lives under `~/.config/coco-flow/` by default (configurable via `COCO_FLOW_CONFIG_DIR`):
- `tasks/<task_id>/` — per-task directory with JSON metadata and markdown artifacts
- `knowledge/` — knowledge documents used during refine/plan
- Task metadata is file-based (`task.json`, `repos.json`, `source.json`) — no database.

### Background Execution

API handlers return `202` immediately and launch background threads (`services/tasks/background.py`) that log to per-stage `.log` files in the task directory.

## Key Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `COCO_FLOW_CONFIG_DIR` | `~/.config/coco-flow` | Root config/data directory |
| `COCO_FLOW_COCO_BIN` | `coco` | Path to the coco binary |
| `COCO_FLOW_REFINE_EXECUTOR` | `native` | `native` or `local` |
| `COCO_FLOW_PLAN_EXECUTOR` | `native` | `native` or `local` |
| `COCO_FLOW_CODE_EXECUTOR` | `native` | `native` or `local` |
| `COCO_FLOW_ACP_IDLE_TIMEOUT_SECONDS` | `600` | ACP session idle timeout |
| `COCO_FLOW_DAEMON_IDLE_TIMEOUT_SECONDS` | `3600` | Daemon auto-shutdown timeout |
| `COCO_FLOW_ENABLE_GO_TEST_VERIFY` | unset | Set `1` to enable `go test` during code verification |

## Code Style Notes

- Python 3.13+, uses `from __future__ import annotations` consistently
- Pydantic models for all API schema; dataclasses for internal config (`Settings`)
- No type stubs or mypy config — `py_compile` is the primary static check
- Web UI uses React 19, TanStack Router, Tailwind 4, Vite 8
