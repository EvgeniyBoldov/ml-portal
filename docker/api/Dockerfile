FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# 1) Install dependencies strictly from requirements.txt that sits NEXT TO this Dockerfile
COPY docker/api/requirements.txt ./
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# 2) Copy application sources that sit NEXT TO this Dockerfile
COPY backend/ .

EXPOSE 8000
ENV PORT=8000

# Adjust the module path if your entrypoint differs
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
