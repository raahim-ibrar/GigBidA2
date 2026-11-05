FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY . .
RUN pip install --no-cache-dir uv==0.9.6 && uv sync --frozen --no-dev
CMD [".venv/bin/arq", "worker.settings.WorkerSettings"]
