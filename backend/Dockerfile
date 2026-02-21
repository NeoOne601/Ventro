FROM python:3.11-slim-bookworm

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libgomp1 \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e "."

# Source code
COPY src/ ./src/

# Upload directory
RUN mkdir -p /tmp/ventro_uploads

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /tmp/ventro_uploads
USER appuser

EXPOSE 8000

# Render/Railway set $PORT automatically; fall back to 8000 for local
CMD ["sh", "-c", "uvicorn src.presentation.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
