#!/bin/sh
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
DATA_DIR="${ONIONDROP_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
  current_gid="$(getent group oniondrop | cut -d: -f3 || true)"
  current_uid="$(id -u oniondrop 2>/dev/null || true)"

  if [ -n "$current_gid" ] && [ "$current_gid" != "$PGID" ]; then
    groupmod -o -g "$PGID" oniondrop
  fi
  if [ -n "$current_uid" ] && [ "$current_uid" != "$PUID" ]; then
    usermod -o -u "$PUID" oniondrop
  fi

  mkdir -p "$DATA_DIR" "$DATA_DIR/services" "$DATA_DIR/inboxes" "$DATA_DIR/logs" "$DATA_DIR/home" "$DATA_DIR/tmp"
  chown -R "$PUID:$PGID" "$DATA_DIR"
  exec gosu "$PUID:$PGID" python -m oniondrop
fi

exec python -m oniondrop
