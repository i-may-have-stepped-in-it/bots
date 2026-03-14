"""
Rate limiting utilities for Jennifer.

Provides token bucket rate limiter for controlling API call rates.
"""

import time
import threading
from typing import Optional


class TokenBucket:
    """Token bucket rate limiter.
    
    Thread-safe implementation for use across multiple async tasks.
    
    Example:
        bucket = TokenBucket(capacity=5, refill_rate=1.0)  # 5 requests per second
        if bucket.consume(1):
            # Proceed with API call
        else:
            # Rate limit exceeded
    """
    
    def __init__(self, capacity: float, refill_rate: float):
        """Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens in the bucket
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill_time = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: float) -> bool:
        """Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False if not enough tokens available
        """
        with self._lock:
            current_time = time.time()
            elapsed = current_time - self.last_refill_time
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.refill_rate
            )
            self.last_refill_time = current_time
            
            # Check if we have enough tokens
            if tokens <= self.tokens:
                self.tokens -= tokens
                return True
            return False
    
    def get_tokens(self) -> float:
        """Get current token count (for monitoring)."""
        with self._lock:
            current_time = time.time()
            elapsed = current_time - self.last_refill_time
            return min(self.capacity, self.tokens + elapsed * self.refill_rate)


class RateLimiterManager:
    """Manages multiple named rate limiters."""
    
    _instance = None
    _limiters: dict = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._limiters = {}
        return cls._instance
    
    def get_limiter(self, name: str, capacity: float, refill_rate: float) -> TokenBucket:
        """Get or create a named rate limiter."""
        if name not in self._limiters:
            self._limiters[name] = TokenBucket(capacity, refill_rate)
        return self._limiters[name]
    
    def reset(self, name: Optional[str] = None):
        """Reset a specific limiter or all limiters."""
        if name:
            self._limiters.pop(name, None)
        else:
            self._limiters.clear()


# Convenience function for common rate limits
def create_rate_limiter(requests_per_minute: float) -> TokenBucket:
    """Create a rate limiter for N requests per minute.
    
    Example:
        # 10 requests per minute
        limiter = create_rate_limiter(10)
    """
    return TokenBucket(
        capacity=requests_per_minute,
        refill_rate=requests_per_minute / 60.0
    )
