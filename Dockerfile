FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md LICENSE ./
COPY quantumrag/ quantumrag/

# Install QuantumRAG with all dependencies
RUN pip install --no-cache-dir ".[all,api]"

# Create data directory
RUN mkdir -p /data/quantumrag

# Default config
ENV QUANTUMRAG_STORAGE__DATA_DIR=/data/quantumrag
ENV QUANTUMRAG_LANGUAGE=auto

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/v1/status').raise_for_status()" || exit 1

# Run the API server
CMD ["quantumrag", "serve", "--host", "0.0.0.0", "--port", "8000"]
