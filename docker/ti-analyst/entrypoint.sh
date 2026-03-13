#!/bin/sh
set -eu

if [ "${MIGRATE_ON_START:-1}" = "1" ]; then
  echo "[ti-analyst] Running startup migrations (best effort)..."
  if ! alembic upgrade head; then
    echo "[ti-analyst] Startup migrations failed; continuing container startup."
  fi
fi

# Start the Telegram bot as a separate background process.
# This keeps the bot alive across uvicorn hot-reloads.
BOT_PID=""
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  python3 -m app.services.telegram_bot_runner &
  BOT_PID=$!
  echo "[ti-analyst] Telegram bot started (PID $BOT_PID)"
fi

# Forward SIGTERM to both uvicorn and the bot runner so the bot can close its
# Telegram session gracefully — preventing 409 Conflict on next startup.
_shutdown() {
  echo "[ti-analyst] Shutting down (uvicorn=$UVICORN_PID bot=${BOT_PID:-none})"
  kill -TERM "$UVICORN_PID" 2>/dev/null || true
  if [ -n "$BOT_PID" ]; then
    kill -TERM "$BOT_PID" 2>/dev/null || true
    wait "$BOT_PID" 2>/dev/null || true
  fi
  wait "$UVICORN_PID" 2>/dev/null || true
  exit 0
}
trap _shutdown TERM INT

# Run uvicorn as a child (not exec) so the shell stays as PID 1 and the trap fires.
"$@" &
UVICORN_PID=$!
wait $UVICORN_PID
