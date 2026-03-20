# Jennifer Discord Bot - Agent Documentation

> **For AI Coding Agents**: This document provides essential context for working with the Jennifer Discord bot codebase.

## Project Overview

**Jennifer** is a human-like Discord AI bot designed to provide engaging, personality-driven conversations. The bot uses Large Language Models (LLMs) to generate contextual responses and can produce images via Stable Diffusion when prompted.

### Key Capabilities
- AI-powered conversational responses using OpenAI-compatible APIs
- Persistent per-user conversation memory
- Image generation via Automatic1111 Stable Diffusion API
- Voice channel integration with speech recognition (Whisper) and TTS
- Music playback from URLs (YouTube, etc.)
- Integration with OpenClaw Gateway for advanced agent management

## Technology Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12 |
| Discord Library | discord.py (custom fork for voice receive) |
| Configuration | JSON with Pydantic validation |
| Task Queues | SQLite-backed persistent queues (aiosqlite) |
| Logging | Structured JSON logging with rotation |
| Containerization | Docker + Docker Compose |
| AI Backends | LocalAI, OpenClaw Gateway, vLLM |
| Image Gen | Automatic1111 Stable Diffusion |

## Project Structure

```
jennifer/
├── app.py                      # Entry point (refactored, minimal)
├── entrypoint.sh               # Container startup script
├── requirements.txt            # Python dependencies
├── config.json.template        # Configuration template
├── Dockerfile                  # Main bot container
├── docker-compose-jennifer.yml # Multi-service orchestration
│
├── bot/                        # Discord bot implementation
│   ├── client.py              # JenniferBot class, event handlers
│   └── commands/
│       ├── handlers.py        # Command routing and implementations
│       └── music.py           # Voice channel music player
│
├── core/                       # Core infrastructure
│   ├── config.py              # Pydantic configuration models
│   ├── logging_config.py      # Structured logging setup
│   └── persistent_queue.py    # SQLite-backed task queues
│
├── utils/                      # Utility modules
│   ├── interactions.py        # Message processing, history management
│   ├── openclaw.py            # OpenClaw Gateway client
│   ├── image_gen.py           # Stable Diffusion integration
│   ├── voice_recv_class.py    # Voice recognition handler
│   ├── music.py               # Music playback utilities
│   ├── model_router.py        # Intelligent model selection
│   └── discord-ext-voice-recv/ # Custom discord.py voice extension
│
├── integrations/               # External service integrations (empty)
├── config/                     # Runtime configuration (mounted volume)
├── data/                       # Persistent data (SQLite queues)
├── logs/                       # Rotated log files
└── letta/                      # Letta deployment data (PostgreSQL)
```

## Configuration System

### Config File Location
- **Development**: `config/config.json`
- **Template**: `config.json.template`

### Key Configuration Sections

```python
# From core/config.py - Pydantic models
JenniferConfig:          # Main configuration
├── name: str           # Bot name (default: "Jennifer")
├── personality: str    # System personality prompt
├── appearance: str     # Visual description
├── discord_token: str  # Discord bot token
├── allowed_channels: List[int]    # Channel whitelist
├── ignored_users: List[int]       # User blacklist
├── power_users: List[int]         # Admin users
├── sd: SDConfig                    # Stable Diffusion settings
├── openclaw: OpenClawConfig       # OpenClaw Gateway config
└── voice: VoiceConfig             # TTS/STT settings
```

### Legacy Config Migration
The system auto-migrates legacy flat config format (e.g., `OpenClawmodel1` through `OpenClawmodel6`) to the new nested structure via `JenniferConfig._migrate_legacy()`.

## Build and Run Commands

### Prerequisites
- Docker and Docker Compose
- NVIDIA GPU (optional, for `nvidia` profile)
- Intel GPU (optional, for `intel` profile)

### Setup (First Time)
```bash
# Create data directories and set permissions
docker-compose -f docker-compose-jennifer.yml --profile setup run --rm init
```

### Development Build
```bash
# Build the bot image
docker-compose -f docker-compose-jennifer.yml build jennifer
```

### Running the Bot

**With NVIDIA GPU (full stack):**
```bash
docker-compose -f docker-compose-jennifer.yml --profile nvidia up -d
```

**With Intel GPU:**
```bash
docker-compose -f docker-compose-jennifer.yml --profile intel up -d
```

**Bot only (connects to external backends):**
```bash
docker-compose -f docker-compose-jennifer.yml up -d jennifer
```

### Viewing Logs
```bash
# Follow bot logs
docker logs -f jennifer

# View logs with grep
docker logs jennifer 2>&1 | grep -i error
```

### Stopping
```bash
docker-compose -f docker-compose-jennifer.yml down
```

## Code Style Guidelines

### Python Style
- **Follow PEP 8** with 4-space indentation
- **Maximum line length**: 100 characters
- **Docstrings**: Google-style docstrings for all public functions/classes
- **Type hints**: Use typing annotations where practical
- **Imports**: Group as: stdlib, third-party, local (each group alphabetically)

### Naming Conventions
- **Classes**: `PascalCase` (e.g., `JenniferBot`, `PersistentQueue`)
- **Functions/Variables**: `snake_case` (e.g., `handle_command`, `image_queue`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `YTDL_FORMAT_OPTIONS`)
- **Private**: Leading underscore (e.g., `_cleanup_task`)

### Async Patterns
- All Discord event handlers are `async`
- Use `asyncio.Queue` for in-memory queuing
- Database operations use `aiosqlite` for async SQLite
- Background tasks are created with `loop.create_task()`

### Error Handling
```python
# Preferred pattern
try:
    result = await some_async_operation()
except SpecificException as e:
    logger.exception(f"Contextual message: {e}")
    # Handle or re-raise
except Exception as e:
    logger.exception(f"Unexpected error in function_name: {e}")
    raise  # Re-raise unexpected errors
```

## Architecture Patterns

### Bot Client (`bot/client.py`)
The `JenniferBot` class extends `discord.AutoShardedClient`:
- **Setup Hook**: Initializes databases, loads histories, starts workers
- **Event Handlers**: `on_ready`, `on_message`, `on_voice_state_update`
- **Background Workers**: Image generation worker, message processing worker
- **Graceful Shutdown**: Saves data, cancels workers, closes connections

### Command Routing (`bot/commands/handlers.py`)
Commands are routed via prefix matching:
```python
handlers = [
    ("!draw", handle_draw_command),
    ("!play", handle_play_command),
    # ... more handlers
]
```

### Persistent Queues (`core/persistent_queue.py`)
- Tasks survive container restarts
- In-memory queue for speed, SQLite for durability
- Automatic retry with exponential backoff
- Periodic cleanup of old completed tasks

### Task Flow
1. User sends message/command
2. `on_message` validates and routes
3. Task created and added to appropriate queue
4. Background worker processes task
5. Result sent to Discord channel

## Testing

### No Formal Test Suite
This project does **not** currently have automated tests. Testing is manual:

1. **Unit Testing**: Test individual utilities in Python REPL
2. **Integration**: Run bot locally with test Discord server
3. **Commands**: Verify each `!command` responds correctly

### Manual Testing Checklist
```bash
# Test basic connectivity
!status          # Should show all services green

# Test conversation
Hello Jennifer   # Should get personality-driven response

# Test commands
!draw a cat      # Should generate image
!help            # Should show command list
!join_vc         # Should join voice channel
!play <url>      # Should play music
```

## Deployment Considerations

### Security
- **Never commit** `config/config.json` (contains secrets)
- **Never commit** `.env` (contains API keys)
- Use `config.json.template` as reference
- Discord tokens and API keys are in the config file

### Resource Limits (docker-compose)
```yaml
# jennifer service
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 8G
    reservations:
      memory: 2G
```

### Health Checks
- Bot: File-based (`/app/healthy`)
- LocalAI: HTTP `/readyz` endpoint
- Stable Diffusion: HTTP `/sdapi/v1/memory` endpoint

### Volumes
- `./config/` → `/app/config/` (config files)
- `./data/` → `/app/data/` (SQLite databases)
- `./logs/` → `/app/logs/` (rotated logs)
- `./nltk_data/` → `/home/appuser/nltk_data` (NLTK corpora)

## Common Tasks

### Adding a New Command
1. Add handler function in `bot/commands/handlers.py`
2. Add entry to `handlers` list in `handle_command()`
3. Add help text in `handle_help_command()`

### Modifying Configuration
1. Update Pydantic model in `core/config.py`
2. Add migration logic in `_migrate_legacy()` if needed
3. Update `config.json.template`

### Adding a New Integration
1. Create module in `integrations/` or `utils/`
2. Import and use in `bot/commands/handlers.py`
3. Add configuration to `JenniferConfig` if needed

## Troubleshooting

### Bot Won't Start
```bash
# Check config syntax
python -c "import json; json.load(open('config/config.json'))"

# Check logs
docker logs jennifer
```

### Queue Not Processing
```bash
# Check queue status
sqlite3 data/image_queue.db "SELECT * FROM tasks WHERE status='pending';"
```

### Voice Not Working
- Ensure `discord-ext-voice-recv` is installed
- Verify FFmpeg is available in container
- Check voice channel permissions

## External Dependencies

### Required Services (for full functionality)
| Service | Default URL | Purpose |
|---------|-------------|---------|
| LocalAI | `http://localhost:38078` | LLM inference |
| Stable Diffusion | `http://localhost:7860` | Image generation |
| OpenClaw Gateway | Configurable | Advanced agent management |

### Python Package Highlights
- `discord.py` - Discord API wrapper
- `pydantic>=2.0` - Configuration validation
- `aiosqlite>=0.19.0` - Async SQLite
- `yt-dlp` - YouTube/audio extraction
- `openai-whisper` - Speech recognition
- `torch`, `transformers`, `diffusers` - ML libraries

## Development Workflow

1. **Make changes** to source files
2. **Test locally** with `docker-compose up --build`
3. **Check logs** for errors
4. **Verify commands** work in test Discord server
5. **Commit** (do not commit config files with secrets)

## Contact & References

- **Original inspiration**: Modified clone of [IsaBot](https://github.com/Raw-Darkness/IsaBot)
- **Project language**: English (all code and documentation)
- **Primary deployment**: Docker Compose on Linux hosts
