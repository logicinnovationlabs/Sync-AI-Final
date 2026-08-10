FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY fixtures ./fixtures
COPY tests ./tests

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
ENV VECTOR_DB_TYPE=qdrant
ENV QDRANT_HOST=qdrant
ENV QDRANT_PORT=6333
ENV ENVIRONMENT=development

EXPOSE 8087

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8087"]
