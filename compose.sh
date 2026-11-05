#!/usr/bin/env bash
# WSL 下 usermod 后旧终端无 docker 组时，用 sg 包装 docker compose
set -euo pipefail
cd "$(dirname "$0")"
if docker info >/dev/null 2>&1; then
  exec docker compose "$@"
fi
if getent group docker >/dev/null 2>&1 && id -nG "$USER" | grep -qw docker || getent group docker | grep -q "$USER"; then
  exec sg docker -c "docker compose $(printf '%q ' "$@")"
fi
echo "无法连接 Docker。请执行: newgrp docker  或  wsl --shutdown 后重开终端" >&2
exit 1
