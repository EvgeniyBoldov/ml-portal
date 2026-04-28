# =============================================================================
# ML Portal API - Service Dockerfile
# =============================================================================
FROM ml-portal-base-ml:latest

# Install service-specific dependencies
USER root
COPY infra/docker/api/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
USER appuser

# Copy application code to /app/app/ (unified structure)
COPY apps/api/src/app/ ./app/
COPY apps/api/alembic.ini ./

# Set PYTHONPATH to /app so imports work as "from app."
ENV PYTHONPATH=/app

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
