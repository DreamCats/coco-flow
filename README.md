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

Install once, then use `coco-flow` directly:

```bash
source ./install.sh
coco-flow version
coco-flow start
```

You can also install in one command:

```bash
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash -s -- --no-ui
```

If you do not use `source`, reopen the shell or export the tool bin directory shown by the script before using `coco-flow`.

Uninstall:

```bash
uv tool uninstall coco-flow
rm -rf ~/.local/share/coco-flow

# optional: remove local task and knowledge data
rm -rf ~/.config/coco-flow
```

Direct command examples:

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

Remote install script:

```bash
source ./install.sh
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
```

## Workflow Behavior

### Input

- Tasks are stored under `~/.config/coco-flow/tasks/`.
- `POST /api/tasks` accepts plain text, local file paths, and Lark doc links.
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
source ./install.sh
coco-flow start
```

This command will:

- build `web/`
- start the FastAPI app
- bind on `0.0.0.0:4318`
- serve static assets and API together; on the same machine you can open `http://127.0.0.1:4318`

If you run `coco-flow start` on a remote development machine and want to open the Web UI from your local computer:

- if the machine IP and port are directly reachable, open `http://<dev-machine-ip>:4318`
- otherwise, use SSH port forwarding:

```bash
ssh -L 4318:127.0.0.1:4318 <user>@<dev-machine>
```

Then open `http://127.0.0.1:4318` in your local browser.

Useful options:

```bash
coco-flow start --no-build
coco-flow start --web-dir /absolute/path/to/dist
coco-flow start --api-only
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
