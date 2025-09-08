FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install deps from local requirements.txt placed NEXT TO this Dockerfile
COPY docker/worker/requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Copy worker sources
COPY backend/ .

# Tip: override the CMD in docker-compose to run celery if you have it
# e.g. command: celery -A app.celery_app worker --loglevel=INFO
CMD ["python", "-c", "import time; print('Worker ready'); time.sleep(10**9)"]
