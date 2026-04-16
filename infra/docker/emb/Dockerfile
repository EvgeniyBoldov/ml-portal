# =============================================================================
# ML Portal Embedding Service - Service Dockerfile
# =============================================================================
FROM ml-portal-base-ml:latest

# Install service-specific dependencies
USER root
COPY infra/docker/emb/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
USER appuser

# Copy embedding service files
COPY apps/emb/src/app/ /app/

# Set environment variables
ENV PYTHONPATH=/app
ENV EMB_MODEL_ALIAS="all-MiniLM-L6-v2"
ENV EMB_MODEL_PATH=/models_llm/sentence-transformers--all-MiniLM-L6-v2
ENV EMB_MODEL_DIMENSIONS=384
ENV EMB_MODEL_MAX_TOKENS=512
ENV EMB_MODEL_VERSION=1.0
ENV EMB_BATCH_SIZE=128
ENV EMB_MAX_WAIT_MS=8
ENV EMB_MODEL_PARALLELISM=2

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
