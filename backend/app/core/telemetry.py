"""
Block O – OpenTelemetry bootstrap shared by API (uvicorn) and Celery.

Must run once per process before instrumented libraries are used.
"""

from __future__ import annotations

import os
from typing import Iterator
from urllib.parse import urlparse

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.logging import setup_otel_logging
from app.core.telemetry_redaction import SafeSpanProcessor

_BOOTSTRAPPED = False
_LIBS_INSTRUMENTED = False

REQUESTS_COUNTER = None
ACTIVE_REQUESTS = None
REQUEST_DURATION = None
SPAN_PROCESSOR = None


def otlp_grpc_endpoint() -> str:
    """Resolve gRPC target from OTLP_ENDPOINT (HTTP :4318 is mapped to :4317)."""
    raw = os.getenv("OTLP_ENDPOINT")
    if not raw:
        try:
            from app.core.config import settings
            raw = settings.otlp_endpoint
        except Exception:
            raw = "http://otel-collector:4317"
    parsed = urlparse(raw if "://" in raw else f"http://{raw}")
    host = parsed.hostname or "otel-collector"
    port = parsed.port or 4317
    if port == 4318:
        port = 4317
    return f"{host}:{port}"


def setup_telemetry(service_name: str = "snyq-backend") -> None:
    """Install TracerProvider + MeterProvider + library instrumentors (idempotent)."""
    global _BOOTSTRAPPED, REQUESTS_COUNTER, ACTIVE_REQUESTS, REQUEST_DURATION, SPAN_PROCESSOR
    if _BOOTSTRAPPED:
        _instrument_libraries()
        return

    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: "2.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
    })
    endpoint = otlp_grpc_endpoint()

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True, timeout=2)
    batch = BatchSpanProcessor(
        exporter,
        max_queue_size=2048,
        schedule_delay_millis=5000,
        max_export_batch_size=512,
        export_timeout_millis=2000,
    )
    SPAN_PROCESSOR = SafeSpanProcessor(batch)
    provider.add_span_processor(SPAN_PROCESSOR)
    trace.set_tracer_provider(provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True, timeout=2),
        export_interval_millis=10_000,
        export_timeout_millis=2000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    meter = metrics.get_meter("snyq.http")
    REQUESTS_COUNTER = meter.create_counter(
        "snyq.http.requests", unit="1", description="HTTP requests"
    )
    ACTIVE_REQUESTS = meter.create_up_down_counter(
        "snyq.http.active_requests", unit="1", description="In-flight HTTP requests"
    )
    REQUEST_DURATION = meter.create_histogram(
        "snyq.http.duration", unit="ms", description="HTTP server duration (app middleware)"
    )

    def _up(_options: CallbackOptions) -> Iterator[Observation]:
        yield Observation(1, {})

    meter.create_observable_gauge(
        "snyq.up", callbacks=[_up], unit="1", description="Process liveness"
    )

    setup_otel_logging()
    _BOOTSTRAPPED = True
    _instrument_libraries()


def _instrument_libraries() -> None:
    global _LIBS_INSTRUMENTED
    if _LIBS_INSTRUMENTED:
        return
    if not RequestsInstrumentor()._is_instrumented_by_opentelemetry:
        RequestsInstrumentor().instrument()
    if not RedisInstrumentor()._is_instrumented_by_opentelemetry:
        RedisInstrumentor().instrument()
    if not CeleryInstrumentor()._is_instrumented_by_opentelemetry:
        CeleryInstrumentor().instrument()
    try:
        SQLAlchemyInstrumentor().instrument()
    except Exception:
        pass
    _LIBS_INSTRUMENTED = True


def instrument_fastapi(app) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    # instrument_app() does not always flip the class flag tests/SDK check
    FastAPIInstrumentor._is_instrumented_by_opentelemetry = True
