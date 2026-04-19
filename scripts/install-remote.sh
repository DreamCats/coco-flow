#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WITH_UI=0
LOCAL_EXECUTORS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-ui)
      WITH_UI=1
      shift
      ;;
    --local-executors)
      LOCAL_EXECUTORS=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/install-remote.sh [--with-ui] [--local-executors]

  --with-ui           Install web dependencies under web/
  --local-executors   Print local executor exports after install
EOF
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

cd "$ROOT_DIR"

uv python install 3.13
uv sync

if [[ "$WITH_UI" -eq 1 ]]; then
  (
    cd web
    npm install
  )
fi

uv run coco-flow version

if [[ "$LOCAL_EXECUTORS" -eq 1 ]]; then
  cat <<'EOF'

Add these exports if the remote machine does not have coco ready yet:
export COCO_FLOW_KNOWLEDGE_EXECUTOR=local
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
EOF
fi
