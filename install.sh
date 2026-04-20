#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_URL="${COCO_FLOW_REPO_URL:-https://github.com/DreamCats/coco-flow.git}"
REPO_REF="${COCO_FLOW_REPO_REF:-main}"
INSTALL_DIR="${COCO_FLOW_INSTALL_DIR:-$HOME/.local/share/coco-flow}"
WITH_UI=1
LOCAL_EXECUTORS=0
SOURCE_MODE=0
HAD_ERREXIT=0
HAD_NOUNSET=0
HAD_PIPEFAIL=0

if (return 0 2>/dev/null); then
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

project_root_from_repo_script() {
  if [[ -f "$ROOT_DIR/pyproject.toml" && -f "$ROOT_DIR/src/coco_flow/cli.py" ]]; then
    printf '%s\n' "$ROOT_DIR"
    return 0
  fi
  return 1
}

ensure_repo_checkout() {
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required for curl-based installation" >&2
    return 1
  fi

  mkdir -p "$(dirname "$INSTALL_DIR")"

  if [[ ! -d "$INSTALL_DIR/.git" ]]; then
    git clone --branch "$REPO_REF" "$REPO_URL" "$INSTALL_DIR"
    printf '%s\n' "$INSTALL_DIR"
    return 0
  fi

  git -C "$INSTALL_DIR" fetch origin "$REPO_REF"
  git -C "$INSTALL_DIR" checkout "$REPO_REF"
  git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_REF"
  printf '%s\n' "$INSTALL_DIR"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-ui)
      WITH_UI=0
      shift
      ;;
    --local-executors)
      LOCAL_EXECUTORS=1
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage:
  ./install.sh [--no-ui] [--local-executors]
  source ./install.sh [--no-ui] [--local-executors]
  curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash
  curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash -s -- --no-ui

Options:
  --no-ui             Skip web dependencies under web/
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

PROJECT_ROOT="$(project_root_from_repo_script || true)"
if [[ -z "$PROJECT_ROOT" ]]; then
  PROJECT_ROOT="$(ensure_repo_checkout)" || {
    if [[ "$SOURCE_MODE" -eq 1 ]]; then
      restore_shell_opts
      return 1
    fi
    exit 1
  }
fi

cd "$PROJECT_ROOT"

uv python install 3.13
uv tool install --force --python 3.13 --editable "$PROJECT_ROOT"
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
echo "repo: $PROJECT_ROOT"
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
