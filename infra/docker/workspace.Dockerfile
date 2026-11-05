FROM python:3.13-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir uv==0.9.6 && uv sync --frozen --no-dev
CMD [".venv/bin/python", "-m", "mcp_servers.workspace.server"]
