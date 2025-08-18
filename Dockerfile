# Multi-stage build for smaller image
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set up caching for uv
ENV UV_CACHE_DIR=/cache/uv
ENV UV_TOOL_DIR=/cache/uv-tools
ENV UV_PYTHON_PREFERENCE=only-system

# Copy project files
WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install dependencies with caching and increased timeout
# This layer will be cached as long as pyproject.toml and uv.lock don't change
ENV UV_HTTP_TIMEOUT=300
RUN --mount=type=cache,target=/cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    uv sync --frozen

# Runtime stage
FROM python:3.12-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 adcp

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Set ownership
RUN chown -R adcp:adcp /app

# Switch to non-root user
USER adcp

# Add .venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Default port
ENV ADCP_PORT=8080
ENV ADCP_HOST=0.0.0.0

# Expose ports
EXPOSE 8080 8001

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default command - can be overridden in docker-compose
CMD ["./entrypoint.sh"]
