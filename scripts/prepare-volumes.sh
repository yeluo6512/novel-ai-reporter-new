#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ROOT_DIR}/data"
CONFIG_DIR="${ROOT_DIR}/config"

mkdir -p "${DATA_DIR}"
mkdir -p "${CONFIG_DIR}"

chmod 775 "${DATA_DIR}"
chmod 775 "${CONFIG_DIR}"

cat <<'EOF'
✅ Volume directories prepared.

Host paths:
  - data   -> ./data
  - config -> ./config

If you need to adjust the ownership for a different UID/GID inside the
container, run a command such as:

  sudo chown -R <uid>:<gid> data config

The container defaults to UID/GID 1000. Update docker-compose.yml or rebuild
with custom build arguments if your environment requires different values.
EOF
