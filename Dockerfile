# Multi-stage build for production efficiency
FROM python:3.12-slim-bookworm AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Try to install bd (beads) CLI if available via pip
RUN pip install --no-cache-dir beads-cli 2>/dev/null || echo "beads-cli not on PyPI, will need manual install"

# Production stage
FROM python:3.12-slim-bookworm AS production

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install bd CLI from GitHub releases (fallback method)
RUN if ! command -v bd &> /dev/null; then \
    curl -L -o /tmp/bd.tar.gz \
    "https://github.com/ohmyopencodes/beads/releases/latest/download/bd-linux-amd64.tar.gz" 2>/dev/null || \
    echo "Could not download bd, will need to be mounted/installed manually"; \
    if [ -f /tmp/bd.tar.gz ]; then \
    tar -xzf /tmp/bd.tar.gz -C /usr/local/bin/ 2>/dev/null || true; \
    rm -f /tmp/bd.tar.gz; \
    fi; \
    fi

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser static/ ./static/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser pyproject.toml .
COPY --chown=appuser:appuser README.md .

# Create data directory and set permissions
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 9754

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:9754/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9754"]

# Development stage
FROM production AS development

# Switch back to root for development tools
USER root

# Install development dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install dev dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir pytest pytest-asyncio httpx

# Switch back to appuser
USER appuser

# Development command with hot reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9754", "--reload", "--reload-dir", "app"]
