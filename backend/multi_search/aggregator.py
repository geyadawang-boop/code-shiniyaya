"""
multi_search/aggregator.py — MultiSearchAggregator: cross-platform search orchestrator.

Implements:
  - Parallel multi-engine search execution
  - Configurable fallback chain (Bilibili -> Zhihu -> YouTube -> Web)
  - Result dedup and ranking pipeline
  - Search suggestions generation
  - Timeout and error handling per engine
"""

from __future__ import annotations

import asyncio
import time
import hashlib
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import (
    SearchResult, SearchQuery, SearchResponse,
    SearchEngineType, ResultSource, FallbackConfig
)
from .engines import (
    SearchEngine, BilibiliEngine, YoutubeEngine,
    ZhihuEngine, FirecrawlWebEngine, create_engine
)
from .dedup import ResultDeduplicator, ResultRanker


# ============================================================================
# Default Fallback Configuration
# ============================================================================

DEFAULT_FALLBACK_CONFIG = FallbackConfig(
    chains=[
        [SearchEngineType.BILIBILI],
        [SearchEngineType.BILIBILI, SearchEngineType.ZHIHU],
        [
            SearchEngineType.BILIBILI,
            SearchEngineType.ZHIHU,
            SearchEngineType.YOUTUBE,
        ],
        [
            SearchEngineType.BILIBILI,
            SearchEngineType.ZHIHU,
            SearchEngineType.YOUTUBE,
            SearchEngineType.WEB_SEARCH,
        ],
    ],
    min_results_to_stop=5,
    max_fallback_depth=4,
    engine_timeout=10,
)


# ============================================================================
# MultiSearchAggregator
# ============================================================================

class MultiSearchAggregator:
    """
    Orchestrates multi-engine search with fallback, dedup, and ranking.

    Usage:
        aggregator = MultiSearchAggregator(
            bilibili_cookie="...",
            youtube_api_key="...",
            brave_api_key="...",
        )
        response = await aggregator.search(
            SearchQuery(query="机器学习", engines=[...])
        )
    """

    def __init__(
        self,
        bilibili_cookie: str = "",
        youtube_api_key: str = "",
        zhihu_cookie: str = "",
        firecrawl_api_key: str = "",
        brave_api_key: str = "",
        fallback_config: Optional[FallbackConfig] = None,
        dedup_threshold: float = 0.75,
        max_concurrent_engines: int = 5,
        engine_timeout: int = 15,
    ):
        self.bilibili_cookie = bilibili_cookie
        self.youtube_api_key = youtube_api_key
        self.zhihu_cookie = zhihu_cookie
        self.firecrawl_api_key = firecrawl_api_key
        self.brave_api_key = brave_api_key
        self.fallback_config = fallback_config or DEFAULT_FALLBACK_CONFIG
        self.fallback_config.engine_timeout = engine_timeout
        self.dedup_threshold = dedup_threshold
        self.max_concurrent_engines = max_concurrent_engines
        self.engine_timeout = engine_timeout

        # Lazy-initialized engine instances
        self._engine_cache: Dict[SearchEngineType, SearchEngine] = {}

    # ------------------------------------------------------------------
    # Main search method
    # ------------------------------------------------------------------

    async def search(self, query: SearchQuery) -> SearchResponse:
        """Execute multi-engine search with full pipeline.

        Pipeline:
          1. Validate query
          2. Execute chosen engines in parallel
          3. If results insufficient, activate fallback chain
          4. Deduplicate across all engines
          5. Rank and score results
          6. Generate suggestions
          7. Build SearchResponse
        """
        t0 = time.time()
        request_id = query.request_id or str(uuid.uuid4())
        query.request_id = request_id

        all_results: List[SearchResult] = []
        engines_queried: List[str] = []
        engines_failed: List[str] = []
        engine_stats: Dict[str, int] = {}
        fallback_chain: List[str] = []
        fallback_used = False

        # Validate
        if not query.query.strip():
            return SearchResponse(
                request_id=request_id,
                query=query.query,
                results=[],
                query_time_ms=(time.time() - t0) * 1000,
            )

        # Step 1: Execute primary engines in parallel
        primary_results, primary_queried, primary_failed = await self._run_engines(
            query.engines, query
        )
        all_results.extend(primary_results)
        engines_queried.extend(primary_queried)
        engines_failed.extend(primary_failed)

        for eng, count in self._count_by_engine(primary_results).items():
            engine_stats[eng] = count

        # Step 2: Fallback chain if insufficient results
        if query.fallback_enabled and len(all_results) < self.fallback_config.min_results_to_stop:
            fallback_used = True
            remaining_engines = self._get_fallback_chain(
                query.engines, depth=0
            )
            for depth, fallback_engines in enumerate(remaining_engines):
                if depth >= self.fallback_config.max_fallback_depth:
                    break
                if len(all_results) >= self.fallback_config.min_results_to_stop:
                    break

                # Figure out which engines are new (not yet queried)
                new_engines = [
                    e for e in fallback_engines
                    if e.value not in engines_queried
                ]
                if not new_engines:
                    continue

                fb_results, fb_queried, fb_failed = await self._run_engines(
                    new_engines, query
                )
                all_results.extend(fb_results)
                engines_queried.extend(fb_queried)
                engines_failed.extend(fb_failed)
                fallback_chain.extend(fb_queried)

                for eng, count in self._count_by_engine(fb_results).items():
                    engine_stats[eng] = engine_stats.get(eng, 0) + count

        # Step 3: Deduplicate
        dedup_removed = 0
        if query.dedup_enabled and len(all_results) > 1:
            deduplicator = ResultDeduplicator(threshold=query.dedup_threshold)
            all_results, dedup_removed = deduplicator.deduplicate(all_results, query)

        # Step 4: Rank
        ranker = ResultRanker()
        all_results = ranker.rank(all_results)

        # Step 5: Truncate to max_total_results
        all_results = all_results[:query.max_total_results]

        # Step 6: Generate suggestions
        suggestions = self._generate_suggestions(query.query, all_results)

        query_time_ms = (time.time() - t0) * 1000

        return SearchResponse(
            request_id=request_id,
            query=query.query,
            results=all_results,
            total_count=len(all_results),
            engines_queried=engines_queried,
            engines_failed=list(set(engines_failed) - set(engines_queried)),
            engine_stats=engine_stats,
            fallback_used=fallback_used,
            fallback_chain=fallback_chain,
            dedup_removed=dedup_removed,
            query_time_ms=query_time_ms,
            suggestions=suggestions,
        )

    # ------------------------------------------------------------------
    # Parallel engine execution
    # ------------------------------------------------------------------

    async def _run_engines(
        self,
        engine_types: List[SearchEngineType],
        query: SearchQuery,
    ) -> Tuple[List[SearchResult], List[str], List[str]]:
        """Execute multiple engines concurrently with timeout.

        Returns:
            (all_results, engines_queried, engines_failed)
        """
        if not engine_types:
            return [], [], []

        # Limit concurrency
        engine_types = engine_types[:self.max_concurrent_engines]

        tasks = []
        for eng_type in engine_types:
            engine = self._get_engine(eng_type)
            tasks.append(self._run_single_engine(engine, query))

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[SearchResult] = []
        engines_queried: List[str] = []
        engines_failed: List[str] = []

        for eng_type, result in zip(engine_types, results_list):
            if isinstance(result, Exception):
                engines_failed.append(eng_type.value)
            else:
                engines_queried.append(eng_type.value)
                all_results.extend(result)

        return all_results, engines_queried, engines_failed

    async def _run_single_engine(
        self,
        engine: SearchEngine,
        query: SearchQuery,
    ) -> List[SearchResult]:
        """Execute one engine with timeout wrapper."""
        try:
            return await asyncio.wait_for(
                engine.search(query),
                timeout=self.fallback_config.engine_timeout,
            )
        except asyncio.TimeoutError:
            return []
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Fallback chain logic
    # ------------------------------------------------------------------

    def _get_fallback_chain(
        self,
        already_queried: List[SearchEngineType],
        depth: int = 0,
    ) -> List[List[SearchEngineType]]:
        """Get the appropriate fallback chain starting from current depth.

        Returns a list of engine groups, each representing one fallback tier.
        Each tier in the config is a complete set of engines to try at that level.
        We extract the engines NOT yet queried from each tier in order.
        """
        already_set = {e.value for e in already_queried}

        tiers: List[List[SearchEngineType]] = []
        for chain in self.fallback_config.chains:
            new_engines = [e for e in chain if e.value not in already_set]
            if new_engines:
                tiers.append(new_engines)
                # Mark these as "already queried" for subsequent tiers
                already_set.update(e.value for e in new_engines)

        return tiers

    # ------------------------------------------------------------------
    # Engine management
    # ------------------------------------------------------------------

    def _get_engine(self, engine_type: SearchEngineType) -> SearchEngine:
        """Get or create engine instance (cached)."""
        if engine_type in self._engine_cache:
            return self._engine_cache[engine_type]

        kwargs = {}
        if engine_type == SearchEngineType.BILIBILI:
            kwargs = {"cookie": self.bilibili_cookie, "timeout": self.engine_timeout}
        elif engine_type == SearchEngineType.YOUTUBE:
            kwargs = {"api_key": self.youtube_api_key, "timeout": self.engine_timeout}
        elif engine_type == SearchEngineType.ZHIHU:
            kwargs = {"cookie": self.zhihu_cookie, "timeout": self.engine_timeout}
        elif engine_type == SearchEngineType.WEB_SEARCH:
            kwargs = {
                "firecrawl_api_key": self.firecrawl_api_key,
                "brave_api_key": self.brave_api_key,
                "timeout": self.engine_timeout,
            }

        engine = create_engine(engine_type, **kwargs)
        self._engine_cache[engine_type] = engine
        return engine

    # ------------------------------------------------------------------
    # Result counting
    # ------------------------------------------------------------------

    @staticmethod
    def _count_by_engine(
        results: List[SearchResult],
    ) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in results:
            key = r.engine.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Search suggestions
    # ------------------------------------------------------------------

    def _generate_suggestions(
        self,
        query: str,
        results: List[SearchResult],
    ) -> List[str]:
        """Generate related search suggestions from results.

        Extracts common keywords, tags, and topics from top results.
        """
        suggestions: List[str] = []
        seen: Set[str] = set()

        # Extract tags from metadata
        for r in results[:10]:
            tags = r.metadata.get("tag", "")
            if isinstance(tags, str) and tags:
                for tag in tags.split("|")[:3]:
                    tag = tag.strip()
                    if tag and tag not in seen and tag != query:
                        suggestions.append(tag)
                        seen.add(tag)
            if len(suggestions) >= 5:
                break

        # Extract common phrases from titles
        if len(suggestions) < 5:
            import re
            all_words: List[str] = []
            for r in results[:20]:
                words = re.findall(r'[\w一-龥]{2,}', r.title)
                all_words.extend(words)

            word_freq: Dict[str, int] = {}
            for w in all_words:
                if w.lower() != query.lower() and len(w) >= 2:
                    word_freq[w] = word_freq.get(w, 0) + 1

            popular_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            for word, _ in popular_words:
                if word not in seen:
                    suggestions.append(word)
                    seen.add(word)
                if len(suggestions) >= 8:
                    break

        return suggestions[:8]


# ============================================================================
# Convenience: Quick search helper
# ============================================================================

async def multi_search(
    query: str,
    engines: Optional[List[SearchEngineType]] = None,
    bilibili_cookie: str = "",
    youtube_api_key: str = "",
    brave_api_key: str = "",
    **kwargs,
) -> SearchResponse:
    """One-shot multi-engine search convenience function.

    Usage:
        response = await multi_search("机器学习")
        for r in response.results:
            print(f"[{r.source.value}] {r.title}")
    """
    if engines is None:
        engines = [
            SearchEngineType.BILIBILI,
            SearchEngineType.WEB_SEARCH,
        ]

    search_query = SearchQuery(query=query, engines=engines, **kwargs)

    aggregator = MultiSearchAggregator(
        bilibili_cookie=bilibili_cookie,
        youtube_api_key=youtube_api_key,
        brave_api_key=brave_api_key,
        **kwargs,
    )
    return await aggregator.search(search_query)


__all__ = [
    "MultiSearchAggregator",
    "multi_search",
    "DEFAULT_FALLBACK_CONFIG",
]
