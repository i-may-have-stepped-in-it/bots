"""
OpenTelemetry-based Tracing System for Jennifer Bot.
Provides comprehensive tracing and observability for all bot operations.
"""

import functools
import inspect
import logging
import os
from collections.abc import Callable
from enum import Enum
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.trace import Status, StatusCode

logger = logging.getLogger(__name__)


class SpanStatus(Enum):
    """Span execution status (mapping to OpenTelemetry StatusCode)."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


# Initialize OpenTelemetry
def _initialize_otel(service_name: str = "jennifer"):
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Check for OTLP exporter endpoint
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        logger.info(f"Configuring OTLP exporter to {otlp_endpoint}")
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    else:
        # Fallback to console for debugging if enabled
        if os.getenv("ENABLE_CONSOLE_SPAN_LOGGING", "false").lower() == "true":
            logger.debug("Configuring console span exporter")
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)


_initialize_otel()
otel_tracer = trace.get_tracer("jennifer")


class Tracer:
    """Wrapper around OpenTelemetry Tracer to maintain compatibility with legacy Tracer API."""

    def __init__(self, service_name: str = "jennifer"):
        self.service_name = service_name
        self._otel_tracer = otel_tracer
        # Stack of active OTel spans to handle parent/child relationships without explicit IDs
        self._span_stack: list[trace.Span] = []

    def start_trace(self, name: str, attributes: dict | None = None) -> str:
        """Start a new trace (root span)."""
        span = self._otel_tracer.start_span(name, attributes=attributes)
        self._span_stack.append(span)
        trace_id = format(span.get_span_context().trace_id, '032x')
        logger.info(f"[TRACE:{trace_id[:8]}] Started trace: {name}")
        return trace_id

    def start_span(self, name: str, service: str,
                   trace_id: str | None = None,
                   parent_id: str | None = None,
                   attributes: dict | None = None) -> str:
        """Start a new span. OpenTelemetry handles parent/child via context."""
        # Add service name as an attribute for filtering
        attrs = attributes or {}
        attrs["service.name"] = service

        span = self._otel_tracer.start_span(name, attributes=attrs)
        self._span_stack.append(span)

        span_id = format(span.get_span_context().span_id, '016x')
        logger.debug(f"[SPAN:{span_id[:8]}] Started: {name} ({service})")
        return span_id

    def end_span(self, span_id: str | None = None,
                 status: SpanStatus = SpanStatus.SUCCESS,
                 error: str | None = None):
        """End a span."""
        if not self._span_stack:
            return

        span = self._span_stack.pop()

        if status == SpanStatus.ERROR:
            span.set_status(Status(StatusCode.ERROR, description=error or "Unknown error"))
            if error:
                span.record_exception(Exception(error))
        else:
            span.set_status(Status(StatusCode.OK))

        span.end()
        span_id_val = format(span.get_span_context().span_id, '016x')
        logger.debug(f"[SPAN:{span_id_val[:8]}] Ended: {span.name} ({status.value})")

    def end_trace(self, trace_id: str | None = None):
        """End all remaining spans in the trace."""
        while self._span_stack:
            self.end_span()

    def add_event(self, name: str, attributes: dict | None = None,
                  span_id: str | None = None):
        """Add an event to the current span."""
        if self._span_stack:
            self._span_stack[-1].add_event(name, attributes=attributes or {})

    def add_attribute(self, key: str, value: Any, span_id: str | None = None):
        """Add an attribute to the current span."""
        if self._span_stack:
            self._span_stack[-1].set_attribute(key, value)

    def trace_method(self, service: str, name: str | None = None):
        """Decorator to trace a method."""
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with self._otel_tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("service.name", service)
                    try:
                        # Extract useful attributes from args
                        sig = inspect.signature(func)
                        bound = sig.bind(*args, **kwargs)
                        bound.apply_defaults()

                        for param_name, value in bound.arguments.items():
                            if param_name in ['user_id', 'message', 'command']:
                                span.set_attribute(param_name, str(value)[:100])

                        return await func(*args, **kwargs)
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, description=str(e)))
                        span.record_exception(e)
                        raise

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self._otel_tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("service.name", service)
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, description=str(e)))
                        span.record_exception(e)
                        raise

            return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
        return decorator


# Global tracer instance
tracer = Tracer()


def get_tracer() -> Tracer:
    """Get the global tracer instance."""
    return tracer
