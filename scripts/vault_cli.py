#!/usr/bin/env python3
"""
CLI tool to encrypt secrets for the Jennifer Bot Vault.
Usage: python scripts/vault_cli.py "MY_SUPER_SECRET_KEY"
"""

import sys
import os

# Add parent directory to path so we can import core modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.secrets import vault

def main():
    if len(sys.argv) < 2:
        print("Usage: python vault_cli.py <secret_string>")
        sys.exit(1)
        
    secret = sys.argv[1]
    encrypted = vault.encrypt_secret(secret)
    
    print("\n--- Encrypted Secret ---")
    print(encrypted)
    print("------------------------\n")
    print("Add this to your config/secrets.enc file like so:")
    print(f"JENNIFER_DISCORD_TOKEN={encrypted}")

if __name__ == "__main__":
    main()
