"""
B站 API 客户端 - 参考 server/src/bilibili.js 实现 Python 版
支持：视频信息、多通道字幕获取、评论、弹幕、搜索、热门
"""

import os
import re
import json
import urllib.parse
import httpx
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from models import VideoInfo, VideoStat, SubtitleData, SubtitleEntry, CommentEntry, CommentReply

_logger = logging.getLogger(__name__)

# Per-call timeout for non-subtitle B站 API calls — shorter than the
# client-level default (15 s) but generous enough for slow responses.
_API_TIMEOUT = httpx.Timeout(10.0, connect=3.0, read=15.0)

# Base request headers -- NEVER mutated after module init.
# Cookie is stored separately to avoid unsynchronized mutation of a
# shared dict while in-flight coroutines are reading from it.
_BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}
_cookie_str = ""


def set_cookie(cookie_str: str):
    """Store the B站 cookie globally (module-level replace, no dict mutation)."""
    global _cookie_str
    if cookie_str:
        _cookie_str = cookie_str


def _get_headers() -> dict:
    """Return a fresh copy of base headers with the current cookie.

    Each call produces an independent dict so that concurrent
    coroutines never observe a half-mutated header dict.
    """
    h = dict(_BASE_HEADERS)
    if _cookie_str:
        h["Cookie"] = _cookie_str
    return h


# --- Shared httpx.AsyncClient singleton (v7.1: eliminate per-call client creation) ---
_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def _get_client() -> httpx.AsyncClient:
    """Return a shared, lazily-created httpx.AsyncClient with connection pooling.

    All async functions reuse this single client instead of creating a new one
    per call, saving ~50ms connection-setup per request and reducing socket churn.
    The client lives for the process lifetime; Python GC cleans it up on exit.
    """
    global _client
    if _client is not None and not _client.is_closed:
        return _client
    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=3.0, read=20.0, write=15.0),
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            )
        return _client


async def _retry_get(client, url, *, params=None, max_retries=3, timeout=10.0):
    """GET with retry on transient errors (timeout, network, 429, 5xx) with exponential backoff.

    On httpx.TimeoutException, httpx.NetworkError, or status 429/5xx → retry with backoff.
    On status 4xx (except 429) → return immediately (no retry on client errors).
    Returns raw response object on success; raises last error on exhaustion.
    Callers must call .json() on the returned response.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            r = await client.get(url, params=params, headers=_get_headers(), timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (2 ** attempt))
                    continue
            if 400 <= r.status_code < 500 and r.status_code != 429:
                return r  # client error — no retry
            return r  # success (2xx, 3xx) or exhausted retries on 429/5xx
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (2 ** attempt))
                continue
            raise
    if last_error is not None:
        raise last_error
    return r  # fallback: exhausted retries on 429/5xx


async def _signed_get(url, params=None, *, with_wbi=True, timeout=10.0):
    """B站 WBI-signed GET with automatic fallback to unsigned on failure.

    _retry_get always uses _get_headers() internally (includes Cookie).
    """
    client = await _get_client()
    if with_wbi:
        try:
            from wbi import sign_params
            signed = await sign_params(params or {})
            if signed:
                query = urllib.parse.urlencode(signed)
                signed_url = f"{url}?{query}" if "?" not in url else f"{url}&{query}"
                r = await _retry_get(client, signed_url, timeout=timeout)
                return r.json()
        except Exception:
            _logger.debug("_signed_get: WBI sign failed, falling back to unsigned", exc_info=True)
    r = await _retry_get(client, url, params=params, timeout=timeout)
    return r.json()


async def get_video_info(bvid: str, cid: Optional[int] = None) -> VideoInfo:
    """获取B站视频基本信息 (v7.2: shared client, pubdate_dt, fetched_at)"""
    client = await _get_client()
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    if cid is not None:
        url += f"&cid={cid}"
    r = await _retry_get(client, url, timeout=_API_TIMEOUT)
    data = r.json()
    if data.get("code") != 0:
        raise ValueError(data.get("message", "Video not found"))

    d = data["data"]
    stat_raw = d.get("stat", {})
    stat = VideoStat(
        view=int(stat_raw.get("view", 0) or 0),
        danmaku=int(stat_raw.get("danmaku", 0) or 0),
        reply=int(stat_raw.get("reply", 0) or 0),
        favorite=int(stat_raw.get("favorite", 0) or 0),
        coin=int(stat_raw.get("coin", 0) or 0),
        share=int(stat_raw.get("share", 0) or 0),
        like=int(stat_raw.get("like", 0) or 0),
        now_rank=int(stat_raw.get("now_rank", 0) or 0),
    )

    # Parse pubdate as datetime and generate fetched_at
    pubdate_ts = int(d.get("pubdate", 0) or 0)
    pubdate_dt = datetime.fromtimestamp(pubdate_ts, tz=timezone.utc) if pubdate_ts else None
    fetched_at = datetime.now(tz=timezone.utc).isoformat()

    return VideoInfo(
        bvid=d.get("bvid", bvid),
        aid=d.get("aid", 0),
        cid=cid if cid is not None else d.get("cid", 0),
        title=d.get("title", ""),
        desc=d.get("desc", ""),
        pic=d.get("pic", ""),
        duration=d.get("duration", 0),
        owner_name=d.get("owner", {}).get("name", ""),
        owner_mid=d.get("owner", {}).get("mid", 0),
        videos_count=d.get("videos", 1),
        tname=d.get("tname", ""),
        owner_face=d.get("owner", {}).get("face", ""),
        stat=stat,
        pubdate=str(pubdate_ts),
        pubdate_dt=pubdate_dt,
        fetched_at=fetched_at,
        tags=_normalize_tags(d.get("tags", ""))
    )


def _normalize_tags(tags) -> str:
    """Normalize tags from B站 API: returns pipe-separated string regardless of input format."""
    if not tags:
        return ""
    if isinstance(tags, str):
        return tags
    if isinstance(tags, list):
        return " | ".join(
            t.get("tag_name", str(t)) if isinstance(t, dict) else str(t)
            for t in tags
        )
    return str(tags)


def _pick_subtitle(subtitles: list) -> dict | None:
    """Pick best subtitle track: manual Chinese > auto Chinese > any Chinese > first available."""
    if not subtitles:
        return None
    def _is_zh(sub):
        lan = (sub.get("lan") or "").lower()
        return any(tag in lan for tag in ("zh", "cn", "zh-hans", "zh-hant"))
    # Round 1: manual Chinese (ai_status=0 means manually uploaded)
    for sub in subtitles:
        if _is_zh(sub) and str(sub.get("ai_status", "0")) == "0":
            return sub
    # Round 2: any Chinese (including AI-generated)
    for sub in subtitles:
        if _is_zh(sub):
            return sub
    # Round 3: first available subtitle (prefer auto-translate if non-Chinese)
    selected = subtitles[0]
    # If subtitle is English-only, request AI subtitle with Chinese translation
    lan = (selected.get("lan") or "").lower()
    if not _is_zh(selected) and any(t in lan for t in ("en", "ja", "ko", "fr", "de")):
        # Return first non-Chinese track so the caller can trigger subtitle translation via ASR
        selected["_needs_translation"] = True
    return selected


# --- Three-tier subtitle fallback (v8): Tier1 official, Tier2 ASR, Tier3 visual ---
_ASR_TIER_TIMEOUT = float(os.environ.get("BILISUM_ASR_TIMEOUT", "900"))      # real ASR budget, not 6s
_ASR_MAX_DURATION = int(os.environ.get("BILISUM_ASR_MAX_DURATION", "7200"))  # skip ASR for videos > 2h
_VISUAL_TIER_TIMEOUT = float(os.environ.get("BILISUM_VISUAL_TIMEOUT", "600"))
_ASR_SEMAPHORE = asyncio.Semaphore(1)  # one Whisper transcription at a time (executor-thread + VRAM guard)
_ASR_TS_RE = re.compile(r"^\[(\d+(?:\.\d+)?)s\]\s*(.*)$")
_VISUAL_TS_RE = re.compile(r"^\[(?:(\d+):)?(\d{1,2}):(\d{2})\]\s*(.*)$")


def _asr_text_to_body(asr_text: str) -> list:
    """Parse '[12.3s] text' lines from asr_service.transcribe_video into subtitle body dicts.
    Fixes the old bug of fabricating from=i, to=i+5 line indexes as timestamps."""
    body = []
    lines = [ln for ln in asr_text.split("\n") if ln.strip()]
    for i, line in enumerate(lines):
        m = _ASR_TS_RE.match(line.strip())
        if m:
            start, content = float(m.group(1)), m.group(2).strip()
        else:
            start, content = float(i * 5), line.strip()
        if content:
            body.append({"from": start, "to": start + 5.0, "content": content})
    for j in range(len(body) - 1):
        nxt = body[j + 1]["from"]
        if nxt > body[j]["from"]:
            body[j]["to"] = nxt
    return body


async def _try_asr_tier(bvid: str, cid: int, duration: int) -> list | None:
    """Tier 2: full-length ASR transcription. Runs only when Tier 1 found nothing."""
    if os.environ.get("BILISUM_ASR_FALLBACK", "1") != "1":
        return None
    if duration and duration > _ASR_MAX_DURATION:
        _logger.info("[%s] Tier 2 skipped: duration %ss > cap %ss", bvid, duration, _ASR_MAX_DURATION)
        return None
    try:
        from asr_service import transcribe_video, is_asr_available
        if not is_asr_available():
            return None
        _logger.info("[%s] Tier 2: ASR fallback (timeout=%ss)", bvid, _ASR_TIER_TIMEOUT)
        async with _ASR_SEMAPHORE:
            asr_text = await asyncio.wait_for(transcribe_video(bvid, cid), timeout=_ASR_TIER_TIMEOUT)
        if asr_text:
            body = _asr_text_to_body(asr_text)
            if body:
                _logger.info("[%s] Tier 2 (ASR) OK: %d entries", bvid, len(body))
                return body
    except asyncio.TimeoutError:
        _logger.warning("[%s] Tier 2 (ASR) timed out after %ss", bvid, _ASR_TIER_TIMEOUT)
    except Exception as e:
        _logger.warning("[%s] Tier 2 (ASR) failed: %s", bvid, e)
    return None


async def _try_visual_tier(bvid: str, cid: int, duration: float) -> list | None:
    """Tier 3: visual-only — no usable speech track. Keyframes -> vision-model text."""
    if os.environ.get("BILISUM_VISUAL_FALLBACK", "1") != "1":
        return None
    try:
        from asr_service import download_video_for_frames
        from frame_text_service import extract_frame_text
        video_path = await download_video_for_frames(bvid, cid)
        if not video_path:
            return None
        _logger.info("[%s] Tier 3: visual-only fallback", bvid)
        result = await asyncio.wait_for(
            extract_frame_text(bvid, video_path=video_path, duration_sec=duration),
            timeout=_VISUAL_TIER_TIMEOUT
        )
        if result is None or result.gated_off or not result.text_blocks:
            return None
        body = []
        for block in result.text_blocks:  # "[MM:SS] desc" or "[HH:MM:SS] desc"
            m = _VISUAL_TS_RE.match(block.strip())
            if not m:
                continue
            start = int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            body.append({"from": float(start), "to": float(start + 10), "content": f"[画面] {m.group(4).strip()}"})
        if body:
            _logger.info("[%s] Tier 3 (visual) OK: %d frames", bvid, len(body))
            return body
    except asyncio.TimeoutError:
        _logger.warning("[%s] Tier 3 (visual) timed out after %ss", bvid, _VISUAL_TIER_TIMEOUT)
    except Exception as e:
        _logger.warning("[%s] Tier 3 (visual) failed: %s", bvid, e)
    return None


async def get_full_subtitle(bvid: str, cid: Optional[int] = None) -> SubtitleData:
    """三层字幕回退：Tier1 官方字幕通道并行扇出（WBI v2 | player v2(bvid) | player v2(aid) | AI字幕）
    → Tier2 ASR 顺序回退 → Tier3 视觉关键帧回退"""
    info = await get_video_info(bvid, cid=cid)
    cid = cid if cid is not None else info.cid
    aid = info.aid
    mid = info.owner_mid

    body = []
    tags = info.tags
    desc = info.desc
    client = await _get_client()

    async def _try_channel1() -> list | None:
        """Channel 1: Player WBI v2 API (signed)"""
        try:
            data = await asyncio.wait_for(
                _signed_get(
                    "https://api.bilibili.com/x/player/wbi/v2",
                    params={"bvid": bvid, "cid": str(cid)},
                    timeout=15.0
                ),
                timeout=6
            )
            if data.get("code") == 0:
                subs = data.get("data", {}).get("subtitle", {}).get("subtitles", [])
                if subs:
                    selected = _pick_subtitle(subs)
                    if selected:
                        sub_url = selected.get("subtitle_url", "")
                        if sub_url:
                            if sub_url.startswith("//"):
                                sub_url = "https:" + sub_url
                            body_ch1 = await fetch_subtitle_with_retry(sub_url, _get_headers())
                            if body_ch1:
                                _logger.debug("[%s] Channel 1 (WBI) OK: %s", bvid, selected.get("lan", "?"))
                                # If subtitle needs translation, try AI-generated Chinese subtitle
                                if selected.get("_needs_translation") and body_ch1:
                                    try:
                                        ai_subs = [s for s in subs if s.get("lan", "").lower().startswith("ai-zh") or (s.get("ai_status", 0) == 1 and any(t in (s.get("lan") or "").lower() for t in ("zh", "cn")))]
                                        if ai_subs:
                                            ai_url = ai_subs[0].get("subtitle_url", "")
                                            if ai_url.startswith("//"):
                                                ai_url = "https:" + ai_url
                                            ai_body = await fetch_subtitle_with_retry(ai_url, _get_headers())
                                            if ai_body:
                                                body_ch1 = ai_body
                                                _logger.debug("[%s] AI Chinese subtitle OK via Channel 1", bvid)
                                    except Exception:
                                        _logger.debug("[%s] AI subtitle fallback failed, using original", bvid, exc_info=True)
                                return body_ch1
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("[%s] Channel 1 (WBI) failed: %s", bvid, e)
        return None

    async def _try_channel1b() -> list | None:
        """Channel 1b: Plain player v2 (bvid-based, no WBI)"""
        try:
            r = await asyncio.wait_for(
                client.get(
                    f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={str(cid)}",
                    headers=_get_headers(),
                    timeout=httpx.Timeout(15.0)
                ),
                timeout=6
            )
            if r.json().get("code") == 0:
                subs = r.json().get("data", {}).get("subtitle", {}).get("subtitles", [])
                if subs:
                    selected = _pick_subtitle(subs)
                    if selected:
                        sub_url = selected.get("subtitle_url", "")
                        if sub_url:
                            if sub_url.startswith("//"):
                                sub_url = "https:" + sub_url
                            body_ch1b = await fetch_subtitle_with_retry(sub_url, _get_headers())
                            if body_ch1b:
                                _logger.debug("[%s] Channel 1b (player v2) OK: %s", bvid, selected.get("lan", "?"))
                                if selected.get("_needs_translation") and body_ch1b:
                                    try:
                                        ai_subs = [s for s in subs if s.get("lan", "").lower().startswith("ai-zh") or (s.get("ai_status", 0) == 1 and any(t in (s.get("lan") or "").lower() for t in ("zh", "cn")))]
                                        if ai_subs:
                                            ai_url = ai_subs[0].get("subtitle_url", "")
                                            if ai_url.startswith("//"):
                                                ai_url = "https:" + ai_url
                                            ai_body = await fetch_subtitle_with_retry(ai_url, _get_headers())
                                            if ai_body:
                                                body_ch1b = ai_body
                                                _logger.debug("[%s] AI Chinese subtitle OK via Channel 1b", bvid)
                                    except Exception:
                                        _logger.debug("[%s] AI subtitle fallback failed, using original", bvid, exc_info=True)
                                return body_ch1b
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("[%s] Channel 1b (player v2) failed: %s", bvid, e)
        return None

    async def _try_channel2() -> list | None:
        """Channel 2: player v2 with aid"""
        try:
            r = await asyncio.wait_for(
                client.get(
                    f"https://api.bilibili.com/x/player/v2?aid={str(aid)}&cid={str(cid)}",
                    headers=_get_headers(),
                    timeout=httpx.Timeout(15.0)
                ),
                timeout=6
            )
            if r.json().get("code") == 0:
                subs = r.json().get("data", {}).get("subtitle", {}).get("subtitles", [])
                if subs:
                    selected = _pick_subtitle(subs)
                    if selected:
                        sub_url = selected.get("subtitle_url", "")
                        if sub_url:
                            if sub_url.startswith("//"):
                                sub_url = "https:" + sub_url
                            body_ch2 = await fetch_subtitle_with_retry(sub_url, _get_headers())
                            if body_ch2:
                                _logger.debug("[%s] Channel 2 (aid) OK: %s", bvid, selected.get("lan", "?"))
                                return body_ch2
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("[%s] Channel 2 (aid) failed: %s", bvid, e)
        return None

    async def _try_channel3() -> list | None:
        """Channel 3: AI subtitle JSON endpoint"""
        if not mid:
            return None
        try:
            ai_url = f"https://aisubtitle.hdslb.com/aisubtitle/{mid}/{aid}/{cid}.json"
            r = await asyncio.wait_for(
                client.get(ai_url, headers=_get_headers(), timeout=10),
                timeout=6
            )
            if r.status_code == 200 and r.json().get("body"):
                _logger.debug("[%s] Channel 3 (AI subtitle) OK", bvid)
                return r.json()["body"]
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("[%s] Channel 3 (AI subtitle) failed: %s", bvid, e)
        return None

    # ---------------- Tier 1: official subtitle channels (parallel fan-out) ----------------
    tasks = [
        _try_channel1(),
        _try_channel1b(),
        _try_channel2(),
        _try_channel3(),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    source = "none"
    # Pick first successful result (priority: channel order 1 > 1b > 2 > 3)
    for r in results:
        if isinstance(r, list) and r:
            body = r
            source = "official"
            break

    # ---------------- Tier 2: ASR fallback (sequential, only when Tier 1 is empty) ----------------
    if not body:
        asr_body = await _try_asr_tier(bvid, cid, info.duration)
        if asr_body:
            body = asr_body
            source = "asr"

    # ---------------- Tier 3: visual-only fallback (keyframes -> vision text) ----------------
    if not body:
        visual_body = await _try_visual_tier(bvid, cid, float(info.duration or 0))
        if visual_body:
            body = visual_body
            source = "visual"

    # Get tags
    try:
        r = await client.get(
            f"https://api.bilibili.com/x/tag/archive/tags?aid={aid}",
            headers=_get_headers(),
            timeout=_API_TIMEOUT
        )
        if r.json().get("code") == 0:
            tags = " | ".join([t["tag_name"] for t in r.json().get("data", [])])
    except Exception:
        _logger.debug("[%s] Tag fetch failed", bvid, exc_info=True)

    entries = []
    text_parts = []
    for item in body:
        entry = SubtitleEntry(
            from_=item.get("from", 0),
            to=item.get("to", 0),
            content=item.get("content", "")
        )
        entries.append(entry)
        text_parts.append(entry.content)

    return SubtitleData(
        body=entries,
        text=" ".join(text_parts),
        tags=tags,
        desc=desc,
        source=source,
        all_channels_failed=not entries,
    )


async def get_full_subtitle_multi(bvid: str, pages: Optional[list] = None) -> SubtitleData:
    """Multi-P subtitle aggregation: fetches subtitles for all video pages and combines them.

    Single-page videos return the same result as get_full_subtitle(bvid).
    Multi-page videos prefix each page's subtitle text with a `## P{n} {part_title}` header
    and join them with double newlines.
    `pages` may be passed by callers that already fetched get_video_parts(bvid)
    to avoid a duplicate API round-trip.
    """
    if pages is None:
        pages = await get_video_parts(bvid)
    if not pages or len(pages) <= 1:
        return await get_full_subtitle(bvid)

    all_entries: list = []
    all_texts: list[str] = []
    combined_tags = ""
    combined_desc = ""
    parts_ok = 0
    _SOURCE_RANK = {"official": 0, "asr": 1, "visual": 2, "none": 3}
    combined_source = "none"

    for i, page in enumerate(pages, start=1):
        cid = page.get("cid", 0)
        part_title = page.get("part", f"P{i}")

        try:
            sub = await get_full_subtitle(bvid, cid=cid)
        except Exception:
            _logger.warning("[%s] get_full_subtitle_multi: page %s (cid=%s) failed, skipping", bvid, i, cid)
            continue

        if sub.body and sub.text.strip():
            parts_ok += 1
            if _SOURCE_RANK.get(sub.source, 3) < _SOURCE_RANK.get(combined_source, 3):
                combined_source = sub.source
            # Renumber entries to avoid overlapping timestamps across pages.
            # Each page gets an offset large enough to keep its entries contiguous
            # and globally ordered: page offset = (i-1) * 100000.
            page_offset = (i - 1) * 100000.0
            for entry in sub.body:
                entry.from_ += page_offset
                entry.to += page_offset
            all_entries.extend(sub.body)

            header = f"## P{i} {part_title}\n\n"
            all_texts.append(header + sub.text)

            # Accumulate tags/desc from the first page only (primary metadata)
            if i == 1:
                combined_tags = sub.tags
                combined_desc = sub.desc

    if not all_entries:
        # All pages failed — fall back to single-page fetch
        fallback = await get_full_subtitle(bvid)
        fallback.parts_total = len(pages)
        fallback.parts_ok = 0
        return fallback

    return SubtitleData(
        body=all_entries,
        text="\n\n".join(all_texts),
        tags=combined_tags,
        desc=combined_desc,
        source=combined_source,
        all_channels_failed=not all_entries,
        parts_total=len(pages),
        parts_ok=parts_ok,
    )


async def get_comments(bvid: str) -> list[CommentEntry]:
    """获取视频评论 — 双通道（参考 bilibili.js getComments + bili-note fetch_comments）

    主通道: x/v2/comment/reply?sort=2 (原版JS端点, 按热度, 无需WBI, 无需登录)
    回退: x/v2/reply/main?mode=3 (WBI签名, 需要WBI key)
    """
    try:
        info = await get_video_info(bvid)
        if info.desc and "充电专属" in (info.desc or ""):
            return []

        comments = []
        seen_rids = set()

        # ---- 通道1: 原版 comment/reply (参考 bilibili.js L7, 无需WBI, 无需登录) ----
        _logger.debug("[%s] Trying comment/reply?sort=2", bvid)
        try:
            r1 = await _retry_get(
                await _get_client(),
                "https://api.bilibili.com/x/v2/comment/reply",
                params={"type": 1, "oid": info.aid, "ps": 30, "sort": 2},
                timeout=httpx.Timeout(8.0, connect=3.0, read=12.0)
            )
            d1 = r1.json()
            if d1.get("code") == 0 and d1.get("data", {}).get("replies"):
                for rr in d1["data"]["replies"]:
                    rid = rr.get("rpid")
                    if rid is None or rid in seen_rids:
                        continue
                    seen_rids.add(rid)
                    member = rr.get("member", {})
                    content = rr.get("content", {})
                    sub_replies = []
                    for sr in rr.get("replies", [])[:15]:
                        sub_replies.append(CommentReply(
                            user=sr.get("member", {}).get("uname", ""),
                            content=sr.get("content", {}).get("message", ""),
                            likes=sr.get("like", 0)
                        ))
                    comments.append(CommentEntry(
                        user=member.get("uname", "匿名"),
                        content=content.get("message", ""),
                        likes=rr.get("like", 0),
                        replies=sub_replies
                    ))
        except Exception:
            _logger.debug("[%s] comment/reply failed, falling back to reply/main", bvid)

        # ---- 通道2: WBI reply/main (参考 bili-note extract_bilibili.py fetch_comments) ----
        if not comments:
            try:
                data = await _signed_get(
                    "https://api.bilibili.com/x/v2/reply/main",
                    params={"type": 1, "oid": info.aid, "mode": 3, "ps": 40, "web_location": "1315875"},
                    timeout=_API_TIMEOUT
                )
                if data.get("code") == 0:
                    replies = data.get("data", {}).get("replies") or []
                    for rr in replies:
                        rid = rr.get("rpid")
                        if rid is None or rid in seen_rids:
                            continue
                        seen_rids.add(rid)
                        member = rr.get("member", {})
                        content = rr.get("content", {})
                        sub_replies = []
                        for sr in rr.get("replies", [])[:15]:
                            sub_replies.append(CommentReply(
                                user=sr.get("member", {}).get("uname", ""),
                                content=sr.get("content", {}).get("message", ""),
                                likes=sr.get("like", 0)
                            ))
                        comments.append(CommentEntry(
                            user=member.get("uname", "匿名"),
                            content=content.get("message", ""),
                            likes=rr.get("like", 0),
                            replies=sub_replies
                        ))
            except Exception:
                _logger.debug("[%s] reply/main also failed", bvid, exc_info=True)

        return comments
    except Exception:
        _logger.debug("get_comments failed", exc_info=True)
        return []


async def get_all_comments(bvid: str, max_pages: int = 20) -> list[CommentEntry]:
    """获取视频全部评论用于AI筛选。

    双通道回退策略（参考 bilibili.js getComments + bili-note fetch_comments）：
    1. 主通道: x/v2/comment/reply?sort=2 (原版JS可用的端点, 按热度, 无需WBI, 无需登录)
    2. 回退: x/v2/reply/wbi/main?mode=3 (bili-note WBI v2 cursor分页, 更完整)

    原版JS评论API: https://api.bilibili.com/x/v2/comment/reply?type=1&oid=AID&ps=30&sort=2
    只取第一页热门评论，简单可用。
    """
    all_comments = []
    seen_rids = set()
    try:
        info = await get_video_info(bvid)
        aid = info.aid

        # ---- 通道1: 原版 comment/reply (sort=2=热度, 不需要WBI, 不需要登录) ----
        _logger.info("[%s] Trying comment/reply?sort=2 (original JS endpoint, no WBI needed)", bvid)
        try:
            r1 = await _retry_get(
                await _get_client(),
                "https://api.bilibili.com/x/v2/comment/reply",
                params={"type": 1, "oid": aid, "ps": 30, "sort": 2},
                timeout=httpx.Timeout(8.0, connect=3.0, read=12.0)
            )
            d1 = r1.json()
            if d1.get("code") == 0 and d1.get("data", {}).get("replies"):
                count = 0
                for rr in d1["data"]["replies"]:
                    rid = rr.get("rpid")
                    if rid is None or rid in seen_rids:
                        continue
                    seen_rids.add(rid)
                    member = rr.get("member", {})
                    content = rr.get("content", {})
                    sub_replies = []
                    for sr in rr.get("replies", [])[:5]:
                        sub_replies.append(CommentReply(
                            user=sr.get("member", {}).get("uname", ""),
                            content=sr.get("content", {}).get("message", ""),
                            likes=sr.get("like", 0)
                        ))
                    all_comments.append(CommentEntry(
                        user=member.get("uname", "匿名"),
                        content=content.get("message", ""),
                        likes=rr.get("like", 0),
                        replies=sub_replies
                    ))
                    count += 1
                _logger.info("[%s] comment/reply returned %s comments", bvid, count)
        except Exception as e1:
            _logger.warning("[%s] comment/reply failed: %s, trying wbi/main", bvid, str(e1)[:150])

        # ---- 通道2 (回退): WBI cursor分页 (来自 bili-note extract_bilibili.py) ----
        if not all_comments:
            _logger.info("[%s] Fallback to reply/wbi/main (cursor pagination + WBI v2)", bvid)
            try:
                from wbi import sign_params as wbi_sign
                import time as _time2
                next_val = 0
                for _page in range(4):  # up to 4 pages (80 comments)
                    signed_params = await wbi_sign({
                        "type": 1, "oid": aid, "mode": 3, "ps": 20, "next": next_val
                    })
                    query = urllib.parse.urlencode(signed_params)
                    r2 = await _retry_get(
                        await _get_client(),
                        f"https://api.bilibili.com/x/v2/reply/wbi/main?{query}",
                        timeout=_API_TIMEOUT
                    )
                    d2 = r2.json()
                    if d2.get("code") != 0:
                        _logger.warning("[%s] reply/wbi/main failed code=%s", bvid, d2.get("code"))
                        break
                    data = d2.get("data") or {}
                    cursor = data.get("cursor") or {}
                    candidates = []
                    candidates.extend(data.get("top_replies") or [])
                    candidates.extend(data.get("replies") or [])
                    top = data.get("top") or {}
                    if isinstance(top, dict):
                        for key in ("admin", "upper"):
                            val = top.get(key)
                            if isinstance(val, dict) and val.get("rpid"):
                                candidates.append(val)
                    for rr in candidates:
                        rid = rr.get("rpid")
                        if rid is None or rid in seen_rids:
                            continue
                        seen_rids.add(rid)
                        member = rr.get("member", {})
                        content = rr.get("content", {})
                        sub_replies = []
                        for sr in rr.get("replies", [])[:5]:
                            sub_replies.append(CommentReply(
                                user=sr.get("member", {}).get("uname", ""),
                                content=sr.get("content", {}).get("message", ""),
                                likes=sr.get("like", 0)
                            ))
                        all_comments.append(CommentEntry(
                            user=member.get("uname", "匿名"),
                            content=content.get("message", ""),
                            likes=rr.get("like", 0),
                            replies=sub_replies
                        ))
                    if cursor.get("is_end"):
                        break
                    new_next = cursor.get("next")
                    if new_next is None or new_next == next_val:
                        break
                    next_val = new_next
                    await asyncio.sleep(0.25)
                _logger.info("[%s] reply/wbi/main returned %s total comments", bvid, len(all_comments))
            except Exception as e2:
                _logger.warning("[%s] reply/wbi/main also failed: %s", bvid, str(e2)[:150])

        return all_comments
    except Exception:
        _logger.warning("[%s] get_all_comments failed", bvid, exc_info=True)
        return all_comments



async def fetch_subtitle_with_retry(url, headers, max_retries=3):
    """Fetch subtitle JSON with retry and backoff (v7.2: deterministic exit on success)"""
    client = await _get_client()
    for attempt in range(max_retries):
        try:
            r = await client.get(url, headers=headers, timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                if data.get("body"):
                    return data["body"]
                # Valid 200 but no body -- subtitle may be empty; don't retry
                return None
            if r.status_code in (403, 404, 502, 503):  # expired URL or transient error
                await asyncio.sleep(1 * (2 ** attempt))
                continue
            return None  # non-retriable status
        except Exception:
            if attempt < max_retries - 1:
                await asyncio.sleep(1 * (2 ** attempt))
            else:
                _logger.debug("subtitle fetch failed after %s retries: %s", max_retries, url)
                return None
    return None


async def get_danmaku(cid: int, duration: float = 0, owner_mid: int = 0) -> list[str]:
    """获取弹幕列表 — v3 JSON API + v1 XML fallback with dedup + frequency sort + UP主 tagging

    When owner_mid > 0, danmaku whose mid_hash matches UP主 are prefixed with [UP主].
    Returns list of danmaku text strings, sorted by frequency (high to low).
    Channels tried in parallel with 6s timeout each. Segments capped at 4.
    """
    import math as _math_dm
    import zlib as _zlib_dm
    client = await _get_client()

    def _crc32_mid(mid: int) -> str:
        """CRC32 of mid, matching B站's mid_hash format (unsigned, hex, lowercased)."""
        crc = _zlib_dm.crc32(str(mid).encode("utf-8")) & 0xFFFFFFFF
        return f"{crc:08x}"

    # Pre-compute UP主 mid_hash for matching
    _up_mid_hash = _crc32_mid(owner_mid) if owner_mid > 0 else ""

    def _parse_d_text(text3: str, seg_matches: list) -> None:
        """Parse XML-like danmaku text, extracting text + mid_hash for UP主 matching."""
        if text3.startswith("{"):
            try:
                import gzip as _gzip_dm
                jd = json.loads(text3)
                dm_list = jd.get("data", [])
                if isinstance(dm_list, list):
                    for dm in dm_list:
                        txt = dm.get("text", "") if isinstance(dm, dict) else str(dm)
                        mid_h = str(dm.get("mid_hash", "")) if isinstance(dm, dict) else ""
                        if txt:
                            seg_matches.append((txt, mid_h))
                    return
            except (json.JSONDecodeError, KeyError):
                _logger.debug("Danmaku JSON parse failed in _parse_d_text for cid=%s", cid, exc_info=True)
        # XML fallback: <d p="time,mode,size,color,send_time,pool,mid_hash,dbid">text</d>
        clean = re.sub(r"<!\[CDATA\[|\]\]>", "", text3)
        for m in re.finditer(r'<d p="([^"]*)">([^<]+)</d>', clean):
            p_attr = m.group(1)
            text = m.group(2)
            parts = p_attr.split(",")
            mid_h = parts[6] if len(parts) > 6 else ""
            seg_matches.append((text, mid_h))

    async def _try_channel1(seg: int) -> list[tuple[str, str]]:
        """Channel 1: v3 JSON API"""
        matches: list[tuple[str, str]] = []
        try:
            r3 = await asyncio.wait_for(
                client.get(
                    f"https://api.bilibili.com/x/v2/dm/list.so?oid={cid}&segment_index={seg}&type=1",
                    headers=_get_headers(),
                    timeout=_API_TIMEOUT
                ),
                timeout=6
            )
            if r3.status_code == 200:
                _parse_d_text(r3.text, matches)
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("Danmaku channel 1 (v3 JSON) failed for cid=%s: %s", cid, e)
        return matches

    async def _try_channel2(seg: int) -> list[tuple[str, str]]:
        """Channel 2: v2 seg.so with WBI signing + retry"""
        matches: list[tuple[str, str]] = []
        # WBI key fetch with 3 retries
        wbi_signed = None
        for retry in range(3):
            try:
                wbi_signed = await asyncio.wait_for(
                    sign_params({"type": 1, "oid": cid, "segment_index": seg}),
                    timeout=10
                )
                break
            except Exception as e:
                if retry < 2:
                    await asyncio.sleep(0.5 * (2 ** retry))
                else:
                    _logger.debug("WBI sign failed for cid=%s after 3 retries: %s", cid, e)
        if wbi_signed is None:
            # fallback: try without WBI signing
            wbi_signed = {"type": 1, "oid": cid, "segment_index": seg}
        try:
            r = await asyncio.wait_for(
                client.get(
                    "https://api.bilibili.com/x/v2/dm/wbi/web/seg.so",
                    params=wbi_signed,
                    headers=_get_headers(),
                    timeout=_API_TIMEOUT
                ),
                timeout=6
            )
            if r.status_code == 200:
                _parse_d_text(r.text, matches)
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("Danmaku channel 2 (seg.so) failed for cid=%s: %s", cid, e)
        return matches

    async def _try_channel3() -> list[tuple[str, str]]:
        """Channel 3: v1 XML endpoint (classic, no WBI required)"""
        matches: list[tuple[str, str]] = []
        try:
            r1 = await asyncio.wait_for(
                client.get(
                    f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}",
                    headers=_get_headers(),
                    timeout=_API_TIMEOUT
                ),
                timeout=6
            )
            if r1.status_code == 200:
                _parse_d_text(r1.text, matches)
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("Danmaku channel 3 (v1 XML) failed for cid=%s: %s", cid, e)
        return matches

    try:
        total_segments = max(1, _math_dm.ceil(duration / 360)) if duration else 1
        # Cap segments at 4 to limit latency (6s parallel per segment = max ~30s total)
        total_segments = min(total_segments, 4)
        all_raw: list[tuple[str, str]] = []

        for seg in range(1, total_segments + 1):
            # Parallel: channels 1+2 per segment, plus channel 3 only once on first segment
            tasks = [_try_channel1(seg), _try_channel2(seg)]
            if seg == 1:
                tasks.append(_try_channel3())
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect matches from all channels that succeeded
            for r in results:
                if isinstance(r, list):
                    all_raw.extend(r)

        # If no results from parallel attempts, try channel 3 alone
        if not all_raw and total_segments == 1:
            ch3 = await _try_channel3()
            all_raw.extend(ch3)

        # Build frequency map: text -> (count, is_up)
        freq: dict[str, tuple[int, bool]] = {}
        for text, mid_h in all_raw:
            if len(text) < 2:
                continue
            is_up = bool(_up_mid_hash and mid_h and mid_h == _up_mid_hash)
            prev_count, prev_up = freq.get(text, (0, False))
            freq[text] = (prev_count + 1, prev_up or is_up)

        # Sort: frequency descending, UP主 first within same frequency
        sorted_items = sorted(freq.items(), key=lambda x: (not x[1][1], -x[1][0]))

        # Format output
        result = []
        for text, (count, is_up) in sorted_items:
            prefix = "[UP主]" if is_up else ""
            if count >= 3:
                prefix += f"[x{count}]"
            result.append(f"{prefix}{text}" if prefix else text)

        return result[:200]
    except Exception:
        _logger.debug("[cid=%s] get_danmaku failed", cid, exc_info=True)
        return []


async def search_videos(keyword: str, page: int = 1) -> dict:
    """搜索B站视频"""
    return await _signed_get(
        "https://api.bilibili.com/x/web-interface/search/type",
        params={"keyword": keyword, "search_type": "video", "page": str(page)},
        timeout=_API_TIMEOUT
    )


async def get_popular_videos() -> dict:
    """获取B站热门视频"""
    return await _signed_get(
        "https://api.bilibili.com/x/web-interface/popular",
        timeout=_API_TIMEOUT
    )


async def get_video_parts(bvid: str) -> list:
    """获取多P视频的所有分P信息 (v7.2: shared client, error logging)"""
    client = await _get_client()
    try:
        r = await _retry_get(
            client,
            f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}",
            timeout=_API_TIMEOUT
        )
        data = r.json()
        if data.get("code") == 0:
            return data.get("data", [])
    except Exception:
        _logger.debug("[%s] get_video_parts failed", bvid, exc_info=True)
    return []


async def get_view_points(bvid: str, cid: Optional[int] = None) -> list[dict]:
    """获取B站官方章节标记 (view_points) — UP主在创作中心手动划分的视频分段。

    双通道回退（与字幕通道同源）:
      1. 播放器 v2 API:  x/player/v2?bvid=&cid=       (无需WBI)
      2. 播放器 WBI v2:  x/player/wbi/v2 (signed)     (兜底)

    B站原始 view_points 条目形如:
        {"type": 2, "from": 0, "to": 210, "content": "开场", "imgUrl": "...", "logoUrl": ""}
    其中 type==2 为章节标记（"分段章节"）; 其他 type（如高能进度条）会被跳过。

    Returns 规范化章节列表（按起始时间升序）:
        [{"title": str, "from": int, "to": int, "img_url": str, "source": "official"}]
    视频无章节或任何一步失败时返回 [] —— 章节是可选增强，绝不抛错阻塞主流程。
    """
    from constants import MIN_CHAPTER_SECONDS, MAX_CHAPTERS
    try:
        if cid is None:
            info = await get_video_info(bvid)
            cid = info.cid

        raw: list = []
        client = await _get_client()

        # ---- 通道1: player v2 (plain) ----
        try:
            r = await asyncio.wait_for(
                client.get(
                    f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}",
                    headers=_get_headers(),
                    timeout=_API_TIMEOUT,
                ),
                timeout=6,
            )
            data = r.json()
            if data.get("code") == 0:
                raw = data.get("data", {}).get("view_points") or []
        except (asyncio.TimeoutError, Exception) as e:
            _logger.debug("[%s] view_points channel 1 (player v2) failed: %s", bvid, e)

        # ---- 通道2: player WBI v2 (signed 兜底) ----
        if not raw:
            try:
                data = await asyncio.wait_for(
                    _signed_get(
                        "https://api.bilibili.com/x/player/wbi/v2",
                        params={"bvid": bvid, "cid": str(cid)},
                        timeout=10.0,
                    ),
                    timeout=6,
                )
                if data.get("code") == 0:
                    raw = data.get("data", {}).get("view_points") or []
            except (asyncio.TimeoutError, Exception) as e:
                _logger.debug("[%s] view_points channel 2 (WBI) failed: %s", bvid, e)

        # ---- 规范化 + 过滤 ----
        chapters: list[dict] = []
        for vp in raw:
            if not isinstance(vp, dict):
                continue
            try:
                vp_type = int(vp.get("type", 0) or 0)
                f = int(vp.get("from", 0) or 0)
                t = int(vp.get("to", 0) or 0)
            except (TypeError, ValueError):
                continue
            if vp_type != 2:          # 仅保留章节标记
                continue
            if t <= f or (t - f) < MIN_CHAPTER_SECONDS:
                continue
            title = str(vp.get("content", "") or "").strip()
            chapters.append({
                "title": title or f"章节 {len(chapters) + 1}",
                "from": f,
                "to": t,
                "img_url": vp.get("imgUrl", "") or "",
                "source": "official",
            })

        chapters.sort(key=lambda c: c["from"])
        if len(chapters) > MAX_CHAPTERS:
            chapters = chapters[:MAX_CHAPTERS]
        if chapters:
            _logger.info("[%s] view_points OK: %d official chapters", bvid, len(chapters))
        return chapters
    except Exception:
        _logger.debug("[%s] get_view_points failed", bvid, exc_info=True)
        return []


def extract_bvid(url: str) -> str:
    """从URL或BV号提取标准BV号"""
    if not url:
        raise ValueError("请输入视频链接或BV号")
    m = re.search(r"BV[a-zA-Z0-9]+", url)
    if m:
        return m[0]
    if re.match(r"av\d+", url, re.IGNORECASE):
        return url
    raise ValueError("无法识别BV号，请检查输入")


async def resolve_b23_url(short_url: str) -> str:
    """解析 b23.tv 短链接为完整 BV 号 (v7.2: shared client, error logging)"""
    if "b23.tv" not in short_url:
        return short_url
    client = await _get_client()
    try:
        r = await client.get(short_url, headers=_get_headers(), timeout=_API_TIMEOUT)
        # b23.tv redirects with 301/302
        location = r.headers.get("Location", "")
        if location:
            bvid = extract_bvid(location)
            if bvid:
                return bvid
    except Exception:
        _logger.debug("resolve_b23_url failed for %s", short_url, exc_info=True)
    return short_url  # Return original if resolution fails


async def get_audio_url(bvid: str) -> dict:
    """获取视频音频流URL（用于Whisper转写），带宽感知选择"""
    info = await get_video_info(bvid)
    data = await _signed_get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"bvid": bvid, "cid": str(info.cid), "fnval": "80"},
        timeout=_API_TIMEOUT
    )
    if data.get("code") != 0:
        raise ValueError(data.get("message", "Failed to get audio URL"))

    d = data.get("data", {})
    audio_urls = []
    best_url = ""
    MAX_BW = 64000  # 64 kbps for ASR — efficient enough, clear enough

    dash = d.get("dash", {})
    if dash and dash.get("audio"):
        audio_list = dash["audio"]
        audio_urls = [
            {
                "id": a.get("id"),
                "baseUrl": a.get("baseUrl") or a.get("base_url") or "",
                "codec": a.get("codec", ""),
                "bandwidth": a.get("bandwidth", 0),
            }
            for a in audio_list
        ]

        def _bw(item) -> int:
            value = item.get("bandwidth") or item.get("bandWidth") or 0
            try:
                return int(value)
            except Exception:
                return 0

        candidates = [a for a in audio_list if _bw(a) > 0]
        if candidates:
            preferred = [a for a in candidates if _bw(a) <= MAX_BW]
            if preferred:
                best = max(preferred, key=_bw)
            else:
                best = min(candidates, key=_bw)
            best_url = best.get("baseUrl") or best.get("base_url") or best.get("url") or ""

    # Fallback: if no DASH audio, try durl
    if not best_url:
        durl = d.get("durl") or []
        if durl:
            best_url = durl[0].get("url") or ""

    return {
        "title": info.title,
        "bvid": bvid,
        "url": best_url,
        "audio_urls": audio_urls
    }


async def detect_subtitle_formats(bvid: str) -> dict:
    """检测视频可用字幕格式 (v7.2: shared client, error logging)"""
    info = await get_video_info(bvid)
    cid = info.cid
    aid = info.aid
    mid = info.owner_mid

    formats = []
    client = await _get_client()

    # Player v2 subtitle
    try:
        r = await client.get(
            f"https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}",
            headers=_get_headers(),
            timeout=_API_TIMEOUT
        )
        if r.json().get("code") == 0:
            subs = r.json().get("data", {}).get("subtitle", {}).get("subtitles", [])
            for s in subs:
                formats.append({
                    "lan_doc": s.get("lan_doc", ""),
                    "lan": s.get("lan", ""),
                    "format": "json"
                })
    except Exception:
        _logger.debug("[%s] detect_subtitle_formats: player v2 failed", bvid, exc_info=True)

    # AI subtitle
    try:
        r = await client.get(
            f"https://aisubtitle.hdslb.com/aisubtitle/{mid}/{aid}/{cid}.json",
            headers=_get_headers(), timeout=5
        )
        if r.status_code == 200 and r.json().get("body"):
            formats.append({"lan_doc": "AI字幕", "lan": "ai-zh", "format": "json"})
    except Exception:
        _logger.debug("[%s] detect_subtitle_formats: AI subtitle failed", bvid, exc_info=True)

    parts = await get_video_parts(bvid)

    return {
        "bvid": bvid,
        "title": info.title,
        "duration": info.duration,
        "formats": formats,
        "videos_count": info.videos_count,
        "parts": [{"title": p.get("part", ""), "cid": p.get("cid", 0)} for p in parts]
    }


# ==================== Favorites API (v7.2) ====================

async def get_user_favorites(mid: int = None) -> list:
    """获取用户所有收藏夹列表"""
    client = await _get_client()
    all_folders = []
    page = 1
    while True:
            url = f"https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid={mid}&pn={page}&ps=50"
            r = await _retry_get(client, url, timeout=_API_TIMEOUT)
            data = r.json()
            if data.get("code") != 0:
                break
            folders = data.get("data", {}).get("list", [])
            if not folders:
                break
            all_folders.extend(folders)
            if not data.get("data", {}).get("has_more", False):
                break
            page += 1
            await asyncio.sleep(0.3)
    return all_folders

async def get_favorite_content(media_id: int, pn: int = 1, ps: int = 20) -> dict:
    """获取收藏夹单页内容"""
    return await _signed_get(
        "https://api.bilibili.com/x/v3/fav/resource/list",
        params={"media_id": media_id, "pn": pn, "ps": ps, "platform": "web"},
        timeout=_API_TIMEOUT
    )

async def get_all_favorite_videos(media_id: int) -> list:
    """获取收藏夹全部视频（分页循环，per-page 错误跳过）"""
    all_videos = []
    page = 1
    while True:
        try:
            data = await get_favorite_content(media_id, pn=page, ps=20)
            code = data.get("code")
            if code != 0:
                if code in (-404, -400):
                    _logger.warning(
                        "get_favorite_content media_id=%s pn=%s permanent error code=%s — stopping",
                        media_id, page, code)
                    break
                _logger.warning(
                    "get_favorite_content media_id=%s pn=%s transient error code=%s message=%s — skipping page",
                    media_id, page, code, data.get("message", ""))
                page += 1
                await asyncio.sleep(0.3)
                continue
            _d = data.get("data") or {}
            medias = _d.get("medias", [])
            if not medias:
                break
            for m in medias:
                bvid = m.get("bvid") or m.get("bv_id", "")
                if not bvid:
                    continue
                attr = m.get("attr", 0)
                title = m.get("title", "")
                if attr == 9 or title in ["已失效视频", "已删除视频"]:
                    continue
                all_videos.append({
                    "bvid": bvid,
                    "title": title,
                    "cover": m.get("cover", ""),
                    "duration": m.get("duration", 0),
                    "author": m.get("upper", {}).get("name", ""),
                    "intro": m.get("intro", ""),
                })
            _has_more = (data.get("data") or {}).get("has_more", False)
            if not _has_more:
                break
            page += 1
            await asyncio.sleep(0.3)
        except Exception:
            _logger.warning(
                "get_favorite_content media_id=%s pn=%s connection error — stopping",
                media_id, page, exc_info=True)
            break
    return all_videos

async def move_favorite_resources(src_media_id: int, tar_media_id: int, resources: list) -> dict:
    """批量移动收藏夹内容"""
    headers = _get_headers()
    jct = ""
    for pair in headers.get("Cookie", "").split(";"):
        if "bili_jct=" in pair:
            jct = pair.split("bili_jct=", 1)[1].strip()
            break
    if not jct:
        return {"code": -1, "message": "missing bili_jct"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.bilibili.com/x/v3/fav/resource/move",
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "src_media_id": src_media_id,
                "tar_media_id": tar_media_id,
                "resources": ",".join(resources),
                "platform": "web",
                "csrf": jct,
            }
        )
        return r.json()
