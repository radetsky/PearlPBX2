#!/bin/bash
set -euo pipefail

INSTALL_DIR="/usr/local/PearlPBX2"
ENV_FILE="${INSTALL_DIR}/.env"
PYTHON="${INSTALL_DIR}/.venv/bin/python3"

if [ ! -f "${ENV_FILE}" ]; then
    echo "Error: env file not found: ${ENV_FILE}" >&2
    exit 1
fi

cd "${INSTALL_DIR}"

set -a
# shellcheck source=/dev/null
source "${ENV_FILE}"
set +a

exec "${PYTHON}" manage.py "$@"
