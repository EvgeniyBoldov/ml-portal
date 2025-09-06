FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY backend/requirements/worker.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

# copy FULL backend code into /app/
COPY backend/ /app/

# change celery app path from backend.app.celery_app:app -> app.celery_app:app
CMD ["bash","-lc","celery -A app.celery_app:app worker -Q ${QUEUES:-normalize,chunk,embed,index,analyze,watch} -n worker@%h --loglevel=INFO"]
