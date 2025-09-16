#!/bin/sh
set -e

is_true () {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

PORT="${PORT:-8002}"
export PYTHONPATH=/srv

# LLM service uses mock for testing
echo "[llm] Starting LLM mock service at :${PORT}"
echo "[llm] Using mock LLM for testing purposes"
exec uvicorn adapters.llm_proxy:app --host 0.0.0.0 --port "${PORT}" --app-dir /srv
