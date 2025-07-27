FROM python:3.12-slim

# Install uv
RUN pip install uv

# Create working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY . .

# Copy sample config if no config exists
RUN if [ ! -f config.json ]; then cp config.json.sample config.json || true; fi

# Set production environment
ENV PRODUCTION=true
ENV PYTHONUNBUFFERED=1

# Initialize database (no sample data in production)
RUN rm -f adcp.db && uv run python database.py

# Default port
ENV ADCP_SALES_PORT=8000
ENV ADCP_SALES_HOST=0.0.0.0

# Expose port
EXPOSE 8000

# Run the server
CMD ["./run_server.py"]