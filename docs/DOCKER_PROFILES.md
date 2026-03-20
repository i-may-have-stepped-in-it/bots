# Docker Compose Profile Guide

## Overview

Jennifer Bot uses Docker Compose profiles to manage different Stable Diffusion backends and hardware configurations. This allows you to easily switch between A1111, ComfyUI, and InvokeAI.

## Profile Structure

### SD Backend Profiles (Choose One)

| Profile | Backend | Hardware | Port | Description |
|---------|---------|----------|------|-------------|
| `sd-a1111-nvidia` | Automatic1111 | NVIDIA GPU | 7860 | WebUI with GPU acceleration |
| `sd-a1111-cpu` | Automatic1111 | CPU only | 7860 | WebUI CPU-only mode |
| `sd-comfyui-nvidia` | ComfyUI | NVIDIA GPU | 8188 | Node-based workflow with GPU |
| `sd-comfyui-cpu` | ComfyUI | CPU only | 8188 | Node-based workflow CPU-only |
| `sd-invokeai-nvidia` | InvokeAI | NVIDIA GPU | 9090 | InvokeAI with GPU |
| `sd-invokeai-cpu` | InvokeAI | CPU only | 9090 | InvokeAI CPU-only |

### LLM/Text Backend Profiles (Optional)

| Profile | Backend | Hardware | Port | Description |
|---------|---------|----------|------|-------------|
| `llm-nvidia` | LocalAI | NVIDIA GPU | 38078 | LLM with GPU acceleration |
| `llm-intel` | LocalAI | Intel GPU | 38078 | LLM with Intel acceleration |
| `llm-cpu` | LocalAI | CPU only | 38078 | LLM CPU-only mode |

### Convenience Profiles

| Profile | Description |
|---------|-------------|
| `all` | Full stack with NVIDIA GPU (A1111 + LLM) |
| `all-cpu` | Full stack CPU-only |
| `setup` | One-time initialization tasks |
| `bot-only` | Just the bot (no SD or LLM) |

## Usage Examples

### Start with ComfyUI (NVIDIA GPU)
```bash
docker-compose --profile sd-comfyui-nvidia --profile llm-nvidia up -d
```

### Start with Automatic1111 (NVIDIA GPU)
```bash
docker-compose --profile sd-a1111-nvidia --profile llm-nvidia up -d
```

### Start with InvokeAI (CPU)
```bash
docker-compose --profile sd-invokeai-cpu --profile llm-cpu up -d
```

### Full Stack (NVIDIA GPU)
```bash
docker-compose --profile all up -d
```

### Bot Only (No Image Generation)
```bash
docker-compose --profile bot-only --profile llm-nvidia up -d
```

## Switching Backends

### Method 1: Using the Helper Script
```bash
# Switch to ComfyUI with GPU
./scripts/switch-sd-backend.sh comfyui nvidia

# Switch to A1111 CPU-only
./scripts/switch-sd-backend.sh a1111 cpu

# Switch to InvokeAI with GPU
./scripts/switch-sd-backend.sh invokeai nvidia
```

### Method 2: Manual Switch
```bash
# 1. Stop current SD containers
docker-compose -f docker-compose-jennifer.yml stop sd-a1111-nvidia sd-comfyui-nvidia sd-invokeai-nvidia

# 2. Update config.json (set SDBackend to "comfyui", "automatic1111", or "invokeai")

# 3. Start new backend
docker-compose -f docker-compose-jennifer.yml --profile sd-comfyui-nvidia up -d
```

## Container Names

After the update, containers follow this naming convention:

| Old Name | New Name |
|----------|----------|
| `stable-diffusion-jennifer` | `jennifer-sd-a1111-nvidia` |
| `stable-diffusion-jennifer-intel` | `jennifer-sd-a1111-cpu` |
| `comfyui-jennifer` | `jennifer-sd-comfyui-nvidia` |
| `comfyui-jennifer-cpu` | `jennifer-sd-comfyui-cpu` |
| `invokeai-jennifer` | `jennifer-sd-invokeai-nvidia` |
| `invokeai-jennifer-cpu` | `jennifer-sd-invokeai-cpu` |
| `jennifer-text-backend-nvidia` | `jennifer-llm-nvidia` |
| `jennifer-text-backend-intel` | `jennifer-llm-intel` |
| `jennifer-text-backend-cpu` | `jennifer-llm-cpu` |

## Migration from Old Profile Names

### Old vs New Profiles

| Old Profile | New Profile |
|-------------|-------------|
| `nvidia` | `sd-a1111-nvidia` |
| `intel` | `sd-a1111-cpu` |
| `comfyui-nvidia` | `sd-comfyui-nvidia` |
| `comfyui-cpu` | `sd-comfyui-cpu` |
| `invokeai-nvidia` | `sd-invokeai-nvidia` |
| `invokeai-cpu` | `sd-invokeai-cpu` |

### Migration Steps

1. **Backup your current setup:**
   ```bash
   cp docker-compose-jennifer.yml docker-compose-jennifer.yml.backup
   ```

2. **Replace the docker-compose file:**
   ```bash
   cp docker-compose-jennifer-updated.yml docker-compose-jennifer.yml
   ```

3. **Update your startup scripts/aliases:**
   ```bash
   # Old command
   docker-compose --profile comfyui-nvidia up -d
   
   # New command
   docker-compose --profile sd-comfyui-nvidia --profile llm-nvidia up -d
   ```

4. **Restart containers:**
   ```bash
   docker-compose down
   docker-compose --profile sd-comfyui-nvidia --profile llm-nvidia up -d
   ```

## Configuration

### config.json Backend Settings

When switching backends, update `config.json`:

```json
{
  "SDBackend": "comfyui",
  "SDURL": "http://localhost:7860",
  "SDComfyURL": "http://localhost:8188",
  "SDInvokeURL": "http://localhost:9090"
}
```

The `switch-sd-backend.sh` script does this automatically.

## Troubleshooting

### Port Conflicts

If you see "port already in use" errors:
```bash
# Check what's using the port
sudo lsof -i :7860  # A1111
sudo lsof -i :8188  # ComfyUI
sudo lsof -i :9090  # InvokeAI

# Kill the process or use different ports in docker-compose
```

### Container Name Conflicts

If old container names conflict:
```bash
# Remove old containers
docker-compose down
docker rm -f stable-diffusion-jennifer comfyui-jennifer invokeai-jennifer 2>/dev/null || true

# Start with new profiles
docker-compose --profile sd-comfyui-nvidia up -d
```

### Profile Not Found

If you get "profile not found" errors:
```bash
# Verify you're using the updated docker-compose file
docker-compose -f docker-compose-jennifer.yml config --profiles

# Should list: setup, sd-a1111-nvidia, sd-a1111-cpu, sd-comfyui-nvidia, etc.
```

## Makefile Targets (Recommended)

Add these to your `Makefile` for convenience:

```makefile
# Stable Diffusion Backends
.PHONY: sd-a111 sd-comfy sd-invoke

sd-a111:
	docker-compose --profile sd-a1111-nvidia --profile llm-nvidia up -d

sd-comfy:
	docker-compose --profile sd-comfyui-nvidia --profile llm-nvidia up -d

sd-invoke:
	docker-compose --profile sd-invokeai-nvidia --profile llm-nvidia up -d

# CPU variants
sd-a111-cpu:
	docker-compose --profile sd-a1111-cpu --profile llm-cpu up -d

sd-comfy-cpu:
	docker-compose --profile sd-comfyui-cpu --profile llm-cpu up -d

# Full stack
all:
	docker-compose --profile all up -d

# Stop all
stop:
	docker-compose down
```

Usage:
```bash
make sd-comfy    # Start with ComfyUI
make sd-a111     # Start with A1111
make stop        # Stop everything
```
