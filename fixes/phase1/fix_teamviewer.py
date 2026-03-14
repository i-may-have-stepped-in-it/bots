#!/usr/bin/env python3
"""
Fix script for teamviewer.py to remove hardcoded credentials.
"""

import shutil
from pathlib import Path

FIXED_CONTENT = '''import os
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
        await message.channel.send("❌ TeamViewer not configured. Set TEAMVIEWER_SSH_HOST environment variable.")
        logger.error("TEAMVIEWER_SSH_HOST not set")
        return False
    
    if not os.path.exists(ssh_key_path):
        await message.channel.send("❌ SSH key not found. Ensure key is mounted at the configured path.")
        logger.error(f"SSH key not found at {ssh_key_path}")
        return False
    
    try:
        # Use key-based auth instead of password
        ssh_cmd = (
            f'ssh -i {ssh_key_path} '
            f'-o StrictHostKeyChecking=no '
            f'-o ConnectTimeout=10 '
            f'{ssh_user}@{ssh_host}'
        )
        
        logger.info(f"Connecting to {ssh_host} as {ssh_user}")
        ssh_conn = pexpect.spawn(ssh_cmd, timeout=30)
        
        # Wait for prompt or key passphrase
        patterns = ['passphrase', '[$#]', pexpect.EOF, pexpect.TIMEOUT]
        index = ssh_conn.expect(patterns, timeout=30)
        
        if index == 0:  # Passphrase prompt
            await message.channel.send("❌ SSH key requires passphrase. Please use an unencrypted key.")
            ssh_conn.close()
            return False
            
        elif index == 1:  # Got shell prompt
            logger.info("SSH connection established, executing command...")
            ssh_conn.sendline('sudo /usr/local/bin/teamviewer.sh')
            
            # Wait for command completion
            cmd_index = ssh_conn.expect(['[$#]', pexpect.EOF, pexpect.TIMEOUT], timeout=60)
            
            if cmd_index in [0, 1]:
                output = ssh_conn.before.decode('utf-8', errors='ignore')
                logger.info(f"Command output: {output}")
                await message.channel.send(f"✅ TeamViewer activated successfully!")
                ssh_conn.close()
                return True
            else:
                await message.channel.send("❌ Command timed out.")
                ssh_conn.close()
                return False
                
        elif index == 2:  # EOF
            await message.channel.send("❌ SSH connection closed unexpectedly.")
            logger.error(f"SSH EOF: {ssh_conn.before}")
            return False
            
        else:  # Timeout
            await message.channel.send("❌ SSH connection timed out.")
            ssh_conn.close()
            return False
            
    except pexpect.ExceptionPexpect as e:
        logger.exception("Pexpect error in TeamViewer")
        await message.channel.send("❌ Failed to execute SSH command.")
        return False
    except Exception as e:
        logger.exception("TeamViewer command failed")
        await message.channel.send("❌ An unexpected error occurred.")
        return False
'''


def fix_teamviewer():
    """Apply the teamviewer fix."""
    target = Path("utils/teamviewer.py")
    backup = Path("utils/teamviewer.py.bak")
    
    if not target.exists():
        print(f"ERROR: {target} not found!")
        return False
    
    # Create backup
    shutil.copy2(target, backup)
    print(f"Created backup: {backup}")
    
    # Write fixed content
    with open(target, 'w') as f:
        f.write(FIXED_CONTENT)
    
    print(f"Fixed {target}")
    print("\n⚠️  IMPORTANT: Update your .env file with:")
    print("  TEAMVIEWER_SSH_HOST=your_host_ip")
    print("  TEAMVIEWER_SSH_USER=bot")
    print("  TEAMVIEWER_SSH_KEY_PATH=/app/config/teamviewer_key")
    
    return True


if __name__ == "__main__":
    fix_teamviewer()
