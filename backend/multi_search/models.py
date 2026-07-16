"""
multi_search/models.py — Data models for Multi-Search-Engine system.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class SearchEngineType(str, Enum):
    BILIBILI = "bilibili"
    YOUTUBE = "youtube"
    ZHIHU = "zhihu"
    WEB_SEARCH = "web_search"


class ResultSource(str, Enum):
    BILIBILI = "bilibili"
    YOUTUBE = "youtube"
    ZHIHU = "zhihu"
    WEB_SEARCH = "web_search"
    FIRE_CRAWL = "firecrawl"


@dataclass
class SearchResult:
    """Unified search result across all engines."""
    id: str = ""                          # unique hash
    title: str = ""
    description: str = ""
    url: str = ""
    source: ResultSource = ResultSource.WEB_SEARCH
    engine: SearchEngineType = SearchEngineType.WEB_SEARCH
    thumbnail: str = ""
    published_at: str = ""                # ISO format
    author: str = ""
    duration: int = 0                     # seconds (for videos)
    view_count: int = 0
    like_count: int = 0
    relevance_score: float = 0.0          # engine-native score [0, 1]
    final_score: float = 0.0              # aggregated score after ranking
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def content_hash(self) -> str:
        """Compute a content-based hash for dedup."""
        import hashlib
        base = f"{self.title}|{self.url}|{self.description[:200]}"
        return hashlib.md5(base.encode()).hexdigest()

    def similarity_fingerprint(self) -> str:
        """Generate a fuzzy fingerprint for title similarity dedup."""
        import re
        cleaned = re.sub(r'[^\w一-鿿]', '', self.title.lower())
        return cleaned


@dataclass
class SearchQuery:
    """Represents a search query with metadata."""
    query: str
    engines: List[SearchEngineType] = field(default_factory=lambda: [
        SearchEngineType.BILIBILI,
        SearchEngineType.WEB_SEARCH
    ])
    max_results_per_engine: int = 20
    max_total_results: int = 100
    page: int = 1
    region: str = "CN"
    language: str = "zh"
    safe_search: bool = True
    sort_by: str = "relevance"            # relevance, date, popularity
    fallback_enabled: bool = True
    dedup_enabled: bool = True
    dedup_threshold: float = 0.75
    timeout: int = 30
    request_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SearchResponse:
    """Aggregated search response."""
    request_id: str = ""
    query: str = ""
    results: List[SearchResult] = field(default_factory=list)
    total_count: int = 0
    engines_queried: List[str] = field(default_factory=list)
    engines_failed: List[str] = field(default_factory=list)
    engine_stats: Dict[str, int] = field(default_factory=dict)
    fallback_used: bool = False
    fallback_chain: List[str] = field(default_factory=list)
    dedup_removed: int = 0
    query_time_ms: float = 0.0
    suggestions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SearchHistoryEntry:
    """A single search history record."""
    id: str = ""
    query: str = ""
    engines_used: List[str] = field(default_factory=list)
    result_count: int = 0
    clicked_results: List[str] = field(default_factory=list)
    search_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    user_id: str = "anonymous"


@dataclass
class SearchAnalytics:
    """Aggregated search analytics."""
    total_searches: int = 0
    unique_queries: int = 0
    top_queries: List[Dict[str, Any]] = field(default_factory=list)
    engine_usage: Dict[str, int] = field(default_factory=dict)
    avg_response_time_ms: float = 0.0
    popular_topics: List[str] = field(default_factory=list)
    daily_searches: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FallbackConfig:
    """Configuration for fallback strategy."""
    chains: List[List[SearchEngineType]] = field(default_factory=lambda: [
        [SearchEngineType.BILIBILI],
        [SearchEngineType.BILIBILI, SearchEngineType.ZHIHU],
        [SearchEngineType.BILIBILI, SearchEngineType.ZHIHU, SearchEngineType.YOUTUBE],
        [SearchEngineType.BILIBILI, SearchEngineType.ZHIHU, SearchEngineType.YOUTUBE, SearchEngineType.WEB_SEARCH],
    ])
    min_results_to_stop: int = 5
    max_fallback_depth: int = 4
    engine_timeout: int = 10
