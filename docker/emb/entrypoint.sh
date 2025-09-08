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

if is_true "${TEST_MODE}"; then
  echo "[emb] TEST_MODE=ON -> starting stub at :${PORT}"
  exec uvicorn stubs.emb_server:app --host 0.0.0.0 --port "${PORT}" --app-dir /srv
else
  echo "[emb] TEST_MODE=OFF -> starting proxy to REAL_EMBEDDINGS_URL=${REAL_EMBEDDINGS_URL:-<unset>} at :${PORT}"
  exec uvicorn adapters.emb_proxy:app --host 0.0.0.0 --port "${PORT}" --app-dir /srv
fi
