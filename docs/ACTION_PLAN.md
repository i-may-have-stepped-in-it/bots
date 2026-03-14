# Jennifer Bot - Action Plan

> **Comprehensive remediation plan for identified issues**

## Quick Reference

| Phase | Duration | Issues Addressed | Risk Level |
|-------|----------|------------------|------------|
| Phase 1 | Days 1-2 | Critical bugs, security | 🔴 High |
| Phase 2 | Days 3-5 | Broken features | 🔴 High |
| Phase 3 | Week 2 | Code quality | 🟡 Medium |
| Phase 4 | Week 3-4 | Architecture | 🟡 Medium |
| Phase 5 | Month 2+ | Testing, monitoring | 🟢 Low |

---

## SSL/TLS Configuration Strategy

### Local vs Remote Services

| Service Type | Examples | SSL Verify | Reason |
|--------------|----------|------------|--------|
| **Local inference** | localhost:38078, 192.168.x.x | `False` | No SSL on local network |
| **Private network** | tailscale, VPN endpoints | `False` | Encrypted tunnel, no HTTPS needed |
| **Public cloud** | OpenAI, remote APIs | `True` | Must verify certificates |
| **Self-hosted remote** | VPS with HTTPS | `Configurable` | User decides based on cert setup |

### Implementation Approach

```python
# utils/ssl_config.py (NEW)
import ssl
from urllib.parse import urlparse

class SSLConfigManager:
    """Manages SSL verification based on endpoint type."""
    
    # Local/private networks that don't need SSL
    LOCAL_HOSTS = {'localhost', '127.0.0.1'}
    PRIVATE_PREFIXES = ('192.168.', '10.', '172.16.', '172.17.', '172.18.',
                       '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
                       '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
                       '172.29.', '172.30.', '172.31.')
    
    @classmethod
    def should_verify_ssl(cls, url: str) -> bool:
        """Determine if SSL verification should be enabled for URL."""
        if not url:
            return False
            
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        
        # Always verify public HTTPS
        if parsed.scheme == 'https':
            # Check if it's a private/reserved IP
            if cls._is_private_host(hostname):
                return False  # Private HTTPS (self-signed, tailscale, etc.)
            return True  # Public HTTPS - must verify
        
        # HTTP connections - no SSL to verify
        return False
    
    @classmethod
    def _is_private_host(cls, hostname: str) -> bool:
        """Check if hostname is a local/private address."""
        if hostname in cls.LOCAL_HOSTS:
            return True
        if hostname.startswith(cls.PRIVATE_PREFIXES):
            return True
        # Check for tailscale domains
        if '.tail' in hostname or 'ts.net' in hostname:
            return True
        return False
    
    @classmethod
    def get_ssl_context(cls, url: str):
        """Get appropriate SSL context for URL."""
        if cls.should_verify_ssl(url):
            return ssl.create_default_context()
        return False  # Disable SSL verification for local/private
```

---

## Phase 1: Critical Security & Bug Fixes (Days 1-2)

### Task 1.1: Fix Voice Recognition Syntax Errors
**Priority:** 🔴 Critical  
**File:** `utils/voice_recv_class.py`

#### Problem
- Line 94: Broken indentation on `await message.channel.send(chunk)`
- Line 95: `else` clause incorrectly attached to `for` loop
- Lines 126-158: Unreachable code after `return`

#### Implementation
```python
# utils/voice_recv_class.py - Lines 56-101 (FIXED)
@classmethod
async def process_recognized_speech(cls, text: str, message):
    try:
        response_chunks = await generate_response(
            config, message.author.id, message.author.display_name, {}, 
            message=None, prompt=text
        )
        
        if not response_chunks:
            logging.error("No response text generated.")
            return
            
        concatenated_response = ''
        for chunk in response_chunks:
            await cls.text_to_speech(chunk)
            audio_bytes_list = await cls.tts_queue.get()
            if audio_bytes_list:
                member = message.author
                if member.voice:
                    voice_client = member.voice.channel.guild.voice_client
                    if voice_client:
                        for audio_bytes in audio_bytes_list:
                            audio_source = discord.FFmpegPCMAudio(
                                io.BytesIO(audio_bytes), pipe=True
                            )
                            playback_finished = asyncio.Future()

                            def set_playback_finished(error):
                                if error:
                                    print(f"Playback error: {error}")
                                playback_finished.set_result(None)

                            voice_client.play(audio_source, after=set_playback_finished)
                            await playback_finished

                        concatenated_response += chunk
                        
        if concatenated_response:
            max_length = 1900
            chunks = []
            lines = concatenated_response.split('\n')
            for line in lines:
                wrapped_lines = textwrap.wrap(
                    line, width=max_length, break_long_words=False
                )
                for wrapped_line in wrapped_lines:
                    chunks.append(wrapped_line.strip())
            
            for chunk in chunks:
                await message.channel.send(chunk)
        else:
            logging.error("No response text generated.")

    except Exception as e:
        await message.channel.send("Sorry, I'm having trouble processing your request.")
        logging.error(e)
```

#### Verification Steps
1. Run `python -m py_compile utils/voice_recv_class.py`
2. Test voice command `!join_vc` followed by speaking bot's name

---

### Task 1.2: Remove Hardcoded Credentials
**Priority:** 🔴 Critical  
**File:** `utils/teamviewer.py`

#### Problem
Hardcoded SSH credentials are a severe security vulnerability.

#### Implementation
```python
# utils/teamviewer.py (NEW)
import os
import pexpect
import logging

logger = logging.getLogger(__name__)


async def teamviewer(config, message):
    """
    Execute teamviewer script on remote host via SSH.
    Requires TEAMVIEWER_SSH_HOST, TEAMVIEWER_SSH_USER, TEAMVIEWER_SSH_KEY_PATH
    environment variables to be set.
    """
    # Get configuration from environment (NOT hardcoded)
    ssh_host = os.getenv('TEAMVIEWER_SSH_HOST')
    ssh_user = os.getenv('TEAMVIEWER_SSH_USER', 'bot')
    ssh_key_path = os.getenv('TEAMVIEWER_SSH_KEY_PATH', '/app/config/teamviewer_key')
    
    if not ssh_host:
        await message.channel.send("❌ TeamViewer not configured.")
        logger.error("TEAMVIEWER_SSH_HOST not set")
        return False
    
    if not os.path.exists(ssh_key_path):
        await message.channel.send("❌ SSH key not found.")
        logger.error(f"SSH key not found at {ssh_key_path}")
        return False
    
    try:
        # Use key-based auth instead of password
        ssh_conn = pexpect.spawn(
            f'ssh -i {ssh_key_path} -o StrictHostKeyChecking=no '
            f'{ssh_user}@{ssh_host}'
        )
        
        # Wait for prompt or key passphrase
        index = ssh_conn.expect(['passphrase', '[$#]', pexpect.EOF], timeout=30)
        
        if index == 0:  # Passphrase prompt
            await message.channel.send("❌ SSH key requires passphrase.")
            return False
        elif index == 1:  # Got prompt
            ssh_conn.sendline('sudo /usr/local/bin/teamviewer.sh')
            ssh_conn.expect('[$#]', timeout=60)
            output = ssh_conn.before.decode('utf-8')
            await message.channel.send(f"✅ TeamViewer activated!")
            return True
            
    except Exception as e:
        logger.exception("TeamViewer command failed")
        await message.channel.send("❌ Failed to execute TeamViewer command.")
        return False
```

#### Environment Variables to Add
```bash
# .env file
TEAMVIEWER_SSH_HOST=192.168.128.134
TEAMVIEWER_SSH_USER=bot
TEAMVIEWER_SSH_KEY_PATH=/app/config/teamviewer_key
```

---

### Task 1.3: Fix Circular Import in Voice Module
**Priority:** 🔴 Critical  
**File:** `utils/voice_recv_class.py`, `bot/client.py`

#### Problem
Line 22: `from app import config` creates circular import.

#### Implementation
```python
# utils/voice_recv_class.py (FIXED HEADER)
import logging
import asyncio
import torch
import torchaudio
import nltk
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)
from nltk.tokenize import sent_tokenize
import discord
from discord.ext import voice_recv
import io
from openai import AsyncOpenAI
import textwrap
import re
from silero import *
from discord.ext.voice_recv.extras import *
import sys
import os
import concurrent.futures

# REMOVE: from app import config
# REMOVE: from utils import *
# REMOVE: from utils.utility_functions import generate_response

class VoiceRecvClient(voice_recv.VoiceRecvClient):
    """Voice client with TTS/STT capabilities."""
    
    def __init__(self, config, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = config  # Store config as instance variable
        self.loop = asyncio.get_event_loop()
        self._load_silero_model()
    
    def _load_silero_model(self):
        """Lazy-load Silero model."""
        self.language = 'en'
        self.model_id = 'v3_en'
        self.device = torch.device("cpu")
        self.tts_queue = asyncio.Queue()
        
        try:
            self.silero_model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language=self.language,
                speaker=self.model_id,
                trust_repo=True
            )
            self.silero_model.to(self.device)
        except Exception as e:
            logging.error(f"Error loading Silero model: {e}")
            self.silero_model = None
```

Update `bot/client.py` to pass config:
```python
# bot/client.py - In handle_join_vc_command
from utils.voice_recv_class import VoiceRecvClient

# ...
vc = await channel.connect(
    cls=lambda *args, **kwargs: VoiceRecvClient(self.config, *args, **kwargs)
)
```

---

### Task 1.4: Implement Smart SSL Verification
**Priority:** 🔴 Critical  
**File:** `utils/ssl_config.py` (new), `utils/openclaw.py`, `utils/image_gen.py`

#### Implementation - SSL Config Manager
```python
# utils/ssl_config.py (NEW FILE)
"""
SSL/TLS configuration manager for local vs remote services.
Automatically disables SSL verification for local/private networks.
"""

import ssl
import os
from urllib.parse import urlparse
from typing import Union
import logging

logger = logging.getLogger(__name__)


class SSLConfigManager:
    """
    Manages SSL verification based on endpoint type.
    
    Local/private network services (LocalAI, SD) don't use SSL.
    Public cloud services (OpenAI) require SSL verification.
    """
    
    # Local hostnames that never need SSL
    LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}
    
    # Private IP ranges (RFC 1918)
    PRIVATE_PREFIXES = (
        '192.168.', '10.', '172.16.', '172.17.', '172.18.',
        '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
        '172.24.', '172.25.', '172.26.', '172.27.', '172.28.',
        '172.29.', '172.30.', '172.31.'
    )
    
    # Common Tailscale/Tailnet domains
    TAILSCALE_DOMAINS = ('.tailscale.net', '.ts.net', '.tail')
    
    @classmethod
    def should_verify_ssl(cls, url: str) -> bool:
        """
        Determine if SSL verification should be enabled for URL.
        
        Args:
            url: The endpoint URL
            
        Returns:
            True if SSL should be verified, False otherwise
        """
        if not url:
            return False
        
        # Check for override environment variable
        override = os.getenv('VERIFY_SSL', '').lower()
        if override == 'always':
            return True
        if override == 'never':
            return False
            
        parsed = urlparse(url)
        hostname = parsed.hostname or ''
        scheme = parsed.scheme or 'http'
        
        # HTTP connections don't use SSL
        if scheme == 'http':
            logger.debug(f"SSL disabled for HTTP endpoint: {url}")
            return False
        
        # HTTPS connections - check if private
        if cls._is_private_host(hostname):
            logger.debug(f"SSL disabled for private HTTPS endpoint: {url}")
            return False
        
        # Public HTTPS - verify SSL
        logger.debug(f"SSL enabled for public HTTPS endpoint: {url}")
        return True
    
    @classmethod
    def _is_private_host(cls, hostname: str) -> bool:
        """Check if hostname is a local/private address."""
        if not hostname:
            return True
            
        hostname_lower = hostname.lower()
        
        # Check local hosts
        if hostname_lower in cls.LOCAL_HOSTS:
            return True
        
        # Check private IP prefixes
        if hostname_lower.startswith(cls.PRIVATE_PREFIXES):
            return True
        
        # Check Tailscale domains
        if any(domain in hostname_lower for domain in cls.TAILSCALE_DOMAINS):
            return True
        
        return False
    
    @classmethod
    def get_ssl_context(cls, url: str) -> Union[ssl.SSLContext, bool]:
        """
        Get appropriate SSL context for URL.
        
        Args:
            url: The endpoint URL
            
        Returns:
            SSLContext for verification, or False to disable verification
        """
        if cls.should_verify_ssl(url):
            return ssl.create_default_context()
        return False
    
    @classmethod
    def get_aiohttp_ssl_param(cls, url: str):
        """
        Get the ssl parameter for aiohttp requests.
        
        Usage:
            ssl_param = SSLConfigManager.get_aiohttp_ssl_param("https://api.example.com")
            async with session.get(url, ssl=ssl_param) as resp:
                ...
        """
        return cls.get_ssl_context(url)


# Convenience function for quick access
def get_ssl_for_url(url: str):
    """Get SSL context/parameter for a URL."""
    return SSLConfigManager.get_aiohttp_ssl_param(url)
```

#### Update OpenClaw Client
```python
# utils/openclaw.py - Update to use smart SSL
from utils.ssl_config import SSLConfigManager

class OpenClawClient:
    def __init__(self, gateway_url, api_token, prefix="jennifer"):
        self.url = gateway_url.rstrip('/')
        self.ws_url = self.url.replace('http://', 'ws://').replace('https://', 'wss://')
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
        self.api_token = api_token
        self.prefix = prefix.lower().replace(" ", "-")
        self._verified_agents = set()
        
        # Determine SSL verification based on URL
        self.ssl_verify = SSLConfigManager.should_verify_ssl(self.url)
        logger.info(f"OpenClaw SSL verification: {self.ssl_verify} for {self.url}")
    
    async def call_rpc(self, method, params):
        """Calls a Gateway RPC method via WebSocket."""
        ssl_context = SSLConfigManager.get_ssl_context(self.url)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(
                    self.ws_url, 
                    headers={"Authorization": f"Bearer {self.api_token}"}, 
                    ssl=ssl_context,  # Smart SSL based on URL
                    timeout=300
                ) as ws:
                    # ... rest of method
                    
    async def send_message_with_fallback(self, session, payload, headers, primary_model, fallback_chain=None):
        """Send message with smart SSL handling."""
        ssl_context = SSLConfigManager.get_ssl_context(self.url)
        
        async with session.post(
            f"{self.url}/v1/chat/completions", 
            json=payload, 
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=600),
            ssl=ssl_context  # Smart SSL
        ) as resp:
            # ... rest of method
```

#### Update Image Generation
```python
# utils/image_gen.py - Update API calls to use smart SSL
from utils.ssl_config import SSLConfigManager

async def stable_diffusion_generate_image(config, prompt, upscale):
    """Generate image with smart SSL handling."""
    try:
        json_payload = prepare_json_payload(config, prompt, upscale)
        sd_url = config.get("SDURL", "")
        
        # Get appropriate SSL context
        ssl_context = SSLConfigManager.get_ssl_context(sd_url)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url=sd_url + "/sdapi/v1/txt2img", 
                json=json_payload,
                ssl=ssl_context  # Smart SSL based on URL
            ) as response:
                response.raise_for_status()
                return await response.json()
                
    except Exception as e:
        logging.error(f"Image generation failed: {e}")
        raise

async def fetch_options(config):
    """Fetch SD options with smart SSL."""
    sd_url = config.get("SDURL", "")
    ssl_context = SSLConfigManager.get_ssl_context(sd_url)
    
    async with aiohttp.ClientSession() as session:
        url = sd_url + "/sdapi/v1/options"
        async with session.get(url, ssl=ssl_context) as response:
            response.raise_for_status()
            return await response.json()
```

#### Environment Variable Override
```bash
# .env - SSL Configuration Options

# Auto-detect (default) - SSL enabled for public HTTPS, disabled for local
VERIFY_SSL=auto

# Force SSL verification for all HTTPS (not recommended for local inference)
# VERIFY_SSL=always

# Disable SSL verification entirely (security risk for remote APIs)
# VERIFY_SSL=never
```

---

### Task 1.5: Fix Token Bucket Rate Limiting
**Priority:** 🔴 High  
**File:** `utils/image_gen.py`

#### Implementation
```python
# utils/image_gen.py - At module level
import threading

# Shared token bucket instance
_image_bucket = None
_bucket_lock = threading.Lock()

def get_image_bucket():
    """Get or create shared token bucket for image generation."""
    global _image_bucket
    if _image_bucket is None:
        with _bucket_lock:
            if _image_bucket is None:
                _image_bucket = TokenBucket(capacity=3, refill_rate=0.5)
    return _image_bucket

async def handle_image_generation(config, message, user_message_histories, bot, draw_msg):
    """Handle image generation with proper rate limiting."""
    try:
        bucket = get_image_bucket()  # Use shared instance
        channel = message.channel
        
        async with channel.typing():
            if bucket.consume(1):
                # ... rest of generation logic
            else:
                await draw_msg.edit(
                    "I'm busy sketching for you. Please wait until I finish this one."
                )
                logging.info("Image drawing throttled.")
    except Exception as e:
        logging.error(f"Error during image generation: {e}")
        await draw_msg.edit(content="I'm sorry, I was not able to do that for you.")
```

---

### Task 1.6: Implement Health Check File
**Priority:** 🔴 High  
**File:** `bot/client.py`

#### Implementation
```python
# bot/client.py - In JenniferBot class

async def setup_hook(self):
    """Called when bot is starting up."""
    # Initialize databases
    await self.task_manager.initialize_all()
    
    # Create health check file
    try:
        Path('/app/healthy').touch()
        logger.info("Health check file created")
    except Exception as e:
        logger.warning(f"Could not create health check file: {e}")

async def close(self):
    """Clean shutdown."""
    logger.info("Shutting down...")
    
    # Remove health check file
    try:
        Path('/app/healthy').unlink()
        logger.info("Health check file removed")
    except FileNotFoundError:
        pass
    
    # ... rest of cleanup
```

---

## Remaining Phases (See Original Document)

The rest of the action plan (Phases 2-5) remains the same as the original document:
- Phase 2: Broken Features (permission checks, connection pooling, etc.)
- Phase 3: Code Quality (atomic writes, cooldowns, etc.)
- Phase 4: Architecture (LLM provider interface, DI container)
- Phase 5: Testing & Monitoring (Prometheus, Grafana, etc.)

See the original `ACTION_PLAN.md` for complete details on these phases.

---

## Updated Testing Strategy

### SSL Configuration Tests
```python
# tests/unit/utils/test_ssl_config.py (NEW)
import pytest
from utils.ssl_config import SSLConfigManager

class TestSSLConfigManager:
    def test_localhost_no_ssl(self):
        assert SSLConfigManager.should_verify_ssl("http://localhost:8080") is False
        assert SSLConfigManager.should_verify_ssl("https://localhost:8080") is False
    
    def test_private_ip_no_ssl(self):
        assert SSLConfigManager.should_verify_ssl("http://192.168.1.50:8000") is False
        assert SSLConfigManager.should_verify_ssl("https://10.0.0.5:38078") is False
    
    def test_tailscale_no_ssl(self):
        assert SSLConfigManager.should_verify_ssl("https://vmi3115281.tail36566.ts.net") is False
    
    def test_public_https_ssl(self):
        assert SSLConfigManager.should_verify_ssl("https://api.openai.com") is True
    
    def test_env_override_always(self, monkeypatch):
        monkeypatch.setenv("VERIFY_SSL", "always")
        assert SSLConfigManager.should_verify_ssl("http://localhost:8080") is True
    
    def test_env_override_never(self, monkeypatch):
        monkeypatch.setenv("VERIFY_SSL", "never")
        assert SSLConfigManager.should_verify_ssl("https://api.openai.com") is False
```

---

## Implementation Checklist

### Phase 1 Checklist (Updated)
- [ ] Fix voice_recv_class.py syntax errors
- [ ] Remove hardcoded credentials from teamviewer.py
- [ ] Fix circular import in voice module
- [ ] **Create utils/ssl_config.py with smart SSL detection**
- [ ] **Update openclaw.py to use SSLConfigManager**
- [ ] **Update image_gen.py to use SSLConfigManager**
- [ ] Test SSL behavior with local endpoints (should be disabled)
- [ ] Test SSL behavior with public endpoints (should be enabled)
- [ ] Implement shared TokenBucket
- [ ] Add health check file creation
- [ ] Test all voice commands
- [ ] Security review of all credential usage

---

**Document Version:** 1.1 (Updated for SSL handling)  
**Last Updated:** 2026-03-13  
**Owner:** DevOps Team
