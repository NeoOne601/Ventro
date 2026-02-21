FROM python:3.11-slim-bookworm

WORKDIR /app

# System dependencies for document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    libglib2.0-0 \
    libgl1-mesa-glx \
    libgomp1 \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"

# Copy application code
COPY src/ ./src/

# Create temp upload directory
RUN mkdir -p /tmp/mas_vgfr_uploads

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /tmp/mas_vgfr_uploads
USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.presentation.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
