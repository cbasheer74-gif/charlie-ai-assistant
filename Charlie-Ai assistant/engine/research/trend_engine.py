"""engine/research/trend_engine.py — Trend Discovery, Signal Normalization, and Topic Clustering."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.research.models import SourceRecord, TrendCandidate


class TopicClusterer:
    """Clusters multiple headlines and articles describing the same event into unified trend topics."""

    @staticmethod
    def extract_keywords(text: str) -> Set[str]:
        # Filter stop words and keep nouns / proper names
        stop_words = {"the", "a", "an", "in", "on", "at", "for", "with", "by", "from", "and", "or", "is", "are", "was", "were", "to", "of", "new", "latest"}
        words = re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", text.lower())
        return {w for w in words if w not in stop_words}

    @staticmethod
    def compute_similarity(set_a: Set[str], set_b: Set[str]) -> float:
        if not set_a or not set_b:
            return 0.0
        inter = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return inter / max(1, union)

    def cluster_sources(self, sources: List[SourceRecord]) -> List[List[SourceRecord]]:
        clusters: List[List[SourceRecord]] = []
        cluster_keywords: List[Set[str]] = []

        for src in sources:
            kw = self.extract_keywords(f"{src.title} {src.snippet}")
            matched_idx = -1
            best_sim = 0.0

            for idx, c_kw in enumerate(cluster_keywords):
                sim = self.compute_similarity(kw, c_kw)
                if sim > 0.28 and sim > best_sim:
                    best_sim = sim
                    matched_idx = idx

            if matched_idx >= 0:
                clusters[matched_idx].append(src)
                cluster_keywords[matched_idx].update(kw)
            else:
                clusters.append([src])
                cluster_keywords.append(kw)

        return clusters


class TrendDiscoveryEngine:
    """Discovers trending topics, normalizes momentum signals, and distinguishes single news from trends."""

    def __init__(self):
        self.clusterer = TopicClusterer()

    def discover_trends(
        self,
        sources: List[SourceRecord],
        niche: str = "technology",
        region: str = "GLOBAL",
    ) -> List[TrendCandidate]:
        if not sources:
            return []

        clusters = self.clusterer.cluster_sources(sources)
        candidates: List[TrendCandidate] = []
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        for cluster in clusters:
            primary_src = cluster[0]
            cluster_size = len(cluster)
            unique_domains = {s.domain for s in cluster if s.domain}

            # Distinct signals
            signal_sources = list(unique_domains)
            if any("youtube" in s.url.lower() or "video" in s.snippet.lower() for s in cluster):
                signal_sources.append("YouTube Activity")
            if any("reddit" in s.url.lower() or "community" in s.domain.lower() for s in cluster):
                signal_sources.append("Community Discussion")

            # Check for rumours
            combined_text = " ".join(f"{s.title} {s.snippet}" for s in cluster).lower()
            is_rumour = any(w in combined_text for w in ("rumor", "rumour", "leak", "alleged", "unconfirmed", "supposedly"))

            # Calculate momentum features
            freshness = 1.0 if not any(s.is_stale for s in cluster) else 0.4
            evidence_quality = min(1.0, 0.3 * len(unique_domains) + (0.4 if any(s.is_primary for s in cluster) else 0.0))
            novelty = 0.9 if "2026" in combined_text or "announced" in combined_text or "launch" in combined_text else 0.6
            content_saturation = min(0.9, 0.2 * cluster_size)  # High cluster size = higher saturation

            # Topic title
            topic_title = primary_src.title
            if len(topic_title) > 70:
                topic_title = topic_title[:67] + "..."

            # Generate possible angles
            angles = [
                f"How this changes {niche}",
                "The surprising truth behind the announcement",
                "3 things everyone missed about this update",
            ]

            candidate = TrendCandidate(
                topic=topic_title,
                summary=primary_src.snippet[:200] if primary_src.snippet else primary_src.title,
                first_seen=primary_src.published_at or now_iso,
                latest_activity=now_iso,
                supporting_sources=cluster,
                signal_sources=signal_sources,
                audience_match=0.85 if region.upper() in ("GLOBAL", "INDIA") else 0.7,
                novelty=novelty,
                content_saturation=content_saturation,
                evidence_quality=evidence_quality,
                freshness=freshness,
                content_angle_options=angles,
                cluster_size=cluster_size,
                region=region,
                is_rumour=is_rumour,
            )
            candidates.append(candidate)

        # Sort candidates by combined trend score: evidence + freshness + diversity - saturation
        candidates.sort(
            key=lambda c: (c.evidence_quality * 0.4 + c.freshness * 0.3 + len(c.signal_sources) * 0.2 - c.content_saturation * 0.1),
            reverse=True,
        )

        return candidates
