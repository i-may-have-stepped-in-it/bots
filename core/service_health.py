"""
Service health tracking for graceful degradation.

Provides a lightweight circuit-breaker-lite pattern: after N consecutive
failures a service is marked unavailable for a cooldown period, during which
callers skip the call and return a safe fallback instead of hammering a dead
endpoint.

Usage:
    from core.service_health import ServiceRegistry

    # Mark success/failure at call sites
    try:
        result = await call_external_service()
        ServiceRegistry.get("my_service").mark_success()
    except Exception as e:
        ServiceRegistry.get("my_service").mark_failure(str(e))
        return fallback_value

    # Gate calls before making them
    if not ServiceRegistry.get("my_service").is_available:
        return fallback_value
"""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ServiceHealth:
    """Tracks availability of a single external service."""

    name: str
    failure_threshold: int = 3       # failures before marking unavailable
    cooldown_seconds: float = 30.0   # seconds to wait before retrying

    _failure_count: int = field(default=0, init=False, repr=False)
    _available: bool = field(default=True, init=False, repr=False)
    _last_failure: float = field(default=0.0, init=False, repr=False)

    @property
    def is_available(self) -> bool:
        """True if the service is considered healthy and worth calling."""
        if self._available:
            return True
        # Auto-recover after cooldown
        if time.time() - self._last_failure >= self.cooldown_seconds:
            logger.info(
                f"Service '{self.name}' cooldown expired — marking available for retry"
            )
            self._available = True
            self._failure_count = 0
        return self._available

    def mark_failure(self, error: str = "") -> None:
        """Record a failure; disable the service if threshold is crossed."""
        self._failure_count += 1
        self._last_failure = time.time()
        if self._failure_count >= self.failure_threshold:
            if self._available:
                logger.warning(
                    f"Service '{self.name}' marked UNAVAILABLE after "
                    f"{self._failure_count} consecutive failures "
                    f"(cooldown {self.cooldown_seconds}s). Last error: {error}"
                )
            self._available = False

    def mark_success(self) -> None:
        """Record a successful call; reset failure counter."""
        if not self._available:
            logger.info(f"Service '{self.name}' recovered — marking available")
        self._available = True
        self._failure_count = 0

    def wait_seconds(self) -> float:
        """Seconds remaining in cooldown (0 if available)."""
        if self._available:
            return 0.0
        remaining = self.cooldown_seconds - (time.time() - self._last_failure)
        return max(0.0, remaining)

    def status_summary(self) -> str:
        """Human-readable one-liner for status commands."""
        if self.is_available:
            return f"{self.name}: OK"
        wait = self.wait_seconds()
        return (
            f"{self.name}: UNAVAILABLE (retry in {wait:.0f}s, "
            f"{self._failure_count} failures)"
        )


class _ServiceRegistry:
    """Singleton registry of all tracked services."""

    def __init__(self):
        self._services: dict[str, ServiceHealth] = {}

    def get(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ) -> ServiceHealth:
        """Get or create a ServiceHealth entry by name."""
        if name not in self._services:
            self._services[name] = ServiceHealth(
                name=name,
                failure_threshold=failure_threshold,
                cooldown_seconds=cooldown_seconds,
            )
        return self._services[name]

    def all_statuses(self) -> list[str]:
        """One-liner status for every registered service."""
        return [svc.status_summary() for svc in self._services.values()]


# Module-level singleton
ServiceRegistry = _ServiceRegistry()
