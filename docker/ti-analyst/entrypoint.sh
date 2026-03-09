#!/bin/sh
set -eu

if [ "${MIGRATE_ON_START:-1}" = "1" ]; then
  echo "[ti-analyst] Running startup migrations (best effort)..."
  if ! alembic upgrade head; then
    echo "[ti-analyst] Startup migrations failed; continuing container startup."
  fi
fi

exec "$@"
