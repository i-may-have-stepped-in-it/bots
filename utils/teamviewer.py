"""
TeamViewer remote access functionality.
Uses SSH key-based authentication (no hardcoded passwords).
"""

import os
import pexpect
import logging

logger = logging.getLogger(__name__)


async def teamviewer(config, message):
    """
    Execute TeamViewer script on remote host via SSH.
    
    Requires environment variables:
    - TEAMVIEWER_SSH_HOST: SSH host to connect to
    - TEAMVIEWER_SSH_USER: SSH username (default: bot)
    - TEAMVIEWER_SSH_KEY_PATH: Path to SSH private key
    
    Args:
        config: Bot configuration
        message: Discord message object
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Get configuration from environment (NOT hardcoded)
    ssh_host = os.getenv('TEAMVIEWER_SSH_HOST')
    ssh_user = os.getenv('TEAMVIEWER_SSH_USER', 'bot')
    ssh_key_path = os.getenv(
        'TEAMVIEWER_SSH_KEY_PATH',
        '/app/config/teamviewer_key'
    )
    
    if not ssh_host:
        await message.channel.send(
            "❌ TeamViewer not configured. Set TEAMVIEWER_SSH_HOST environment variable."
        )
        logger.error("TEAMVIEWER_SSH_HOST not set")
        return False
    
    if not os.path.exists(ssh_key_path):
        await message.channel.send(
            "❌ SSH key not found. Ensure key is mounted at the configured path."
        )
        logger.error(f"SSH key not found at {ssh_key_path}")
        return False
    
    try:
        # Use key-based auth instead of password
        ssh_cmd = (
            f'ssh -i {ssh_key_path} '
            f'-o StrictHostKeyChecking=no '
            f'-o ConnectTimeout=10 '
            f'-o BatchMode=yes '  # Disable password prompt
            f'{ssh_user}@{ssh_host}'
        )
        
        logger.info(f"Connecting to {ssh_host} as {ssh_user}")
        
        ssh_conn = pexpect.spawn(ssh_cmd, timeout=30)
        
        # Wait for prompt
        patterns = ['passphrase', '[$#]', 'password:', pexpect.EOF, pexpect.TIMEOUT]
        index = ssh_conn.expect(patterns, timeout=30)
        
        if index == 0:  # Passphrase prompt
            await message.channel.send(
                "❌ SSH key requires passphrase. Please use an unencrypted key."
            )
            ssh_conn.close()
            return False
        
        elif index == 2:  # Password prompt (shouldn't happen with keys)
            await message.channel.send(
                "❌ SSH key not accepted. Check key permissions and authorized_keys."
            )
            ssh_conn.close()
            return False
            
        elif index == 1:  # Got shell prompt
            logger.info("SSH connection established, executing command...")
            ssh_conn.sendline('sudo /usr/local/bin/teamviewer.sh')
            
            # Wait for command completion
            cmd_index = ssh_conn.expect(
                ['[$#]', pexpect.EOF, pexpect.TIMEOUT],
                timeout=60
            )
            
            if cmd_index in [0, 1]:
                output = ssh_conn.before.decode('utf-8', errors='ignore')
                logger.info(f"Command output: {output[:500]}")
                await message.channel.send("✅ TeamViewer activated successfully!")
                ssh_conn.close()
                return True
            else:
                await message.channel.send("❌ Command timed out.")
                ssh_conn.close()
                return False
                
        elif index == 3:  # EOF
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
