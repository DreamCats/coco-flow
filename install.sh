#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WITH_UI=0
LOCAL_EXECUTORS=0
SOURCE_MODE=0
HAD_ERREXIT=0
HAD_NOUNSET=0
HAD_PIPEFAIL=0

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  SOURCE_MODE=1
fi

case $- in
  *e*) HAD_ERREXIT=1 ;;
esac
case $- in
  *u*) HAD_NOUNSET=1 ;;
esac
if set -o | grep -q '^pipefail[[:space:]]*on$'; then
  HAD_PIPEFAIL=1
fi

set -euo pipefail

restore_shell_opts() {
  if [[ "$HAD_ERREXIT" -eq 0 ]]; then
    set +e
  fi
  if [[ "$HAD_NOUNSET" -eq 0 ]]; then
    set +u
  fi
  if [[ "$HAD_PIPEFAIL" -eq 0 ]]; then
    set +o pipefail
  fi
}

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
Usage:
  ./install.sh [--with-ui] [--local-executors]
  source ./install.sh [--with-ui] [--local-executors]

Options:
  --with-ui           Install web dependencies under web/
  --local-executors   Print local executor exports after install
EOF
      if [[ "$SOURCE_MODE" -eq 1 ]]; then
        restore_shell_opts
        return 0
      fi
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      if [[ "$SOURCE_MODE" -eq 1 ]]; then
        restore_shell_opts
        return 1
      fi
      exit 1
      ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

export PATH="$HOME/.local/bin:$PATH"

cd "$ROOT_DIR"

uv python install 3.13
uv tool install --force --python 3.13 --editable "$ROOT_DIR"
uv tool update-shell >/dev/null 2>&1 || true

if [[ "$WITH_UI" -eq 1 ]]; then
  (
    cd web
    npm install
  )
fi

TOOL_BIN_DIR="$(uv tool dir --bin)"
if [[ -n "$TOOL_BIN_DIR" ]]; then
  export PATH="$TOOL_BIN_DIR:$PATH"
fi

"$TOOL_BIN_DIR/coco-flow" version

echo
echo "ready: coco-flow start"

if [[ "$LOCAL_EXECUTORS" -eq 1 ]]; then
  cat <<'EOF'

If this machine does not have coco ready yet, export:
export COCO_FLOW_KNOWLEDGE_EXECUTOR=local
export COCO_FLOW_REFINE_EXECUTOR=local
export COCO_FLOW_PLAN_EXECUTOR=local
export COCO_FLOW_CODE_EXECUTOR=local
EOF
fi

if [[ "$SOURCE_MODE" -eq 1 ]]; then
  restore_shell_opts
  return 0
fi
