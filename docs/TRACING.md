# End-to-End Tracing System

## Overview

Jennifer Bot now includes comprehensive end-to-end tracing that tracks requests through the entire application stack. This helps with debugging, performance monitoring, and understanding the flow of operations.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Discord   │────▶│   Command   │────▶│  Image Gen  │────▶│   ComfyUI   │
│   Message   │     │   Handler   │     │   Adapter   │     │     API     │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
       └───────────────────┴───────────────────┴───────────────────┘
                           │
                    ┌──────▼──────┐
                    │    Trace    │
                    │   (JSON)    │
                    └─────────────┘
```

## Services Traced

| Service | Description | Key Spans |
|---------|-------------|-----------|
| `discord` | Discord message handling | `discord_message`, `handle_command`, `handle_conversation` |
| `image_gen` | Image generation orchestration | `sd_generate_image`, `process_image_task` |
| `comfyui` | ComfyUI API calls | `comfyui_generate`, `comfyui_poll`, `comfyui_fetch_image` |
| `openclaw` | OpenClaw agent operations | `openclaw_generate_response`, `openclaw_delete_agent` |

## Trace Structure

Each trace contains:
- **Trace ID**: Unique identifier for the request
- **Spans**: Individual operations within the trace
- **Events**: Timestamped points of interest within a span
- **Attributes**: Key-value pairs with context data
- **Status**: SUCCESS, ERROR, PENDING, or CANCELLED

## Example Trace Flow

```
Trace: discord_message (abc-123)
├── Span: process_message [discord] (2ms)
│   ├── Event: filters_passed
│   └── Event: command_detected
├── Span: handle_command [discord] (5ms)
│   └── Span: generate_image [image_gen] (4500ms)
│       ├── Event: creating_adapter
│       ├── Event: sending_request
│       └── Span: comfyui_generate [comfyui] (4480ms)
│           ├── Event: queueing_prompt
│           ├── Event: prompt_queued
│           ├── Span: comfyui_poll [comfyui] (4000ms)
│           │   └── Event: workflow_completed
│           └── Span: comfyui_fetch_image [comfyui] (80ms)
│               └── Event: image_fetched
└── Event: response_sent
```

## Log Output

Traces are logged at two levels:

### 1. Human-Readable Summary
```
╔══════════════════════════════════════════════════════════════════╗
║  TRACE COMPLETED: abc12345...                                    ║
╠══════════════════════════════════════════════════════════════════╣
║  Duration: 4523.45ms                                             ║
║  Spans: 7                                                        ║
╠══════════════════════════════════════════════════════════════════╣
║  Services Called:                                                ║
║    • discord         (3 spans, 15.2ms, 0 errors)                 ║
║    • image_gen       (1 spans, 4500.1ms, 0 errors)               ║
║    • comfyui         (3 spans, 4485.3ms, 0 errors)               ║
╚══════════════════════════════════════════════════════════════════╝
```

### 2. Structured JSON (for parsing)
```json
{
  "trace_id": "abc-123-xyz",
  "start_time": 1709834567.123,
  "end_time": 1709834571.646,
  "duration_ms": 4523.45,
  "span_count": 7,
  "spans": [
    {
      "span_id": "span-1",
      "trace_id": "abc-123-xyz",
      "name": "comfyui_generate",
      "service": "comfyui",
      "duration_ms": 4480.5,
      "status": "success",
      "attributes": {"prompt_id": "xyz-789"},
      "events": [...]
    }
  ]
}
```

## Configuration

Tracing is enabled by default. To disable:

```bash
# In docker-compose or environment
ENABLE_TRACING=false
```

## Usage Examples

### View Recent Traces
```bash
# View trace summaries
docker logs jennifer 2>&1 | grep "TRACE COMPLETED"

# View structured JSON traces
docker logs jennifer 2>&1 | grep "TRACE_JSON"

# Filter for errors
docker logs jennifer 2>&1 | grep -E "(ERROR|error)"
```

### Debug Specific User
```bash
# Find traces for specific user
docker logs jennifer 2>&1 | grep '"user_id": 123456789'
```

### Performance Analysis
```bash
# Find slow image generations
docker logs jennifer 2>&1 | grep "image_gen" | grep -E "duration_ms.*[0-9]{5,}"
```

## Adding Custom Traces

To add tracing to a new function:

```python
from core.tracing import get_tracer, SpanStatus

tracer = get_tracer()

async def my_function():
    span_id = tracer.start_span("my_operation", "my_service")
    
    try:
        # Add events
        tracer.add_event("step_1_complete")
        
        # Add attributes
        tracer.add_attribute("key", "value")
        
        # Do work...
        result = await do_work()
        
        tracer.end_span(span_id, SpanStatus.SUCCESS)
        return result
        
    except Exception as e:
        tracer.end_span(span_id, SpanStatus.ERROR, str(e))
        raise
```

## Benefits

1. **Debugging**: See exactly where errors occur in the call chain
2. **Performance**: Identify slow operations (e.g., ComfyUI polling)
3. **Monitoring**: Track success/failure rates per service
4. **Understanding**: Visualize the full request lifecycle

## Troubleshooting

### Traces Not Appearing
- Check `ENABLE_TRACING=true` is set
- Verify log level is INFO or DEBUG
- Check disk space for logs

### Missing Spans
- Ensure `tracer.end_span()` is called (use try/finally)
- Check for exceptions that bypass span cleanup

### Performance Impact
- Tracing adds minimal overhead (~1-2ms per trace)
- Disable in production if needed with `ENABLE_TRACING=false`
