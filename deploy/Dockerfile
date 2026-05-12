# Largestack AI — Production Dockerfile
# Multi-stage build for small, secure images

# Stage 1: builder
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY pricing/ ./pricing/
COPY largestack/ ./largestack/
RUN python -m venv /opt/venv && pip install --no-cache-dir .

# Stage 2: runtime
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd -r -u 1001 -m -d /home/largestack largestack

WORKDIR /app

# Copy installed application environment from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build /app

# Healthcheck endpoint relies on FastAPI server
EXPOSE 8000

USER largestack

CMD ["python", "-c", "import os; from largestack import Agent; from largestack.serve import serve; from largestack._core.yaml_agent import load_agent; agent = load_agent('agent.yaml') if os.path.exists('agent.yaml') else Agent(name=os.getenv('LARGESTACK_SERVE_AGENT_NAME','largestack'), llm=os.getenv('LARGESTACK_DEFAULT_LLM','openai/gpt-4o-mini')); serve(agent, port=8000)"]
