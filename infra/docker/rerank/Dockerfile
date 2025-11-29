# =============================================================================
# ML Portal Reranker Service - Service Dockerfile
# =============================================================================
FROM ml-portal-base-ml:latest

# Install service-specific dependencies
USER root
COPY infra/docker/rerank/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
USER appuser

# Copy rerank service files
COPY apps/rerank/src/app/ /app/

# Set environment variables
ENV PYTHONPATH=/app
ENV RERANK_MODEL_PATH=/models_llm/cross-encoder--ms-marco-MiniLM-L-6-v2

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"]
