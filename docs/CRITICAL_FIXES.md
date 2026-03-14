# Critical Fixes Required

> **These 4 issues must be fixed before deployment or the bot will crash/fail**

---

## Fix 1: Voice Command Broken 🔴

**File:** `bot/commands/handlers.py` line 480

**Current Code (BROKEN):**
```python
vc = await channel.connect(cls=VoiceRecvClient)
```

**Fixed Code:**
```python
vc = await channel.connect(
    cls=lambda *args, **kwargs: VoiceRecvClient(config, *args, **kwargs)
)
```

**Why:** The refactored VoiceRecvClient requires `config` as first parameter.

---

## Fix 2: Image Generation Broken 🔴

**File:** `bot/client.py` line 169

**Current Code (BROKEN):**
```python
await handle_image_generation(
    self.config,
    message,
    self.user_message_histories,
    self,
    message,  # BUG: Should be draw_msg
)
```

**Fixed Code:**
```python
# Get the loading message that was sent earlier
draw_msg = await channel.fetch_message(payload["message_id"])
await handle_image_generation(
    self.config,
    message,
    self.user_message_histories,
    self,
    draw_msg,  # FIXED: Pass the loading message
)
```

**Why:** The image generation function expects the loading message to update, not the original message.

---

## Fix 3: OpenClaw Import Broken 🔴

**File:** `utils/utility_functions.py` line 15

**Current Code (BROKEN):**
```python
from openclaw import generate_openclaw_response
```

**Fixed Code:**
```python
from utils.openclaw import generate_openclaw_response
```

**Why:** Wrong import path causes ModuleNotFoundError.

---

## Fix 4: Status Command SSL Error 🔴

**File:** `bot/commands/handlers.py` lines 709-718, 724-737, 743-754

**Current Code (BROKEN):**
```python
async with s.get(f"{config.openclaw.gateway}/health", ...) as r:
```

**Fixed Code:**
```python
# Add at top of file
from utils.ssl_config import SSLConfigManager

# Then update all three status checks:
ssl_context = SSLConfigManager.get_ssl_context(config.openclaw.gateway)
async with s.get(
    f"{config.openclaw.gateway}/health",
    ssl=ssl_context,
    ...
) as r:
```

**Why:** Missing SSL context causes SSL verification errors for private endpoints.

---

## Apply All Fixes

### Option 1: Manual Edit
Edit each file with the changes above.

### Option 2: Patch File
```bash
# Create a patch file with all fixes
git diff > critical_fixes.patch

# Apply the patch
git apply critical_fixes.patch
```

### Option 3: Quick Python Script
```python
#!/usr/bin/env python3
"""Apply critical fixes to Jennifer bot."""

import re

def fix_voice_command():
    with open("bot/commands/handlers.py", "r") as f:
        content = f.read()
    
    # Fix voice client instantiation
    content = content.replace(
        "vc = await channel.connect(cls=VoiceRecvClient)",
        "vc = await channel.connect(\n            cls=lambda *args, **kwargs: VoiceRecvClient(config, *args, **kwargs)\n        )"
    )
    
    with open("bot/commands/handlers.py", "w") as f:
        f.write(content)
    print("✅ Fixed voice command")

def fix_openclaw_import():
    with open("utils/utility_functions.py", "r") as f:
        content = f.read()
    
    content = content.replace(
        "from openclaw import generate_openclaw_response",
        "from utils.openclaw import generate_openclaw_response"
    )
    
    with open("utils/utility_functions.py", "w") as f:
        f.write(content)
    print("✅ Fixed OpenClaw import")

if __name__ == "__main__":
    fix_voice_command()
    fix_openclaw_import()
    print("\n⚠️  Manual fixes still needed:")
    print("  - bot/client.py line 169: Change 'message' to 'draw_msg'")
    print("  - bot/commands/handlers.py: Add SSL context to status command")
```

---

## Verify Fixes

After applying fixes, test each:

```bash
# Test voice
!join_vc

# Test image generation
!draw a cat

# Test chat (uses OpenClaw)
Hello Jennifer

# Test status
!status
```

---

**Status:** 4 critical fixes required before deployment  
**Risk if not fixed:** Bot crashes on voice command, images fail, OpenClaw fails, status fails
