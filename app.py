"""
Jennifer Discord Bot - Refactored Entry Point

This is the main entry point for the Jennifer bot.
All functionality has been refactored into modular components:

  - core/           - Configuration, logging, persistent queues
  - bot/            - Discord client, command handlers, music player
  - integrations/   - External service integrations
  - utils/          - Utility functions (existing)

Usage:
    python app.py

Environment Variables:
    LOG_LEVEL                    - Logging level (DEBUG, INFO, WARNING, ERROR)
    CONFIG_PATH                  - Path to config file (default: config/config.json)
    ENABLE_TRACING               - Enable end-to-end tracing (default: true)
    SD_URL                       - Stable Diffusion (A1111) base URL
    SD_COMFY_URL                 - ComfyUI base URL
    SD_INVOKE_URL                - InvokeAI base URL
    OPENCLAW_GATEWAY             - OpenClaw gateway URL
    OPENCLAW_EMBEDDING_ENDPOINT  - Embedding API endpoint URL
    OPENCLAW_MODEL_ENDPOINT      - Model API endpoint URL
"""

import asyncio
import os
import sys
import tracemalloc

from core.config import load_config
from core.logging_config import setup_logging
from core.tracing import get_tracer, tracer
from bot.client import start_bot

# Enable memory tracing for debugging
tracemalloc.start()


def main():
    """Main entry point with tracing."""
    enable_tracing = os.getenv("ENABLE_TRACING", "true").lower() == "true"
    
    try:
        # Start root trace
        if enable_tracing:
            tracer.start_trace("app_startup", attributes={
                "version": "2.0",
                "python_version": sys.version,
            })
        
        # Load configuration
        config_path = os.getenv("CONFIG_PATH", "config/config.json")
        config = load_config(config_path)

        if enable_tracing:
            tracer.add_event("config_loaded", {"bot_name": config.name})

        # Start bot with tracing (pass path for live reload watcher)
        asyncio.run(start_bot(config, config_path=config_path))
        
    except FileNotFoundError as e:
        if enable_tracing:
            tracer.add_event("config_load_failed", {"error": str(e)})
            tracer.end_trace()
        print(f"Error: Configuration file not found - {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if enable_tracing:
            tracer.add_event("fatal_error", {"error": str(e)})
            tracer.end_trace()
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
