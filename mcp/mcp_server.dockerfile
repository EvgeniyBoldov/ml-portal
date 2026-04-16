FROM python:3.11-slim

ARG MCP_SERVER_DIR=sql

WORKDIR /opt/mcp

COPY mcp /opt/mcp

RUN test -f "/opt/mcp/${MCP_SERVER_DIR}/requirements.txt"
RUN pip install --no-cache-dir -r "/opt/mcp/${MCP_SERVER_DIR}/requirements.txt"

ENV PYTHONPATH=/opt/mcp
ENV MCP_SERVER_DIR=${MCP_SERVER_DIR}
ENV MCP_SERVER_ENTRYPOINT=server:app

CMD sh -c "cd /opt/mcp/${MCP_SERVER_DIR} && uvicorn ${MCP_SERVER_ENTRYPOINT} --host 0.0.0.0 --port ${PORT:-8080}"

