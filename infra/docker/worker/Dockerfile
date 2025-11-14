# =============================================================================
# ML Portal Worker Service - Service Dockerfile
# =============================================================================
FROM ml-portal-base-ml:latest

# Install service-specific dependencies
USER root
COPY infra/docker/worker/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
USER appuser

# Copy entire application structure to /app/app/ (unified structure)
COPY apps/api/src/app/ ./app/

# Set environment variables
ENV PYTHONPATH=/app
ENV CELERY_APP=app.celery_app
ENV CELERY_WORKER_CONCURRENCY=4
ENV CELERY_WORKER_PREFETCH_MULTIPLIER=1

# Force rebuild timestamp
RUN echo "Build timestamp: $(date)" > /app/build_info.txt

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD celery -A app.celery_app inspect ping || exit 1

# Default command
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--concurrency=4"]