# =============================================================================
# ML Portal ML Services - Base Image
# =============================================================================
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    libmagic1 \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy requirements and install Python dependencies
COPY infra/docker/base/requirements.ml.txt ./requirements.txt
# Install CPU-only torch first so the default CUDA wheels from PyPI are never
# pulled in; the requirements below then see torch as already satisfied.
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        "torch>=2.0.0" && \
    pip install --no-cache-dir -r requirements.txt


# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Default environment variables
ENV SERVICE_TYPE=llm
ENV EMB_PORT=8001

# Health check (will be overridden by docker-compose)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1
