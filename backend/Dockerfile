FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (libmagic, tesseract OCR, build tools, PostgreSQL client, curl)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libmagic1 \
    tesseract-ocr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt requirements-dev.txt ./

# OpenTelemetry instrumentation still imports pkg_resources (setuptools < 80).
# python:3.12-slim no longer ships it, so pin it explicitly for Celery/app boot.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir "setuptools>=70,<72" && \
    sed -i 's/python-magic-bin==0.4.14/python-magic==0.4.27/' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-dev.txt

# Copy application code, migrations, configs, and scripts
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts ./scripts
COPY keys ./keys

# Set environment variables defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    JWT_PRIVATE_KEY_PATH=/app/keys/private.pem \
    JWT_PUBLIC_KEY_PATH=/app/keys/public.pem

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=5s --retries=10 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

