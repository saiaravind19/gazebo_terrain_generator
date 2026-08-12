FROM python:3.14-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System libs needed by opencv-python
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application code (.venv excluded via .dockerignore)
COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8080

CMD ["uv", "run", "--no-sync", "python", "scripts/server.py", "--host", "0.0.0.0", "--port", "8080"]
