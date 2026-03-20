# Image Generation Workflow Trace

This document traces through the full image generation workflow from configuration to API response.

## Overview

The image generation system now supports three backends:
- **Automatic1111** (default) - Stable Diffusion WebUI
- **ComfyUI** - Node-based workflow system
- **InvokeAI** - Modern RESTful API

## Workflow Steps

### Step 1: Configuration Loading

**Location**: `core/config.py`

**Process**:
1. Load JSON config file
2. Migrate legacy config format to new structure
3. Parse `SDBackend` field (defaults to "automatic1111")
4. Create `JenniferConfig` with nested `SDConfig`

**Example Config**:
```json
{
    "SDBackend": "comfyui",
    "SDURL": "http://localhost:8188",
    "SDmodel": "model.safetensors",
    "SDSteps": 30,
    ...
}
```

**Code Trace**:
```python
config = JenniferConfig.load("config/config.json")
backend = config.sd.backend  # "comfyui"
```

### Step 2: Adapter Creation

**Location**: `integrations/image_generation/adapter_factory.py`

**Process**:
1. Read `SDBackend` from config
2. Look up adapter class in registry
3. Instantiate appropriate adapter
4. Pass config to adapter

**Code Trace**:
```python
from integrations.image_generation import create_adapter_from_config

adapter = create_adapter_from_config(config)
# Returns ComfyUIAdapter instance
```

**Adapter Registry**:
| Alias | Backend |
|-------|---------|
| automatic1111, auto, a1111, webui | Automatic1111 |
| comfyui, comfy | ComfyUI |
| invokeai, invoke | InvokeAI |

### Step 3: Prompt Formatting

**Location**: `integrations/image_generation/prompt_formatter.py`

**Process**:
1. Create `PromptFormatter` with adapter
2. Call `format_prompt()` with user prompt
3. Delegate to adapter's `prepare_payload()`
4. Return backend-specific payload

**Code Trace**:
```python
from integrations.image_generation import PromptFormatter

formatter = PromptFormatter(adapter)
payload = formatter.format_prompt("a beautiful sunset", upscale=False)
```

**Backend-Specific Payloads**:

**Automatic1111**:
```json
{
    "prompt": "masterpiece, best quality a beautiful sunset",
    "steps": 30,
    "width": 512,
    "height": 768,
    "sampler_index": "DPM++ 2M",
    "enable_hr": false,
    "override_settings": {
        "sd_model_checkpoint": "model.ckpt"
    }
}
```

**ComfyUI**:
```json
{
    "prompt": {
        "node_1": {"class_type": "CheckpointLoaderSimple", ...},
        "node_2": {"class_type": "CLIPTextEncode", "inputs": {"text": "masterpiece..."}},
        "node_3": {"class_type": "KSampler", ...},
        ...
    },
    "client_id": "uuid"
}
```

**InvokeAI**:
```json
{
    "prompt": "masterpiece, best quality a beautiful sunset",
    "steps": 30,
    "width": 512,
    "sampler": "dpmpp_2m",
    "scheduler": "auto",
    "model": "model-name"
}
```

### Step 4: Model Checking

**Location**: `utils/image_gen.py::check_current_model()`

**Process**:
1. Fetch current options from backend
2. Parse current model using adapter
3. Compare with configured model
4. Switch model if needed (Automatic1111 only)

**Backend Differences**:
- **Automatic1111**: Full model switching support
- **ComfyUI**: Skipped (model per-workflow)
- **InvokeAI**: Limited support

**Code Trace**:
```python
adapter = create_adapter_from_config(config)
options = await fetch_options(config)
current_model = adapter.parse_current_model(options)

if current_model != config.sd.model:
    switch_payload = adapter.create_model_switch_payload(config.sd.model)
    await post(adapter.get_options_endpoint(), switch_payload)
```

### Step 5: Image Generation

**Location**: `utils/image_gen.py::stable_diffusion_generate_image()`

**Process**:
1. Create adapter and formatter
2. Prepare payload
3. Route to backend-specific handler
4. Make API call
5. Process response

**Backend-Specific Handling**:

**Automatic1111**:
```python
response = await _make_api_call_automatic1111(adapter, config, payload)
image = adapter.process_response(response)
```

**ComfyUI**:
```python
# 1. Queue workflow
queue_response = await post(adapter.get_generation_endpoint(), payload)
prompt_id = queue_response["prompt_id"]

# 2. Poll for completion
result = await adapter.poll_for_result(prompt_id, session)

# 3. Fetch image
image_url = adapter.get_image_endpoint(filename)
image_data = await get(image_url)
image = Image.open(io.BytesIO(image_data))
```

**InvokeAI**:
```python
response = await _make_api_call_automatic1111(adapter, config, payload)
image = adapter.process_response(response)
```

### Step 6: Response Processing

**Location**: Adapter-specific `process_response()` methods

**Process**:
1. Parse response JSON
2. Extract base64 image data
3. Decode and create PIL Image
4. Return image

**Backend-Specific Responses**:

**Automatic1111**:
```json
{
    "images": ["base64encodedstring..."],
    "parameters": {...},
    "info": "..."
}
```

**ComfyUI**:
```json
{
    "prompt_id": "uuid",
    "number": 1,
    "node_errors": {}
}
# Image fetched separately from /view endpoint
```

**InvokeAI**:
```json
{
    "items": [{"image": "base64encodedstring...", "seed": 12345}]
}
# or
{
    "image": "base64encodedstring..."
}
```

### Step 7: Model Listing

**Location**: `utils/image_gen.py::check_models()`

**Process**:
1. Refresh models (if supported)
2. Fetch models list
3. Parse using adapter-specific method
4. Return list of model names

**Code Trace**:
```python
adapter = create_adapter_from_config(config)
models_data = await fetch(adapter.get_models_endpoint())
models = adapter.parse_models_list(models_data)
# Returns: ["model1", "model2", ...]
```

## API Endpoints by Backend

| Endpoint | Automatic1111 | ComfyUI | InvokeAI |
|----------|---------------|---------|----------|
| Generation | `/sdapi/v1/txt2img` | `/prompt` | `/api/v1/images/generate` |
| Options | `/sdapi/v1/options` | `/system_stats` | `/api/v1/app/config` |
| Models | `/sdapi/v1/sd-models` | `/object_info/CheckpointLoaderSimple` | `/api/v1/models/` |
| Refresh | `/sdapi/v1/refresh-checkpoints` | N/A | N/A |
| History | N/A | `/history/{prompt_id}` | N/A |
| Image | N/A | `/view?filename={file}` | N/A |

## Error Handling

### Unknown Backend
```python
create_adapter("unknown", config)
# Raises: ValueError("Unknown backend 'unknown'. Available backends: ...")
```

### API Errors
```python
try:
    response = await make_api_call(adapter, config, payload)
except aiohttp.ClientError as e:
    logging.error(f"HTTP error: {e}")
    return None
```

### Response Processing Errors
```python
try:
    image = adapter.process_response(response)
except ValueError as e:
    logging.error(f"Failed to process response: {e}")
    return None
```

## Performance Considerations

### Adapter Creation
- Adapters are lightweight objects
- Creation time: < 1ms
- Can be created per-request or reused

### Prompt Formatting
- Simple dictionary operations
- Time: < 0.1ms per prompt
- No external dependencies

### ComfyUI Polling
- Polls every 1 second
- Max 300 attempts (5 minutes)
- Configurable in adapter

## Testing

Run the full test suite:
```bash
pytest tests/unit/integrations/image_generation/ -v
pytest tests/integration/test_image_generation_workflow.py -v
```

Test summary:
- 64 adapter unit tests
- 26 workflow integration tests
- 90 total tests (all passing)

## Configuration Examples

### Automatic1111
```json
{
    "SDBackend": "automatic1111",
    "SDURL": "http://localhost:7860",
    "SDmodel": "model.ckpt",
    "SDSteps": 25
}
```

### ComfyUI
```json
{
    "SDBackend": "comfyui",
    "SDURL": "http://localhost:8188",
    "SDmodel": "model.safetensors",
    "SDSteps": 30
}
```

### InvokeAI
```json
{
    "SDBackend": "invokeai",
    "SDURL": "http://localhost:9090",
    "SDmodel": "model-name",
    "SDSteps": 30
}
```

## Migration Guide

### From Old Config (no SDBackend)
No changes needed - defaults to Automatic1111.

### To ComfyUI
1. Set `"SDBackend": "comfyui"`
2. Update `"SDURL"` to ComfyUI port (8188)
3. Ensure model names include `.safetensors` extension

### To InvokeAI
1. Set `"SDBackend": "invokeai"`
2. Update `"SDURL"` to InvokeAI port (9090)
3. Update sampler names if needed (auto-converted)
