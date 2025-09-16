#!/bin/sh
set -e

is_true () {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

PORT="${PORT:-8001}"
export PYTHONPATH=/srv

# Embedding service now uses the new embedding system
echo "[emb] Starting embedding service at :${PORT}"
echo "[emb] Using new embedding system with model registry and MinIO caching"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" --app-dir /srv
