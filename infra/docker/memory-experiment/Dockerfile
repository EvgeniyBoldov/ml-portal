FROM python:3.11-slim
WORKDIR /runner
COPY scripts/memory-experiment/ /runner/
ENV PYTHONUNBUFFERED=1 EXPERIMENT_ROOT=/experiment HIPPO_URL=http://hipporag:8080
CMD ["sleep", "infinity"]
