#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/prepare-volumes.sh"

cd "${ROOT_DIR}"

docker compose up --build "$@"
