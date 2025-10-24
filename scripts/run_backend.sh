#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
VENV_PATH="${BACKEND_DIR}/.venv"

if [ ! -d "${VENV_PATH}" ]; then
    python -m venv "${VENV_PATH}"
fi

# shellcheck source=/dev/null
source "${VENV_PATH}/bin/activate"

pip install --upgrade pip
pip install -r "${BACKEND_DIR}/requirements.txt"

cd "${BACKEND_DIR}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
