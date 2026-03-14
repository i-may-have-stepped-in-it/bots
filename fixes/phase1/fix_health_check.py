#!/usr/bin/env python3
"""
Fix script to add health check file creation to bot.
"""

import shutil
from pathlib import Path


def fix_health_check():
    """Add health check file creation to JenniferBot."""
    target = Path("bot/client.py")
    backup = Path("bot/client.py.bak")
    
    if not target.exists():
        print(f"ERROR: {target} not found!")
        return False
    
    # Read original
    with open(target, 'r') as f:
        content = f.read()
    
    # Create backup
    shutil.copy2(target, backup)
    print(f"Created backup: {backup}")
    
    # Fix 1: Add Path import if not present
    if 'from pathlib import Path' not in content:
        content = content.replace(
            'from pathlib import Path',
            'from pathlib import Path\\nimport os'
        )
    
    # Fix 2: Add health file creation in setup_hook
    old_setup = '''    async def setup_hook(self):
        """Called when bot is starting up."""
        # Initialize databases
        await self.task_manager.initialize_all()'''
    
    new_setup = '''    async def setup_hook(self):
        """Called when bot is starting up."""
        # Initialize databases
        await self.task_manager.initialize_all()
        
        # Create health check file
        try:
            Path('/app/healthy').touch()
            logger.info("Health check file created")
        except Exception as e:
            logger.warning(f"Could not create health check file: {e}")'''
    
    content = content.replace(old_setup, new_setup)
    
    # Fix 3: Add health file removal in close
    old_close = '''    async def close(self):
        """Clean shutdown."""
        logger.info("Shutting down...")
        
        # Cancel background tasks'''
    
    new_close = '''    async def close(self):
        """Clean shutdown."""
        logger.info("Shutting down...")
        
        # Remove health check file
        try:
            if os.path.exists('/app/healthy'):
                os.remove('/app/healthy')
                logger.info("Health check file removed")
        except Exception as e:
            logger.warning(f"Could not remove health check file: {e}")
        
        # Cancel background tasks'''
    
    content = content.replace(old_close, new_close)
    
    # Write fixed content
    with open(target, 'w') as f:
        f.write(content)
    
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
    fix_health_check()
