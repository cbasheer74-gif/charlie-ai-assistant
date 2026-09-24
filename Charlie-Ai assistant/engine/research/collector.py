"""engine/research/collector.py — Source Collection, Page Reading, Quality Evaluation, and Recency Analysis."""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from engine.research.guard import UntrustedContentGuard
from engine.research.models import (
    ResearchIntent,
    SourceRecord,
    SourceType,
)

# Known primary, authoritative, and reputable domains
PRIMARY_DOMAINS = {
    "github.com", "python.org", "docs.python.org", "flutter.dev", "dart.dev",
    "developer.mozilla.org", "w3.org", "apple.com", "microsoft.com",
    "google.com", "openai.com", "anthropic.com", "whitehouse.gov", "who.int",
    "gov.uk", "arxiv.org", "nature.com", "science.org",
}

AUTHORITATIVE_NEWS_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bloomberg.com", "ft.com",
    "thehindu.com", "timesofindia.indiatimes.com", "indianexpress.com",
    "wsj.com", "nytimes.com", "theguardian.com",
}

SPECIALIST_TECH_DOMAINS = {
    "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com",
    "engadget.com", "venturebeat.com", "bleepingcomputer.com", "huggingface.co",
}

COMMUNITY_DOMAINS = {
    "reddit.com", "news.ycombinator.com", "twitter.com", "x.com",
    "quora.com", "medium.com", "dev.to",
}

DATE_PATTERNS = [
    re.compile(r"\b(202[0-9])[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12][0-9]|3[01])\b"),
    re.compile(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2}),?\s+(202[0-9])\b", re.I),
    re.compile(r"\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(202[0-9])\b", re.I),
    re.compile(r"\b(\d+)\s+(hour|minute|day|week|month)s?\s+ago\b", re.I),
]


class SourceEvaluator:
    """Evaluates source credibility and determines source type independently."""

    @staticmethod
    def evaluate(url: str, title: str = "", author: str = "") -> Tuple[SourceType, bool]:
        domain = SourceCollector.extract_domain(url)
        is_primary = False

        if any(domain == pd or domain.endswith("." + pd) for pd in PRIMARY_DOMAINS):
            return SourceType.PRIMARY_SOURCE, True
        if any(domain == ad or domain.endswith("." + ad) for ad in AUTHORITATIVE_NEWS_DOMAINS):
            return SourceType.AUTHORITATIVE_SOURCE, False
        if any(domain == td or domain.endswith("." + td) for td in SPECIALIST_TECH_DOMAINS):
            return SourceType.SPECIALIST_SOURCE, False
        if any(domain == cd or domain.endswith("." + cd) for cd in COMMUNITY_DOMAINS):
            return SourceType.COMMUNITY_SOURCE, False

        # Check for official release keywords in title / domain
        low_title = title.lower()
        if "official documentation" in low_title or "official announcement" in low_title:
            return SourceType.PRIMARY_SOURCE, True

        return SourceType.REPUTABLE_REPORTING if domain else SourceType.UNKNOWN_SOURCE, False


class RecencyEngine:
    """Parses publication and event dates, assesses staleness against research intent."""

    @staticmethod
    def parse_date_string(date_str: str) -> Optional[datetime]:
        if not date_str:
            return None
        text = str(date_str).strip()

        # Handle 'X days/hours ago'
        rel_match = re.search(r"(\d+)\s+(hour|minute|day|week)s?\s+ago", text, re.I)
        if rel_match:
            qty = int(rel_match.group(1))
            unit = rel_match.group(2).lower()
            now = datetime.now(timezone.utc)
            if "minute" in unit:
                return now.replace(minute=max(0, now.minute - qty))
            if "hour" in unit:
                return now.replace(hour=max(0, now.hour - (qty % 24)))
            if "day" in unit:
                return now.replace(day=max(1, now.day - (qty % 28)))
            if "week" in unit:
                return now.replace(day=max(1, now.day - ((qty * 7) % 28)))

        # Handle ISO format
        try:
            cleaned = text.replace("Z", "+00:00")
            if "T" in cleaned:
                return datetime.fromisoformat(cleaned[:19]).replace(tzinfo=timezone.utc)
        except Exception:
            pass

        # Handle YYYY-MM-DD
        m_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m_iso:
            try:
                return datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)), tzinfo=timezone.utc)
            except Exception:
                pass

        return None

    @staticmethod
    def is_stale_for_intent(
        published_at: Optional[str],
        intent: ResearchIntent,
        time_sensitive: bool = False,
        ttl_seconds: int = 86400,
    ) -> bool:
        if not published_at:
            # If no date and strictly time-sensitive breaking event, treat with caution
            return False

        pub_dt = RecencyEngine.parse_date_string(published_at)
        if not pub_dt:
            return False

        now = datetime.now(timezone.utc)
        if pub_dt.date() == now.date():
            return False

        age_seconds = max(0.0, (now - pub_dt).total_seconds())

        # For trend discovery or time-sensitive query, anything older than TTL is stale
        if time_sensitive or intent in (ResearchIntent.TREND_DISCOVERY, ResearchIntent.CURRENT_EVENT):
            return age_seconds > ttl_seconds

        # Evergreen software / documentation stays fresh longer
        if intent == ResearchIntent.SOFTWARE_RESEARCH:
            return age_seconds > (86400 * 365 * 2)  # 2 years

        return age_seconds > (86400 * 30)  # 30 days for general research


class PageReader:
    """Fetches and extracts primary text content from webpage, stripping navigation and scripts."""

    def __init__(self):
        self.guard = UntrustedContentGuard()

    def extract_from_html(self, html: str, url: str = "") -> Dict[str, Any]:
        """Parses HTML content cleanly into primary article text, title, and metadata."""
        if not html:
            return {"title": "", "text": "", "author": None, "date": None, "canonical_url": url}

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # Remove scripts, styles, forms, headers, footers, navs
            for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                element.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""

            # Attempt to find meta tags for date / author
            author = None
            date_str = None
            meta_author = soup.find("meta", attrs={"name": re.compile(r"author", re.I)})
            if meta_author and meta_author.get("content"):
                author = meta_author["content"]

            meta_date = soup.find("meta", attrs={"property": re.compile(r"published_time|pubdate", re.I)}) or \
                        soup.find("meta", attrs={"name": re.compile(r"date|published", re.I)})
            if meta_date and meta_date.get("content"):
                date_str = meta_date["content"]

            # Main content heuristic
            article = soup.find("article") or soup.find("main") or soup.find("div", attrs={"class": re.compile(r"content|article|post", re.I)})
            raw_text = article.get_text(separator="\n") if article else soup.get_text(separator="\n")

            # Clean whitespace
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            cleaned_text = "\n".join(lines[:300])  # Cap length for safety

            # Pass through UntrustedContentGuard
            sanitized_text, suspicious, reason = self.guard.inspect_and_sanitize(cleaned_text, source_label=url or "webpage")

            return {
                "title": title,
                "text": sanitized_text,
                "raw_text": cleaned_text,
                "author": author,
                "date": date_str,
                "canonical_url": url,
                "is_suspicious": suspicious,
                "security_note": reason,
            }
        except Exception:
            # Fallback simple regex extraction
            clean = re.sub(r"<[^>]+>", " ", html)
            clean = " ".join(clean.split())
            sanitized, suspicious, reason = self.guard.inspect_and_sanitize(clean[:4000], source_label=url or "webpage")
            return {
                "title": "",
                "text": sanitized,
                "raw_text": clean[:4000],
                "author": None,
                "date": None,
                "canonical_url": url,
                "is_suspicious": suspicious,
                "security_note": reason,
            }


class SourceCollector:
    """Collects, deduplicates, groups syndicated articles, and builds SourceRecords."""

    def __init__(self):
        self.evaluator = SourceEvaluator()
        self.recency = RecencyEngine()
        self.page_reader = PageReader()

    @staticmethod
    def extract_domain(url: str) -> str:
        try:
            netloc = urlparse(url).netloc.lower().split(":")[0]
            return netloc[4:] if netloc.startswith("www.") else netloc
        except Exception:
            return ""

    @staticmethod
    def compute_content_hash(text: str) -> str:
        norm = re.sub(r"\W+", "", text.lower())
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

    def create_record(
        self,
        raw_result: Dict[str, Any],
        query: str = "",
        intent: ResearchIntent = ResearchIntent.FACT_LOOKUP,
        time_sensitive: bool = False,
        ttl_seconds: int = 86400,
    ) -> SourceRecord:
        url = raw_result.get("url") or ""
        title = raw_result.get("title") or ""
        snippet = raw_result.get("snippet") or raw_result.get("body") or ""
        author = raw_result.get("author") or raw_result.get("source")
        published_at = raw_result.get("date") or raw_result.get("published_at")

        domain = self.extract_domain(url)
        source_type, is_primary = self.evaluator.evaluate(url, title=title)
        is_stale = self.recency.is_stale_for_intent(
            published_at, intent=intent, time_sensitive=time_sensitive, ttl_seconds=ttl_seconds
        )

        content_hash = self.compute_content_hash(f"{title} {snippet}")

        return SourceRecord(
            url=url,
            title=title,
            domain=domain,
            snippet=snippet,
            author=author,
            published_at=published_at,
            source_type=source_type,
            query=query,
            content_hash=content_hash,
            raw_content=snippet,
            is_stale=is_stale,
            is_primary=is_primary,
        )

    def deduplicate_and_group(self, records: List[SourceRecord]) -> List[SourceRecord]:
        """Deduplicates exact URLs and detects syndicated stories (same content hash/quotes)."""
        seen_urls: Set[str] = set()
        seen_hashes: Dict[str, str] = {}  # content_hash -> primary_source_domain
        filtered: List[SourceRecord] = []

        for rec in records:
            norm_url = rec.url.rstrip("/").lower()
            if not norm_url or norm_url in seen_urls:
                continue
            seen_urls.add(norm_url)

            # Syndication check: detect mirror / wire syndication
            if rec.content_hash and rec.content_hash in seen_hashes:
                rec.syndication_group = seen_hashes[rec.content_hash]
            else:
                if rec.content_hash:
                    seen_hashes[rec.content_hash] = rec.domain

            filtered.append(rec)

        return filtered
