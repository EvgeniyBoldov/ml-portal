FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY backend/ /app/
RUN python -m pip install --upgrade pip &&     if [ -f requirements.txt ]; then         pip install -r requirements.txt;     elif [ -f pyproject.toml ]; then         pip install 'poetry>=1.7.1' && poetry config virtualenvs.create false && poetry install --no-root --no-interaction;     else         pip install 'celery>=5.3' 'redis>=5';     fi
CMD python -c "import time; print('Worker stub started'); time.sleep(10**9)"
