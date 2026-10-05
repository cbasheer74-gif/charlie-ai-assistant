"""Conversational safety filter and fallback engine for CHARLIE.

Provides fast, deterministic safety evaluation for user prompts, enforcing:
1. Strict boundaries against vulgarity, sexually explicit generation, and erotica.
2. Open, objective access to factual sexual health, biology, and wellness.
3. Constructive relationship communication guidance.
4. Consistent, respectful fallback responses in English and Hindi/Hinglish.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SafetyResult:
    """Result of content safety evaluation."""
    is_safe: bool
    category: str
    fallback: str | None = None
    is_educational: bool = False


# Factual sexual health, anatomy, and biological wellness keywords
HEALTH_BIOLOGY_TERMS = {
    "anatomy", "biology", "reproduction", "reproductive", "pregnancy",
    "contraception", "contraceptive", "condom", "condoms", "sti", "std",
    "hiv", "aids", "infection", "prevention", "puberty", "menstruation",
    "period", "periods", "hormone", "hormones", "estrogen", "testosterone",
    "uterus", "ovary", "ovaries", "sperm", "ovum", "egg", "fertilization",
    "testis", "testes", "prostate", "cervix", "vagina", "penis",
    "safe sex", "sexual health", "wellness", "hygiene", "gynecology",
    "urology", "doctor", "symptoms", "transmission", "screening",
}

# Relationship communication & dynamics keywords
RELATIONSHIP_TERMS = {
    "relationship", "communication", "partner", "spouse", "marriage",
    "dating", "breakup", "conflict", "boundaries", "boundary", "consent",
    "trust", "active listening", "emotional intimacy", "respect", "feelings",
    "arguments", "talking with partner", "healthy relationship",
}

# Explicit vulgarity, obscene demands, erotica, and explicit sexual talk patterns
VULGAR_EXPLICIT_PATTERNS = [
    # Explicit requests for erotic conversation / dirty talk
    r"\b(dirty\s+talk|vulgar\s+talk|erotica|cybersex|sex\s+chat|talk\s+dirty)\b",
    r"\b(write\s+(smut|erotica|nsfw|porn))\b",
    r"\b(ashlil|gandi\s+baat|gandi\s+baatein|chudai|chudwana)\b",
    # Hard vulgarities & anatomical slurs (English & Hindi)
    r"\b(fuck|fucking|fucker|motherfucker|cunt|pussy|cock|dick|asshole|bitch)\b",
    r"\b(lund|chut|gaand|bhosad|bhosdike|madarchod|behenchod|chutiya)\b",
    r"\b(blowjob|handjob|cumshot|dildo|gangbang|threesome|porn|porno|xxx)\b",
]

_COMPILED_VULGAR = [re.compile(pat, re.IGNORECASE) for pat in VULGAR_EXPLICIT_PATTERNS]

# Hindi / Hinglish indicator patterns
HINDI_INDICATORS = re.compile(
    r"\b(karo|karein|baat|baatein|batao|kaise|kya|kyun|mujhe|tum|aap|ashlil|gandi|hai|hote|hoti)\b",
    re.IGNORECASE,
)

FALLBACK_EN = (
    "I keep our conversations respectful and safe. I don't engage in vulgar "
    "or sexually explicit talk, but I can provide factual information about "
    "sexual health, biology, wellness, or relationship communication."
)

FALLBACK_HI = (
    "Main ashlil ya explicit baatein nahi kar sakta, lekin sexual health, "
    "biology, wellness ya relationship communication par factual jankari de sakta hoon."
)


def is_hindi_or_hinglish(text: str) -> bool:
    """Detect if the input text appears to be in Hindi or Hinglish."""
    return bool(HINDI_INDICATORS.search(text))


def get_safety_fallback(text: str) -> str:
    """Return an appropriate fallback response based on detected language."""
    return FALLBACK_HI if is_hindi_or_hinglish(text) else FALLBACK_EN


def contains_vulgar_or_explicit(text: str) -> bool:
    """Check if text contains explicit vulgarity or explicit sexual requests."""
    return any(pattern.search(text) for pattern in _COMPILED_VULGAR)


def is_educational_or_health_topic(text: str) -> bool:
    """Check if text addresses factual biology, health, or relationship topics."""
    lower = text.lower()
    has_health = any(term in lower for term in HEALTH_BIOLOGY_TERMS)
    has_rel = any(term in lower for term in RELATIONSHIP_TERMS)
    return has_health or has_rel


def evaluate_safety(text: str) -> SafetyResult:
    """Evaluate text safety and determine routing.

    Returns:
        SafetyResult indicating if the request is safe to process,
        whether it qualifies as educational/wellness, and the fallback response
        if blocked.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return SafetyResult(is_safe=True, category="EMPTY")

    has_vulgar = contains_vulgar_or_explicit(cleaned)
    has_educational = is_educational_or_health_topic(cleaned)

    # If it contains vulgarities or demands for explicit dirty talk
    if has_vulgar:
        # If user is asking a purely educational question that happens to mention an anatomical
        # term (e.g. "is bleeding after intercourse normal?"), we check if vulgar obscenities were used
        # If true vulgar/slurs or explicit roleplay requests exist, block with fallback
        return SafetyResult(
            is_safe=False,
            category="VULGAR_OR_EXPLICIT",
            fallback=get_safety_fallback(cleaned),
            is_educational=has_educational,
        )

    if has_educational:
        return SafetyResult(
            is_safe=True,
            category="HEALTH_OR_RELATIONSHIP",
            is_educational=True,
        )

    return SafetyResult(is_safe=True, category="GENERAL")
