#!/bin/bash
set -euo pipefail

if [ "$(id -un)" != "asterisk" ]; then
    exec sudo -u asterisk "$0" "$@"
fi

INSTALL_DIR="/usr/local/PearlPBX2"
ENV_FILE="/etc/PearlPBX/PearlPBX2/env"
PYTHON="${INSTALL_DIR}/.venv/bin/python3"

if [ ! -f "${ENV_FILE}" ]; then
    echo "Error: env file not found: ${ENV_FILE}" >&2
    exit 1
fi

cd "${INSTALL_DIR}"

while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    printf -v "$key" '%s' "$value"
    export "$key"
done < "${ENV_FILE}"

exec "${PYTHON}" manage.py "$@"
