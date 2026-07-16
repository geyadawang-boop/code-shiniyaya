"""
multi_search/engines.py — Abstract SearchEngine base + all platform engines.
Implements: BilibiliEngine, YoutubeEngine, ZhihuEngine, FirecrawlWebEngine

Usage:
    engine = BilibiliEngine()
    results = await engine.search("机器学习")
"""

from __future__ import annotations

import abc
import hashlib
import json
import time
import re
import urllib.parse
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from .models import (
    SearchResult, SearchQuery, ResultSource, SearchEngineType, FallbackConfig
)

# ============================================================================
# Default User-Agent pool
# ============================================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENTS[0],
    "Accept": "text/html,application/json,application/xhtml+xml",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# ============================================================================
# Abstract Base
# ============================================================================

class SearchEngine(abc.ABC):
    """
    Abstract base for all search engines.

    Subclasses implement:
      - engine_type() -> SearchEngineType
      - _search(query: SearchQuery) -> List[SearchResult]
      - _parse_results(raw_data: Any) -> List[SearchResult]

    Public:
      - search(query) -> List[SearchResult]
      - supports_query(query) -> bool
      - is_available() -> bool
    """

    is_abstract = True

    @abc.abstractmethod
    def engine_type(self) -> SearchEngineType:
        ...

    @abc.abstractmethod
    async def _search(self, query: SearchQuery) -> List[SearchResult]:
        ...

    @abc.abstractmethod
    def supports_query(self, query: SearchQuery) -> bool:
        ...

    @abc.abstractmethod
    async def is_available(self) -> bool:
        """Check if this engine is reachable."""

    async def search(self, query: SearchQuery) -> List[SearchResult]:
        """Public search entry point with timing and error handling."""
        t0 = time.time()
        try:
            results = await self._search(query)
            for r in results:
                r.engine = self.engine_type()
                # Assign unique ID if not present
                if not r.id:
                    r.id = hashlib.md5(
                        f"{self.engine_type().value}|{r.url}|{r.title}".encode()
                    ).hexdigest()[:16]
            return results
        except Exception as e:
            # Return empty results on failure; caller handles fallback
            return []

    def _build_result(
        self,
        title: str = "",
        description: str = "",
        url: str = "",
        thumbnail: str = "",
        published_at: str = "",
        author: str = "",
        duration: int = 0,
        view_count: int = 0,
        like_count: int = 0,
        relevance_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SearchResult:
        return SearchResult(
            title=title,
            description=description,
            url=url,
            source=self._source_type(),
            engine=self.engine_type(),
            thumbnail=thumbnail,
            published_at=published_at,
            author=author,
            duration=duration,
            view_count=view_count,
            like_count=like_count,
            relevance_score=relevance_score,
            metadata=metadata or {},
        )

    def _source_type(self) -> ResultSource:
        engine_map = {
            SearchEngineType.BILIBILI: ResultSource.BILIBILI,
            SearchEngineType.YOUTUBE: ResultSource.YOUTUBE,
            SearchEngineType.ZHIHU: ResultSource.ZHIHU,
            SearchEngineType.WEB_SEARCH: ResultSource.WEB_SEARCH,
        }
        return engine_map.get(self.engine_type(), ResultSource.WEB_SEARCH)


# ============================================================================
# Bilibili Engine
# ============================================================================

class BilibiliEngine(SearchEngine):
    """
    Bilibili video search engine using official API.

    API: https://api.bilibili.com/x/web-interface/search/type
    Endpoints:
      - video search: search_type=video
      - user search:   search_type=bili_user
      - article search: search_type=article
    """

    BASE_URL = "https://api.bilibili.com/x/web-interface/search/type"
    VIDEO_BASE = "https://www.bilibili.com/video/"

    def __init__(self, cookie: str = "", timeout: int = 15):
        self.cookie = cookie
        self.timeout = timeout

    def engine_type(self) -> SearchEngineType:
        return SearchEngineType.BILIBILI

    def supports_query(self, query: SearchQuery) -> bool:
        # Bilibili supports Chinese/English queries
        return len(query.query.strip()) >= 1

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self.BASE_URL}?search_type=video&keyword=test&page=1",
                    headers={**DEFAULT_HEADERS, "Referer": "https://www.bilibili.com/"}
                )
                return r.status_code == 200
        except Exception:
            return False

    async def _search(self, query: SearchQuery) -> List[SearchResult]:
        max_results = query.max_results_per_engine
        results: List[SearchResult] = []
        page = query.page

        headers = {**DEFAULT_HEADERS, "Referer": "https://www.bilibili.com/"}
        if self.cookie:
            headers["Cookie"] = self.cookie

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Search videos
            r = await client.get(
                self.BASE_URL,
                params={
                    "search_type": "video",
                    "keyword": query.query,
                    "page": page,
                    "order": query.sort_by
                },
                headers=headers
            )
            data = r.json()
            if data.get("code") != 0:
                return results

            items = data.get("data", {}).get("result", [])
            for item in items[:max_results]:
                bvid = item.get("bvid", "")
                result = self._build_result(
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    url=f"{self.VIDEO_BASE}{bvid}",
                    thumbnail=item.get("pic", ""),
                    author=item.get("author", ""),
                    duration=self._parse_duration(item.get("duration", "")),
                    view_count=item.get("play", 0),
                    like_count=item.get("favorites", 0),
                    relevance_score=item.get("score", 0) / 100.0 if item.get("score") else 0.5,
                    metadata={
                        "bvid": bvid,
                        "aid": item.get("aid", 0),
                        "danmaku": item.get("video_review", 0),
                        "pubdate": item.get("pubdate", 0),
                        "tag": item.get("tag", ""),
                    }
                )
                results.append(result)

            # Also try searching articles for richer context
            try:
                r2 = await client.get(
                    self.BASE_URL,
                    params={
                        "search_type": "article",
                        "keyword": query.query,
                        "page": 1
                    },
                    headers=headers
                )
                d2 = r2.json()
                if d2.get("code") == 0:
                    for item in d2.get("data", {}).get("result", [])[:min(5, max_results)]:
                        result = self._build_result(
                            title=item.get("title", ""),
                            description=item.get("summary", "")[:500],
                            url=f"https://www.bilibili.com/read/cv{item.get('id', '')}",
                            author=item.get("author", ""),
                            relevance_score=0.3,
                            metadata={"type": "article", "id": item.get("id", 0)}
                        )
                        results.append(result)
            except Exception:
                pass

        return results

    @staticmethod
    def _parse_duration(dur_str: str) -> int:
        """Parse Bilibili duration like '03:45' -> 225 seconds."""
        if not dur_str:
            return 0
        parts = dur_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        try:
            return int(dur_str)
        except ValueError:
            return 0


# ============================================================================
# YouTube Engine
# ============================================================================

class YoutubeEngine(SearchEngine):
    """
    YouTube search engine using YouTube Data API v3 or web scraping fallback.

    Required: YOUTUBE_API_KEY env var or config for API mode.
    Fallback: Invidious (no API key required).

    API: https://www.googleapis.com/youtube/v3/search
    Invidious: https://invidious.snopyta.org/api/v1/search
    """

    YT_API_BASE = "https://www.googleapis.com/youtube/v3/search"
    YT_VIDEO_BASE = "https://www.youtube.com/watch"
    INVIDIOUS_INSTANCES = [
        "https://invidious.snopyta.org",
        "https://invidious.fdn.fr",
        "https://yewtu.be",
        "https://vid.puffyan.us",
    ]

    def __init__(self, api_key: str = "", timeout: int = 15):
        self.api_key = api_key
        self.timeout = timeout

    def engine_type(self) -> SearchEngineType:
        return SearchEngineType.YOUTUBE

    def supports_query(self, query: SearchQuery) -> bool:
        return len(query.query.strip()) >= 1

    async def is_available(self) -> bool:
        """Check if at least one method (API or Invidious) is available."""
        if self.api_key:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(
                        self.YT_API_BASE,
                        params={"part": "snippet", "q": "test", "key": self.api_key, "maxResults": 1}
                    )
                    if r.status_code == 200:
                        return True
            except Exception:
                pass
        # Try Invidious
        for instance in self.INVIDIOUS_INSTANCES[:2]:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(f"{instance}/api/v1/search?q=test")
                    if r.status_code == 200:
                        return True
            except Exception:
                continue
        return False

    async def _search(self, query: SearchQuery) -> List[SearchResult]:
        if self.api_key:
            return await self._search_api(query)
        return await self._search_invidious(query)

    async def _search_api(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        max_results = query.max_results_per_engine

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                self.YT_API_BASE,
                params={
                    "part": "snippet",
                    "q": query.query,
                    "type": "video",
                    "maxResults": min(max_results, 50),
                    "key": self.api_key,
                    "relevanceLanguage": query.language,
                    "safeSearch": "moderate" if query.safe_search else "none",
                }
            )
            data = r.json()
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")
                result = self._build_result(
                    title=snippet.get("title", ""),
                    description=snippet.get("description", "")[:500],
                    url=f"{self.YT_VIDEO_BASE}?v={video_id}" if video_id else "",
                    thumbnail=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    author=snippet.get("channelTitle", ""),
                    published_at=snippet.get("publishedAt", ""),
                    relevance_score=0.7,
                    metadata={"videoId": video_id, "channelId": snippet.get("channelId", "")}
                )
                results.append(result)
        return results[:max_results]

    async def _search_invidious(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        max_results = query.max_results_per_engine

        for instance in self.INVIDIOUS_INSTANCES:
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    r = await client.get(
                        f"{instance}/api/v1/search",
                        params={
                            "q": query.query,
                            "type": "video",
                            "sort": "relevance",
                        }
                    )
                    if r.status_code != 200:
                        continue
                    items = r.json()
                    for item in items[:max_results]:
                        result = self._build_result(
                            title=item.get("title", ""),
                            description=item.get("description", ""),
                            url=f"{self.YT_VIDEO_BASE}?v={item.get('videoId', '')}",
                            thumbnail=item.get("videoThumbnails", [{}])[0].get("url", "") if item.get("videoThumbnails") else "",
                            author=item.get("author", ""),
                            duration=item.get("lengthSeconds", 0),
                            view_count=item.get("viewCount", 0),
                            relevance_score=0.6,
                            metadata={"videoId": item.get("videoId", "")}
                        )
                        results.append(result)
                    break
            except Exception:
                continue
        return results[:max_results]


# ============================================================================
# Zhihu Engine
# ============================================================================

class ZhihuEngine(SearchEngine):
    """
    Zhihu (知乎) search engine.

    Uses Firecrawl / web scraping to extract search results from zhihu.com.
    Zhihu has no public API, so we scrape the search page or use Firecrawl.

    Search URL: https://www.zhihu.com/search?type=content&q={keyword}
    """

    ZHIHU_SEARCH_URL = "https://www.zhihu.com/search"
    ZHIHU_BASE = "https://www.zhihu.com"

    def __init__(self, cookie: str = "", use_firecrawl: bool = False, timeout: int = 15):
        self.cookie = cookie
        self.use_firecrawl = use_firecrawl
        self.timeout = timeout

    def engine_type(self) -> SearchEngineType:
        return SearchEngineType.ZHIHU

    def supports_query(self, query: SearchQuery) -> bool:
        return len(query.query.strip()) >= 1

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self.ZHIHU_SEARCH_URL}?type=content&q=test",
                    headers={
                        **DEFAULT_HEADERS,
                        "User-Agent": USER_AGENTS[1],
                        "Referer": "https://www.zhihu.com/"
                    }
                )
                return r.status_code in (200, 302)
        except Exception:
            return False

    async def _search(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        max_results = query.max_results_per_engine

        headers = {
            **DEFAULT_HEADERS,
            "User-Agent": USER_AGENTS[1],
            "Referer": "https://www.zhihu.com/",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "fetch",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie

        # Attempt 1: Zhihu internal search API (undocumented, may break)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            try:
                r = await client.get(
                    "https://www.zhihu.com/api/v4/search_v3",
                    params={
                        "q": query.query,
                        "t": "general",
                        "correction": 1,
                        "offset": 0,
                        "limit": min(max_results, 20),
                    },
                    headers=headers
                )
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("data", [])
                    for item in items:
                        obj = item.get("object", {}) or item.get("target", {})
                        if not obj:
                            continue
                        obj_type = obj.get("type", "") or item.get("type", "")
                        url = ""
                        if obj_type == "answer":
                            qid = obj.get("question", {}).get("id", "")
                            aid = obj.get("id", "")
                            url = f"https://www.zhihu.com/question/{qid}/answer/{aid}"
                        elif obj_type == "article":
                            aid = obj.get("id", "")
                            url = f"https://zhuanlan.zhihu.com/p/{aid}"
                        elif obj_type == "question":
                            qid = obj.get("id", "")
                            url = f"https://www.zhihu.com/question/{qid}"

                        result = self._build_result(
                            title=obj.get("title", "") or obj.get("excerpt", "")[:200],
                            description=obj.get("excerpt", "")[:500],
                            url=url,
                            author=obj.get("author", {}).get("name", ""),
                            view_count=obj.get("voteup_count", 0),
                            like_count=obj.get("comment_count", 0),
                            relevance_score=item.get("highlight", {}).get("title", False) * 0.8 + 0.2,
                            metadata={"type": obj_type, "id": obj.get("id", 0)}
                        )
                        results.append(result)
            except Exception:
                pass

            # Attempt 2: HTML page scrape as fallback
            if not results:
                try:
                    r = await client.get(
                        f"{self.ZHIHU_SEARCH_URL}?type=content&q={urllib.parse.quote(query.query)}",
                        headers={
                            **DEFAULT_HEADERS,
                            "User-Agent": USER_AGENTS[2],
                        }
                    )
                    html = r.text
                    results = self._parse_html_results(html, max_results)
                except Exception:
                    pass

        return results[:max_results]

    def _parse_html_results(self, html: str, max_results: int) -> List[SearchResult]:
        """Best-effort HTML scraping for Zhihu search results.

        Extracts JSON-LD / initial-state from the page.
        """
        results: List[SearchResult] = []
        try:
            # Look for window.__INITIAL_STATE__
            match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\});', html, re.DOTALL)
            if match:
                state = json.loads(match.group(1))
                entities = state.get("entities", {}).get("search", {}).get("list", [])
                for item in entities[:max_results]:
                    results.append(self._build_result(
                        title=item.get("title", ""),
                        description=item.get("excerpt", "")[:500],
                        url=f"https://www.zhihu.com{item.get('url', '')}",
                        relevance_score=0.4,
                    ))
        except Exception:
            # Fallback: regex extraction of titles and URLs
            title_matches = re.findall(
                r'<a[^>]*class="[^"]*title[^"]*"[^>]*href="([^"]+)"[^>]*>(.+?)</a>',
                html, re.DOTALL
            )
            for url_path, title_raw in title_matches[:max_results]:
                clean_title = re.sub(r'<[^>]+>', '', title_raw).strip()
                results.append(self._build_result(
                    title=clean_title,
                    description="",
                    url=f"https://www.zhihu.com{url_path}" if url_path.startswith("/") else url_path,
                    relevance_score=0.3,
                ))
        return results[:max_results]


# ============================================================================
# Firecrawl Web Search Engine (external web search)
# ============================================================================

class FirecrawlWebEngine(SearchEngine):
    """
    General web search via Firecrawl API.

    Integrates with Firecrawl search + scrape for full-page content extraction.
    Falls back to DuckDuckGo HTML scraping if Firecrawl is unavailable.

    API: Firecrawl CLI or API key
    DuckDuckGo fallback: https://html.duckduckgo.com/html/?q={keyword}
    """

    FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v1/search"
    DDG_HTML_URL = "https://html.duckduckgo.com/html/"
    BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(
        self,
        firecrawl_api_key: str = "",
        brave_api_key: str = "",
        timeout: int = 15,
    ):
        self.firecrawl_api_key = firecrawl_api_key
        self.brave_api_key = brave_api_key
        self.timeout = timeout

    def engine_type(self) -> SearchEngineType:
        return SearchEngineType.WEB_SEARCH

    def supports_query(self, query: SearchQuery) -> bool:
        return len(query.query.strip()) >= 1

    async def is_available(self) -> bool:
        if self.brave_api_key:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    r = await client.get(
                        self.BRAVE_API_URL,
                        params={"q": "test", "count": 1},
                        headers={
                            "Accept": "application/json",
                            "X-Subscription-Token": self.brave_api_key,
                        }
                    )
                    return r.status_code == 200
            except Exception:
                pass
        # Fallback: DDG
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.DDG_HTML_URL}?q=test")
                return r.status_code == 200
        except Exception:
            return False

    async def _search(self, query: SearchQuery) -> List[SearchResult]:
        # Try Brave Search API first (best quality, free tier available)
        if self.brave_api_key:
            results = await self._search_brave(query)
            if results:
                return results

        # Try Firecrawl
        if self.firecrawl_api_key:
            results = await self._search_firecrawl(query)
            if results:
                return results

        # Fallback: DuckDuckGo HTML
        return await self._search_duckduckgo(query)

    async def _search_brave(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    self.BRAVE_API_URL,
                    params={
                        "q": query.query,
                        "count": min(query.max_results_per_engine, 20),
                        "search_lang": query.language,
                        "country": "CN" if query.region in ("CN", "zh") else "all",
                    },
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.brave_api_key,
                    }
                )
                if r.status_code != 200:
                    return results
                data = r.json()
                web_results = data.get("web", {}).get("results", [])
                for item in web_results:
                    results.append(self._build_result(
                        title=item.get("title", ""),
                        description=item.get("description", "")[:500],
                        url=item.get("url", ""),
                        published_at=item.get("age", ""),
                        relevance_score=0.7,
                        metadata={"source_engine": "brave"}
                    ))
        except Exception:
            pass
        return results

    async def _search_firecrawl(self, query: SearchQuery) -> List[SearchResult]:
        results: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    self.FIRECRAWL_SEARCH_URL,
                    headers={
                        "Authorization": f"Bearer {self.firecrawl_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": query.query,
                        "limit": query.max_results_per_engine,
                        "scrapeOptions": {"formats": ["markdown"]},
                    }
                )
                if r.status_code != 200:
                    return results
                data = r.json()
                for item in data.get("data", []):
                    results.append(self._build_result(
                        title=item.get("title", ""),
                        description=item.get("description", ""),
                        url=item.get("url", ""),
                        relevance_score=0.6,
                        metadata={"source_engine": "firecrawl"}
                    ))
        except Exception:
            pass
        return results

    async def _search_duckduckgo(self, query: SearchQuery) -> List[SearchResult]:
        """DuckDuckGo HTML scraping as last-resort fallback."""
        results: List[SearchResult] = []
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    self.DDG_HTML_URL,
                    params={"q": query.query},
                    headers=DEFAULT_HEADERS
                )
                if r.status_code != 200:
                    return results
                html = r.text

                # Extract result blocks
                result_blocks = re.findall(
                    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
                    html, re.DOTALL
                )
                snippet_blocks = re.findall(
                    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
                    html, re.DOTALL
                )

                for i, (url, title_raw) in enumerate(result_blocks[:query.max_results_per_engine]):
                    clean_title = re.sub(r'<[^>]+>', '', title_raw).strip()
                    snippet = ""
                    if i < len(snippet_blocks):
                        snippet = re.sub(r'<[^>]+>', '', snippet_blocks[i]).strip()
                    results.append(self._build_result(
                        title=clean_title,
                        description=snippet,
                        url=urllib.parse.unquote(url) if url else "",
                        relevance_score=0.5,
                        metadata={"source_engine": "duckduckgo"}
                    ))
        except Exception:
            pass
        return results


# ============================================================================
# Engine Registry
# ============================================================================

ENGINE_REGISTRY: Dict[SearchEngineType, type] = {
    SearchEngineType.BILIBILI: BilibiliEngine,
    SearchEngineType.YOUTUBE: YoutubeEngine,
    SearchEngineType.ZHIHU: ZhihuEngine,
    SearchEngineType.WEB_SEARCH: FirecrawlWebEngine,
}


def create_engine(
    engine_type: SearchEngineType,
    **kwargs,
) -> SearchEngine:
    """Factory for creating search engine instances."""
    cls = ENGINE_REGISTRY.get(engine_type)
    if not cls:
        raise ValueError(f"Unknown engine type: {engine_type}")
    return cls(**kwargs)


__all__ = [
    "SearchEngine",
    "BilibiliEngine",
    "YoutubeEngine",
    "ZhihuEngine",
    "FirecrawlWebEngine",
    "ENGINE_REGISTRY",
    "create_engine",
    "DEFAULT_HEADERS",
    "USER_AGENTS",
]
