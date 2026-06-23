"""
Standalone worker entrypoint for Jennifer Bot.
Enables running image, video, or message workers as separate processes.
"""

import argparse
import asyncio
import logging

from bot.client import JenniferBot
from core.config import load_config
from core.logging_config import setup_logging


async def main():
    parser = argparse.ArgumentParser(description="Jennifer Worker Process")
    parser.add_argument("--type", required=True, choices=["image", "video", "message"], help="Worker type")
    parser.add_argument("--config", default="config/config.json", help="Path to config file")
    args = parser.parse_args()

    # Load config and setup logging
    config = load_config(args.config)
    setup_logging(
        log_level=config.log_level,
        log_dir="logs",
        use_json=True,
        app_name=f"jennifer-worker-{args.type}"
    )

    logger = logging.getLogger(__name__)
    logger.info(f"Starting {args.type} worker process...")

    # Create a minimal bot instance for worker context
    # Note: In a true decoupled architecture, we'd avoid the full Bot class here,
    # but for this migration, we'll reuse the existing worker methods.
    bot = JenniferBot(config, config_path=args.config)

    # Initialize necessary components
    await bot.task_manager.initialize_all()
    from core.history import history_manager
    await history_manager.initialize()

    # Start the specific worker
    if args.type == "image":
        await bot._image_worker()
    elif args.type == "video":
        await bot._video_worker()
    elif args.type == "message":
        await bot._message_worker()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
