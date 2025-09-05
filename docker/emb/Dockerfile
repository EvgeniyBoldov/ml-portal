FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements/emb.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY backend /app/backend

ENV PORT=8001 MODELS_DIR=/models MODEL_ID="BAAI/bge-m3"
VOLUME ["/models"]
EXPOSE 8001
CMD ["uvicorn","backend.apps.emb.main:app","--host","0.0.0.0","--port","8001"]
