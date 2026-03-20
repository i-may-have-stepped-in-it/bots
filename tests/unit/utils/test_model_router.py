"""
Unit tests for utils/model_router.py - Model routing and complexity scoring.
"""

import pytest
from unittest.mock import patch

from utils.model_router import (
    ModelTier,
    RoutingDecision,
    MODELS,
    FALLBACK_CHAINS,
    _contains_phrase,
    estimate_tokens,
    calculate_complexity_score,
    detect_task_type,
    route_message,
    detect_uncensored_content,
)


# =============================================================================
# ModelTier Tests
# =============================================================================

class TestModelTier:
    """Tests for the ModelTier enum."""

    def test_tier_values(self):
        """Test ModelTier enum values."""
        assert ModelTier.HIGHSPEED.value == "highspeed"
        assert ModelTier.INTELLIGENCE.value == "intelligence"
        assert ModelTier.UNCENSORED.value == "uncensored"

    def test_model_mappings(self):
        """Test that all tiers have model mappings."""
        for tier in ModelTier:
            assert tier in MODELS
            assert isinstance(MODELS[tier], str)

    def test_fallback_chains(self):
        """Test that fallback chains exist for all tiers."""
        for tier in ModelTier:
            assert tier in FALLBACK_CHAINS
            assert isinstance(FALLBACK_CHAINS[tier], list)


# =============================================================================
# RoutingDecision Tests
# =============================================================================

class TestRoutingDecision:
    """Tests for the RoutingDecision dataclass."""

    def test_creation(self):
        """Test creating a RoutingDecision."""
        decision = RoutingDecision(
            tier=ModelTier.HIGHSPEED,
            model="test-model",
            score=0.5,
            reason="Test reason",
            tokens=100,
        )
        
        assert decision.tier == ModelTier.HIGHSPEED
        assert decision.model == "test-model"
        assert decision.score == 0.5
        assert decision.reason == "Test reason"
        assert decision.tokens == 100
        assert decision.fallback_model is None
        assert decision.fallback_chain is None

    def test_with_fallbacks(self):
        """Test RoutingDecision with fallback chain."""
        decision = RoutingDecision(
            tier=ModelTier.INTELLIGENCE,
            model="primary-model",
            score=0.8,
            reason="High complexity",
            tokens=500,
            fallback_model="fallback-1",
            fallback_chain=["fallback-1", "fallback-2"],
        )
        
        assert decision.fallback_model == "fallback-1"
        assert decision.fallback_chain == ["fallback-1", "fallback-2"]


# =============================================================================
# _contains_phrase Tests
# =============================================================================

class TestContainsPhrase:
    """Tests for the _contains_phrase function."""

    def test_exact_match(self):
        """Test exact word matching."""
        assert _contains_phrase("hello world", ["hello"]) is True
        assert _contains_phrase("hello world", ["world"]) is True

    def test_case_insensitive(self):
        """Test case-insensitive matching."""
        assert _contains_phrase("Hello World", ["hello"]) is True
        assert _contains_phrase("HELLO WORLD", ["hello"]) is True
        assert _contains_phrase("hello world", ["HELLO"]) is True

    def test_word_boundary(self):
        """Test word boundary matching."""
        assert _contains_phrase("debugging code", ["debug"]) is False
        assert _contains_phrase("debug code", ["debug"]) is True

    def test_partial_match(self):
        """Test partial word doesn't match."""
        assert _contains_phrase("debugger", ["debug"]) is False
        assert _contains_phrase("codeword", ["code"]) is False

    def test_empty_phrases(self):
        """Test with empty phrases list."""
        assert _contains_phrase("hello world", []) is False

    def test_empty_text(self):
        """Test with empty text."""
        assert _contains_phrase("", ["hello"]) is False


# =============================================================================
# estimate_tokens Tests
# =============================================================================

class TestEstimateTokens:
    """Tests for the estimate_tokens function."""

    def test_basic_estimation(self):
        """Test basic token estimation (~4 chars per token)."""
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("abcdefghijklmnop") == 4

    def test_empty_string(self):
        """Test empty string."""
        assert estimate_tokens("") == 0

    def test_code_block_bonus(self):
        """Test code blocks get +50% tokens."""
        text_with_code = "```python\nprint('hello')\n```"
        base_tokens = len(text_with_code) // 4
        expected = int(base_tokens * 1.5)
        
        assert estimate_tokens(text_with_code) == expected

    def test_inline_code_bonus(self):
        """Test inline code gets +50% tokens."""
        text_with_inline = "Use `print()` function"
        base_tokens = len(text_with_inline) // 4
        expected = int(base_tokens * 1.5)
        
        assert estimate_tokens(text_with_inline) == expected

    def test_no_code(self):
        """Test regular text without code."""
        text = "This is a regular sentence without any code blocks."
        expected = len(text) // 4
        
        assert estimate_tokens(text) == expected

    def test_very_long_text(self):
        """Test very long text."""
        text = "a" * 10000
        expected = 2500  # 10000 // 4
        
        assert estimate_tokens(text) == expected


# =============================================================================
# calculate_complexity_score Tests
# =============================================================================

class TestCalculateComplexityScore:
    """Tests for the calculate_complexity_score function."""

    def test_empty_message(self):
        """Test empty message returns minimum score."""
        score = calculate_complexity_score("")
        assert 0 <= score <= 1

    def test_very_short_message(self):
        """Test very short message (<=50 tokens)."""
        score = calculate_complexity_score("Hi")
        assert score >= 0.1  # Base score for short

    def test_short_message(self):
        """Test short message (<=150 tokens)."""
        text = "Hello world " * 10  # ~120 chars = ~30 tokens
        score = calculate_complexity_score(text)
        assert score >= 0.1  # Base score for short messages

    def test_medium_message(self):
        """Test medium message (<=500 tokens)."""
        text = "Hello world " * 50  # ~600 chars = ~150 tokens
        score = calculate_complexity_score(text)
        assert score >= 0.2  # Actual base score for this token range

    def test_long_message(self):
        """Test long message (>5000 chars)."""
        text = "A" * 6000
        score = calculate_complexity_score(text)
        assert score >= 0.15  # Bonus for long context

    def test_error_keywords(self):
        """Test error keywords increase score."""
        base_score = calculate_complexity_score("Hello world")
        error_score = calculate_complexity_score("There is an error in the code")
        
        assert error_score > base_score

    def test_high_complexity_keywords(self):
        """Test high complexity keywords increase score significantly."""
        base_score = calculate_complexity_score("Hello world")
        arch_score = calculate_complexity_score("Design the system architecture")
        
        assert arch_score > base_score + 0.3

    def test_reasoning_keywords(self):
        """Test reasoning keywords increase score."""
        base_score = calculate_complexity_score("Hello world")
        reason_score = calculate_complexity_score("Analyze the tradeoffs")
        
        assert reason_score > base_score + 0.2

    def test_code_presence(self):
        """Test code presence increases score."""
        base_score = calculate_complexity_score("Hello world")
        code_score = calculate_complexity_score("Use function test()")
        
        assert code_score > base_score + 0.25

    def test_multiple_questions(self):
        """Test multiple questions increase score."""
        base_score = calculate_complexity_score("Hello?")
        multi_score = calculate_complexity_score("What? How? When? Where?")
        
        assert multi_score > base_score

    def test_vague_keywords(self):
        """Test vague keywords increase score."""
        base_score = calculate_complexity_score("Hello world")
        vague_score = calculate_complexity_score("Do something with stuff")
        
        assert vague_score > base_score

    def test_data_patterns(self):
        """Test data patterns (numbers with units) increase score."""
        base_score = calculate_complexity_score("Hello world")
        data_score = calculate_complexity_score("Latency is 100ms, throughput 50%")
        
        assert data_score > base_score

    def test_score_capped_at_one(self):
        """Test score is capped at 1.0."""
        # Create a message with many complexity indicators
        text = """
        Analyze the distributed system architecture and debug the error.
        The system has 100ms latency, 50% throughput, 10 million requests.
        Consider the tradeoffs and implications of the microservice design.
        Optimize the concurrent implementation of the algorithm.
        ```python
def complex_function():
    pass
        ```
        What are the pros and cons? How can we improve performance?
        Something about stuff...
        """ + "A" * 6000  # Long context bonus
        
        score = calculate_complexity_score(text)
        assert score <= 1.0


# =============================================================================
# detect_task_type Tests
# =============================================================================

class TestDetectTaskType:
    """Tests for the detect_task_type function."""

    def test_debugging_task(self):
        """Test detecting debugging tasks."""
        assert detect_task_type("I have an error in my code") == "debugging"
        assert detect_task_type("Debug this exception") == "debugging"
        assert detect_task_type("Fix the bug") == "debugging"
        assert detect_task_type("Stack trace shows failure") == "debugging"

    def test_architecture_task(self):
        """Test detecting architecture tasks."""
        assert detect_task_type("Design the system architecture") == "architecture"
        assert detect_task_type("How to make it scalable?") == "architecture"
        assert detect_task_type("Microservice infrastructure") == "architecture"

    def test_reasoning_task(self):
        """Test detecting reasoning tasks."""
        assert detect_task_type("Analyze the tradeoffs") == "reasoning"
        assert detect_task_type("Evaluate the implications") == "reasoning"
        assert detect_task_type("Research this topic") == "reasoning"

    def test_development_task(self):
        """Test detecting development tasks."""
        assert detect_task_type("Write a function") == "development"
        assert detect_task_type("Implement the API") == "development"
        assert detect_task_type("Build a class") == "development"

    def test_data_task(self):
        """Test detecting data tasks."""
        assert detect_task_type("Show metrics dashboard") == "data"
        assert detect_task_type("SQL query for analytics") == "data"
        assert detect_task_type("Create visualization") == "data"

    def test_query_task(self):
        """Test detecting query tasks."""
        assert detect_task_type("What is the status?") == "query"
        assert detect_task_type("How to do this?") == "query"
        assert detect_task_type("Look up the value") == "query"

    def test_writing_task(self):
        """Test detecting writing tasks."""
        assert detect_task_type("Write a summary") == "writing"
        assert detect_task_type("Draft an email") == "writing"
        assert detect_task_type("Translate this text") == "writing"

    def test_administrative_task(self):
        """Test detecting administrative tasks."""
        assert detect_task_type("Hello! Thanks!") == "administrative"
        assert detect_task_type("Schedule a meeting") == "administrative"
        assert detect_task_type("Remind me") == "administrative"

    def test_general_task(self):
        """Test detecting general tasks (or administrative for greetings)."""
        # "Hello" is in administrative keywords
        assert detect_task_type("Hello world") in ["general", "administrative"]
        assert detect_task_type("Random text") == "general"
        assert detect_task_type("") == "general"

    def test_priority_order(self):
        """Test that earlier types take priority."""
        # Should be debugging, not development
        assert detect_task_type("Debug and write code") == "debugging"
        # Should be architecture, not reasoning
        assert detect_task_type("Design architecture and analyze") == "architecture"


# =============================================================================
# should_use_uncensored_model Tests
# =============================================================================

class TestDetectUncensoredContent:
    """Tests for the detect_uncensored_content function."""

    def test_no_uncensored_content(self):
        """Test that normal content doesn't trigger uncensored."""
        assert detect_uncensored_content("Hello world") is False
        assert detect_uncensored_content("Write some code") is False
        assert detect_uncensored_content("What's the weather?") is False

    def test_explicit_keywords(self):
        """Test explicit content detection."""
        assert detect_uncensored_content("This is nsfw content") is True
        assert detect_uncensored_content("XXX rated") is True
        assert detect_uncensored_content("Explicit material") is True

    def test_adult_keywords(self):
        """Test adult content detection."""
        assert detect_uncensored_content("Adult content warning") is True
        assert detect_uncensored_content("Erotic story") is True

    def test_case_insensitive(self):
        """Test case-insensitive detection."""
        assert detect_uncensored_content("NSFW") is True
        assert detect_uncensored_content("nsfw") is True
        assert detect_uncensored_content("Nsfw") is True

    def test_word_boundaries(self):
        """Test word boundary matching."""
        assert detect_uncensored_content("This is innocuous") is False
        assert detect_uncensored_content("xxx-rated") is True


# =============================================================================
# route_message Tests
# =============================================================================

class TestRouteMessage:
    """Tests for the route_message function."""

    def test_simple_query_routes_to_highspeed(self):
        """Test simple queries route to highspeed model."""
        decision = route_message("Hello")
        
        assert decision.tier == ModelTier.HIGHSPEED
        assert decision.score < 0.4  # Low complexity

    def test_debugging_routes_to_intelligence(self):
        """Test debugging tasks route to intelligence model."""
        decision = route_message("I have an error in my code")
        
        assert decision.tier == ModelTier.INTELLIGENCE
        assert decision.score > 0.3  # Moderate complexity

    def test_architecture_routes_to_intelligence(self):
        """Test architecture tasks route to intelligence model."""
        decision = route_message("Design a distributed system architecture")
        
        assert decision.tier == ModelTier.INTELLIGENCE
        assert decision.score > 0.3  # Architecture forces intelligence regardless of score

    def test_uncensored_content_routes_to_uncensored(self):
        """Test uncensored content routes to uncensored model."""
        decision = route_message("Tell me about nsfw content")
        
        assert decision.tier == ModelTier.UNCENSORED

    def test_token_estimation_included(self):
        """Test that token estimation is included in decision."""
        decision = route_message("Hello world")
        
        assert decision.tokens > 0
        assert isinstance(decision.tokens, int)

    def test_fallback_chain_included(self):
        """Test that fallback chain is included for high tiers."""
        decision_intelligence = route_message("Design a system architecture")
        decision_highspeed = route_message("Hello")
        
        assert decision_intelligence.fallback_chain is not None
        assert decision_highspeed.fallback_chain is not None
        assert len(decision_intelligence.fallback_chain) > 0

    def test_reason_provided(self):
        """Test that routing reason is provided."""
        decision = route_message("Hello")
        
        assert decision.reason != ""
        assert isinstance(decision.reason, str)

    def test_custom_default_model(self):
        """Test custom default model parameter (used when tier not in MODELS)."""
        # Note: default_model is only used as fallback if tier lookup fails
        decision = route_message("Hello", default_model="custom/model")
        # For highspeed tier, it uses MODELS[HIGHSPEED] not default_model
        assert decision.tier == ModelTier.HIGHSPEED

    def test_long_context_routes_to_intelligence(self):
        """Test very long context routes to intelligence."""
        long_message = "A" * 6000  # Very long message
        decision = route_message(long_message)
        
        assert decision.tier == ModelTier.INTELLIGENCE
        assert decision.score > 0.6  # Long context pushes score high


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================

class TestRouterEdgeCases:
    """Tests for edge cases."""

    def test_empty_message(self):
        """Test routing empty message."""
        decision = route_message("")
        
        assert decision.tier == ModelTier.HIGHSPEED
        assert decision.score < 0.2

    def test_very_long_message(self):
        """Test routing very long message."""
        message = "Word " * 10000
        decision = route_message(message)
        
        assert decision.score >= 0.9  # Should be near max (capped at 1.0)

    def test_unicode_message(self):
        """Test routing unicode message."""
        decision = route_message("你好世界 🎉 日本語")
        
        assert decision.tier == ModelTier.HIGHSPEED
        assert decision.tokens > 0

    def test_code_heavy_message(self):
        """Test routing message with lots of code."""
        code_message = """
```python
def function1():
    pass

def function2():
    return 42

class MyClass:
    def method(self):
        return self.value
```
Analyze this code
        """
        decision = route_message(code_message)
        
        assert decision.score > 0.5  # Code increases complexity

    def test_mixed_signals(self):
        """Test message with mixed complexity signals."""
        # Short but has complexity keywords
        message = "Debug this"  # Short but debugging keyword
        decision = route_message(message)
        
        # Should still route appropriately based on overall score
        assert decision.tier in [ModelTier.HIGHSPEED, ModelTier.INTELLIGENCE]
