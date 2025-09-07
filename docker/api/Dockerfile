FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential curl && rm -rf /var/lib/apt/lists/*

# Copy backend sources
COPY backend/ /app/

# Install deps (requirements.txt > poetry > baseline)
RUN set -eux;     python -m pip install --upgrade pip;     if [ -f requirements.txt ]; then         pip install -r requirements.txt;     elif [ -f pyproject.toml ]; then         pip install 'poetry>=1.7.1';         poetry config virtualenvs.create false;         poetry install --no-root --no-interaction;     else         pip install 'fastapi>=0.110' 'uvicorn[standard]>=0.23' 'psycopg[binary]>=3.1'                     'redis>=5' 'qdrant-client>=1.7' 'boto3>=1.28' 'python-multipart>=0.0.9'                     'pydantic-settings>=2' 'passlib[bcrypt]>=1.7.4' 'sqlalchemy>=2.0';     fi

EXPOSE 8000
ENV PORT=8000

# shell-form to allow ${PORT} expansion
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
