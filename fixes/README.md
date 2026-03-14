# Jennifer Bot Fixes

This directory contains automated fix scripts for identified issues.

## Quick Start

### Apply All Phase 1 Fixes (Critical)

```bash
cd /path/to/jennifer
python fixes/apply_all_phase1.py
```

This will:
1. ✅ Fix voice recognition syntax errors
2. ✅ Remove hardcoded SSH credentials
3. ✅ Fix image rate limiting (shared TokenBucket)
4. ✅ Add health check file creation

### Apply Individual Fixes

```bash
# Fix voice syntax only
python fixes/phase1/fix_voice_syntax.py

# Fix teamviewer security
python fixes/phase1/fix_teamviewer.py

# Fix rate limiting
python fixes/phase1/fix_token_bucket.py

# Add health checks
python fixes/phase1/fix_health_check.py
```

## Fix Details

### Phase 1: Critical (Apply Immediately)

#### 1. Voice Recognition Syntax Fix
- **Issue:** Broken indentation, misplaced `else` clause, unreachable code
- **File:** `utils/voice_recv_class.py`
- **Impact:** Voice features completely broken
- **Risk if not fixed:** Bot crashes when joining voice channel

#### 2. Teamviewer Security Fix
- **Issue:** Hardcoded SSH password and IP address
- **File:** `utils/teamviewer.py`
- **Impact:** Security vulnerability - credentials exposed in code
- **Risk if not fixed:** Unauthorized server access

#### 3. Token Bucket Rate Limiting Fix
- **Issue:** New TokenBucket instance created per function call
- **File:** `utils/image_gen.py`
- **Impact:** Rate limiting doesn't work across requests
- **Risk if not fixed:** API abuse, potential bans

#### 4. Health Check Fix
- **Issue:** Docker health check expects `/app/healthy` file that never gets created
- **File:** `bot/client.py`
- **Impact:** Docker marks container as unhealthy, may restart repeatedly
- **Risk if not fixed:** Unstable deployments

## Backups

All fix scripts create `.bak` files before modifying. To restore:

```bash
# Restore specific file
cp utils/voice_recv_class.py.bak utils/voice_recv_class.py

# Restore all
git checkout -- utils/ utils/teamviewer.py utils/image_gen.py bot/client.py
```

## Verification

After applying fixes:

```bash
# Check Python syntax
python -m py_compile utils/voice_recv_class.py
python -m py_compile utils/teamviewer.py
python -m py_compile utils/image_gen.py
python -m py_compile bot/client.py

# Check for hardcoded secrets
grep -r "password" utils/teamviewer.py || echo "No hardcoded passwords found"

# Build and test
docker-compose -f docker-compose-jennifer.yml build jennifer
docker-compose -f docker-compose-jennifer.yml up -d
```

## Environment Variables

After applying the teamviewer fix, add to your `.env`:

```bash
# TeamViewer SSH Configuration
TEAMVIEWER_SSH_HOST=192.168.128.134
TEAMVIEWER_SSH_USER=bot
TEAMVIEWER_SSH_KEY_PATH=/app/config/teamviewer_key
```

And mount your SSH key in docker-compose:

```yaml
volumes:
  - ./config/teamviewer_key:/app/config/teamviewer_key:ro
```

## Phase 2+ Fixes

Phase 2 and later fixes require manual implementation. See `ACTION_PLAN.md` for:
- Permission checks
- Connection pooling
- Atomic file writes
- Architecture refactoring
- Monitoring and metrics

## Troubleshooting

### Fix script fails

```bash
# Check Python version
python --version  # Need 3.11+

# Run with verbose output
python -v fixes/apply_all_phase1.py
```

### Syntax errors after fix

The scripts automatically verify syntax. If they fail:
1. Check the backup file exists: `ls -la utils/voice_recv_class.py.bak`
2. Restore: `cp utils/voice_recv_class.py.bak utils/voice_recv_class.py`
3. Report the issue with the error message

### Bot won't start after fixes

```bash
# Check logs
docker logs jennifer

# Rebuild from scratch
docker-compose -f docker-compose-jennifer.yml down
docker-compose -f docker-compose-jennifer.yml build --no-cache jennifer
docker-compose -f docker-compose-jennifer.yml up -d
```
