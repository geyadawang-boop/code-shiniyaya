"""
multi_search/integration.py — FastAPI router integration for multi-search-engine.

Drop-in API routes to add multi-engine search to BiliSum backend.
Import `router` into main.py and `app.include_router(router)`.

Routes:
  GET  /api/multi-search/search          — Multi-engine search
  POST /api/multi-search/search          — Multi-engine search (POST body)
  GET  /api/multi-search/history         — Search history
  GET  /api/multi-search/suggestions     — Auto-complete
  GET  /api/multi-search/analytics       — Search analytics
  GET  /api/multi-search/engines         — List available engines + status
  POST /api/multi-search/click           — Log result click
"""

from __future__ import annotations

import os
import json
from typing import List, Optional

from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import JSONResponse

from .models import (
    SearchQuery, SearchResponse, SearchEngineType, ResultSource
)
from .aggregator import MultiSearchAggregator, multi_search
from .history import SearchHistoryManager

# ============================================================================
# Router
# ============================================================================

router = APIRouter(prefix="/api/multi-search", tags=["multi-search"])

# ------------------------------------------------------------------
# Engine configuration (from env or defaults)
# ------------------------------------------------------------------

def _get_aggregator() -> MultiSearchAggregator:
    """Build aggregator from environment variables or defaults."""
    return MultiSearchAggregator(
        bilibili_cookie=os.getenv("BILIBILI_COOKIE", ""),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
        zhihu_cookie=os.getenv("ZHIHU_COOKIE", ""),
        brave_api_key=os.getenv("BRAVE_API_KEY", ""),
        firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", ""),
        engine_timeout=int(os.getenv("SEARCH_ENGINE_TIMEOUT", "15")),
        max_concurrent_engines=int(os.getenv("SEARCH_MAX_CONCURRENT", "5")),
    )


_history_manager = SearchHistoryManager()


# ============================================================================
# Routes
# ============================================================================

@router.get("/search")
async def search_get(
    q: str = Query(..., description="Search query"),
    engines: str = Query("bilibili,web_search", description="Comma-separated engine list"),
    page: int = Query(1, ge=1),
    max_per_engine: int = Query(20, ge=1, le=50),
    max_total: int = Query(100, ge=1, le=500),
    sort_by: str = Query("relevance"),
    fallback: bool = Query(True),
    dedup: bool = Query(True),
    dedup_threshold: float = Query(0.75, ge=0.5, le=1.0),
    region: str = Query("CN"),
):
    """
    Multi-engine search across Bilibili, YouTube, Zhihu, and Web.

    Query params:
      - q: Search keyword (required)
      - engines: Comma-separated: bilibili, youtube, zhihu, web_search
      - page: Page number
      - max_per_engine: Max results per engine
      - max_total: Max total results after dedup
      - sort_by: relevance, date, popularity
      - fallback: Enable fallback chain
      - dedup: Enable cross-platform dedup
      - dedup_threshold: Similarity threshold for dedup [0.5, 1.0]
    """
    # Parse engines
    engine_list = _parse_engines(engines)

    # Build query
    search_query = SearchQuery(
        query=q.strip(),
        engines=engine_list,
        page=page,
        max_results_per_engine=max_per_engine,
        max_total_results=max_total,
        sort_by=sort_by,
        fallback_enabled=fallback,
        dedup_enabled=dedup,
        dedup_threshold=dedup_threshold,
        region=region,
    )

    aggregator = _get_aggregator()
    response = await aggregator.search(search_query)

    # Save to history
    _history_manager.save_search(
        query=q.strip(),
        engines_used=response.engines_queried,
        result_count=response.total_count,
        search_time_ms=response.query_time_ms,
    )

    return JSONResponse(_response_to_dict(response))


@router.post("/search")
async def search_post(request: Request):
    """
    Multi-engine search via POST body (JSON).

    Body:
    {
      "q": "机器学习",
      "engines": ["bilibili", "youtube"],
      "page": 1,
      "max_per_engine": 20,
      "max_total": 100,
      "sort_by": "relevance",
      "fallback": true,
      "dedup": true,
      "dedup_threshold": 0.75
    }
    """
    body = await request.json()
    q = (body.get("q") or body.get("query") or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Query 'q' is required")

    engines_raw = body.get("engines", ["bilibili", "web_search"])
    if isinstance(engines_raw, str):
        engine_list = _parse_engines(engines_raw)
    else:
        engine_list = _parse_engine_list(engines_raw)

    search_query = SearchQuery(
        query=q,
        engines=engine_list,
        page=body.get("page", 1),
        max_results_per_engine=body.get("max_per_engine", 20),
        max_total_results=body.get("max_total", 100),
        sort_by=body.get("sort_by", "relevance"),
        fallback_enabled=body.get("fallback", True),
        dedup_enabled=body.get("dedup", True),
        dedup_threshold=body.get("dedup_threshold", 0.75),
        region=body.get("region", "CN"),
    )

    aggregator = _get_aggregator()
    response = await aggregator.search(search_query)

    _history_manager.save_search(
        query=q,
        engines_used=response.engines_queried,
        result_count=response.total_count,
        search_time_ms=response.query_time_ms,
    )

    return JSONResponse(_response_to_dict(response))


@router.get("/history")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str = Query(""),
):
    """Get search history."""
    if search:
        entries = _history_manager.get_history_by_query(search, limit)
    else:
        entries = _history_manager.get_recent_searches(limit, offset)

    return JSONResponse({
        "success": True,
        "data": {
            "count": len(entries),
            "entries": [
                {
                    "id": e["id"],
                    "query": e["query"],
                    "engines_used": json.loads(e.get("engines_used", "[]")),
                    "result_count": e["result_count"],
                    "search_time_ms": e["search_time_ms"],
                    "timestamp": e["timestamp"],
                }
                for e in entries
            ]
        }
    })


@router.get("/suggestions")
async def get_suggestions(
    q: str = Query("", description="Query prefix for auto-complete"),
    limit: int = Query(8, ge=1, le=20),
):
    """Get auto-complete suggestions based on query prefix."""
    suggestions = _history_manager.get_suggestions(q, limit)
    return JSONResponse({
        "success": True,
        "data": {
            "prefix": q,
            "suggestions": suggestions,
        }
    })


@router.get("/analytics")
async def get_analytics(
    days: int = Query(30, ge=1, le=365),
):
    """Get search analytics for specified time window."""
    analytics = _history_manager.get_analytics(days)
    return JSONResponse({
        "success": True,
        "data": {
            "total_searches": analytics.total_searches,
            "unique_queries": analytics.unique_queries,
            "top_queries": analytics.top_queries,
            "engine_usage": analytics.engine_usage,
            "avg_response_time_ms": analytics.avg_response_time_ms,
            "popular_topics": analytics.popular_topics,
            "daily_searches": analytics.daily_searches,
            "period_days": days,
        }
    })


@router.get("/engines")
async def list_engines():
    """List available engines and check their availability."""
    aggregator = _get_aggregator()
    import asyncio

    engine_statuses = {}
    for eng_type in SearchEngineType:
        engine = aggregator._get_engine(eng_type)
        try:
            available = await asyncio.wait_for(engine.is_available(), timeout=5)
        except Exception:
            available = False
        engine_statuses[eng_type.value] = {
            "type": eng_type.value,
            "available": available,
            "description": _engine_description(eng_type),
        }

    return JSONResponse({
        "success": True,
        "data": {
            "engines": engine_statuses,
            "default_fallback_chain": [
                [e.value for e in chain]
                for chain in aggregator.fallback_config.chains
            ],
        }
    })


@router.post("/click")
async def log_click(request: Request):
    """Log a user click on a search result."""
    body = await request.json()
    search_id = body.get("search_id", "")
    result_url = body.get("url", "")
    result_title = body.get("title", "")
    result_source = body.get("source", "")
    position = body.get("position", 0)

    if not search_id or not result_url:
        raise HTTPException(status_code=400, detail="search_id and url are required")

    _history_manager.log_click(
        search_id=search_id,
        result_url=result_url,
        result_title=result_title,
        result_source=result_source,
        position=position,
    )

    return JSONResponse({"success": True})


# ============================================================================
# Helpers
# ============================================================================

def _parse_engines(engines_str: str) -> List[SearchEngineType]:
    """Parse comma-separated engine names."""
    engine_map = {
        "bilibili": SearchEngineType.BILIBILI,
        "youtube": SearchEngineType.YOUTUBE,
        "zhihu": SearchEngineType.ZHIHU,
        "web_search": SearchEngineType.WEB_SEARCH,
        "web": SearchEngineType.WEB_SEARCH,
    }
    result = []
    for name in engines_str.split(","):
        name = name.strip().lower()
        if name in engine_map:
            result.append(engine_map[name])
    return result if result else [SearchEngineType.BILIBILI, SearchEngineType.WEB_SEARCH]


def _parse_engine_list(engines_raw: list) -> List[SearchEngineType]:
    """Parse list of engine name strings."""
    engine_map = {
        "bilibili": SearchEngineType.BILIBILI,
        "youtube": SearchEngineType.YOUTUBE,
        "zhihu": SearchEngineType.ZHIHU,
        "web_search": SearchEngineType.WEB_SEARCH,
        "web": SearchEngineType.WEB_SEARCH,
    }
    result = []
    for name in engines_raw:
        if isinstance(name, str):
            name = name.strip().lower()
            if name in engine_map:
                result.append(engine_map[name])
    return result if result else [SearchEngineType.BILIBILI, SearchEngineType.WEB_SEARCH]


def _engine_description(eng_type: SearchEngineType) -> str:
    descriptions = {
        SearchEngineType.BILIBILI: "B站视频、文章搜索 (CN)",
        SearchEngineType.YOUTUBE: "YouTube视频搜索 (Global, requires API key)",
        SearchEngineType.ZHIHU: "知乎问答、文章搜索 (CN)",
        SearchEngineType.WEB_SEARCH: "通用网页搜索 via Brave/DuckDuckGo (Global)",
    }
    return descriptions.get(eng_type, "Unknown")


def _response_to_dict(response: SearchResponse) -> dict:
    """Convert SearchResponse to JSON-safe dict."""
    return {
        "success": True,
        "data": {
            "request_id": response.request_id,
            "query": response.query,
            "total_count": response.total_count,
            "results": [
                {
                    "id": r.id,
                    "title": r.title,
                    "description": r.description,
                    "url": r.url,
                    "source": r.source.value,
                    "engine": r.engine.value,
                    "thumbnail": r.thumbnail,
                    "published_at": r.published_at,
                    "author": r.author,
                    "duration": r.duration,
                    "view_count": r.view_count,
                    "like_count": r.like_count,
                    "relevance_score": r.relevance_score,
                    "final_score": round(r.final_score, 4),
                }
                for r in response.results
            ],
            "engines_queried": response.engines_queried,
            "engines_failed": response.engines_failed,
            "engine_stats": response.engine_stats,
            "fallback_used": response.fallback_used,
            "fallback_chain": response.fallback_chain,
            "dedup_removed": response.dedup_removed,
            "query_time_ms": round(response.query_time_ms, 2),
            "suggestions": response.suggestions,
            "timestamp": response.timestamp,
        }
    }


__all__ = ["router", "SearchHistoryManager", "MultiSearchAggregator"]
