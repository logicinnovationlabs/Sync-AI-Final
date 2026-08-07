FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY mocks ./mocks
COPY fixtures ./fixtures
COPY tests ./tests

RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app
ENV ENVIRONMENT=development
ENV ACL_BACKEND=memory
ENV RERANKER_BACKEND=mock
ENV EMBEDDING_BACKEND=mock
ENV SERVICE_PORT=8089

EXPOSE 8089

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8089"]
