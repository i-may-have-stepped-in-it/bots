"""
End-to-End Tracing System for Jennifer Bot

Provides comprehensive tracing of requests through the entire application stack:
- Discord message received → Command parsed → Handler executed → Response sent
- Image/Video generation tasks: Queued → Processing → Completed
- OpenClaw agent operations
"""

import functools
import inspect
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)

# Context variable to track current trace ID
current_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
current_span_id: ContextVar[Optional[str]] = ContextVar('span_id', default=None)


class SpanStatus(Enum):
    """Span execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class Span:
    """Represents a single operation span."""
    id: str
    trace_id: str
    parent_id: Optional[str]
    name: str
    service: str  # e.g., 'discord', 'openclaw', 'image_gen', 'comfyui'
    start_time: float
    end_time: Optional[float] = None
    status: SpanStatus = SpanStatus.PENDING
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "span_id": self.id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "service": self.service,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.end_time - self.start_time) * 1000 if self.end_time else None,
            "status": self.status.value,
            "attributes": self.attributes,
            "events": self.events,
            "error": self.error,
        }


@dataclass  
class Trace:
    """Represents a complete request trace."""
    id: str
    start_time: float
    end_time: Optional[float] = None
    spans: List[Span] = field(default_factory=list)
    root_span_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "trace_id": self.id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.end_time - self.start_time) * 1000 if self.end_time else None,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }


class Tracer:
    """Main tracer class for managing traces and spans."""
    
    def __init__(self, service_name: str = "jennifer"):
        self.service_name = service_name
        self._active_traces: Dict[str, Trace] = {}
        self._active_spans: Dict[str, Span] = {}
        
    def start_trace(self, name: str, attributes: Optional[Dict] = None) -> str:
        """Start a new trace."""
        trace_id = str(uuid.uuid4())
        trace = Trace(
            id=trace_id,
            start_time=time.time(),
        )
        self._active_traces[trace_id] = trace
        
        # Start root span
        span_id = self.start_span(name, service=self.service_name, 
                                  trace_id=trace_id, attributes=attributes)
        trace.root_span_id = span_id
        
        # Set context
        current_trace_id.set(trace_id)
        
        logger.info(f"[TRACE:{trace_id}] Started trace: {name}", 
                    extra={"trace_id": trace_id, "span_id": span_id})
        return trace_id
    
    def start_span(self, name: str, service: str, 
                   trace_id: Optional[str] = None,
                   parent_id: Optional[str] = None,
                   attributes: Optional[Dict] = None) -> str:
        """Start a new span."""
        if trace_id is None:
            trace_id = current_trace_id.get() or self.start_trace(name)
        
        span_id = str(uuid.uuid4())
        span = Span(
            id=span_id,
            trace_id=trace_id,
            parent_id=parent_id or current_span_id.get(),
            name=name,
            service=service,
            start_time=time.time(),
            status=SpanStatus.RUNNING,
            attributes=attributes or {},
        )
        
        self._active_spans[span_id] = span
        if trace_id in self._active_traces:
            self._active_traces[trace_id].spans.append(span)
        
        current_span_id.set(span_id)
        
        logger.debug(f"[SPAN:{span_id}] Started: {name} ({service})",
                    extra={"trace_id": trace_id, "span_id": span_id, "service": service})
        return span_id
    
    def end_span(self, span_id: Optional[str] = None, 
                 status: SpanStatus = SpanStatus.SUCCESS,
                 error: Optional[str] = None):
        """End a span."""
        if span_id is None:
            span_id = current_span_id.get()
        
        if span_id and span_id in self._active_spans:
            span = self._active_spans[span_id]
            span.end_time = time.time()
            span.status = status
            span.error = error
            
            logger.debug(f"[SPAN:{span_id}] Ended: {span.name} ({status.value})",
                        extra={"span_id": span_id, "status": status.value})
            
            # Restore parent span context if exists
            if span.parent_id:
                current_span_id.set(span.parent_id)
            else:
                current_span_id.set(None)
    
    def end_trace(self, trace_id: Optional[str] = None):
        """End a trace and log the complete flow."""
        if trace_id is None:
            trace_id = current_trace_id.get()
        
        if trace_id and trace_id in self._active_traces:
            trace = self._active_traces[trace_id]
            trace.end_time = time.time()
            
            # End any remaining spans
            for span in trace.spans:
                if span.end_time is None:
                    span.end_time = time.time()
                    span.status = SpanStatus.CANCELLED
            
            # Log complete trace
            self._log_trace(trace)
            
            # Cleanup
            del self._active_traces[trace_id]
            for span in list(self._active_spans.values()):
                if span.trace_id == trace_id:
                    del self._active_spans[span.id]
            
            current_trace_id.set(None)
            current_span_id.set(None)
    
    def add_event(self, name: str, attributes: Optional[Dict] = None,
                  span_id: Optional[str] = None):
        """Add an event to a span."""
        if span_id is None:
            span_id = current_span_id.get()
        
        if span_id and span_id in self._active_spans:
            event = {
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {},
            }
            self._active_spans[span_id].events.append(event)
            logger.debug(f"[EVENT] {name}", extra={"span_id": span_id, "event": name})
    
    def add_attribute(self, key: str, value: Any, span_id: Optional[str] = None):
        """Add an attribute to a span."""
        if span_id is None:
            span_id = current_span_id.get()
        
        if span_id and span_id in self._active_spans:
            self._active_spans[span_id].attributes[key] = value
    
    def _log_trace(self, trace: Trace):
        """Log complete trace information."""
        trace_data = trace.to_dict()
        
        # Create a formatted trace summary
        spans_by_service: Dict[str, List[Span]] = {}
        for span in trace.spans:
            spans_by_service.setdefault(span.service, []).append(span)
        
        summary = f"""
╔══════════════════════════════════════════════════════════════════╗
║  TRACE COMPLETED: {trace.id[:8]}...                                          ║
╠══════════════════════════════════════════════════════════════════╣
║  Duration: {trace_data['duration_ms']:.2f}ms                                        ║
║  Spans: {len(trace.spans)}                                                    ║
╠══════════════════════════════════════════════════════════════════╣
║  Services Called:                                                ║
"""
        for service, spans in spans_by_service.items():
            total_time = sum((s.end_time or s.start_time) - s.start_time 
                           for s in spans if s.end_time) * 1000
            errors = sum(1 for s in spans if s.error)
            summary += f"║    • {service:20s} ({len(spans)} spans, {total_time:.1f}ms, {errors} errors)  ║\n"
        
        summary += "╚══════════════════════════════════════════════════════════════════╝"
        
        logger.info(summary)
        
        # Also log as JSON for structured parsing
        logger.info(f"TRACE_JSON: {json.dumps(trace_data, default=str)}")
    
    def trace_method(self, service: str, name: Optional[str] = None):
        """Decorator to trace a method."""
        def decorator(func: Callable) -> Callable:
            span_name = name or func.__name__
            
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Save context before creating child span so we can always restore it.
                parent_span_id = current_span_id.get()
                span_id = self.start_span(span_name, service)
                exc_to_raise = None
                result = None
                try:
                    # Extract useful attributes from args
                    sig = inspect.signature(func)
                    bound = sig.bind(*args, **kwargs)
                    bound.apply_defaults()

                    for param_name, value in bound.arguments.items():
                        if param_name in ['user_id', 'message', 'command']:
                            self.add_attribute(param_name, str(value)[:100], span_id)

                    result = await func(*args, **kwargs)
                    self.end_span(span_id, SpanStatus.SUCCESS)
                except Exception as e:
                    exc_to_raise = e
                    self.end_span(span_id, SpanStatus.ERROR, str(e))
                finally:
                    # Guarantee context is restored even if end_span has a bug.
                    if current_span_id.get() == span_id:
                        current_span_id.set(parent_span_id)
                if exc_to_raise is not None:
                    raise exc_to_raise
                return result

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                parent_span_id = current_span_id.get()
                span_id = self.start_span(span_name, service)
                try:
                    result = func(*args, **kwargs)
                    self.end_span(span_id, SpanStatus.SUCCESS)
                    return result
                except Exception as e:
                    self.end_span(span_id, SpanStatus.ERROR, str(e))
                    raise
                finally:
                    if current_span_id.get() == span_id:
                        current_span_id.set(parent_span_id)
            
            return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
        return decorator


# Global tracer instance
tracer = Tracer()


def get_tracer() -> Tracer:
    """Get the global tracer instance."""
    return tracer
