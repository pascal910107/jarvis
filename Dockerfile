# Multi-stage build for optimized image size
FROM python:3.12-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Create non-root user
RUN useradd -m -u 1000 jarvis && \
    mkdir -p /app && \
    chown -R jarvis:jarvis /app

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/jarvis/.local

# Copy application code
COPY --chown=jarvis:jarvis . .

# Switch to non-root user
USER jarvis

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import core; print('Health check passed')" || exit 1

# Default command (can be overridden)
CMD ["python", "-m", "core.main"]