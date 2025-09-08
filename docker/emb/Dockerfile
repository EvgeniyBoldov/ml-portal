FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

# Install deps from local requirements.txt placed NEXT TO this Dockerfile
COPY docker/emb/requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Copy service code
COPY backend/ .

EXPOSE 8001
ENV PORT=8001
# Adjust the module if different (e.g., "emb.app:app")
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
