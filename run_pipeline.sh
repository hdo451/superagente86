#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"
ENV_FILE="${PROJECT_DIR}/.env"

export PATH="/usr/local/bin:/usr/bin:/bin"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at ${VENV_PYTHON}" >&2
    exit 1
fi

if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
fi

exec "$VENV_PYTHON" -m superagente86.cli \
    --config "${PROJECT_DIR}/config.yaml" \
    --state-file "${PROJECT_DIR}/data/state.json"
