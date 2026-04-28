# coco-flow

中文说明见：[README.zh-CN.md](README.zh-CN.md)

`coco-flow` is a local workflow product for PRD-driven task orchestration. It combines a Typer CLI, a FastAPI service, a local Web UI, and worktree-based code execution around one task model.

## At A Glance

- Product: `coco-flow`
- Package: `coco-flow`
- Python: `>=3.13`
- Stack: Python, `uv`, Typer, FastAPI, Vite/React, Chrome Extension
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

# optional: remove local task and skills data
rm -rf ~/.config/coco-flow
```

Direct command examples:

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
coco-flow tasks refine <task_id>
coco-flow tasks design <task_id>
coco-flow tasks plan <task_id>
coco-flow tasks code <task_id>
coco-flow tasks reset <task_id>
coco-flow tasks archive <task_id>

coco-flow daemon start
coco-flow daemon status
coco-flow daemon stop

coco-flow gateway start
coco-flow gateway start -d
coco-flow gateway status --json
coco-flow gateway stop

coco-flow remote add dev --host 10.37.122.5 --user maifeng
coco-flow remote list
coco-flow remote connect dev
coco-flow remote status
coco-flow remote disconnect dev
```

Remote install script:

```bash
source ./install.sh
curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
```

## Remote Development Machines

`coco-flow` can now manage the common “run on a remote development machine, open from the local laptop” flow over SSH.

Typical usage:

```bash
# save a remote once
coco-flow remote add dev --host 10.37.122.5 --user maifeng

# inspect saved remotes
coco-flow remote list

# connect from the local laptop
coco-flow remote connect dev

# inspect managed tunnels
coco-flow remote status

# disconnect the local tunnel
coco-flow remote disconnect dev
```

You can also connect directly by SSH alias or IP without saving a profile first:

```bash
coco-flow remote connect dev
coco-flow remote connect 10.37.122.5 --user maifeng
```

What `remote connect` does:

- reuse an existing healthy local tunnel when possible
- check whether the remote `coco-flow` service is already healthy
- start remote `coco-flow` only when needed
- create or recreate the local SSH tunnel only when needed
- open `http://127.0.0.1:<local-port>` locally unless `--no-open` is set

Useful options:

```bash
coco-flow remote connect dev --no-open
coco-flow remote connect dev --restart
coco-flow remote connect dev --reconnect-tunnel
coco-flow remote status dev --json
coco-flow remote disconnect
```

Notes:

- if your SSH config already defines `User`, you usually do not need `--user`
- `remote connect` uses non-interactive SSH in managed flows; if the target still needs password, passphrase, host-key confirmation, or Kerberos, first run `ssh <target>` in a terminal to finish that step, then retry
- if your remote host relies on Kerberos/GSSAPI (common for internal aliases such as `sgdev`), first run `kinit <mail-prefix>@BYTEDANCE.COM` in a terminal, then retry `remote connect`
- `remote connect` now compares the local build fingerprint with the running remote service; if they differ, it will print a warning and suggest `--restart`
- after `coco-flow update`, the remote installation also rebuilds the bundled Web UI; `coco-flow start` and `coco-flow ui serve` will additionally rebuild when `web/dist` is stale
- `remote disconnect` currently stops the local tunnel only; it does not stop the remote `coco-flow` service
- saved remote profiles live under `~/.config/coco-flow/remote/`

## Workflow Behavior

### Input

- Tasks are stored under `~/.config/coco-flow/tasks/`.
- `POST /api/tasks` accepts plain text, local file paths, and Lark doc links.
- Plain text and local files are stored immediately and enter `input_ready`.
- Lark doc links enter `input_processing`, then finish asynchronously after the document body is fetched.
- Input now requires a filled manual extract block before downstream stages. The Web UI pre-fills a server-oriented template under `人工提炼范围`, and `refine` is blocked until at least `本次范围` and `人工提炼改动点` are filled.
- The Input stage writes `input.json` and `input.log`.

### Refine

- `refine` supports `native` and `local`.
- The current refine engine is `manual-first`: it treats the Input-stage `人工提炼范围` as the primary source of truth and writes `prd-refined.md`.
- `local` renders the markdown directly.
- `native` uses temporary generation inputs and writes only the markdown template result.
- Refine no longer persists stage schema artifacts such as brief, intent, verify, diagnosis, or result JSON.
- Refine verification now classifies common failures and runs a bounded local repair loop for low-risk markdown issues such as missing sections, template placeholders, and acceptance criteria mixed with boundary text.
- If the required manual extract fields are missing, refine writes a `needs_human` diagnosis and stops before generation.

### Design And Plan

- `design` is a standalone stage exposed in both CLI and API.
- Design now follows a doc-only MVP flow: refined PRD, repo research, and Skills/SOP are collapsed directly into `design.md`.
- Design no longer persists adjudication, review, debate, decision, repo-binding, sections, verify, diagnosis, or result JSON.
- `plan` supports `native` and `local`.
- Plan writes a human-readable `plan.md` plus Code-consumable sidecars: `plan-work-items.json`, `plan-execution-graph.json`, `plan-validation.json`, `plan-sync.json`, and `plan-result.json`.
- Plan also writes per-repo task files under `plan-repos/<repo_id>.md` for multi-repo review.
- Editing `plan.md` or `plan-repos/<repo_id>.md` marks `plan-sync.json` as unsynced; use Sync Plan before Code so structured artifacts match the reviewed Markdown without overwriting the Markdown.
- If Plan detects unresolved blockers, `plan-result.json` sets `code_allowed=false` so Code cannot proceed until the blocker is resolved.

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
ssh -fN -o ExitOnForwardFailure=yes -o ServerAliveInterval=60 \
  -L 4318:127.0.0.1:4318 \
  <user>@<dev-machine>
```

Then open `http://127.0.0.1:4318` in your local browser.

Useful options:

```bash
coco-flow start --no-build
coco-flow start --detach
coco-flow start --web-dir /absolute/path/to/dist
coco-flow start --api-only
coco-flow status
coco-flow stop
```

Current UI capabilities:

- create tasks
- run `refine`, `design`, `plan`, and `code`
- manage skills sources, clone/pull Git-backed skills repositories, and browse skills packages read-only
- edit `prd.source.md`, `prd-refined.md`, `design.md`, and `plan.md`
- reset, archive, and inspect task artifacts

## Chrome Extension Gateway MVP

The lightweight browser entrypoint lives in [`extension/chrome/`](extension/chrome/).

Current shape:

- a local `coco-flow gateway` process serves HTTP on `127.0.0.1:4319`
- the Chrome extension popup talks to the gateway over HTTP
- `Local` and `Remote` entry actions are available in the popup
- remote profile management lives in the extension options page
- remote auth is still terminal-driven; if SSH asks for password, passphrase, host-key confirmation, or `kinit`, do that in a terminal first and then retry from the popup

Run the gateway locally:

```bash
coco-flow gateway start -d
coco-flow gateway status --json
coco-flow gateway stop
```

Load the extension in Chrome:

1. Open `chrome://extensions`
2. Enable `Developer mode`
3. Click `Load unpacked`
4. Select `/Users/bytedance/Work/tools/bytedance/coco-flow/extension/chrome`

Current constraints:

- the extension assumes the local gateway is already running
- it does not execute shell commands by itself
- action progress currently uses operation polling from the gateway

## Execution Modes

Executors:

- `native`: default, backed by local `coco` and ACP
- `local`: built-in fallback implementation

Common environment variables:

```bash
export COCO_FLOW_COCO_BIN=/path/to/coco
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
- `GET /api/meta`
- `GET /api/workspace`
- `GET /api/skills/sources`
- `POST /api/skills/sources`
- `DELETE /api/skills/sources/{source_id}`
- `POST /api/skills/sources/{source_id}/clone`
- `POST /api/skills/sources/{source_id}/pull`
- `GET /api/skills/tree?source=...`
- `GET /api/skills/file?source=...&path=...`
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
└── cli/            # Typer entrypoint and command modules

web/
├── src/App.tsx
├── src/api.ts
└── src/index.css
```

## Verification

Targeted checks:

```bash
uv run python -m py_compile src/coco_flow/engines/refine/__init__.py
uv run python -m py_compile src/coco_flow/engines/plan/__init__.py
uv run python -m py_compile src/coco_flow/engines/plan/source.py
uv run python -m py_compile src/coco_flow/engines/plan/task_outline.py
uv run python -m py_compile src/coco_flow/engines/shared/models.py
uv run python -m py_compile src/coco_flow/engines/plan_skills.py
uv run python -m py_compile src/coco_flow/engines/shared/research.py
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
