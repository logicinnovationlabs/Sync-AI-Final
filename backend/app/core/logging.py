"""
OpenTelemetry-aware logging configuration.

Injects ``trace_id`` and ``span_id`` into every log record so that logs can
be correlated with traces in Grafana / Tempo without manual annotation at
each call-site.
"""

import logging

from opentelemetry import trace


class OpenTelemetryLogFilter(logging.Filter):
    """Attach trace_id / span_id to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
        return True


def setup_otel_logging() -> None:
    """Register the log filter on the root logger and every handler.

    Safe to call multiple times – idempotent. Filters must live on handlers
    as well as the root logger: child loggers propagate records to root
    handlers without running the root logger's filters.
    """
    root = logging.getLogger()
    existing = None
    for f in root.filters:
        if isinstance(f, OpenTelemetryLogFilter):
            existing = f
            break
    otel_filter = existing or OpenTelemetryLogFilter()
    if existing is None:
        root.addFilter(otel_filter)

    for handler in root.handlers:
        if not any(isinstance(f, OpenTelemetryLogFilter) for f in handler.filters):
            handler.addFilter(otel_filter)
        if handler.formatter:
            fmt = handler.formatter._fmt
            if fmt and "%(trace_id)s" not in fmt:
                handler.formatter = logging.Formatter(
                    fmt.replace(
                        "%(message)s",
                        "[trace=%(trace_id)s span=%(span_id)s] %(message)s",
                    ),
                    datefmt=handler.formatter.datefmt,
                )
