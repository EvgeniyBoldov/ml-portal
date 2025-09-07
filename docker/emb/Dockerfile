FROM python:3.11-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8001
RUN python -m pip install --upgrade pip && pip install fastapi uvicorn pydantic numpy
COPY docker/emb/server.py /srv/server.py
EXPOSE 8001
CMD uvicorn server:app --host 0.0.0.0 --port ${PORT}
