#!/usr/bin/env bash
#
# Helper script to run OT_online (pot.by) behind CWP via Gunicorn.
# Mirrors the production layout already used by proverka.by.

set -euo pipefail

APP_DIR="/home/django/webapps/potby"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="$APP_DIR/logs"
RUN_DIR="$APP_DIR/run"
ENV_FILE="$APP_DIR/.env"

mkdir -p "$LOG_DIR" "$RUN_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # export all variables from .env for gunicorn (SECRET_KEY, DB, etc.)
  # shellcheck disable=SC2046
  set -a
  source "$ENV_FILE"
  set +a
fi

export DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-settings_prod}

exec "$VENV_DIR/bin/gunicorn" \
  --name potby \
  --workers "${GUNICORN_WORKERS:-4}" \
  --bind "${GUNICORN_BIND:-127.0.0.1:8020}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --log-level "${GUNICORN_LOG_LEVEL:-info}" \
  --access-logfile "$LOG_DIR/gunicorn.access.log" \
  --error-logfile "$LOG_DIR/gunicorn.error.log" \
  --pid "$RUN_DIR/gunicorn.pid" \
  wsgi:application
