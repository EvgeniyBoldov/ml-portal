#!/bin/sh
set -e

is_true () {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

PORT="${PORT:-8000}"
export PYTHONPATH=/app

# LLM service
echo "[llm] Starting LLM service at :${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
