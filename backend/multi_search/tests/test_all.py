"""
multi_search/tests/test_all.py — Comprehensive tests for multi-search-engine.

Run:
    cd backend
    python -m pytest multi_search/tests/test_all.py -v

Or individual:
    python -m pytest multi_search/tests/test_all.py::TestModels -v
    python -m pytest multi_search/tests/test_all.py::TestDedup -v
    python -m pytest multi_search/tests/test_all.py::TestRanker -v
    python -m pytest multi_search/tests/test_all.py::TestHistory -v
"""

import os
import sys
import json
import pytest
import asyncio
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from multi_search.models import (
    SearchResult, SearchQuery, SearchResponse, SearchEngineType,
    ResultSource, FallbackConfig, SearchAnalytics,
)
from multi_search.dedup import (
    canonicalize_url, normalize_text, levenshtein_ratio,
    jaccard_similarity, content_similarity,
    ResultDeduplicator, ResultRanker,
)
from multi_search.engines import (
    BilibiliEngine, ZhihuEngine, FirecrawlWebEngine,
    create_engine, ENGINE_REGISTRY,
)
from multi_search.aggregator import MultiSearchAggregator, multi_search
from multi_search.history import SearchHistoryManager


# ============================================================================
# Test Models
# ============================================================================

class TestModels:
    def test_search_result_defaults(self):
        r = SearchResult()
        assert r.title == ""
        assert r.source == ResultSource.WEB_SEARCH
        assert r.relevance_score == 0.0

    def test_search_result_content_hash(self):
        r1 = SearchResult(title="test", url="http://example.com", description="foo")
        r2 = SearchResult(title="test", url="http://example.com", description="foo")
        assert r1.content_hash() == r2.content_hash()

        r3 = SearchResult(title="different", url="http://example.com")
        assert r1.content_hash() != r3.content_hash()

    def test_similarity_fingerprint_removes_punctuation(self):
        r1 = SearchResult(title="Hello, World!")
        r2 = SearchResult(title="hello world")
        assert r1.similarity_fingerprint() == r2.similarity_fingerprint()

    def test_similarity_fingerprint_handles_chinese(self):
        r1 = SearchResult(title="机器学习入门教程！")
        r2 = SearchResult(title="机器学习入门教程")
        assert r1.similarity_fingerprint() == r2.similarity_fingerprint()

    def test_search_query_defaults(self):
        q = SearchQuery(query="test")
        assert len(q.engines) >= 2
        assert q.fallback_enabled is True
        assert q.dedup_enabled is True
        assert q.max_results_per_engine == 20

    def test_fallback_config_default(self):
        fc = FallbackConfig()
        assert len(fc.chains) == 4
        assert fc.min_results_to_stop == 5
        assert fc.max_fallback_depth == 4


# ============================================================================
# Test URL Canonicalization
# ============================================================================

class TestURLCanonicalization:
    def test_strips_tracking_params(self):
        url = "https://example.com/page?q=test&utm_source=fb&utm_campaign=ads"
        canon = canonicalize_url(url)
        assert "utm_source" not in canon
        assert "q=test" in canon

    def test_removes_www_prefix(self):
        assert canonicalize_url("https://www.example.com/") == canonicalize_url("https://example.com/")

    def test_removes_trailing_slash(self):
        url1 = canonicalize_url("https://example.com/page/")
        url2 = canonicalize_url("https://example.com/page")
        assert url1 == url2

    def test_handles_zhihu_url(self):
        url = "https://www.zhihu.com/question/123/answer/456?utm_source=wechat"
        canon = canonicalize_url(url)
        assert "utm_source" not in canon
        assert "zhihu.com" in canon

    def test_handles_bilibili_url(self):
        url = "https://www.bilibili.com/video/BV123/?spm_id_from=333.337"
        canon = canonicalize_url(url)
        assert "spm_id_from" not in canon
        assert "BV123" in canon

    def test_empty_url(self):
        assert canonicalize_url("") == ""


# ============================================================================
# Test Text Similarity
# ============================================================================

class TestSimilarity:
    def test_levenshtein_identical(self):
        assert levenshtein_ratio("hello", "hello") == pytest.approx(1.0)

    def test_levenshtein_completely_different(self):
        assert levenshtein_ratio("abc", "xyz") <= 0.34

    def test_levenshtein_chinese(self):
        sim = levenshtein_ratio("机器学习", "机器学习入门")
        assert sim > 0.5

    def test_levenshtein_length_mismatch(self):
        # Very different lengths should result in 0.0
        assert levenshtein_ratio("a", "this is a very long string") == 0.0

    def test_jaccard_identical(self):
        assert jaccard_similarity("hello", "hello") == pytest.approx(1.0)

    def test_jaccard_chinese(self):
        sim = jaccard_similarity("深度学习与神经网络", "深度学习与卷积网络", n=2)
        assert sim > 0.3

    def test_normalize_text_removes_punctuation(self):
        assert normalize_text("Hello, World!") == "hello world"
        assert normalize_text("你好，世界！") == "你好世界"

    def test_content_similarity_identical(self):
        r1 = SearchResult(title="Same Title", url="http://example.com/page")
        r2 = SearchResult(title="Same Title", url="http://example.com/page")
        assert content_similarity(r1, r2) == pytest.approx(1.0)

    def test_content_similarity_different(self):
        r1 = SearchResult(title="Machine Learning", url="http://ml.com")
        r2 = SearchResult(title="Deep Learning Basics", url="http://dl.com")
        assert content_similarity(r1, r2) < 0.5


# ============================================================================
# Test Deduplicator
# ============================================================================

class TestDeduplicator:
    def test_exact_url_dedup(self):
        dedup = ResultDeduplicator(threshold=0.75)
        results = [
            SearchResult(title="A", url="http://example.com/page", relevance_score=0.5),
            SearchResult(title="A copy", url="http://example.com/page", relevance_score=0.8),
        ]
        unique, removed = dedup.deduplicate(results)
        assert removed == 1
        assert len(unique) == 1
        # Higher-scoring result should be kept
        assert unique[0].relevance_score == 0.8

    def test_canonical_url_dedup(self):
        dedup = ResultDeduplicator(threshold=0.75)
        results = [
            SearchResult(title="A", url="https://www.example.com/page", relevance_score=0.9),
            SearchResult(title="A", url="https://example.com/page", relevance_score=0.3),
        ]
        unique, removed = dedup.deduplicate(results)
        assert removed >= 1

    def test_title_similarity_dedup(self):
        dedup = ResultDeduplicator(threshold=0.7)
        results = [
            SearchResult(title="Machine Learning Basics", url="http://a.com/1", relevance_score=0.5),
            SearchResult(title="Machine Learning Basic Tutorial", url="http://b.com/2", relevance_score=0.6),
        ]
        unique, removed = dedup.deduplicate(results)
        # These should be similar enough to dedup
        assert removed >= 1

    def test_no_dup_when_different(self):
        dedup = ResultDeduplicator(threshold=0.9)
        results = [
            SearchResult(title="Machine Learning", url="http://a.com", relevance_score=0.5),
            SearchResult(title="Cooking Recipes", url="http://b.com", relevance_score=0.6),
        ]
        unique, removed = dedup.deduplicate(results)
        assert removed == 0
        assert len(unique) == 2

    def test_merges_alt_sources_metadata(self):
        dedup = ResultDeduplicator(threshold=0.7)
        results = [
            SearchResult(
                title="Same Content Different Platform",
                url="http://bilibili.com/video/BV123",
                source=ResultSource.BILIBILI,
                description="",
                relevance_score=0.8,
            ),
            SearchResult(
                title="Same Content Different Platform",
                url="http://youtube.com/watch?v=abc",
                source=ResultSource.YOUTUBE,
                description="A long description from YouTube",
                relevance_score=0.5,
            ),
        ]
        unique, removed = dedup.deduplicate(results)
        assert removed >= 1
        # Description should be merged from duplicate
        kept = unique[0]
        if kept.source == ResultSource.BILIBILI:
            assert "alt_sources" in kept.metadata
        # The higher score should be kept
        assert kept.relevance_score >= 0.8

    def test_empty_list(self):
        dedup = ResultDeduplicator()
        unique, removed = dedup.deduplicate([])
        assert unique == []
        assert removed == 0


# ============================================================================
# Test Ranker
# ============================================================================

class TestRanker:
    def test_ranks_by_score(self):
        ranker = ResultRanker()
        results = [
            SearchResult(title="Low", relevance_score=0.1),
            SearchResult(title="High", relevance_score=0.9, view_count=10000, like_count=500),
            SearchResult(title="Mid", relevance_score=0.5),
        ]
        ranked = ranker.rank(results)
        assert ranked[0].title == "High"
        assert ranked[0].final_score > ranked[-1].final_score

    def test_quality_boost_for_popular(self):
        ranker = ResultRanker()
        popular = SearchResult(relevance_score=0.5, view_count=1000000, like_count=50000)
        unpopular = SearchResult(relevance_score=0.5, view_count=10, like_count=1)
        results = [popular, unpopular]
        ranked = ranker.rank(results)
        assert ranked[0].final_score > ranked[0].relevance_score  # boosted

    def test_freshness_decay(self):
        ranker = ResultRanker(recency_days=30)
        recent = SearchResult(
            relevance_score=0.5,
            published_at=(datetime.now() - timedelta(days=1)).isoformat()
        )
        old = SearchResult(
            relevance_score=0.5,
            published_at=(datetime.now() - timedelta(days=400)).isoformat()
        )
        results = [old, recent]
        ranked = ranker.rank(results)
        assert ranked[0].published_at == recent.published_at

    def test_depth_score(self):
        ranker = ResultRanker()
        rich = SearchResult(
            title="Rich content",
            description="A" * 600,
            author="Author Name",
            thumbnail="http://img.png",
            duration=300,
            metadata={"key": "value"},
            relevance_score=0.5,
        )
        poor = SearchResult(
            title="Poor", relevance_score=0.5
        )
        results = [poor, rich]
        ranked = ranker.rank(results)
        assert ranked[0].title == "Rich content"


# ============================================================================
# Test Engine Registry
# ============================================================================

class TestEngineRegistry:
    def test_create_engine_factory(self):
        engine = create_engine(SearchEngineType.BILIBILI)
        assert isinstance(engine, BilibiliEngine)

    def test_create_engine_unknown(self):
        with pytest.raises(ValueError):
            # Use a non-existent engine type
            from multi_search.models import FallbackConfig
            # Actually test the ValueError path properly
            pass

    def test_engine_registry_has_all_types(self):
        assert SearchEngineType.BILIBILI in ENGINE_REGISTRY
        assert SearchEngineType.YOUTUBE in ENGINE_REGISTRY
        assert SearchEngineType.ZHIHU in ENGINE_REGISTRY
        assert SearchEngineType.WEB_SEARCH in ENGINE_REGISTRY

    def test_engine_type_returns_correct_enum(self):
        b = BilibiliEngine()
        assert b.engine_type() == SearchEngineType.BILIBILI

    def test_supports_query_non_empty(self):
        b = BilibiliEngine()
        assert b.supports_query(SearchQuery(query="test")) is True
        assert b.supports_query(SearchQuery(query="")) is False


# ============================================================================
# Test Aggregator (unit)
# ============================================================================

class TestAggregator:
    def test_multisearch_aggregator_creation(self):
        agg = MultiSearchAggregator()
        assert agg.bilibili_cookie == ""
        assert agg.dedup_threshold == 0.75
        assert agg.max_concurrent_engines == 5

    def test_fallback_chain_generation_basic(self):
        agg = MultiSearchAggregator()
        # Should return remaining engines not yet queried
        chain = agg._get_fallback_chain(
            already_queried=[SearchEngineType.BILIBILI],
            depth=0
        )
        # Next tier should include Zhihu, YouTube, Web
        assert len(chain) >= 1

    def test_count_by_engine(self):
        results = [
            SearchResult(engine=SearchEngineType.BILIBILI, relevance_score=0.5),
            SearchResult(engine=SearchEngineType.BILIBILI, relevance_score=0.5),
            SearchResult(engine=SearchEngineType.WEB_SEARCH, relevance_score=0.5),
        ]
        counts = MultiSearchAggregator._count_by_engine(results)
        assert counts["bilibili"] == 2
        assert counts["web_search"] == 1

    def test_engine_cache_reuse(self):
        agg = MultiSearchAggregator()
        e1 = agg._get_engine(SearchEngineType.BILIBILI)
        e2 = agg._get_engine(SearchEngineType.BILIBILI)
        assert e1 is e2  # Same instance


# ============================================================================
# Test History Manager
# ============================================================================

class TestHistory:
    def test_save_and_retrieve(self, tmp_path):
        # Use temp DB
        import sqlite3
        original_db_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data"
        )

        mgr = SearchHistoryManager(user_id="test_user")
        search_id = mgr.save_search(
            query="机器学习",
            engines_used=["bilibili", "web_search"],
            result_count=10,
            search_time_ms=250.0,
        )
        assert search_id

        # Retrieve
        recent = mgr.get_recent_searches(limit=5, user_id="test_user")
        matching = [r for r in recent if r["id"] == search_id]
        assert len(matching) == 1
        assert matching[0]["query"] == "机器学习"

    def test_suggestions(self):
        mgr = SearchHistoryManager(user_id="test_suggestions")
        mgr.save_search("机器学习", ["bilibili"], 5, 100)
        mgr.save_search("机器学习入门", ["bilibili"], 3, 150)
        mgr.save_search("机器视觉", ["web_search"], 8, 200)

        suggestions = mgr.get_suggestions("机器", limit=5)
        assert len(suggestions) >= 1
        assert any("机器" in s for s in suggestions)

    def test_log_click(self):
        mgr = SearchHistoryManager(user_id="test_click")
        sid = mgr.save_search("test query", ["bilibili"], 5, 100)
        mgr.log_click(sid, "http://example.com", "Test Page", "bilibili", 0)

        clicks = mgr.get_clicks_for_search(sid)
        assert len(clicks) == 1
        assert clicks[0]["result_url"] == "http://example.com"

    def test_analytics(self):
        mgr = SearchHistoryManager(user_id="test_analytics")
        mgr.save_search("test1", ["bilibili"], 5, 100)
        mgr.save_search("test1", ["bilibili", "youtube"], 10, 200)
        mgr.save_search("test2", ["web_search"], 3, 150)

        analytics = mgr.get_analytics(days=30)
        assert analytics.total_searches >= 3
        assert analytics.unique_queries >= 2
        assert len(analytics.top_queries) >= 1

    def test_export_json(self):
        mgr = SearchHistoryManager(user_id="test_export")
        mgr.save_search("export test", ["bilibili"], 1, 50)
        exported = mgr.export_history(days=1, fmt="json")
        data = json.loads(exported)
        assert isinstance(data, list)
        assert any(r["query"] == "export test" for r in data)


# ============================================================================
# Test Engine (Mock / Unit)
# ============================================================================

class TestBilibiliEngineFormat:
    def test_parse_duration_mm_ss(self):
        assert BilibiliEngine._parse_duration("03:45") == 225
        assert BilibiliEngine._parse_duration("01:00") == 60

    def test_parse_duration_hh_mm_ss(self):
        assert BilibiliEngine._parse_duration("01:30:00") == 5400

    def test_parse_duration_invalid(self):
        assert BilibiliEngine._parse_duration("") == 0
        assert BilibiliEngine._parse_duration("abc") == 0

    def test_parse_duration_seconds(self):
        assert BilibiliEngine._parse_duration("120") == 120


class TestZhihuEngineFormat:
    def test_parse_html_empty(self):
        engine = ZhihuEngine()
        results = engine._parse_html_results("", 10)
        assert results == []

    def test_parse_html_no_matches(self):
        engine = ZhihuEngine()
        html = "<html><body><p>No results</p></body></html>"
        results = engine._parse_html_results(html, 10)
        assert results == []


# ============================================================================
# Test Integration Router structure
# ============================================================================

class TestIntegrationRouter:
    def test_router_has_routes(self):
        from multi_search.integration import router
        routes = [r.path for r in router.routes]
        assert "/api/multi-search/search" in routes
        assert "/api/multi-search/history" in routes
        assert "/api/multi-search/suggestions" in routes
        assert "/api/multi-search/analytics" in routes
        assert "/api/multi-search/engines" in routes
        assert "/api/multi-search/click" in routes


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
