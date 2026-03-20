# Jennifer Bot Refactoring

This document describes the refactoring changes made to the Jennifer Discord bot.

## Architecture Changes

### Before
- Single `app.py` file (1059 lines)
- Dict-based configuration
- In-memory queues (lost on restart)
- No health checks
- Monolithic structure

### After
- Modular package structure
- Pydantic-validated configuration
- SQLite-persistent queues (survive restart)
- Health checks and status command
- Clean separation of concerns

## New Directory Structure

```
jennifer/
├── app.py                      # Entry point (simplified)
├── bot/
│   ├── __init__.py
│   ├── client.py              # Discord client, event handlers
│   └── commands/
│       ├── __init__.py
│       ├── handlers.py        # All command handlers
│       └── music.py           # MusicPlayer class
├── core/
│   ├── __init__.py
│   ├── config.py              # Pydantic configuration
│   ├── logging_config.py      # Structured logging
│   └── persistent_queue.py    # SQLite-backed queues
├── integrations/              # External service wrappers
├── utils/                     # Existing utilities
├── data/                      # Persistent data (SQLite)
└── logs/                      # Rotated log files
```

## New Features

### 1. Persistent Queues
Image and message queues are now backed by SQLite. If the container restarts:
- Pending tasks are recovered automatically
- No lost image generations
- Retry logic with exponential backoff

### 2. Health Checks
- `!status` command shows system health
- Docker healthchecks for all services
- Queue depth monitoring

### 3. Better Configuration
- Type-safe Pydantic models
- Auto-migration from legacy JSON format
- No more guessing which endpoint variant to use

### 4. Structured Logging
- JSON format for file logs (machine readable)
- Colored console output (human readable)
- Automatic rotation (10MB x 5 files)

### 5. Resource Limits
All services now have:
- CPU limits
- Memory limits
- Health check endpoints
- Graceful shutdown handling

## Migration Guide

### Step 1: Update Dependencies
```bash
cd jennifer
docker-compose -f docker-compose-jennifer.yml run --rm jennifer pip install -r requirements.txt
```

### Step 2: Run Setup
```bash
# Create data directories and set permissions
docker-compose -f docker-compose-jennifer.yml --profile setup run --rm init
```

### Step 3: Start Services
```bash
# NVIDIA GPU
docker-compose -f docker-compose-jennifer.yml --profile nvidia up -d

# Intel GPU
docker-compose -f docker-compose-jennifer.yml --profile intel up -d
```

### Step 4: Verify
```bash
# Check bot logs
docker logs -f jennifer

# Check status in Discord
!status
```

## Configuration Changes

Your existing `config.json` is fully compatible. The new system:
1. Reads your existing config
2. Auto-migrates to new structure in memory
3. No file changes needed

However, you can optionally clean up your config by removing:
- `OpenClawmodel1` through `OpenClawmodel6` → now `fallback_models` list
- `OpenClawEndpoint1`, `OpenClawEndpoint4` → now `model_endpoints` list
- `OpenClawEmbeddingEndpoint1`, `OpenClawEmbeddingEndpoint3` → now `embedding_endpoints` list

## New Commands

| Command | Description |
|---------|-------------|
| `!status` | Show system health and queue status |
| `!pause` | Pause music playback |
| `!resume` | Resume music playback |

## Changed Behavior

### Model Switching (`!change model`)
- **Before:** Required full bot restart (`os.execv`)
- **After:** Dynamic session update, no restart needed

### Queue Recovery
- **Before:** Lost all pending work on restart
- **After:** Automatically resumes pending tasks

### Error Handling
- **Before:** Silent failures or crashes
- **After:** Proper error messages with retry logic

## Rollback

If you need to rollback:
```bash
# Stop new version
docker-compose -f docker-compose-jennifer.yml down

# Restore backup
cp app.py.backup app.py

# Start old version
docker-compose -f docker-compose-jennifer.yml up -d
```

## Performance Notes

- **Memory:** Slightly higher due to Pydantic models (~10-20MB)
- **Disk:** SQLite queues use ~1-2MB per 1000 tasks
- **CPU:** No significant change
- **Startup:** ~1-2 seconds slower due to queue recovery

## Troubleshooting

### Bot won't start
Check logs:
```bash
docker logs jennifer
```

Common issues:
- Missing `data/` or `logs/` directories → Run setup profile
- Permission errors → Check volume mounts
- Config parse errors → Validate JSON syntax

### Commands not working
- Ensure you're using `!` prefix or mentioning the bot
- Check `!status` to verify backend services
- Verify you're in allowed channels

### Queue not processing
```bash
# Check queue status in bot logs
docker logs jennifer | grep -i queue

# Check database
sqlite3 data/image_queue.db "SELECT * FROM tasks WHERE status='pending';"
```
