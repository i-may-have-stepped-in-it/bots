"""
Model Router for Jennifer Discord Bots
Ports the bash model-router logic to Python for programmatic agent creation.
Integrates with jennifer/utils/openclaw.py for dynamic model selection.

Usage:
    from utils.model_router import route_message, calculate_complexity_score
    
    # Route a user message
    model = route_message(user_message, default_model="zai/glm-4.7-flash")
    
    # Or just get complexity score
    score = calculate_complexity_score(user_message)
"""

import re
import logging
from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Model tiers matching the bash router."""
    HIGHSPEED = "highspeed"
    BALANCED = "balanced"
    INTELLIGENCE = "intelligence"
    UNCENSORED = "uncensored"


@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    tier: ModelTier
    model: str
    score: float
    reason: str
    tokens: int
    fallback_model: Optional[str] = None


# Model mappings
MODELS = {
    ModelTier.INTELLIGENCE: "moonshot/kimi-k2.5",
    ModelTier.BALANCED: "minimax/m2.5",
    ModelTier.HIGHSPEED: "zai/glm-4.7-flash",
    ModelTier.UNCENSORED: "venice/GLM-4.7-Flash-Heretic",
}

# Fallback models (for when primary is unavailable)
FALLBACK_MODELS = {
    ModelTier.UNCENSORED: "localai/Qwen3-14B-Nexa-Uncensored",
}

# Budget configuration
MONTHLY_BUDGET = 15.0
DAILY_BUDGET = 1.5


def estimate_tokens(text: str) -> int:
    """
    Estimate token count from text.
    ~4 chars = 1 token (industry standard)
    Code blocks are more token-dense (+50%)
    """
    char_count = len(text)
    tokens = char_count // 4
    
    # Code blocks are more token-dense
    if re.search(r'```|`[^`]+`', text):
        tokens = int(tokens * 1.5)  # +50% for code
    
    return tokens


def calculate_complexity_score(message: str) -> float:
    """
    Calculate complexity score 0.0-1.0 for a message.
    Port of router-v2.sh complexity scoring.
    """
    score = 0.0
    msg_lower = message.lower()
    
    # Get token estimate
    tokens = estimate_tokens(message)
    
    # Length-based scoring
    if tokens <= 50:
        score += 0.1
    elif tokens <= 150:
        score += 0.2
    elif tokens <= 500:
        score += 0.3
    elif tokens <= 2000:
        score += 0.5
    elif tokens <= 8000:
        score += 0.6
    else:
        score += 0.75  # Very long contexts
    
    # Context length bonus (>5000 chars)
    if len(message) > 5000:
        score += 0.15
    
    # Code presence scoring
    if re.search(r'(```|`[^`]+`|function|class|def |const |let |var |import |#include|=>|\{|\})', message):
        score += 0.3
    
    # Error/debugging indicators (high complexity)
    if re.search(r'\b(error|exception|fail|crash|bug|broken|debug|troubleshoot|not working|doesn\'t work|failed)\b', msg_lower):
        score += 0.25
    
    # Data patterns (metrics, numbers = analysis needed)
    data_patterns = len(re.findall(r'[0-9]+\.?[0-9]*\s*(%|ms|s|mb|gb|tb|million|billion)', message))
    if data_patterns > 2:
        score += 0.20
    
    # High complexity keywords (architecture, design, research)
    if re.search(r'\b(architecture|design|system|scalable|distributed)\b', msg_lower):
        score += 0.35
    
    # Reasoning keywords (analysis, evaluation, tradeoffs)
    if re.search(r'\b(analyze|evaluate|compare|tradeoffs|implications|assess|research|investigate|study|optimize|performance tune)\b', msg_lower):
        score += 0.25
    
    # Standard complexity keywords
    if re.search(r'\b(refactor|implement|complex|optimize|performance|concurrent|algorithm|memory leak|race condition|deadlock|bottleneck)\b', msg_lower):
        score += 0.3
    
    # Medium complexity keywords
    if re.search(r'\b(build|create|develop|write|generate|configure|setup|deploy|install|modify)\b', msg_lower):
        score += 0.1
    
    # Question complexity (multiple questions)
    q_count = message.count('?')
    if q_count > 2:
        score += 0.10
    
    # Vague terms (vague = needs stronger model)
    if re.search(r'\b(something|stuff|thing|whatever|etc|…|\.\.\.)\b', msg_lower):
        score += 0.15
    
    # Cap at 1.0
    return min(score, 1.0)


def detect_task_type(message: str) -> str:
    """
    Detect task type from message for specialized routing.
    Returns: debugging, architecture, reasoning, development, data, query, writing, administrative, general
    """
    msg_lower = message.lower()
    
    # DEBUGGING - Highest complexity
    if re.search(r'\b(debug|troubleshoot|diagnose|fix|error|exception|crash|bug|broken|not working|doesn\'t work|failed|stack trace|breakpoint)\b', msg_lower):
        return "debugging"
    
    # ARCHITECTURE - Highest complexity
    if re.search(r'\b(architect|design.*system|scalable|distributed|microservice|infrastructure|pattern|scalability)\b', msg_lower):
        return "architecture"
    
    # REASONING - High complexity
    if re.search(r'\b(analyze|evaluate|compare.*tradeoffs|implications|assess|research|investigate|study|optimize|performance tune)\b', msg_lower):
        return "reasoning"
    
    # Development tasks
    if re.search(r'\b(code|program|develop|implement|build|refactor|script|function|api|database|write.*code|create.*function)\b', msg_lower):
        return "development"
    
    # Data/Metrics tasks
    if re.search(r'\b(metrics|data|analytics|report|dashboard|visualization|chart|graph)\b', msg_lower):
        return "data"
    
    # Query tasks
    if re.search(r'\b(search|find|look up|check|status|query|get|show|list|what is|what are|how to|help with)\b', msg_lower):
        return "query"
    
    # Writing tasks
    if re.search(r'\b(write|draft|compose|summarize|translate|rewrite|paraphrase|format|edit)\b', msg_lower):
        return "writing"
    
    # Administrative tasks
    if re.search(r'\b(schedule|remind|notify|ping|hello|hi|bye|thanks|ok|yes|no)\b', msg_lower):
        return "administrative"
    
    return "general"


def detect_uncensored_content(message: str) -> bool:
    """
    Detect NSFW/explicit content keywords for uncensored routing.
    Returns True if message contains explicit content indicators.
    """
    msg_lower = message.lower()
    
    # Explicit content keywords
    # Note: This is for routing to uncensored models, not for blocking
    explicit_keywords = [
        # Adult content indicators
        r'\bxxx\b',
        r'\bnsfw\b',
        r'\bexplicit\b',
        r'\buncensored\b',
        r'\badult\b',
        r'\berotic\b',
        r'\bporn\b',
        r'\bhentai\b',
        # Body parts (context-dependent, but strong signal)
        r'\bnipples?\b',
        r'\bpussy\b',
        r'\bdick\b',
        r'\bcock\b',
        r'\btits?\b',
        r'\bboobs?\b',
        r'\basshole\b',
        r'\bcum\b',
        r'\bsquirt\b',
        # Sexual acts
        r'\bfuck(ing)?\b',
        r'\bsex\b',
        r'\bmasturbat(e|ing|ion)\b',
        r'\boral sex\b',
        r'\banal\b',
        # Roleplay/context indicators
        r'\bdaddy\b.*\bkink',
        r'\bsubmissive\b',
        r'\bdominant\b',
    ]
    
    for pattern in explicit_keywords:
        if re.search(pattern, msg_lower):
            return True
    
    return False


def check_prefix_routing(message: str) -> Optional[str]:
    """
    Check for explicit routing prefixes (@kimi, @mini, @flash, @codex, @uncensored).
    Returns the model to use, or None if no prefix found.
    """
    trimmed = message.strip().lower()
    
    if re.match(r'^@kimi\b|^@k\b', trimmed):
        return MODELS[ModelTier.INTELLIGENCE]
    
    if re.match(r'^@minimax\b|^@mini\b|^@m\b', trimmed):
        return MODELS[ModelTier.BALANCED]
    
    if re.match(r'^@flash\b|^@f\b', trimmed):
        return MODELS[ModelTier.HIGHSPEED]
    
    if re.match(r'^@codex\b|^@c\b', trimmed):
        return "openai-codex/gpt-5.3-codex"
    
    if re.match(r'^@uncensored\b|^@u\b|^@nsfw\b', trimmed):
        return MODELS[ModelTier.UNCENSORED]
    
    return None


def get_tier_from_score(score: float, task_type: str) -> ModelTier:
    """
    Determine tier based on complexity score and task type.
    """
    # High complexity tasks always go to intelligence
    if task_type in ("debugging", "architecture", "reasoning"):
        return ModelTier.INTELLIGENCE
    
    if task_type in ("development", "data"):
        if score >= 0.5:
            return ModelTier.INTELLIGENCE
        else:
            return ModelTier.BALANCED
    
    if task_type in ("query", "administrative"):
        return ModelTier.HIGHSPEED
    
    if task_type == "writing":
        if score >= 0.6:
            return ModelTier.BALANCED
        else:
            return ModelTier.HIGHSPEED
    
    # Default score-based routing
    if score >= 0.6:
        return ModelTier.INTELLIGENCE
    elif score <= 0.3:
        return ModelTier.HIGHSPEED
    else:
        return ModelTier.BALANCED


def check_budget_override(current_spend: float, requested_tier: ModelTier) -> Optional[ModelTier]:
    """
    Check if budget constraints force a tier downgrade.
    Returns the tier to use, or None if no override needed.
    """
    budget_percent = (current_spend / MONTHLY_BUDGET) * 100
    
    # 95% budget - force free tier
    if budget_percent >= 95:
        logger.warning(f"Budget at {budget_percent:.1f}% - forcing highspeed tier")
        return ModelTier.HIGHSPEED
    
    # 90% budget - prefer balanced over intelligence
    if budget_percent >= 90 and requested_tier == ModelTier.INTELLIGENCE:
        logger.warning(f"Budget at {budget_percent:.1f}% - downgrading to balanced")
        return ModelTier.BALANCED
    
    return None


def route_message(
    message: str,
    default_model: str = "zai/glm-4.7-flash",
    current_spend: float = 0.0,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None
) -> RoutingDecision:
    """
    Main routing function - determines the best model for a message.
    
    Args:
        message: The user's message
        default_model: Fallback model if routing fails
        current_spend: Current month's API spend (for budget checks)
        user_id: Discord user ID (for logging)
        user_name: Discord username (for logging)
    
    Returns:
        RoutingDecision with tier, model, score, reason, and token estimate
    """
    # 1. Check for prefix routing (explicit user intent)
    prefix_model = check_prefix_routing(message)
    if prefix_model:
        # Determine tier from prefix model
        tier = ModelTier.HIGHSPEED
        for t, m in MODELS.items():
            if m == prefix_model:
                tier = t
                break
        # Include fallback for uncensored tier
        fallback = FALLBACK_MODELS.get(tier) if tier == ModelTier.UNCENSORED else None
        return RoutingDecision(
            tier=tier,
            model=prefix_model,
            score=0.0,
            reason="prefix_override",
            tokens=estimate_tokens(message),
            fallback_model=fallback
        )
    
    # 2. Check for uncensored/explicit content
    if detect_uncensored_content(message):
        return RoutingDecision(
            tier=ModelTier.UNCENSORED,
            model=MODELS[ModelTier.UNCENSORED],
            score=0.0,
            reason="uncensored_content",
            tokens=estimate_tokens(message),
            fallback_model=FALLBACK_MODELS.get(ModelTier.UNCENSORED)
        )
    
    # 3. Calculate complexity
    score = calculate_complexity_score(message)
    task_type = detect_task_type(message)
    
    # 3. Determine tier
    tier = get_tier_from_score(score, task_type)
    
    # 4. Check budget constraints
    budget_override = check_budget_override(current_spend, tier)
    if budget_override:
        tier = budget_override
        reason = f"budget_forced_{tier.value}"
    else:
        reason = f"score_{score:.1f}_task_{task_type}"
    
    # 5. Select model
    model = MODELS.get(tier, default_model)
    tokens = estimate_tokens(message)
    
    # Log the decision
    user_info = f" for {user_name}" if user_name else ""
    logger.info(f"Routed{user_info}: {tier.value} -> {model} ({reason}, ~{tokens} tokens)")
    
    return RoutingDecision(
        tier=tier,
        model=model,
        score=score,
        reason=reason,
        tokens=tokens
    )


def get_model_for_discord_interaction(
    message_content: str,
    conversation_history: Optional[list] = None,
    **kwargs
) -> str:
    """
    Simplified interface for Jennifer's Discord bot.
    Returns just the model string.
    
    Usage:
        model = get_model_for_discord_interaction(user_message)
        # Then use model in openclaw.send_message()
    """
    decision = route_message(message_content, **kwargs)
    return decision.model


# Convenience functions for specific tiers
def is_complex_task(message: str) -> bool:
    """Check if a message is complex enough to need intelligence tier."""
    score = calculate_complexity_score(message)
    return score >= 0.6


def is_simple_task(message: str) -> bool:
    """Check if a message is simple enough for highspeed/free tier."""
    score = calculate_complexity_score(message)
    return score <= 0.3


def get_prefix_help_text() -> str:
    """Get help text for prefix routing."""
    return """
**Model Routing Prefixes:**
• `@kimi` or `@k` - Use Kimi K2.5 (best for complex tasks)
• `@mini` or `@m` - Use MiniMax M2.5 (balanced)
• `@flash` or `@f` - Use Gemini Flash (fast, simple queries)
• `@codex` or `@c` - Use GPT-5.3 Codex (coding)
• `@uncensored` or `@u` - Use Venice GLM 4.7 Flash Heretic (adult/NSFW)

Without a prefix, I'll automatically choose based on your message complexity.
""".strip()


def get_model_with_fallback(decision: RoutingDecision) -> tuple[str, Optional[str]]:
    """
    Get the primary model and optional fallback for a routing decision.
    
    Returns:
        Tuple of (primary_model, fallback_model_or_None)
    """
    return decision.model, decision.fallback_model


# Stats tracking for cost visibility
class RouterStats:
    """Track routing decisions for cost analysis."""
    
    def __init__(self):
        self.requests = {
            ModelTier.INTELLIGENCE: 0,
            ModelTier.BALANCED: 0,
            ModelTier.HIGHSPEED: 0,
            ModelTier.UNCENSORED: 0,
        }
        self.estimated_cost = 0.0
    
    def record(self, decision: RoutingDecision):
        """Record a routing decision."""
        self.requests[decision.tier] += 1
        
        # Estimate cost per request
        costs = {
            ModelTier.INTELLIGENCE: 0.008,
            ModelTier.BALANCED: 0.002,
            ModelTier.HIGHSPEED: 0.0005,
            ModelTier.UNCENSORED: 0.0005,  # Venice GLM 4.7 Flash is cheap like Flash
        }
        self.estimated_cost += costs.get(decision.tier, 0.002)
    
    def get_summary(self) -> str:
        """Get a summary of routing stats."""
        total = sum(self.requests.values())
        if total == 0:
            return "No requests yet."
        
        lines = [
            "**Model Router Stats**",
            f"• Intelligence (Kimi): {self.requests[ModelTier.INTELLIGENCE]} requests",
            f"• Balanced (MiniMax): {self.requests[ModelTier.BALANCED]} requests",
            f"• Highspeed (Flash): {self.requests[ModelTier.HIGHSPEED]} requests",
            f"• Uncensored (Venice): {self.requests[ModelTier.UNCENSORED]} requests",
            f"• Total: {total} requests",
            f"• Est. Cost: ${self.estimated_cost:.3f}",
        ]
        return "\n".join(lines)


# Global stats instance (optional usage)
_global_stats = RouterStats()


def get_global_stats() -> RouterStats:
    """Get the global stats instance."""
    return _global_stats
