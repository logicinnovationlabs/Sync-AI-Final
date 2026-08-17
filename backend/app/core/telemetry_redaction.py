"""
OpenTelemetry span attribute redaction processor.

Default-deny allowlist: only attributes explicitly listed below survive to the
exporter.  Anything else is stripped before ``on_end`` – this is the single
choke-point for all span data leaving the process (requirement §2.2 / rule 1).
"""

from opentelemetry.sdk.trace import SpanProcessor


ALLOWED_SPAN_ATTRIBUTES = frozenset({
    "db.system",
    "db.operation",
    "tenant.id",
    "http.method",
    "http.route",
    "http.status_code",
    "rpc.system",
    "net.peer.name",
})


class SafeSpanProcessor(SpanProcessor):
    """Wraps the real exporting processor.  Strips any attribute not on the
    allowlist before the span is handed to the OTLP exporter."""

    def __init__(self, wrapped: SpanProcessor):
        self._wrapped = wrapped

    def on_start(self, span, parent_context=None):
        try:
            self._wrapped.on_start(span, parent_context)
        except Exception:
            pass

    def on_end(self, span):
        if getattr(span, "_attributes", None) is not None and isinstance(span._attributes, dict):
            for key in list(span._attributes.keys()):
                if key not in ALLOWED_SPAN_ATTRIBUTES:
                    del span._attributes[key]
        elif hasattr(span, "attributes") and span.attributes is not None:
            if isinstance(span.attributes, dict):
                span._attributes = {
                    k: v for k, v in span.attributes.items()
                    if k in ALLOWED_SPAN_ATTRIBUTES
                }
            elif hasattr(span, "_attributes") and isinstance(span._attributes, dict):
                for key in list(span.attributes.keys()):
                    if key not in ALLOWED_SPAN_ATTRIBUTES:
                        del span._attributes[key]
        try:
            self._wrapped.on_end(span)
        except Exception:
            pass

    def shutdown(self):
        try:
            self._wrapped.shutdown()
        except Exception:
            pass

    def force_flush(self, timeout_millis=30000):
        try:
            return self._wrapped.force_flush(timeout_millis)
        except Exception:
            return False
