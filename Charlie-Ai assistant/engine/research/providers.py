"""engine/research/providers.py — Pluggable Search Providers and Provider Manager."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class SearchProvider(ABC):
    """Abstract interface for internet search backends."""

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Returns list of dicts: title, url, snippet, date, author (if any)."""
        pass

    @abstractmethod
    def search_news(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        pass

    def is_available(self) -> bool:
        return True


class DuckDuckGoSearchProvider(SearchProvider):
    """Standard DuckDuckGo provider with news and web fallback."""

    def name(self) -> str:
        return "DuckDuckGo"

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        try:
            from actions.web_search import _ddg_search
            return _ddg_search(query, max_results=max_results)
        except Exception:
            return []

    def search_news(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        try:
            from actions.web_search import _ddg_news
            return _ddg_news(query, max_results=max_results)
        except Exception:
            return self.search(query, max_results=max_results)


class GeminiSearchProvider(SearchProvider):
    """Gemini grounded search provider."""

    def name(self) -> str:
        return "GeminiGrounded"

    def is_available(self) -> bool:
        try:
            from actions.web_search import _gemini_available
            return _gemini_available()
        except Exception:
            return False

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        # Grounded search returns markdown summary or structured citations
        try:
            from actions.web_search import _gemini_search
            res = _gemini_search(query)
            if res:
                return [{
                    "title": f"Gemini Grounded Research: {query}",
                    "url": "https://google.com/search",
                    "snippet": res[:400],
                    "date": "",
                    "source": "Gemini Grounding",
                }]
        except Exception:
            pass
        return []

    def search_news(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return self.search(f"{query} latest news", max_results=max_results)


class MockSearchProvider(SearchProvider):
    """Configurable mock provider for deterministic tests and offline execution."""

    def __init__(self, mock_results: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self._results = mock_results or {}
        self._default_results: List[Dict[str, Any]] = []

    def name(self) -> str:
        return "MockProvider"

    def set_results_for_query(self, query: str, results: List[Dict[str, Any]]) -> None:
        self._results[query.lower().strip()] = results

    def set_default_results(self, results: List[Dict[str, Any]]) -> None:
        self._default_results = results

    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        q = query.lower().strip()
        for k, v in self._results.items():
            if k in q or q in k:
                return v[:max_results]
        return self._default_results[:max_results]

    def search_news(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        return self.search(query, max_results=max_results)


class SearchProviderManager:
    """Manages search providers, failover, quota coordination, and provider routing."""

    def __init__(self, providers: Optional[List[SearchProvider]] = None):
        if providers is not None:
            self._providers = providers
        else:
            self._providers = [
                DuckDuckGoSearchProvider(),
                GeminiSearchProvider(),
            ]

    def add_provider(self, provider: SearchProvider, priority: bool = False) -> None:
        if priority:
            self._providers.insert(0, provider)
        else:
            self._providers.append(provider)

    def execute_search(self, query: str, is_news: bool = False, max_results: int = 5) -> List[Dict[str, Any]]:
        results = []
        for p in self._providers:
            if not p.is_available():
                continue
            try:
                res = p.search_news(query, max_results) if is_news else p.search(query, max_results)
                if res:
                    results.extend(res)
                    if len(results) >= max_results:
                        break
            except Exception:
                continue
        return results[:max_results]
