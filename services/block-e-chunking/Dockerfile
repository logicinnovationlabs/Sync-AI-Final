FROM python:3.12-slim

# Create non-root user
RUN groupadd -r celeryuser && useradd -r -g celeryuser celeryuser

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/

# Set Python path
ENV PYTHONPATH=/app

# Change ownership to non-root user
RUN chown -R celeryuser:celeryuser /app

# Switch to non-root user
USER celeryuser

# Default command
CMD ["python", "-m", "celery", "-A", "app.workers.embedding_worker", "worker", "--loglevel=info"]
