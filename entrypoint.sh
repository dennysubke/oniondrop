#!/bin/sh
set -eu
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
DATA_DIR="${ONIONDROP_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
  groupmod -o -g "$PGID" oniondrop 2>/dev/null || true
  usermod -o -u "$PUID" -g "$PGID" oniondrop 2>/dev/null || true
  mkdir -p "$DATA_DIR" "$DATA_DIR/home"
  chown -R "$PUID:$PGID" "$DATA_DIR"
  exec gosu "$PUID:$PGID" python -m oniondrop
fi

exec python -m oniondrop
