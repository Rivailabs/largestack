FROM python:3.12-slim

WORKDIR /app

# Install system deps for cryptography + curl for prod compose healthcheck
# (v0.3.11: docker-compose.prod.yml overrides healthcheck to `curl /health`,
# so curl must be present in the image. python:3.12-slim does not ship it.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Copy package metadata and source FIRST so pip install has the actual code
COPY pyproject.toml README.md LICENSE ./
COPY pricing ./pricing
COPY largestack ./largestack

# Install the package
RUN pip install --no-cache-dir . cryptography

# Now copy the rest (tests, examples, docs) for runtime use if needed
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 largestack && chown -R largestack:largestack /app
USER largestack

# v0.3.6: container marker — dashboard CLI uses this to bind 0.0.0.0
ENV LARGESTACK_IN_CONTAINER=1

# Healthcheck (v0.3.12): use real HTTP probe to /health.
# v0.3.11 added curl to the image for prod compose's healthcheck override;
# now the base image's healthcheck is also functional. The previous
# `python -c "import largestack"` only verified the Python import succeeded —
# it didn't confirm the dashboard server was actually serving requests.
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=20s \
    CMD curl -fsS http://localhost:8787/health || exit 1

EXPOSE 8787
CMD ["largestack", "dashboard"]
