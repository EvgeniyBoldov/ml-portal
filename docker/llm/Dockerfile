FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8002
RUN python -m pip install --upgrade pip && pip install fastapi uvicorn pydantic
COPY docker/llm/server.py /srv/server.py
EXPOSE 8002
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
