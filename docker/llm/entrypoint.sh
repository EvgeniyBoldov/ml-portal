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

if is_true "${TEST_MODE}"; then
  echo "[llm] TEST_MODE=ON -> starting stub at :${PORT}"
  exec uvicorn stubs.llm_server:app --host 0.0.0.0 --port "${PORT}" --app-dir /srv
else
  echo "[llm] TEST_MODE=OFF -> starting proxy to REAL_LLM_URL=${REAL_LLM_URL:-<unset>} at :${PORT}"
  exec uvicorn adapters.llm_proxy:app --host 0.0.0.0 --port "${PORT}" --app-dir /srv
fi
