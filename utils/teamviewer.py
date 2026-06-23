"""
TeamViewer remote access functionality.
Uses SSH key-based authentication (no hardcoded passwords).
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def _ssh_connect_sync(ssh_host: str, ssh_user: str, ssh_key_path: str) -> tuple[bool, str]:
    """Synchronous SSH + TeamViewer execution (runs in thread pool).

    Returns:
        (success, message) tuple
    """
    import pexpect

    # List form avoids argument-splitting issues if env vars contain spaces
    ssh_args = [
        "-i", ssh_key_path,
        "-o", "StrictHostKeyChecking=accept-new",  # Trust on first connect, verify thereafter
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        f"{ssh_user}@{ssh_host}",
    ]

    try:
        ssh_conn = pexpect.spawn("ssh", ssh_args, timeout=30)

        patterns = ["passphrase", r"[$#]", "password:", pexpect.EOF, pexpect.TIMEOUT]
        index = ssh_conn.expect(patterns, timeout=30)

        if index == 0:  # Passphrase prompt
            ssh_conn.close()
            return False, "SSH key requires passphrase. Please use an unencrypted key."

        if index == 2:  # Password prompt — key not accepted
            ssh_conn.close()
            return False, "SSH key not accepted. Check key permissions and authorized_keys."

        if index == 1:  # Got shell prompt
            logger.info("SSH connection established, executing command...")
            ssh_conn.sendline("sudo /usr/local/bin/teamviewer.sh")

            cmd_index = ssh_conn.expect(
                [r"[$#]", pexpect.EOF, pexpect.TIMEOUT],
                timeout=60,
            )

            if cmd_index in (0, 1):
                output = ssh_conn.before.decode("utf-8", errors="ignore")
                logger.info("Command output: %s", output[:500])
                ssh_conn.close()
                return True, "TeamViewer activated successfully!"

            ssh_conn.close()
            return False, "Command timed out."

        if index == 3:  # EOF
            logger.error("SSH EOF: %s", ssh_conn.before)
            return False, "SSH connection closed unexpectedly."

        # Timeout
        ssh_conn.close()
        return False, "SSH connection timed out."

    except Exception:
        logger.exception("Pexpect error in TeamViewer")
        return False, "Failed to execute SSH command."


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
    ssh_host = os.getenv("TEAMVIEWER_SSH_HOST")
    ssh_user = os.getenv("TEAMVIEWER_SSH_USER", "bot")
    ssh_key_path = os.getenv("TEAMVIEWER_SSH_KEY_PATH", "/app/config/teamviewer_key")

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
        logger.error("SSH key not found at %s", ssh_key_path)
        return False

    logger.info("Connecting to %s as %s", ssh_host, ssh_user)

    try:
        # Run blocking pexpect operations in a thread so the event loop stays free
        success, msg = await asyncio.wait_for(
            asyncio.to_thread(_ssh_connect_sync, ssh_host, ssh_user, ssh_key_path),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        await message.channel.send("❌ SSH operation timed out.")
        logger.error("TeamViewer SSH timed out")
        return False
    except Exception:
        logger.exception("TeamViewer command failed")
        await message.channel.send("❌ An unexpected error occurred.")
        return False

    icon = "✅" if success else "❌"
    await message.channel.send(f"{icon} {msg}")
    return success
