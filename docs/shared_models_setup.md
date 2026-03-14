# Shared Models and Output Directory Setup

This document describes the shared directory structure for all image generation backends (Automatic1111, ComfyUI, InvokeAI).

## Directory Structure

```
stable-diffusion-webui-docker/
├── data/                          # Shared data directory
│   ├── models/                    # Shared models directory
│   │   ├── Stable-diffusion/      # SD checkpoints (.ckpt, .safetensors)
│   │   ├── VAE/                   # VAE models
│   │   ├── Lora/                  # LoRA adapters
│   │   ├── ControlNet/            # ControlNet models
│   │   ├── ESRGAN/                # Upscalers
│   │   ├── embeddings/            # Textual inversion embeddings
│   │   └── ...
│   ├── embeddings/                # Textual inversion embeddings (legacy)
│   ├── config/                    # Configuration files
│   └── .cache/                    # Cache directory
├── output/                        # Shared output directory
│   ├── txt2img/                   # Text-to-image outputs
│   ├── img2img/                   # Image-to-image outputs
│   └── saved/                     # Saved images
└── config/                        # Bot configuration
    └── sd-webui/                  # A1111-specific config
```

## Backend-Specific Mappings

### Automatic1111 (stable-diffusion-jennifer)

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `../data` | `/data` | All data including models |
| `../output` | `/output` | Generated images |
| `./config/sd-webui` | `/data/config/auto` | A1111 configuration |

**Model paths inside container:**
- `/data/models/Stable-diffusion/` - Main checkpoints
- `/data/models/VAE/` - VAE models
- `/data/models/Lora/` - LoRA adapters
- `/data/models/ControlNet/` - ControlNet
- `/data/embeddings/` - Textual inversion

### ComfyUI (comfyui-jennifer)

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `../data/comfyui` | `/root/ComfyUI` | ComfyUI app data |
| `../data/models/Stable-diffusion` | `/root/ComfyUI/models/checkpoints` | Main checkpoints (ro) |
| `../data/models/VAE` | `/root/ComfyUI/models/vae` | VAE models (ro) |
| `../data/models/Lora` | `/root/ComfyUI/models/loras` | LoRA adapters (ro) |
| `../data/models/ControlNet` | `/root/ComfyUI/models/controlnet` | ControlNet (ro) |
| `../data/models/ESRGAN` | `/root/ComfyUI/models/upscale_models` | Upscalers (ro) |
| `../data/embeddings` | `/root/ComfyUI/models/embeddings` | Embeddings (ro) |
| `../output` | `/root/ComfyUI/output` | Generated images |
| `../data/comfyui/custom_nodes` | `/root/ComfyUI/custom_nodes` | Custom nodes |

**Note:** ComfyUI has a different model directory structure than A1111. Models are mapped read-only (`:ro`) to prevent accidental modification.

**Docker Images:** `yanwk/comfyui-boot:cu128-slim` (NVIDIA CUDA 12.8), `yanwk/comfyui-boot:cpu` (CPU only)

### InvokeAI (invokeai-jennifer)

| Host Path | Container Path | Purpose |
|-----------|----------------|---------|
| `../data/invokeai` | `/invokeai` | InvokeAI app data |
| `../data/models` | `/invokeai/models-import` | All models for import (ro) |
| `../data/models/Stable-diffusion` | `/invokeai/models/sd-main` | Main checkpoints (ro) |
| `../data/models/VAE` | `/invokeai/models/vae` | VAE models (ro) |
| `../data/models/Lora` | `/invokeai/models/lora` | LoRA adapters (ro) |
| `../data/models/ControlNet` | `/invokeai/models/controlnet` | ControlNet (ro) |
| `../output` | `/invokeai/outputs` | Generated images |

**Note:** InvokeAI maintains its own model database. It will scan the imported models and create its own database entries on first run.

**Docker Image:** `ghcr.io/invoke-ai/invokeai:latest` (GitHub Container Registry, not Docker Hub)

**Note:** InvokeAI uses the `latest` tag for both CUDA and CPU versions. GPU support is determined by the Docker runtime and environment variables, not the image tag.

## Required Directories

The following directories must exist before starting the services:

### For Automatic1111
```bash
mkdir -p data/models/Stable-diffusion
mkdir -p data/models/VAE
mkdir -p data/models/Lora
mkdir -p data/embeddings
mkdir -p output/txt2img
mkdir -p output/img2img
```

### For ComfyUI
```bash
mkdir -p data/comfyui/custom_nodes
mkdir -p output  # Shared with A1111
```

### For InvokeAI
```bash
mkdir -p data/invokeai
mkdir -p output  # Shared with A1111
```

## Setup Script

Run the provided setup script to create all required directories:

```bash
# On Linux/Mac
bash scripts/setup_shared_dirs.sh

# On Windows (PowerShell)
.\scripts\setup_shared_dirs.ps1
```

## Model Compatibility

### Supported Model Formats

All backends support:
- **Checkpoints**: `.safetensors`, `.ckpt`
- **VAE**: `.safetensors`, `.pt`, `.ckpt`
- **LoRA**: `.safetensors`
- **ControlNet**: `.safetensors`, `.pth`
- **Embeddings**: `.pt`, `.safetensors`

### Model Organization Tips

1. **Keep original filenames** - Some backends parse version info from filenames
2. **Use subdirectories for organization** - e.g., `models/Stable-diffusion/SDXL/`, `models/Stable-diffusion/SD1.5/`
3. **Remove broken models** - Corrupted models can cause all backends to fail loading

## Shared Output Benefits

All backends write to `../output`:
- **Consistent location** - Find all generated images in one place
- **No duplication** - Same image not stored in multiple locations
- **Easy backup** - Back up one directory for all outputs
- **Cross-backend workflow** - Generate in one backend, edit in another

Output subdirectories:
- `txt2img/` - Text-to-image generations
- `img2img/` - Image-to-image generations
- `saved/` - Manually saved images
- `extras/` - Post-processed images

## Troubleshooting

### Models Not Showing Up

**ComfyUI:**
- Check that models are in the correct host directory
- Verify read-only mount isn't blocking model detection
- Refresh ComfyUI browser or restart service

**InvokeAI:**
- InvokeAI needs to scan models on first run (can take several minutes)
- Check InvokeAI logs for scan progress
- Models may need to be "imported" via InvokeAI's interface

### Permission Issues

```bash
# Fix permissions on Linux/Mac
chmod -R 755 data/models
chmod -R 755 output

# On Windows, ensure Docker Desktop has access to the directories
```

### Disk Space

Models are shared (not duplicated), but each backend may create:
- Cache files in their app directories
- Model database/index files
- Temporary files during generation

Monitor disk usage:
```bash
du -sh data/models      # Model storage
du -sh output           # Output storage
du -sh data/*           # Per-backend storage
```

## Migration from Separate Installations

If you previously had separate model directories:

1. **Backup existing models**
2. **Consolidate to shared structure**:
   ```bash
   # Example: Move ComfyUI models to shared location
   mv comfyui/models/checkpoints/* data/models/Stable-diffusion/
   mv comfyui/models/vae/* data/models/VAE/
   ```
3. **Update docker-compose** to use new mappings
4. **Restart services**

## Security Notes

- Model mounts are read-only (`:ro`) for ComfyUI and InvokeAI to prevent accidental modification
- A1111 has read-write access for model management features
- Output directory is read-write for all backends
