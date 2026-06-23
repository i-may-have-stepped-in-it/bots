"""
Secure secrets management for Jennifer Bot.
Allows sensitive API keys to be stored encrypted at rest.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

class SecretVault:
    """Manages encrypted secrets using Fernet symmetric encryption."""
    
    def __init__(self, key_path: str = "config/master.key", vault_path: str = "config/secrets.enc"):
        self.key_path = Path(key_path)
        self.vault_path = Path(vault_path)
        self.fernet = None
        self._load_or_create_key()

    def _load_or_create_key(self):
        """Load the master key or create one if it doesn't exist."""
        if not self.key_path.exists():
            self.key_path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as f:
                f.write(key)
            # Ensure strict permissions
            os.chmod(self.key_path, 0o600)
            logger.info("Generated new master vault key.")
        else:
            with open(self.key_path, "rb") as f:
                key = f.read().strip()
        
        self.fernet = Fernet(key)

    def encrypt_secret(self, secret_value: str) -> str:
        """Encrypt a plaintext secret."""
        return self.fernet.encrypt(secret_value.encode()).decode()

    def decrypt_secret(self, encrypted_value: str) -> str:
        """Decrypt an encrypted secret."""
        try:
            return self.fernet.decrypt(encrypted_value.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt secret: {e}")
            return ""

    def get_secret(self, key: str) -> Optional[str]:
        """On-demand decryption of a secret from the vault."""
        if not self.vault_path.exists():
            return None

        try:
            with open(self.vault_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        v_key, encrypted_val = line.split("=", 1)
                        if v_key == key:
                            return self.decrypt_secret(encrypted_val)
        except Exception as e:
            logger.error(f"Error reading secret {key}: {e}")
        return None

    def get_all_decrypted(self) -> Dict[str, str]:
        """Return all secrets decrypted. Use sparingly!"""
        secrets = {}
        if not self.vault_path.exists():
            return secrets

        try:
            with open(self.vault_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        decrypted = self.decrypt_secret(val)
                        if decrypted:
                            secrets[key] = decrypted
        except Exception as e:
            logger.error(f"Error loading secrets vault: {e}")
        return secrets

# Global vault instance
vault = SecretVault()
