"""
Prometheus metrics for Jennifer Bot.
Enables real-time monitoring of bot performance and sub-systems.
"""

import logging
import time

from prometheus_client import Counter, Gauge, Histogram, start_http_server

logger = logging.getLogger(__name__)

# --- Discord Metrics ---
MESSAGES_RECEIVED = Counter(
    "jennifer_messages_received_total",
    "Total messages received by the bot"
)
COMMANDS_EXECUTED = Counter(
    "jennifer_commands_total",
    "Total commands executed",
    ["command", "status"]
)
ACTIVE_USERS = Gauge(
    "jennifer_active_users",
    "Number of users with active conversation sessions"
)

# --- AI Workload Metrics ---
QUEUE_DEPTH = Gauge(
    "jennifer_queue_depth",
    "Number of pending tasks in queues",
    ["queue_name"]
)
TASK_PROCESSING_TIME = Histogram(
    "jennifer_task_duration_seconds",
    "Time spent processing AI tasks",
    ["task_type"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600)
)
AI_PROVIDER_ERRORS = Counter(
    "jennifer_ai_errors_total",
    "Total errors from AI providers",
    ["provider", "error_type"]
)

# --- System Metrics ---
MEMORY_USAGE = Gauge(
    "jennifer_memory_usage_bytes",
    "Current memory usage of the bot process"
)

def start_metrics_server(port: int = 9090):
    """Start the Prometheus metrics HTTP server."""
    try:
        start_http_server(port)
        logger.info(f"Prometheus metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start Prometheus server: {e}")

class MetricsContext:
    """Helper to track task duration using a context manager."""
    def __init__(self, task_type: str):
        self.task_type = task_type
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        TASK_PROCESSING_TIME.labels(task_type=self.task_type).observe(duration)
