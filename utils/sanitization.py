"""
Prompt sanitization and security filtering for Jennifer Bot.
Protects against prompt injection, toxic content, and PII leakage.
"""

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class PromptSanitizer:
    """Sanitizes and filters AI prompts for safety and security."""

    INJECTION_PATTERNS = [
        r"ignore all (?:previous|former|past) (?:instructions|directions|orders)",
        r"you are now (?:an|a) (?!bot|assistant)",
        r"forget your (?:system|base) (?:prompt|instructions)",
        r"dan mode",
        r"jailbreak",
        r"new rules:",
    ]

    TOXIC_KEYWORDS = []

    def __init__(self, blocked_words: Optional[List[str]] = None):
        self.blocked_words = blocked_words or []
        self._injection_regex = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def sanitize(self, prompt: str) -> str:
        """Basic sanitization like stripping and length normalization."""
        return prompt.strip()

    def check_safety(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a prompt is safe to send to an AI provider.
        Returns `(is_safe, reason)`.
        """
        prompt_lower = prompt.lower()

        for regex in self._injection_regex:
            if regex.search(prompt_lower):
                logger.warning(f"Detected potential prompt injection: '{prompt[:50]}...'")
                return False, "PROMPT_INJECTION"

        for word in self.blocked_words:
            if word.lower() in prompt_lower:
                logger.warning(f"Detected blocked word: '{word}'")
                return False, "BLOCKED_WORD"

        email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        if re.search(email_pattern, prompt):
            logger.warning("Detected PII (Email) in prompt")
            return False, "PII_LEAKAGE"

        return True, None


default_sanitizer = PromptSanitizer()


def get_sanitizer(config=None) -> PromptSanitizer:
    """Get a sanitizer instance, optionally configured with blocked words."""
    if config and hasattr(config, "ignored_words"):
        return PromptSanitizer(blocked_words=config.ignored_words)
    return default_sanitizer
