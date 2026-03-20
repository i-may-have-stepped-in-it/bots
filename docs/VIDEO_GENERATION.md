# Video Generation in Jennifer

Jennifer now supports AI video generation through two backends:
- **Z.AI API** (cloud-based): CogVideoX-3, ViduQ1, Vidu2
- **FramePack** (local): Self-hosted video generation

## Quick Start

### 1. Configuration

Edit your `config/config.json`:

```json
{
    "VideoBackend": "zai",
    "ZaiAPIKey": "your-zai-api-key",
    "ZaiVideoModel": "CogVideoX-3"
}
```

### 2. Usage

In Discord, use the command:

```
!txt2vid a cat playing the piano in a jazz club
```

For image-to-video (img2vid):

```
!txt2vid make this image move --image path/to/image.jpg
```

## Backend Options

### Z.AI API (Cloud)

**Pros:**
- No local GPU required
- Fast inference
- Multiple models available

**Cons:**
- Requires API key
- Rate limited
- Costs credits

**Available Models:**
- `CogVideoX-3` - High quality, good for most use cases
- `ViduQ1` - Theatrical quality, 1080P
- `Vidu2` - Fast delivery, 720P

**Configuration:**
```json
{
    "VideoBackend": "zai",
    "ZaiAPIKey": "your-api-key",
    "ZaiAPIEndpoint": "https://api.z.ai/api/paas/v4",
    "ZaiVideoModel": "CogVideoX-3",
    "ZaiVideoResolution": "720p",
    "ZaiVideoDuration": 5
}
```

Get your API key from: https://z.ai

### FramePack (Local)

**Pros:**
- No API costs
- Private generation
- Full control

**Cons:**
- Requires powerful GPU
- Setup complexity
- Slower generation

**Prerequisites:**
- NVIDIA GPU with 8GB+ VRAM
- FramePack installed: https://github.com/lllyasviel/FramePack

**Configuration:**
```json
{
    "VideoBackend": "framepack",
    "FramePackURL": "http://localhost:7860",
    "FramePackModel": "FramePack (Original)",
    "FramePackSteps": 25,
    "FramePackWidth": 640,
    "FramePackHeight": 480,
    "FramePackVideoLength": 4.0
}
```

## Command Reference

### !txt2vid

Generate a video from text description.

**Syntax:**
```
!txt2vid <prompt> [--image <image_path>]
```

**Examples:**
```
!txt2vid a serene lake at sunset with mountains in the background
!txt2vid a robot dancing --image my_robot.jpg
!txt2vid cinematic shot of a cyberpunk city
```

**Parameters:**
- `prompt` - Text description of the video (required)
- `--image` - Path to image for img2vid mode (optional)

## Rate Limiting

Video generation is rate-limited to prevent abuse:
- Default: 3 videos per minute
- Configurable via `VideoRateLimit` in config

## Queue System

Video generation uses a persistent queue:
- Tasks survive bot restarts
- Queue status shown in `!status` command
- Failed tasks are retried automatically

## Troubleshooting

### "Video generation not configured"
- Check that `ZaiAPIKey` is set (for Z.AI backend)
- Verify `VideoBackend` is set correctly

### "Rate limit exceeded"
- Wait a minute before generating another video
- Or increase `VideoRateLimit` in config

### FramePack connection errors
- Ensure FramePack is running: `python demo_gradio.py`
- Verify `FramePackURL` matches the Gradio URL
- Check firewall settings

### Z.AI API errors
- Verify your API key is valid
- Check your Z.AI account has available credits
- Check the Z.AI status page

## Architecture

```
!txt2vid command
      ↓
handle_txt2vid_command()
      ↓
Create video Task
      ↓
video_queue (PersistentQueue)
      ↓
_video_worker() (bot/client.py)
      ↓
VideoGenerator.generate()
      ↓
Backend (Z.AI API or FramePack)
      ↓
Discord file upload
```

## Files

- `utils/video_gen.py` - Video generation backends
- `core/config.py` - VideoConfig settings
- `bot/commands/handlers.py` - Command handler
- `bot/client.py` - Video queue worker
