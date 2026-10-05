"""Small, deterministic helpers for grounded answers.

The language model still writes the answer, but these helpers make the facts it
receives explicit: whether a request is time-sensitive, how diverse the source
set is, and when the evidence is too thin to claim high confidence.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

CURRENT_WORDS = re.compile(
    r"\b(latest|current|today|now|recent|news|price|cost|availability|"
    r"schedule|status|update|release|weather|stock|score|live)\b", re.I)
LOCAL_WORDS = re.compile(
    r"\b(my|this|the)\s+(file|folder|project|app|computer|screen|window|"
    r"pc|laptop)|open|close|delete|move|rename|run|install|fix|folder|file\b", re.I)

TRUSTED_DOMAINS = {
    "wikipedia.org", "reuters.com", "apnews.com", "bbc.com", "who.int",
    "nasa.gov", "usa.gov", "gov.uk", "microsoft.com", "python.org",
    "docs.python.org", "developer.mozilla.org", "github.com",
}


def request_scope(text: str) -> str:
    """Classify a request for routing guidance, without pretending certainty."""
    text = str(text or "").strip()
    current = bool(CURRENT_WORDS.search(text))
    local = bool(LOCAL_WORDS.search(text))
    if current and local:
        return "mixed"
    if current:
        return "current"
    if local:
        return "local"
    return "unknown"


def domain_for(url: str) -> str:
    host = (urlparse(str(url or "")).netloc or "").lower().split(":", 1)[0]
    return host[4:] if host.startswith("www.") else host


def source_confidence(results: list[dict], *, current: bool = False) -> tuple[str, str]:
    """Return a cautious confidence label and the reason shown to the user."""
    domains = {domain_for(r.get("url", "")) for r in results if r.get("url")}
    domains.discard("")
    trusted = sum(any(d == root or d.endswith("." + root) for root in TRUSTED_DOMAINS)
                  for d in domains)
    if len(domains) >= 4 and (trusted >= 1 or not current):
        return "high", f"{len(domains)} independent sources"
    if len(domains) >= 2:
        return "medium", f"{len(domains)} sources; cross-check important details"
    if len(domains) == 1:
        return "low", "only one source was available"
    return "low", "no linkable source was returned"


def dedupe_results(results: list[dict], limit: int = 10) -> list[dict]:
    """Keep the strongest result for each URL/title pair."""
    seen: set[str] = set()
    out: list[dict] = []
    for result in results or []:
        url = str(result.get("url") or "").strip()
        title = str(result.get("title") or "").strip().lower()
        key = url or title
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(result)
        if len(out) >= limit:
            break
    return out
