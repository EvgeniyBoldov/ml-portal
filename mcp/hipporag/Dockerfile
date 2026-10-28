# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=ml-portal-base-ml:latest
FROM ${BASE_IMAGE}
USER root
WORKDIR /worker
RUN python -m venv --system-site-packages /opt/hippo
ENV PATH=/opt/hippo/bin:$PATH PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false
COPY mcp/hipporag/requirements.txt /worker/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
ARG HIPPO_REVISION=d5c8329422e0a0b834a15874545cb6a74b4f9b26
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps https://github.com/OSU-NLP-Group/HippoRAG/archive/${HIPPO_REVISION}.zip
ENV HF_HOME=/tmp/huggingface
COPY mcp/hipporag/server.py /worker/server.py
COPY mcp/hipporag/common.py /worker/common.py
COPY mcp/hipporag/portal.py /worker/portal.py
COPY mcp/hipporag/document_operations.py /worker/document_operations.py
COPY mcp/hipporag/model_failures.py /worker/model_failures.py
COPY mcp/hipporag/worker.py /worker/worker.py
RUN python -c "from hipporag import HippoRAG; import worker"
RUN mkdir -p /data && chown appuser:appuser /data
USER appuser
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
