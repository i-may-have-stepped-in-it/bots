#!/usr/bin/env python3
"""
Fix script for image_gen.py to use shared TokenBucket instance.
"""

import shutil
from pathlib import Path
import re


def fix_token_bucket():
    """Fix the TokenBucket to be shared across calls."""
    target = Path("utils/image_gen.py")
    backup = Path("utils/image_gen.py.bak")
    
    if not target.exists():
        print(f"ERROR: {target} not found!")
        return False
    
    # Read original
    with open(target, 'r') as f:
        content = f.read()
    
    # Create backup
    shutil.copy2(target, backup)
    print(f"Created backup: {backup}")
    
    # Add shared bucket at module level (after imports)
    bucket_code = '''
# Shared token bucket for rate limiting (module-level singleton)
_image_rate_limiter = None
_image_rate_limiter_lock = asyncio.Lock()

async def get_image_rate_limiter():
    """Get or create the shared TokenBucket for image generation."""
    global _image_rate_limiter
    if _image_rate_limiter is None:
        async with _image_rate_limiter_lock:
            if _image_rate_limiter is None:
                _image_rate_limiter = TokenBucket(capacity=3, refill_rate=0.5)
    return _image_rate_limiter

'''
    
    # Find a good insertion point (after imports)
    import_end = content.find('\\n\\nclass TokenBucket')
    if import_end == -1:
        print("Could not find insertion point")
        return False
    
    # Insert the shared bucket code
    new_content = content[:import_end] + '\\n' + bucket_code + content[import_end:]
    
    # Replace the bucket creation in handle_image_generation
    old_pattern = r'bucket = TokenBucket\\(capacity=3, refill_rate=0\\.5\\)'
    new_pattern = 'bucket = await get_image_rate_limiter()'
    
    new_content = re.sub(old_pattern, new_pattern, new_content)
    
    # Add threading import if not present
    if 'import asyncio' in new_content and 'import threading' not in new_content:
        new_content = new_content.replace(
            'import asyncio',
            'import asyncio\\nimport threading'
        )
    
    # Write fixed content
    with open(target, 'w') as f:
        f.write(new_content)
    
    print(f"Fixed {target}")
    
    # Verify syntax
    try:
        import py_compile
        py_compile.compile(str(target), doraise=True)
        print("✅ Syntax check passed!")
        return True
    except py_compile.PyCompileError as e:
        print(f"❌ Syntax error: {e}")
        shutil.copy2(backup, target)
        print("Restored backup")
        return False


if __name__ == "__main__":
    fix_token_bucket()
