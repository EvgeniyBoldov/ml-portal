FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements/llm.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

COPY backend /app/backend

ENV PORT=8002 LLM_MODEL_PATH=/models/model.gguf
VOLUME ["/models"]
EXPOSE 8002
CMD ["uvicorn","backend.apps.llm.main:app","--host","0.0.0.0","--port","8002"]
