FROM python:3.11-slim

ARG MCP_SERVER_DIR=sql

WORKDIR /opt/mcp

# Keep dependency installation independent from MCP source changes. The build
# context is shared, but only the selected server's requirements invalidate
# this layer.
COPY mcp/${MCP_SERVER_DIR}/requirements.txt /tmp/mcp-requirements.txt
RUN pip install --no-cache-dir -r /tmp/mcp-requirements.txt

# Copy only this server and the shared helper module. Editing another MCP server
# no longer invalidates this image's application layer.
COPY mcp/${MCP_SERVER_DIR}/ /opt/mcp/${MCP_SERVER_DIR}/
COPY mcp/helpers/ /opt/mcp/helpers/

ENV PYTHONPATH=/opt/mcp
ENV MCP_SERVER_DIR=${MCP_SERVER_DIR}
ENV MCP_SERVER_ENTRYPOINT=server:app

CMD sh -c "cd /opt/mcp/${MCP_SERVER_DIR} && uvicorn ${MCP_SERVER_ENTRYPOINT} --host 0.0.0.0 --port ${PORT:-8080}"

