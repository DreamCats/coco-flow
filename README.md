# coco-flow

`coco-flow` is a standalone workflow product for PRD task orchestration, worktree-based code execution,
and the local Web UI / API surface.

Current technical stance:

- product name: `coco-flow`
- stack: Python + `uv`
- runtime shape: Typer CLI + FastAPI local service

## First Version Scope

The first version focuses on a minimal but usable scaffold:

- `coco-flow tasks list` to inspect task summaries
- `coco-flow tasks roots` to inspect the active task root
- `coco-flow tasks refine <task_id>` to generate `prd-refined.md` or a pending refine placeholder for incomplete Lark sources
- `coco-flow tasks plan <task_id>` to generate `design.md` and `plan.md`
- `coco-flow tasks code <task_id>` to run the code stage
- `coco-flow tasks reset <task_id>` to roll the task back to planned state
- `coco-flow tasks archive <task_id>` to archive coded tasks
- `coco-flow api serve` to run a local FastAPI service
- `POST /api/tasks` to create initialized tasks from text, local files, or Lark docs in the new `coco-flow` task root
- `POST /api/tasks/{task_id}/refine` to move initialized tasks into refined state
- `POST /api/tasks/{task_id}/plan` to move refined tasks into planned state
- `POST /api/tasks/{task_id}/code` to start the code stage asynchronously
- `POST /api/tasks/{task_id}/code-all` to batch-run remaining repos asynchronously
- `POST /api/tasks/{task_id}/reset` to roll back code-stage state
- `POST /api/tasks/{task_id}/archive` to archive coded tasks
- `PUT /api/tasks/{task_id}/artifact?name=...` to edit task-level Markdown artifacts
- `GET /api/tasks/{task_id}/artifact?name=diff.patch&repo=...` / `diff.json` to inspect repo-level diff artifacts
All task data lives under `~/.config/coco-flow/tasks` by default.

## Quickstart

```bash
uv sync
uv run coco-flow --help
uv run coco-flow tasks roots
uv run coco-flow tasks list
uv run coco-flow tasks refine <task_id>
uv run coco-flow tasks plan <task_id>
uv run coco-flow tasks code <task_id>
uv run coco-flow tasks reset <task_id>
uv run coco-flow tasks archive <task_id>
uv run coco-flow api serve --host 127.0.0.1 --port 4318
uv run coco-flow ui serve
```

## Web UI

The Web UI lives in [`web/`](</Users/bytedance/Work/tools/bytedance/coco-flow/web>).

The simplest way to test locally is now:

```bash
cd /Users/bytedance/Work/tools/bytedance/coco-flow
uv sync
uv run coco-flow ui serve
```

This command will:

- build the front-end from `web/`
- start the FastAPI server
- serve the built static assets together with the API on `http://127.0.0.1:4318`

```bash
# optional: serve an already-built UI without rebuilding
uv run coco-flow ui serve --no-build

# optional: point to a custom static directory
uv run coco-flow ui serve --web-dir /absolute/path/to/dist
```

Current UI actions:

- create task
- run refine
- run plan
- run code stage asynchronously
- edit `prd.source.md` / `prd-refined.md` / `design.md` / `plan.md`
- reset task
- archive task

## Execution Modes

`coco-flow` currently supports two execution modes:

- `native` (default): call local `coco` directly from `coco-flow`
- `local`: use `coco-flow`'s local fallback implementations

Switch with environment variables:

```bash
export COCO_FLOW_COCO_BIN=/path/to/coco
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
```

Behavior notes:

- `refine` / `plan`: default to native; if native execution fails, `coco-flow` falls back to local template generation
- `refine` accepts plain text, local file paths, and Lark doc links; when a Lark doc cannot be fetched yet, it creates a pending refine placeholder instead of failing task creation
- `code`: supports `native` and `local`
- `code=native` runs through `coco acp serve`, verifies the changed scope, retries once or twice on build failures, and records commit/code-result artifacts back into the task

## API

Current endpoints:

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

## Project Layout

```text
src/coco_flow/
├── api/            # FastAPI app factory
├── models/         # Shared response models
├── services/       # Task store and filesystem access
├── cli.py          # Typer entrypoint
└── config.py       # Config and compatibility roots

web/
├── src/App.tsx     # Local workflow workbench
├── src/api.ts      # Browser API client
└── src/index.css   # First-pass UI styling
```

## Next Steps

- continue aligning `plan` AI candidate-file normalization and repo grouping details with `coco-ext`
- harden the pending Lark refine flow and surface clearer recovery guidance in the UI
- expand automated tests for background task execution and multi-repo flows
