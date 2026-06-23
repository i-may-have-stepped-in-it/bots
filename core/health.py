"""
Advanced health check system for Jennifer Bot.
Provides detailed insights into the bot's sub-systems.
"""

import json
import logging
import time
from pathlib import Path

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitors bot health and exposes it via an HTTP endpoint."""

    def __init__(self, bot=None, port: int = 8080):
        self.bot = bot
        self.port = port
        self.start_time = time.time()
        self._app = web.Application()
        self._app.router.add_get("/health", self.health_handler)
        self._app.router.add_get("/metrics", self.metrics_redirect)

    async def health_handler(self, request: web.Request) -> web.Response:
        """Return detailed health status as JSON."""
        status = {
            "status": "healthy",
            "uptime_seconds": int(time.time() - self.start_time),
            "version": "2.0.0",
            "subsystems": {
                "discord": "unknown",
                "queues": {},
                "ai_backends": {},
            },
        }

        if self.bot:
            status["subsystems"]["discord"] = (
                "connected" if self.bot.is_ready() else "disconnected"
            )
            status["latency_ms"] = int(self.bot.latency * 1000) if self.bot.latency else 0

            if hasattr(self.bot, "image_queue"):
                status["subsystems"]["queues"]["image"] = self.bot.image_queue.qsize()
            if hasattr(self.bot, "message_queue"):
                status["subsystems"]["queues"]["message"] = self.bot.message_queue.qsize()

        try:
            health_path = Path("logs/health.json")
            health_path.parent.mkdir(parents=True, exist_ok=True)
            with open(health_path, "w", encoding="utf-8") as f:
                json.dump(status, f)
            Path("/app/healthy").touch()
            Path("logs/healthy").touch()
        except Exception as e:
            logger.error(f"Failed to write health file: {e}")

        return web.json_response(status)

    async def metrics_redirect(self, request: web.Request) -> web.Response:
        """Redirect to the Prometheus metrics port (if separate)."""
        return web.Response(text="Metrics are on port 9090", status=200)

    async def start(self):
        """Start the health check HTTP server."""
        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"Health monitor server started on port {self.port}")


monitor = HealthMonitor()
