"""
Model Router for Jennifer Discord Bots
Ports the bash model-router logic to Python for programmatic agent creation.
Integrates with jennifer/utils/openclaw.py for dynamic model selection.

Usage:
    from utils.model_router import route_message, calculate_complexity_score
    
    # Route a user message
    model = route_message(user_message, default_model="zai/glm-4.7-flash")
    
    # Or with config for custom model mappings
    model = route_message(user_message, config=config)
    
    # Or just get complexity score
    score = calculate_complexity_score(user_message)
"""

import re
import logging
from typing import Tuple, Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

# Configure logging
logger = logging.getLogger(__name__)


class ModelTier(Enum):
    """Model tiers matching the bash router."""
    HIGHSPEED = "highspeed"
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
    fallback_chain: Optional[List[str]] = None


def get_models_from_config(config: Optional[Dict[str, Any]] = None) -> Dict[ModelTier, str]:
    """Get model mappings from config or use defaults from ModelRouterConfig."""
    # Import here to avoid circular dependency
    from core.config import ModelRouterConfig
    
    defaults = ModelRouterConfig()
    
    if config is None:
        return {
            ModelTier.INTELLIGENCE: defaults.intelligence_model,
            ModelTier.HIGHSPEED: defaults.highspeed_model,
            ModelTier.UNCENSORED: defaults.uncensored_model,
        }
    
    router_config = config.get("model_router", {})
    return {
        ModelTier.INTELLIGENCE: router_config.get("intelligence_model", defaults.intelligence_model),
        ModelTier.HIGHSPEED: router_config.get("highspeed_model", defaults.highspeed_model),
        ModelTier.UNCENSORED: router_config.get("uncensored_model", defaults.uncensored_model),
    }


def get_fallback_chains_from_config(config: Optional[Dict[str, Any]] = None) -> Dict[ModelTier, List[str]]:
    """Get fallback chains from config or use defaults from ModelRouterConfig."""
    # Import here to avoid circular dependency
    from core.config import ModelRouterConfig
    
    defaults = ModelRouterConfig()
    
    if config is None:
        return {
            ModelTier.INTELLIGENCE: list(defaults.intelligence_fallbacks),
            ModelTier.HIGHSPEED: list(defaults.highspeed_fallbacks),
            ModelTier.UNCENSORED: list(defaults.uncensored_fallbacks),
        }
    
    router_config = config.get("model_router", {})
    return {
        ModelTier.INTELLIGENCE: router_config.get("intelligence_fallbacks", list(defaults.intelligence_fallbacks)),
        ModelTier.HIGHSPEED: router_config.get("highspeed_fallbacks", list(defaults.highspeed_fallbacks)),
        ModelTier.UNCENSORED: router_config.get("uncensored_fallbacks", list(defaults.uncensored_fallbacks)),
    }


# Backwards compatibility - these are dynamic but cached at module level
# Use get_models_from_config() and get_fallback_chains_from_config() for fresh values
MODELS = get_models_from_config()
FALLBACK_CHAINS = get_fallback_chains_from_config()

# Budget configuration
MONTHLY_BUDGET = 15.0
DAILY_BUDGET = 1.5

# Keyword lists for scoring and routing
ERROR_KEYWORDS = [
    "error", "errors", "exception", "exceptions", "fail", "failed", "failing", "failure",
    "crash", "crashed", "bug", "broken", "debug", "debugging", "troubleshoot", "troubleshooting",
    "not working", "doesn't work", "timeout", "timed out", "hang", "hanging", "stuck",
    "regression", "flaky", "unstable", "stack trace", "traceback", "segfault", "panic", "null pointer",
]

HIGH_COMPLEXITY_KEYWORDS = [
    "architecture", "system design", "design pattern", "distributed", "scalable", "scalability",
    "microservice", "infrastructure", "fault tolerance", "high availability", "event driven",
    "event-driven", "queue", "pub sub", "pub-sub", "multitenant", "multi tenant", "data pipeline",
]

REASONING_KEYWORDS = [
    "analyze", "analysis", "evaluate", "comparison", "compare", "tradeoff", "tradeoffs",
    "implications", "assess", "assessment", "research", "investigate", "study", "optimize",
    "optimization", "performance tune", "performance tuning", "profile", "benchmark", "root cause",
    "root-cause", "pros and cons",
]

STANDARD_COMPLEXITY_KEYWORDS = [
    "refactor", "implement", "implementation", "complex", "optimize", "performance", "concurrent",
    "concurrency", "algorithm", "memory leak", "race condition", "deadlock", "bottleneck",
    "thread safe", "thread-safe", "async", "synchronization", "latency",
]

MEDIUM_COMPLEXITY_KEYWORDS = [
    "build", "create", "develop", "write", "generate", "configure", "setup", "deploy", "install",
    "modify", "update", "patch", "migrate", "integrate", "wire up", "scaffold",
]

VAGUE_KEYWORDS = ["something", "stuff", "thing", "whatever", "etc", "..."]

TASK_TYPE_KEYWORDS = {
    "debugging": [
        "debug", "troubleshoot", "diagnose", "fix", "error", "exception", "crash", "bug", "broken",
        "not working", "doesn't work", "failed", "stack trace", "breakpoint", "traceback", "timeout",
        "timed out", "regression", "flaky",
    ],
    "architecture": [
        "architect", "architecture", "system design", "scalable", "distributed", "microservice",
        "infrastructure", "pattern", "scalability", "fault tolerance", "high availability",
    ],
    "reasoning": [
        "analyze", "evaluate", "compare", "tradeoffs", "implications", "assess", "research",
        "investigate", "study", "optimize", "performance tuning", "benchmark", "root cause",
    ],
    "development": [
        "code", "program", "develop", "implement", "build", "refactor", "script", "function", "api",
        "database", "endpoint", "class", "method", "write code", "create function",
    ],
    "data": [
        "metrics", "data", "analytics", "report", "dashboard", "visualization", "chart", "graph",
        "sql", "aggregation", "kpi", "query plan",
    ],
    "query": [
        "search", "find", "look up", "lookup", "check", "status", "query", "get", "show", "list",
        "what is", "what are", "how to", "help with", "where is",
    ],
    "writing": [
        "write", "draft", "compose", "summarize", "translate", "rewrite", "paraphrase", "format",
        "edit", "proofread", "polish",
    ],
    "administrative": [
        "schedule", "remind", "notify", "ping", "hello", "hi", "hey", "bye", "thanks", "thank you",
        "ok", "okay", "sounds good", "got it",
    ],
}

UNCENSORED_KEYWORD_PATTERNS = [
    # Adult content indicators
    r'\bxxx\b',
    r'\bnsfw\b',
    r'\bexplicit\b',
    r'\buncensored\b',
    r'\badult\b',
    r'\berotic\b',
    r'\bporn(ography|o|hub)?\b',
    r'\bhentai\b',
    r'\bsmut\b',
    r'\blewd\b',
    r'\bfetish(es)?\b',
    r'\bbdsm\b',
    r'\bkink(y)?\b',
    r'\bnud(e|ity)\b',
    r'\bnaked\b',
    r'\bstrip(ping|tease)?\b',
    r'\bnude\b',
    r'\b18\+?\b',
    r'\bx-rated\b',
    r'\bxxx-rated\b',
    r'\bsoftcore\b',
    r'\bhardcore\b',
    r'\byiff\b',
    r'\bclop\b',
    r'\bcub\b',
    r'\bbara\b',
    r'\byaoi\b',
    r'\byuri\b',
    r'\bfurry\b',
    r'\bvore\b',
    r'\binflation\b',
    r'\bmacro\b',
    r'\bmicro\b',
    r'\bgiantess\b',
    r'\bgiant\b',
    r'\bshrink(ing)?\b',
    # Body parts (strong signal)
    r'\bnipples?\b',
    r'\bpussy\b',
    r'\bdick\b',
    r'\bcock\b',
    r'\btits?\b',
    r'\bboobs?\b',
    r'\bbreasts?\b',
    r'\basshole\b',
    r'\bcum\b',
    r'\bsquirt(ing)?\b',
    r'\bpenis\b',
    r'\bvagina\b',
    r'\bclit(oris)?\b',
    r'\banus\b',
    r'\bgenital(s|ia)?\b',
    r'\btesticle?s?\b',
    r'\bball(s|sack)?\b',
    r'\bscrotum\b',
    r'\bshaft\b',
    r'\bshaft\b',
    r'\bshaft\b',
    r'\bblowjob\b',
    r'\bhandjob\b',
    r'\bfootjob\b',
    r'\btitjob\b',
    r'\bboobjob\b',
    r'\bdeepthroat\b',
    r'\bthroating\b',
    r'\bthroated\b',
    r'\bgag(ged|ging)?\b',
    r'\bcreampie\b',
    r'\bbukkake\b',
    r'\bfacial\b',
    r'\bcumshot\b',
    r'\bmoney shot\b',
    r'\bpearl necklace\b',
    # Sexual acts / context
    r'\bfuck(ing|ed|er)?\b',
    r'\bsex(ual|y)?\b',
    r'\bmasturbat(e|ing|ion)\b',
    r'\bjerk(ing)?\s*off\b',
    r'\bwank(ing)?\b',
    r'\bfap(ping)?\b',
    r'\bedging\b',
    r'\boral\b',
    r'\banal\b',
    r'\bintercourse\b',
    r'\bpenetrat(e|ion|ing)\b',
    r'\bthrust(ing)?\b',
    r'\borgasm(s)?\b',
    r'\bclimax\b',
    r'\bcum(ming)?\b',
    r'\bsquirt(ing)?\b',
    r'\bejaculat(e|ion)\b',
    r'\barous(ed|al|ing)\b',
    r'\bhorny\b',
    r'\bwet\b',
    r'\bhard\b',
    r'\bboner\b',
    r'\berection\b',
    r'\blub(ricat|e)?\b',
    r'\bmoan(ing)?\b',
    r'\bgroan(ing)?\b',
    r'\bwhimper(ing)?\b',
    r'\bscream(ing)?\b',
    r'\bwhore\b',
    r'\bslut(ty)?\b',
    r'\bbitch\b',
    r'\bcunt\b',
    r'\btwat\b',
    r'\bescort\b',
    r'\bprostitute\b',
    r'\bhooker\b',
    r'\bcall girl\b',
    r'\bsex worker\b',
    r'\bcam girl\b',
    r'\bonlyfans\b',
    r'\bcamwhore\b',
    r'\bsugar baby\b',
    r'\bsugar daddy\b',
    # Roleplay / ERP context
    r'\broleplay\b',
    r'\berp\b',
    r'\brp\b',
    r'\bdominant\b',
    r'\bsubmissive\b',
    r'\bdominatrix\b',
    r'\bdomme?\b',
    r'\bsub\b',
    r'\bmaster\b',
    r'\bmistress\b',
    r'\bslave\b',
    r'\bpet\b',
    r'\bowner\b',
    r'\bbreeding\b',
    r'\bknott(ing)?\b',
    r'\bknot\b',
    r'\bheat\b',
    r'\brut\b',
    r'\bmating\b',
    r'\bimpregnat(e|ion)\b',
    r'\bbreed(ing)?\b',
    r'\begg laying\b',
    r'\boviposition\b',
    r'\btentacle(s)?\b',
    r'\bmonster(s)?\b',
    r'\bcreature\b',
    r'\balien\b',
    r'\bdemon\b',
    r'\bsuccubus\b',
    r'\bincubus\b',
    r'\bangel\b',
    r'\bwitch\b',
    r'\belf\b',
    r'\borc\b',
    r'\bgoblin\b',
    r'\bdragon\b',
    r'\bwerewolf\b',
    r'\bvampire\b',
    r'\bzombie\b',
    r'\brobot\b',
    r'\bandroid\b',
    r'\bsexbot\b',
    r'\bpleasure bot\b',
    # Kinks / Paraphilias
    r'\bbondage\b',
    r'\bshibari\b',
    r'\brope(play)?\b',
    r'\brestriction\b',
    r'\brestraint(s)?\b',
    r'\bcuffs\b',
    r'\bcollar\b',
    r'\bleash\b',
    r'\bchains?\b',
    r'\bcage\b',
    r'\bcell\b',
    r'\bconfinement\b',
    r'\bspank(ing)?\b',
    r'\bwhip(ping)?\b',
    r'\bflog(ging)?\b',
    r'\bcane\b',
    r'\bpaddle\b',
    r'\bcrop\b',
    r'\bcaning\b',
    r'\bcorporal\b',
    r'\bpunish(ment)?\b',
    r'\btorture\b',
    r'\bcbt\b',
    r'\bball bust(ing)?\b',
    r'\bchastity\b',
    r'\bcage\b',
    r'\bdenial\b',
    r'\btease(ing)?\b',
    r'\bdenial\b',
    r'\bforced\b',
    r'\brough\b',
    r'\bbrutal\b',
    r'\bviolent\b',
    r'\bnoncon\b',
    r'\bdubcon\b',
    r'\bconsent\b',
    r'\bsomnophilia\b',
    r'\bsleep(ing)?\b',
    r'\bunconscious\b',
    r'\bdrugged\b',
    r'\bintoxicated\b',
    r'\bdrunk\b',
    r'\bhigh\b',
    r'\bstoned\b',
    r'\bhypnosis\b',
    r'\bmind control\b',
    r'\bbrainwash(ing)?\b',
    r'\bbimbo(fy|ification)?\b',
    r'\bsiss(y|ification)?\b',
    r'\bcrossdress(ing)?\b',
    r'\btransvestite\b',
    r'\bfeminiz(e|ation)\b',
    r'\bmasculiniz(e|ation)\b',
    r'\btransformation\b',
    r'\btf\b',
    r'\bbody swap\b',
    r'\bpossession\b',
    r'\bparasite\b',
    r'\binfection\b',
    r'\bcorruption\b',
    r'\bheart\b',
    r'\bheart\b',
    r'\bmind break\b',
    r'\baphrodisiac\b',
    r'\bpheromone(s)?\b',
    r'\bheat\b',
    r'\brut\b',
    r'\bestrus\b',
    r'\bpuberty\b',
    r'\bvirgin(ity)?\b',
    r'\bdeflower(ing)?\b',
    r'\bcherry\b',
    r'\bfirst time\b',
    r'\binnocent\b',
    r'\byoung\b',
    r'\bteen(ager)?\b',
    r'\bminor\b',
    r'\bunderage\b',
    r'\bjailbait\b',
    r'\blolicon\b',
    r'\bshotacon\b',
    r'\bcub\b',
    r'\bpederasty\b',
    r'\bpedophil(e|ia)\b',
    r'\bhebephil(e|ia)\b',
    r'\bephebophil(e|ia)\b',
    # Watersports / Scat
    r'\bwatersports?\b',
    r'\bpee(ing)?\b',
    r'\bpiss(ing)?\b',
    r'\burin(e|ation)\b',
    r'\bgolden shower\b',
    r'\bscat\b',
    r'\bshit(ting)?\b',
    r'\bpoop(ing)?\b',
    r'\bdefecat(e|ion)\b',
    r'\bcopro(philia)?\b',
    r'\benema\b',
    r'\bdouche\b',
    # Blood / Gore
    r'\bblood(play)?\b',
    r'\bmenstruat(e|ion)\b',
    r'\bperiod\b',
    r'\bmenstrual\b',
    r'\bgore\b',
    r'\bviolent\b',
    r'\bsnuff\b',
    r'\bdeath\b',
    r'\bmurder\b',
    r'\bkilling\b',
    r'\btorture\b',
    r'\bdismember(ment)?\b',
    r'\bdecapitat(e|ion)\b',
    r'\bamputat(e|ion)\b',
    r'\bcannibal(ism)?\b',
    r'\bvorarephilia\b',
    r'\bvore\b',
    r'\bunbirth\b',
    r'\banal vore\b',
    r'\bc吸收\b',
    # Other paraphilias
    r'\bexhibitionism\b',
    r'\bvoyeur(ism)?\b',
    r'\bpublic\b',
    r'\boutdoor(s)?\b',
    r'\bcar\b',
    r'\bbathroom\b',
    r'\btoilet\b',
    r'\bstall\b',
    r'\bfitting room\b',
    r'\bchanging room\b',
    r'\bpool\b',
    r'\bbeach\b',
    r'\bpark\b',
    r'\bwoods\b',
    r'\bforest\b',
    r'\bnudist\b',
    r'\bnaturist\b',
    r'\bstreak(ing)?\b',
    r'\bflashing\b',
    r'\bupskirt\b',
    r'\bdownblouse\b',
    r'\bglory hole\b',
    r'\bbathhouse\b',
    r'\bsauna\b',
    r'\bgym\b',
    r'\blocker room\b',
    r'\bshower\b',
    r'\b locker\b',
    r'\bsauna\b',
    r'\bsteam room\b',
    r'\bhot spring\b',
    r'\bonsen\b',
    r'\bmassage\b',
    r'\bspa\b',
    r'\bhappy ending\b',
    r'\bfull service\b',
    r'\bbrothel\b',
    r'\bwhorehouse\b',
    r'\bbordello\b',
    r'\bcat house\b',
    r'\bmassage parlor\b',
    r'\bstrip club\b',
    r'\bgentlemen\'?s club\b',
    r'\bbar\b',
    r'\bclub\b',
    r'\bparty\b',
    r'\borg(y|ies)?\b',
    r'\bgangbang\b',
    r'\bgroup sex\b',
    r'\bthreesome\b',
    r'\bfoursome\b',
    r'\bswing(er|ing)?\b',
    r'\bswapping\b',
    r'\bcuck(old)?\b',
    r'\bcuckold(ress)?\b',
    r'\bbull\b',
    r'\bstud\b',
    r'\bstag\b',
    r'\bhotwife\b',
    r'\bwifesharing\b',
    r'\bwifesharing\b',
    r'\bhotwifing\b',
    r'\bclean-up\b',
    r'\bsloppy seconds\b',
    r'\bcream pie\b',
    r'\bsnowball(ing)?\b',
    r'\bfelch(ing)?\b',
    r'\bass to mouth\b',
    r'\batm\b',
    r'\bdouble penetration\b',
    r'\bdp\b',
    r'\btriple penetration\b',
    r'\bdap\b',
    r'\bdvp\b',
    r'\bairtight\b',
    r'\bspitroast\b',
    r'\brotisserie\b',
    r'\btag team\b',
    r'\btrain\b',
    r'\bline\b',
    # Clothing / Lingerie
    r'\blingerie\b',
    r'\bpanties\b',
    r'\bunderwear\b',
    r'\bthong\b',
    r'\bg-string\b',
    r'\bbra\b',
    r'\bstockings?\b',
    r'\bpantyhose\b',
    r'\bnylon(s)?\b',
    r'\bheel(s)?\b',
    r'\bstiletto(s)?\b',
    r'\bpumps\b',
    r'\bboots?\b',
    r'\bleather\b',
    r'\blatex\b',
    r'\brubber\b',
    r'\bpvc\b',
    r'\bvinyl\b',
    r'\bspandex\b',
    r'\blycra\b',
    r'\bbodysuit\b',
    r'\bcatsuit\b',
    r'\bcorset\b',
    r'\bbustier\b',
    r'\bgarter\b',
    r'\bsuspenders?\b',
    r'\bcostume\b',
    r'\bcosplay\b',
    r'\buniform\b',
    r'\bmaid\b',
    r'\bnurse\b',
    r'\bsecretary\b',
    r'\bschoolgirl\b',
    r'\bcheerleader\b',
    r'\bflight attendant\b',
    r'\bstewardess\b',
    r'\bteacher\b',
    r'\bprofessor\b',
    r'\bstudent\b',
    r'\btutor\b',
    r'\bparent\b',
    r'\bsibling\b',
    r'\bsister\b',
    r'\bbrother\b',
    r'\bmother\b',
    r'\bfather\b',
    r'\bdaughter\b',
    r'\bson\b',
    r'\baunt\b',
    r'\buncle\b',
    r'\bcousin\b',
    r'\bniece\b',
    r'\bnephew\b',
    r'\bgrandmother\b',
    r'\bgrandfather\b',
    r'\bgranddaughter\b',
    r'\bgrandson\b',
    r'\bstep-?(mom|dad|sister|brother|daughter|son)\b',
    r'\bin-law\b',
    r'\bincest\b',
    r'\btaboo\b',
    r'\bforbidden\b',
    r'\bsecret\b',
    r'\billicit\b',
    # Body types / Preferences
    r'\b bbw\b',
    r'\b ssbbw\b',
    r'\b chubby\b',
    r'\b fat\b',
    r'\b thick\b',
    r'\b curvy\b',
    r'\b voluptuous\b',
    r'\b plus[- ]?size\b',
    r'\b milf\b',
    r'\b cougar\b',
    r'\b dilf\b',
    r'\b gilf\b',
    r'\b mature\b',
    r'\b granny\b',
    r'\b grandpa\b',
    r'\b daddy\b',
    r'\b mommy\b',
    r'\b mummy\b',
    r'\b papa\b',
    r'\b mom\b',
    r'\b dad\b',
    r'\b baby\b',
    r'\b babe\b',
    r'\b sweetie\b',
    r'\b honey\b',
    r'\b darling\b',
    r'\b love\b',
    r'\b darling\b',
    r'\b pet\b',
    r'\b kitten\b',
    r'\b puppy\b',
    r'\b bunny\b',
    r'\b pony\b',
    r'\b horse\b',
    r'\b dog\b',
    r'\b bitch\b',
    r'\b animal\b',
    r'\bbeast(iality)?\b',
    r'\bzoophil(e|ia)\b',
    r'\bzoo\b',
    r'\bfurry\b',
    r'\b anthropomorphic\b',
    r'\b anthro\b',
    r'\b furry\b',
    r'\b yiff(y)?\b',
    r'\b murrsuit(er)?\b',
    r'\b mur(r)?\b',
    r'\b purr\b',
    r'\b growl\b',
    r'\b snarl\b',
    r'\b hiss\b',
    r'\b meow\b',
    r'\b bark\b',
    r'\b howl\b',
    r'\b neigh\b',
    r'\b whinny\b',
    r'\b moo\b',
    r'\b oink\b',
    r'\b cluck\b',
    r'\b chirp\b',
    r'\b squeak\b',
    r'\b screech\b',
    r'\b roar\b',
    # Toys / Equipment
    r'\b dildo\b',
    r'\b vibrator\b',
    r'\b butt plug\b',
    r'\b plug\b',
    r'\b beads\b',
    r'\b anal beads\b',
    r'\b prostate\b',
    r'\b p[- ]?spot\b',
    r'\b g[- ]?spot\b',
    r'\b clit(oral)?\b',
    r'\b rabbit\b',
    r'\b wand\b',
    r'\b hitachi\b',
    r'\b magic wand\b',
    r'\b sybian\b',
    r'\b fuck machine\b',
    r'\b sex machine\b',
    r'\b sex toy\b',
    r'\b toy(s)?\b',
    r'\b strap[- ]?on\b',
    r'\b harness\b',
    r'\b double[- ]?ended\b',
    r'\b prostate massager\b',
    r'\b masturbator\b',
    r'\b fleshlight\b',
    r'\b pocket pussy\b',
    r'\b onahole\b',
    r'\b tenga\b',
    r'\b doll\b',
    r'\b sex doll\b',
    r'\b blow[- ]?up doll\b',
    r'\breal doll\b',
    r'\b realdoll\b',
    r'\b love doll\b',
    r'\b silicone doll\b',
    r'\b tpe doll\b',
    r'\b mini doll\b',
    r'\b torso\b',
    r'\b masturbator\b',
    r'\bsleeve\b',
    r'\bextension\b',
    r'\bring\b',
    r'\bcock ring\b',
    r'\bpenis ring\b',
    r'\bviagra\b',
    r'\bcialis\b',
    r'\b lube\b',
    r'\b lubricant\b',
    r'\b oil\b',
    r'\b lotion\b',
    r'\b cream\b',
    r'\b gel\b',
    r'\b spray\b',
    r'\b delay\b',
    r'\b stamina\b',
    r'\b condom(s)?\b',
    r'\b prophylactic\b',
    r'\b birth control\b',
    r'\b contraception\b',
    r'\b morning after\b',
    r'\b plan b\b',
    r'\b iud\b',
    r'\b implant\b',
    r'\b shot\b',
    r'\b patch\b',
    r'\b pill\b',
    r'\b sponge\b',
    r'\b cap\b',
    r'\b diaphragm\b',
    # Positions / Actions
    r'\b missionary\b',
    r'\b doggy\b',
    r'\b doggystyle\b',
    r'\b cowgirl\b',
    r'\b reverse cowgirl\b',
    r'\b spoon(ing)?\b',
    r'\b scissor(ing)?\b',
    r'\b69\b',
    r'\b sixty[- ]?nine\b',
    r'\b standing\b',
    r'\b sitting\b',
    r'\b lying\b',
    r'\b bent over\b',
    r'\b on all fours\b',
    r'\b legs up\b',
    r'\b spread(ing)?\b',
    r'\b open\b',
    r'\b wide\b',
    r'\bshallow\b',
    r'\b deep\b',
    r'\b hard\b',
    r'\b fast\b',
    r'\b slow\b',
    r'\b gentle\b',
    r'\brough\b',
    r'\b wild\b',
    r'\b passionate\b',
    r'\bintense\b',
    r'\bfierce\b',
    r'\bsavage\b',
    r'\banimalistic\b',
    r'\bprimal\b',
    r'\bbestial\b',
    r'\bbestiality\b',
    r'\bzoophilia\b',
    # Media / Content types
    r'\bvideo\b',
    r'\bpicture\b',
    r'\bphoto\b',
    r'\bimage\b',
    r'\bgif\b',
    r'\bgif\b',
    r'\bclip\b',
    r'\bscene\b',
    r'\bmovie\b',
    r'\bfilm\b',
    r'\bstream\b',
    r'\blivestream\b',
    r'\bcam(show)?\b',
    r'\bwebcam\b',
    r'\bchat\b',
    r'\bsext(ing)?\b',
    r'\bdirty talk\b',
    r'\bphone sex\b',
    r'\bcyber sex\b',
    r'\bonline sex\b',
    r'\bvirtual sex\b',
    r'\bvr sex\b',
    r'\bteledildonics\b',
    r'\bremote\b',
    r'\bapp\b',
    r'\btoy\b',
    r'\bcontrol\b',
    r'\bpower\b',
    r'\bexchange\b',
    r'\bdynamic\b',
    r'\brelationship\b',
    r'\bpartner(s)?\b',
    r'\bplay\b',
    r'\bscene\b',
    r'\bsession\b',
    r'\bexperience\b',
    r'\bencounter\b',
    r'\bhookup\b',
    r'\b one[- ]?night[- ]?stand\b',
    r'\b casual\b',
    r'\b fling\b',
    r'\b affair\b',
    r'\b cheating\b',
    r'\b infidelity\b',
    r'\b adulter(y|ous)?\b',
    r'\b open relationship\b',
    r'\b poly(amory|amorous)?\b',
    r'\b swinging\b',
    r'\b monogam(y|ous)?\b',
    r'\bnon-monogam(y|ous)?\b',
    r'\brelationship\b',
    r'\b dating\b',
    r'\b tinder\b',
    r'\b grindr\b',
    r'\b bumble\b',
    r'\b hinge\b',
    r'\b okcupid\b',
    r'\b match\b',
    r'\b pof\b',
    r'\b plenty of fish\b',
    r'\b fetlife\b',
    r'\b adult friend finder\b',
    r'\b ashley madison\b',
    r'\b seeking\b',
    r'\b arrangement\b',
    r'\b sugar\b',
    r'\b sugar daddy\b',
    r'\b sugar baby\b',
    r'\b sugar momma\b',
    r'\b sugar mama\b',
    # Story / Fiction
    r'\bstory\b',
    r'\bfiction\b',
    r'\bfanfic(tion)?\b',
    r'\bsmut\b',
    r'\blemon\b',
    r'\blime\b',
    r'\borange\b',
    r'\bgrapefruit\b',
    r'\b pwp\b',
    r'\b plot\b',
    r'\b what\b',
    r'\b porn\b',
    r'\b without\b',
    r'\b plot\b',
    r'\b one[- ]?shot\b',
    r'\b multi[- ]?chapter\b',
    r'\b series\b',
    r'\b chapter\b',
    r'\b part\b',
    r'\b episode\b',
    r'\b season\b',
    r'\b sequel\b',
    r'\b prequel\b',
    r'\b spin[- ]?off\b',
    r'\b au\b',
    r'\b alternate universe\b',
    r'\b ooc\b',
    r'\b out of character\b',
    r'\b ic\b',
    r'\b in character\b',
    r'\b oc\b',
    r'\b original character\b',
    r'\b self[- ]?insert\b',
    r'\b reader insert\b',
    r'\b y/n\b',
    r'\b your name\b',
    r'\b x reader\b',
    r'\b character x character\b',
    r'\b ship\b',
    r'\b pairing\b',
    r'\b couple\b',
    r'\b duo\b',
    r'\b trio\b',
    r'\b harem\b',
    r'\b reverse harem\b',
    r'\b ot3\b',
    r'\b ot4\b',
    r'\b ot[0-9]+\b',
    r'\b poly(ship)?\b',
    r'\b polyamory\b',
    r'\b polyamorous\b',
    r'\b polygamy\b',
    r'\b polygamous\b',
    r'\b bigamy\b',
    r'\b bigamous\b',
    # Additional explicit / context patterns
    r'\bdaddy\b.*\b(kink|fuck|cum|cock|dick|slut|whore|baby|girl|boy)\b',
    r'\b(mommy|mother)\b.*\b(kink|fuck|cum|cock|dick|slut|whore|baby|girl|boy)\b',
    r'\bbaby\b.*\b(girl|boy)\b.*\b(daddy|mommy)\b',
    r'\bmaster\b.*\b(slave|pet|servant|sub|toy)\b',
    r'\bmistress\b.*\b(slave|pet|servant|sub|toy)\b',
    r'\bowner\b.*\b(pet|slave|toy)\b',
    r'\bpimp\b.*\b(whore|slut|ho|hoe)\b',
    r'\b(rape|rapist|raped)\b',
    r'\bassault\b.*\b(sexual|sex)\b',
    r'\bmolest(ation|er)?\b',
    r'\babuse\b.*\b(sexual|sex)\b',
]


def _contains_phrase(text: str, phrases: List[str]) -> bool:
    """Case-insensitive phrase matching with word boundaries."""
    text_lower = text.lower()
    for phrase in phrases:
        if re.search(rf"\b{re.escape(phrase.lower())}\b", text_lower):
            return True
    return False


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
    if _contains_phrase(msg_lower, ERROR_KEYWORDS):
        score += 0.25
    
    # Data patterns (metrics, numbers = analysis needed)
    data_patterns = len(re.findall(r'[0-9]+\.?[0-9]*\s*(%|ms|s|mb|gb|tb|million|billion)', message))
    if data_patterns > 2:
        score += 0.20
    
    # High complexity keywords (architecture, design, research)
    if _contains_phrase(msg_lower, HIGH_COMPLEXITY_KEYWORDS):
        score += 0.35
    
    # Reasoning keywords (analysis, evaluation, tradeoffs)
    if _contains_phrase(msg_lower, REASONING_KEYWORDS):
        score += 0.25
    
    # Standard complexity keywords
    if _contains_phrase(msg_lower, STANDARD_COMPLEXITY_KEYWORDS):
        score += 0.3
    
    # Medium complexity keywords
    if _contains_phrase(msg_lower, MEDIUM_COMPLEXITY_KEYWORDS):
        score += 0.1
    
    # Question complexity (multiple questions)
    q_count = message.count('?')
    if q_count > 2:
        score += 0.10
    
    # Vague terms (vague = needs stronger model)
    if _contains_phrase(msg_lower, VAGUE_KEYWORDS) or "…" in msg_lower:
        score += 0.15
    
    # Cap at 1.0
    return min(score, 1.0)


def detect_task_type(message: str) -> str:
    """
    Detect task type from message for specialized routing.
    Returns: debugging, architecture, reasoning, development, data, query, writing, administrative, general
    """
    msg_lower = message.lower()

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["debugging"]):
        return "debugging"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["architecture"]):
        return "architecture"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["reasoning"]):
        return "reasoning"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["development"]):
        return "development"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["data"]):
        return "data"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["query"]):
        return "query"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["writing"]):
        return "writing"

    if _contains_phrase(msg_lower, TASK_TYPE_KEYWORDS["administrative"]):
        return "administrative"

    return "general"


def detect_uncensored_content(message: str) -> bool:
    """
    Detect NSFW/explicit content keywords for uncensored routing.
    Returns True if message contains explicit content indicators.
    """
    msg_lower = message.lower()

    for pattern in UNCENSORED_KEYWORD_PATTERNS:
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
        return MODELS[ModelTier.HIGHSPEED]
    
    if re.match(r'^@flash\b|^@f\b', trimmed):
        return MODELS[ModelTier.HIGHSPEED]
    
    if re.match(r'^@codex\b|^@c\b', trimmed):
        return "openai-codex/gpt-5.3-codex"
    
    if re.match(r'^@uncensored\b|^@uc\b|^@u\b|^@nsfw\b', trimmed):
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
            return ModelTier.HIGHSPEED
    
    if task_type in ("query", "administrative"):
        return ModelTier.HIGHSPEED
    
    if task_type == "writing":
        if score >= 0.6:
            return ModelTier.INTELLIGENCE
        else:
            return ModelTier.HIGHSPEED
    
    # Default score-based routing
    if score >= 0.5:
        return ModelTier.INTELLIGENCE
    else:
        return ModelTier.HIGHSPEED


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
    
    # 90% budget - downgrade to highspeed
    if budget_percent >= 90 and requested_tier == ModelTier.INTELLIGENCE:
        logger.warning(f"Budget at {budget_percent:.1f}% - downgrading to highspeed")
        return ModelTier.HIGHSPEED
    
    return None


def route_message(
    message: str,
    default_model: str = "zai/glm-4.7-flash",
    current_spend: float = 0.0,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> RoutingDecision:
    """
    Main routing function - determines the best model for a message.
    
    Args:
        message: The user's message
        default_model: Fallback model if routing fails
        current_spend: Current month's API spend (for budget checks)
        user_id: Discord user ID (for logging)
        user_name: Discord username (for logging)
        config: Optional config dict with model_router section for custom model mappings
    
    Returns:
        RoutingDecision with tier, model, score, reason, and token estimate
    """
    # Get model mappings from config or use defaults
    models = get_models_from_config(config)
    fallback_chains = get_fallback_chains_from_config(config)
    
    # 1. Check for prefix routing (explicit user intent)
    prefix_model = check_prefix_routing(message)
    if prefix_model:
        # Determine tier from prefix model
        tier = ModelTier.HIGHSPEED
        for t, m in models.items():
            if m == prefix_model:
                tier = t
                break
        fallback_chain = list(fallback_chains.get(tier, []))
        return RoutingDecision(
            tier=tier,
            model=prefix_model,
            score=0.0,
            reason="prefix_override",
            tokens=estimate_tokens(message),
            fallback_model=fallback_chain[0] if fallback_chain else None,
            fallback_chain=fallback_chain
        )
    
    # 2. Check for uncensored/explicit content
    if detect_uncensored_content(message):
        uncensored_fallbacks = fallback_chains.get(ModelTier.UNCENSORED, [])
        return RoutingDecision(
            tier=ModelTier.UNCENSORED,
            model=models[ModelTier.UNCENSORED],
            score=0.0,
            reason="uncensored_content",
            tokens=estimate_tokens(message),
            fallback_model=uncensored_fallbacks[0] if uncensored_fallbacks else None,
            fallback_chain=list(uncensored_fallbacks)
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
    model = models.get(tier, default_model)
    tokens = estimate_tokens(message)
    
    # Log the decision
    user_info = f" for {user_name}" if user_name else ""
    logger.info(f"Routed{user_info}: {tier.value} -> {model} ({reason}, ~{tokens} tokens)")
    
    return RoutingDecision(
        tier=tier,
        model=model,
        score=score,
        reason=reason,
        tokens=tokens,
        fallback_model=(fallback_chains.get(tier, [None])[0] if fallback_chains.get(tier) else None),
        fallback_chain=list(fallback_chains.get(tier, []))
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
• `@kimi` or `@k` - Use Intelligence tier (best for complex tasks)
• `@mini` or `@m` - Use Highspeed tier (fast)
• `@flash` or `@f` - Use Highspeed tier (fast, simple queries)
• `@codex` or `@c` - Use Intelligence tier (coding)
• `@uncensored` or `@u` - Use Uncensored tier (adult/NSFW content)

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
            ModelTier.HIGHSPEED: 0.0005,
            ModelTier.UNCENSORED: 0.0005,  # Venice GLM 4.7 Flash → Local fallback
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
            f"• Highspeed (Flash): {self.requests[ModelTier.HIGHSPEED]} requests",
            f"• Uncensored (Venice → Local): {self.requests[ModelTier.UNCENSORED]} requests",
            f"• Total: {total} requests",
            f"• Est. Cost: ${self.estimated_cost:.3f}",
        ]
        return "\n".join(lines)


# Global stats instance (optional usage)
_global_stats = RouterStats()


def get_global_stats() -> RouterStats:
    """Get the global stats instance."""
    return _global_stats
