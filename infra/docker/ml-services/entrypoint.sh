#!/bin/bash
# =============================================================================
# ML Portal ML Services - Unified Entrypoint
# =============================================================================

set -e

# Default service type
SERVICE_TYPE=${SERVICE_TYPE:-llm}

echo "Starting ML service: $SERVICE_TYPE"

case "$SERVICE_TYPE" in
    "llm")
        echo "Starting LLM service on port $LLM_PORT"
        cd /app/llm
        exec python -m uvicorn main:app --host 0.0.0.0 --port ${LLM_PORT:-8002}
        ;;
    "emb")
        echo "Starting EMB service on port $EMB_PORT"
        cd /app/emb
        exec python -m uvicorn main:app --host 0.0.0.0 --port ${EMB_PORT:-8001}
        ;;
    "worker")
        echo "Starting Celery worker"
        cd /app/worker
        exec celery -A celery_app worker --loglevel=info
        ;;
    "test")
        echo "Running test command"
        exec "$@"
        ;;
    *)
        echo "Unknown service type: $SERVICE_TYPE"
        echo "Available services: llm, emb, worker, test"
        exit 1
        ;;
esac
