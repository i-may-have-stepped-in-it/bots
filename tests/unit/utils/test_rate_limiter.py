"""
Unit tests for utils/rate_limiter.py - Rate limiting utilities.
"""

import pytest
import time
import threading
from unittest.mock import patch

from utils.rate_limiter import (
    TokenBucket,
    RateLimiterManager,
    create_rate_limiter,
)


# =============================================================================
# TokenBucket Tests
# =============================================================================

class TestTokenBucket:
    """Tests for TokenBucket rate limiter."""

    def test_initialization(self):
        """Test token bucket initializes with correct values."""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        assert bucket.capacity == 10
        assert bucket.tokens == 10
        assert bucket.refill_rate == 2.0

    def test_consume_within_capacity(self):
        """Test consuming tokens within capacity."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        assert bucket.consume(1) is True
        assert bucket.consume(2) is True
        assert bucket.tokens == 2  # 5 - 1 - 2

    def test_consume_exceeds_capacity(self):
        """Test consuming more tokens than available."""
        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        assert bucket.consume(1) is True
        assert bucket.consume(1) is True
        assert bucket.consume(1) is False  # No tokens left

    def test_consume_exact_capacity(self):
        """Test consuming exactly all tokens."""
        bucket = TokenBucket(capacity=3, refill_rate=1.0)
        assert bucket.consume(3) is True
        assert bucket.tokens == 0

    def test_consume_zero_tokens(self):
        """Test consuming zero tokens."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        assert bucket.consume(0) is True  # Should always succeed
        assert bucket.tokens == 5

    def test_refill_over_time(self):
        """Test tokens refill over time."""
        bucket = TokenBucket(capacity=5, refill_rate=10.0)  # 10 tokens/sec
        assert bucket.consume(5) is True  # Exhaust all tokens
        assert bucket.tokens == 0
        
        time.sleep(0.3)  # Wait for 3 tokens to refill
        
        assert bucket.consume(2) is True  # Should have tokens now
        assert bucket.tokens < 3  # Some tokens were consumed

    def test_refill_does_not_exceed_capacity(self):
        """Test refill doesn't exceed max capacity."""
        bucket = TokenBucket(capacity=3, refill_rate=100.0)  # Fast refill
        assert bucket.consume(1) is True  # 2 tokens left
        
        time.sleep(0.1)  # Wait for refill
        
        # Should be capped at capacity
        assert bucket.get_tokens() <= 3

    def test_get_tokens_returns_current_count(self):
        """Test get_tokens returns accurate count."""
        bucket = TokenBucket(capacity=10, refill_rate=1.0)
        bucket.consume(3)
        
        tokens = bucket.get_tokens()
        assert 6.9 < tokens < 7.1  # Approximately 7 (with small timing variance)

    def test_thread_safety(self):
        """Test token bucket is thread-safe."""
        bucket = TokenBucket(capacity=100, refill_rate=1000.0)
        results = []
        
        def consume_tokens():
            for _ in range(10):
                results.append(bucket.consume(1))
        
        threads = [threading.Thread(target=consume_tokens) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All 100 consumes should succeed
        assert sum(results) == 100


# =============================================================================
# RateLimiterManager Tests
# =============================================================================

class TestRateLimiterManager:
    """Tests for RateLimiterManager singleton."""

    def test_singleton_pattern(self):
        """Test manager is a singleton."""
        manager1 = RateLimiterManager()
        manager2 = RateLimiterManager()
        assert manager1 is manager2

    def test_get_limiter_creates_new(self):
        """Test get_limiter creates new limiter if not exists."""
        manager = RateLimiterManager()
        manager.reset()  # Clear any existing limiters
        
        limiter = manager.get_limiter("test", capacity=5, refill_rate=1.0)
        assert isinstance(limiter, TokenBucket)
        assert limiter.capacity == 5

    def test_get_limiter_returns_existing(self):
        """Test get_limiter returns existing limiter."""
        manager = RateLimiterManager()
        manager.reset()
        
        limiter1 = manager.get_limiter("shared", capacity=5, refill_rate=1.0)
        limiter2 = manager.get_limiter("shared", capacity=10, refill_rate=2.0)  # Different params
        
        # Should return same instance (params ignored if exists)
        assert limiter1 is limiter2

    def test_reset_specific_limiter(self):
        """Test reset removes specific limiter."""
        manager = RateLimiterManager()
        manager.reset()
        
        limiter1 = manager.get_limiter("limiter1", capacity=5, refill_rate=1.0)
        limiter2 = manager.get_limiter("limiter2", capacity=5, refill_rate=1.0)
        
        manager.reset("limiter1")
        
        # limiter1 should be recreated, limiter2 should be same
        limiter1_new = manager.get_limiter("limiter1", capacity=5, refill_rate=1.0)
        limiter2_same = manager.get_limiter("limiter2", capacity=5, refill_rate=1.0)
        
        assert limiter1 is not limiter1_new
        assert limiter2 is limiter2_same

    def test_reset_all_limiters(self):
        """Test reset clears all limiters."""
        manager = RateLimiterManager()
        limiter1 = manager.get_limiter("a", capacity=5, refill_rate=1.0)
        limiter2 = manager.get_limiter("b", capacity=5, refill_rate=1.0)
        
        manager.reset()
        
        # Both should be recreated
        limiter1_new = manager.get_limiter("a", capacity=5, refill_rate=1.0)
        limiter2_new = manager.get_limiter("b", capacity=5, refill_rate=1.0)
        
        assert limiter1 is not limiter1_new
        assert limiter2 is not limiter2_new


# =============================================================================
# create_rate_limiter Tests
# =============================================================================

class TestCreateRateLimiter:
    """Tests for create_rate_limiter convenience function."""

    def test_create_rate_limiter_basic(self):
        """Test creating rate limiter for requests per minute."""
        limiter = create_rate_limiter(requests_per_minute=10)
        assert limiter.capacity == 10
        assert limiter.refill_rate == 10 / 60.0  # per second

    def test_create_rate_limiter_high_rate(self):
        """Test creating rate limiter with high request rate."""
        limiter = create_rate_limiter(requests_per_minute=60)
        assert limiter.capacity == 60
        assert limiter.refill_rate == 1.0  # 1 per second

    def test_create_rate_limiter_low_rate(self):
        """Test creating rate limiter with low request rate."""
        limiter = create_rate_limiter(requests_per_minute=1)
        assert limiter.capacity == 1
        assert limiter.refill_rate == 1 / 60.0  # 1 per minute

    def test_created_limiter_functional(self):
        """Test created limiter actually works."""
        limiter = create_rate_limiter(requests_per_minute=3)
        
        assert limiter.consume(1) is True
        assert limiter.consume(1) is True
        assert limiter.consume(1) is True
        assert limiter.consume(1) is False  # Rate limited


# =============================================================================
# Integration Tests
# =============================================================================

class TestRateLimiterIntegration:
    """Integration tests for rate limiting."""

    def test_multiple_consumers_different_buckets(self):
        """Test independent buckets for different consumers."""
        manager = RateLimiterManager()
        manager.reset()
        
        user1_limiter = manager.get_limiter("user1", capacity=3, refill_rate=1.0)
        user2_limiter = manager.get_limiter("user2", capacity=3, refill_rate=1.0)
        
        # Both should be able to consume independently
        assert user1_limiter.consume(3) is True
        assert user2_limiter.consume(3) is True
        
        # Both should be rate limited
        assert user1_limiter.consume(1) is False
        assert user2_limiter.consume(1) is False

    def test_rate_limiter_recovery(self):
        """Test rate limiter recovers after time."""
        limiter = TokenBucket(capacity=2, refill_rate=5.0)  # 5 tokens/sec
        
        # Exhaust tokens
        assert limiter.consume(2) is True
        assert limiter.consume(1) is False
        
        # Wait for recovery
        time.sleep(0.5)  # Should get 2.5 tokens back
        
        # Should be able to consume again
        assert limiter.consume(1) is True
