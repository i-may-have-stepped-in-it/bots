# Docker Profile Migration Summary

## Overview

The Docker Compose profiles have been reorganized to provide clearer separation between the three Stable Diffusion backends (Automatic1111, ComfyUI, InvokeAI).

## Changes Made

### 1. New Profile Names

| Old Profile | New Profile | Container Name |
|-------------|-------------|----------------|
| `nvidia` | `sd-a1111-nvidia` | `jennifer-sd-a1111-nvidia` |
| `intel` | `sd-a1111-cpu` | `jennifer-sd-a1111-cpu` |
| `comfyui-nvidia` | `sd-comfyui-nvidia` | `jennifer-sd-comfyui-nvidia` |
| `comfyui-cpu` | `sd-comfyui-cpu` | `jennifer-sd-comfyui-cpu` |
| `invokeai-nvidia` | `sd-invokeai-nvidia` | `jennifer-sd-invokeai-nvidia` |
| `invokeai-cpu` | `sd-invokeai-cpu` | `jennifer-sd-invokeai-cpu` |
| `nvidia` (LLM) | `llm-nvidia` | `jennifer-llm-nvidia` |
| `intel` (LLM) | `llm-intel` | `jennifer-llm-intel` |
| `cpu` (LLM) | `llm-cpu` | `jennifer-llm-cpu` |

### 2. Files Created/Updated

#### New Files:
- `docker-compose-jennifer-updated.yml` - Updated compose with new profiles
- `scripts/switch-sd-backend.sh` - Helper script to switch backends
- `docs/DOCKER_PROFILES.md` - Comprehensive profile documentation
- `docs/PROFILE_MIGRATION_SUMMARY.md` - This file

#### Updated Files:
- `Makefile` - Added convenient targets for each backend

### 3. New Makefile Targets

```bash
# Quick start with different backends
make sd-a111        # Automatic1111 + LLM (NVIDIA)
make sd-comfy       # ComfyUI + LLM (NVIDIA)
make sd-invoke      # InvokeAI + LLM (NVIDIA)

# CPU variants
make sd-a111-cpu    # Automatic1111 + LLM (CPU)
make sd-comfy-cpu   # ComfyUI + LLM (CPU)
make sd-invoke-cpu  # InvokeAI + LLM (CPU)

# Management
make all            # Full NVIDIA stack
make stop           # Stop all services
make logs           # View bot logs
make status         # Show container status
make switch         # Switch backend (see below)
```

## Migration Steps

### Step 1: Backup Current Setup
```bash
cp docker-compose-jennifer.yml docker-compose-jennifer.yml.backup.$(date +%Y%m%d)
```

### Step 2: Apply New Compose File
```bash
cp docker-compose-jennifer-updated.yml docker-compose-jennifer.yml
```

### Step 3: Stop Old Containers
```bash
docker-compose down

# Remove old containers if they persist
docker rm -f stable-diffusion-jennifer comfyui-jennifer invokeai-jennifer 2>/dev/null || true
```

### Step 4: Start with New Profiles

#### Option A: Using Make (Recommended)
```bash
# For ComfyUI with GPU
make sd-comfy

# For Automatic1111 with GPU
make sd-a111

# For InvokeAI with GPU
make sd-invoke
```

#### Option B: Using Docker Compose Directly
```bash
# ComfyUI + LLM (NVIDIA GPU)
docker-compose --profile sd-comfyui-nvidia --profile llm-nvidia up -d

# A1111 + LLM (NVIDIA GPU)
docker-compose --profile sd-a1111-nvidia --profile llm-nvidia up -d

# InvokeAI + LLM (NVIDIA GPU)
docker-compose --profile sd-invokeai-nvidia --profile llm-nvidia up -d
```

#### Option C: Using the Switch Script
```bash
# Make script executable (Linux/Mac)
chmod +x scripts/switch-sd-backend.sh

# Switch to ComfyUI
./scripts/switch-sd-backend.sh comfyui nvidia

# Switch to A1111
./scripts/switch-sd-backend.sh a1111 nvidia

# Switch to InvokeAI CPU
./scripts/switch-sd-backend.sh invokeai cpu
```

## Profile Reference

### SD Backend Profiles (Choose One)

| Profile | Description | Default Port |
|---------|-------------|--------------|
| `sd-a1111-nvidia` | Automatic1111 WebUI with NVIDIA GPU | 7860 |
| `sd-a1111-cpu` | Automatic1111 WebUI CPU-only | 7860 |
| `sd-comfyui-nvidia` | ComfyUI with NVIDIA GPU | 8188 |
| `sd-comfyui-cpu` | ComfyUI CPU-only | 8188 |
| `sd-invokeai-nvidia` | InvokeAI with NVIDIA GPU | 9090 |
| `sd-invokeai-cpu` | InvokeAI CPU-only | 9090 |

### LLM Backend Profiles (Optional)

| Profile | Description | Default Port |
|---------|-------------|--------------|
| `llm-nvidia` | LocalAI with NVIDIA GPU | 38078 |
| `llm-intel` | LocalAI with Intel GPU | 38078 |
| `llm-cpu` | LocalAI CPU-only | 38078 |

### Convenience Profiles

| Profile | Description |
|---------|-------------|
| `all` | Full NVIDIA stack (A1111 + LLM) |
| `all-cpu` | Full CPU-only stack |
| `setup` | One-time initialization |
| `bot-only` | Bot without SD/LLM |

## Port Exposure Changes

All SD services now expose ports on **all interfaces** (not just localhost):

```yaml
# Before:
ports:
  - "127.0.0.1:8188:8188"  # Only localhost

# After:
ports:
  - "8188:8188"  # All interfaces (needed for Tailscale)
```

This allows the bot to connect via Tailscale network addresses.

## Config.json Updates

When switching backends, the `SDBackend` config value must match:

```json
// For A1111
{
  "SDBackend": "automatic1111",
  "SDURL": "http://localhost:7860"
}

// For ComfyUI
{
  "SDBackend": "comfyui",
  "SDURL": "http://localhost:7860",
  "SDComfyURL": "http://localhost:8188"
}

// For InvokeAI
{
  "SDBackend": "invokeai",
  "SDURL": "http://localhost:7860",
  "SDInvokeURL": "http://localhost:9090"
}
```

The `switch-sd-backend.sh` script handles this automatically.

## Validation

After migration, verify everything works:

```bash
# Check running containers
make status

# View logs
make logs

# Test image generation in Discord
!draw a beautiful sunset
```

## Rollback

If you need to rollback:

```bash
cp docker-compose-jennifer.yml.backup.YYYYMMDD docker-compose-jennifer.yml
docker-compose down
docker-compose --profile comfyui-nvidia up -d  # Use old profile names
```

## Troubleshooting

### Issue: "profile not found"
**Solution:** Ensure you're using the updated docker-compose file:
```bash
docker-compose -f docker-compose-jennifer.yml config --profiles
```

### Issue: "port already in use"
**Solution:** Kill existing processes or change ports in docker-compose.yml
```bash
sudo lsof -i :7860  # Check what's using port 7860
```

### Issue: Container name conflicts
**Solution:** Remove old containers:
```bash
docker rm -f stable-diffusion-jennifer comfyui-jennifer invokeai-jennifer 2>/dev/null || true
```
