"""
multi_search/__init__.py — Multi-Search-Engine package entry point.

Provides unified import surface for the entire multi-search-engine system.

Usage:
    from multi_search import (
        MultiSearchAggregator, multi_search,
        BilibiliEngine, YoutubeEngine, ZhihuEngine, FirecrawlWebEngine,
        SearchHistoryManager, ResultDeduplicator, ResultRanker,
        SearchResult, SearchQuery, SearchResponse, SearchEngineType,
    )

    aggregator = MultiSearchAggregator(bilibili_cookie="...")
    response = await aggregator.search(SearchQuery(query="机器学习"))
"""

from .models import (
    SearchResult,
    SearchQuery,
    SearchResponse,
    SearchHistoryEntry,
    SearchAnalytics,
    SearchEngineType,
    ResultSource,
    FallbackConfig,
)

from .engines import (
    SearchEngine,
    BilibiliEngine,
    YoutubeEngine,
    ZhihuEngine,
    FirecrawlWebEngine,
    ENGINE_REGISTRY,
    create_engine,
)

from .dedup import (
    ResultDeduplicator,
    ResultRanker,
    canonicalize_url,
    content_similarity,
    levenshtein_ratio,
    jaccard_similarity,
)

from .aggregator import (
    MultiSearchAggregator,
    multi_search,
    DEFAULT_FALLBACK_CONFIG,
)

from .history import (
    SearchHistoryManager,
    save_analytics_snapshot,
    load_analytics_snapshot,
)

__all__ = [
    # Models
    "SearchResult",
    "SearchQuery",
    "SearchResponse",
    "SearchHistoryEntry",
    "SearchAnalytics",
    "SearchEngineType",
    "ResultSource",
    "FallbackConfig",
    # Engines
    "SearchEngine",
    "BilibiliEngine",
    "YoutubeEngine",
    "ZhihuEngine",
    "FirecrawlWebEngine",
    "ENGINE_REGISTRY",
    "create_engine",
    # Dedup & Ranking
    "ResultDeduplicator",
    "ResultRanker",
    "canonicalize_url",
    "content_similarity",
    "levenshtein_ratio",
    "jaccard_similarity",
    # Aggregator
    "MultiSearchAggregator",
    "multi_search",
    "DEFAULT_FALLBACK_CONFIG",
    # History
    "SearchHistoryManager",
    "save_analytics_snapshot",
    "load_analytics_snapshot",
]
