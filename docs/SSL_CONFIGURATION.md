# SSL/TLS Configuration Guide for Jennifer Bot

## The Problem

You have a mix of services:
- **Local inference** (LocalAI, Stable Diffusion) - No SSL, private network
- **Remote gateways** (OpenClaw) - May use HTTPS
- **Public APIs** (OpenAI) - Require SSL verification

Hardcoding `ssl=False` everywhere works for local inference but creates security vulnerabilities for remote connections.

## The Solution: Smart SSL

The bot now automatically detects the endpoint type and applies appropriate SSL settings:

### SSL Behavior Matrix

| Endpoint Type | Example URL | SSL Verification | Reason |
|--------------|-------------|------------------|---------|
| Local HTTP | `http://localhost:38078` | ❌ Disabled | No encryption needed |
| Private IP HTTP | `http://192.168.1.50:7860` | ❌ Disabled | Local network |
| Tailscale HTTPS | `https://vmi3115281.tail36566.ts.net` | ❌ Disabled | Already encrypted tunnel |
| Public HTTPS | `https://api.openai.com` | ✅ Enabled | Standard security |

## Configuration Options

### Option 1: Auto-Detect (Recommended)

```bash
# .env
VERIFY_SSL=auto  # Default - bot decides based on URL
```

The bot automatically:
- Disables SSL for `localhost`, `127.0.0.1`, private IPs (192.168.x.x, 10.x.x.x)
- Disables SSL for Tailscale domains (*.ts.net, *.tailscale.net)
- Enables SSL for public HTTPS endpoints

### Option 2: Force SSL (Not Recommended for Local Inference)

```bash
# .env
VERIFY_SSL=always  # Enable SSL for everything
```

⚠️ **Warning:** This will break local inference that uses HTTPS with self-signed certificates!

### Option 3: Disable SSL (Security Risk)

```bash
# .env
VERIFY_SSL=never  # Disable SSL for everything
```

⚠️ **Warning:** Only use this if you understand the security implications!

## Implementation Details

### How It Works

```python
from utils.ssl_config import SSLConfigManager

# For local inference - SSL disabled automatically
local_url = "http://localhost:38078"
ssl_param = SSLConfigManager.get_aiohttp_ssl_param(local_url)
# Returns: False (SSL disabled)

# For Tailscale - SSL disabled (already encrypted)
tailscale_url = "https://vmi3115281.tail36566.ts.net"
ssl_param = SSLConfigManager.get_aiohttp_ssl_param(tailscale_url)
# Returns: False (Tailscale provides encryption)

# For public API - SSL enabled
api_url = "https://api.openai.com"
ssl_param = SSLConfigManager.get_aiohttp_ssl_param(api_url)
# Returns: ssl.SSLContext() (SSL enabled)
```

### Updated Code Example

```python
# OLD (hardcoded ssl=False - insecure for remote APIs)
async with session.get(url, ssl=False) as resp:
    ...

# NEW (smart SSL based on URL)
from utils.ssl_config import SSLConfigManager

ssl_context = SSLConfigManager.get_ssl_context(url)
async with session.get(url, ssl=ssl_context) as resp:
    ...
```

## Testing SSL Configuration

### Test 1: Local Inference (SSL Disabled)

```python
from utils.ssl_config import SSLConfigManager

# Should return False for local URLs
assert SSLConfigManager.should_verify_ssl("http://localhost:38078") == False
assert SSLConfigManager.should_verify_ssl("https://192.168.1.50:7860") == False
print("✅ Local inference SSL disabled")
```

### Test 2: Tailscale (SSL Disabled)

```python
assert SSLConfigManager.should_verify_ssl("https://vmi3115281.tail36566.ts.net") == False
print("✅ Tailscale SSL disabled")
```

### Test 3: Public API (SSL Enabled)

```python
assert SSLConfigManager.should_verify_ssl("https://api.openai.com") == True
print("✅ Public API SSL enabled")
```

## Migration Guide

### Step 1: Create SSL Config Module

```bash
python fixes/phase1/fix_ssl_config.py
```

This creates `utils/ssl_config.py`.

### Step 2: Update OpenClaw Client

Edit `utils/openclaw.py`:

```python
# Add import at top
from utils.ssl_config import SSLConfigManager

# In __init__, remove hardcoded ssl=False
# OLD:
# ssl=False  # Hardcoded!

# NEW:
# SSL determined automatically per-request

# In methods that make HTTP requests:
async def call_rpc(self, method, params):
    ssl_context = SSLConfigManager.get_ssl_context(self.url)
    async with session.ws_connect(
        self.ws_url,
        ssl=ssl_context,  # Smart SSL
        ...
    ) as ws:
        ...
```

### Step 3: Update Image Generation

Edit `utils/image_gen.py`:

```python
# Add import
from utils.ssl_config import SSLConfigManager

# Update API calls
async def fetch_options(config):
    sd_url = config.get("SDURL", "")
    ssl_context = SSLConfigManager.get_ssl_context(sd_url)
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=ssl_context) as response:
            ...
```

### Step 4: Test

```bash
# Run bot and check logs
python app.py

# You should see messages like:
# "SSL disabled for HTTP endpoint: http://localhost:38078"
# "SSL disabled for private HTTPS endpoint: https://vmi3115281.tail36566.ts.net"
```

## Troubleshooting

### Local Inference Fails with SSL Error

**Symptom:**
```
aiohttp.ClientConnectorSSLError: Cannot connect to host localhost:38078 ssl:True
```

**Cause:** SSL is enabled for local endpoint

**Fix:**
1. Ensure URL uses `http://` not `https://`
2. Check that `VERIFY_SSL` is not set to `always`
3. Verify the URL is in private IP ranges

### Remote API Fails with Certificate Error

**Symptom:**
```
ssl.SSLCertVerificationError: certificate verify failed
```

**Cause:** SSL verification failing for public API

**Fix:**
1. Check system time is correct
2. Update CA certificates: `apt-get update && apt-get install ca-certificates`
3. If using self-signed cert, add to trust store

### Tailscale Connection Issues

**Symptom:**
```
Cannot connect to Tailscale endpoint
```

**Fix:**
1. Tailscale should work with SSL disabled (it's already encrypted)
2. Ensure the Tailscale domain contains `.ts.net` or `.tail`
3. Check Tailscale daemon is running

## Security Best Practices

1. **Never use `VERIFY_SSL=never` in production**
2. **Keep `VERIFY_SSL=auto` as default**
3. **Monitor logs** for unexpected SSL configurations
4. **Use Tailscale or VPN** for remote private endpoints instead of exposing them

## Quick Reference

| Scenario | Recommended Setting |
|----------|---------------------|
| Local only (localhost, 192.168.x.x) | `VERIFY_SSL=auto` |
| Tailscale network | `VERIFY_SSL=auto` |
| Mixed local + public APIs | `VERIFY_SSL=auto` |
| Public HTTPS only | `VERIFY_SSL=auto` or `always` |
| Development/testing | `VERIFY_SSL=auto` |

---

**Last Updated:** 2026-03-13  
**Applies to:** Jennifer Bot v2.x
