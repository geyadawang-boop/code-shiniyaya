"""
B站视频总结工具 - FastAPI 后端
统一后端服务，参考现有 Express + Flask 架构重新实现
"""

import sys
import os
import re
import asyncio
# Ensure backend directory is on path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import uuid
import base64
import httpx
import logging
from io import BytesIO
from datetime import datetime
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

import database as db

logger = logging.getLogger("bilisum")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Initialise DB early (no longer an import-time side-effect of database.py)
try:
    db.init_db()
    logger.info("Database initialised successfully")
except Exception:
    logger.warning("Database initialisation failed -- will retry on first access", exc_info=True)

from bilibili_client import (
    get_video_info, get_full_subtitle, get_comments, get_all_comments, get_danmaku,
    search_videos, get_popular_videos, get_video_parts,
    get_audio_url, detect_subtitle_formats, extract_bvid, set_cookie
)
from summarizer import summarize_with_claude, summarize_segments

# Lazy-init RAG service
_rag_svc = None
_rag_svc_config_hash = None

def get_rag_service():
    """Return a RAG service singleton. Recreates it when the API key/URL/model change."""
    global _rag_svc, _rag_svc_config_hash
    api_key = db.get_setting("api_key", "")
    api_url = db.get_setting("api_url", "")
    model = db.get_setting("model", "deepseek-chat")
    current_hash = hash((api_key, api_url, model))
    if _rag_svc is None or _rag_svc_config_hash != current_hash:
        from rag_service import RAGService
        _rag_svc = RAGService(api_key=api_key, api_url=api_url, model=model)
        _rag_svc_config_hash = current_hash
    return _rag_svc

import time as _time  # used by TraceIdMiddleware

app = FastAPI(title="B站视频总结工具", version="5.0.0")

# ==================== TraceId/SpanId Middleware ====================
# Injects a traceId + spanId into every HTTP request for structured logging.
# Trace IDs are returned to clients in the X-Trace-Id response header for
# correlation with frontend error reports and backend logs.

class TraceIdMiddleware:
    """ASGI middleware: inject traceId + spanId, log request/response timing."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace_id = uuid.uuid4().hex[:12]
        span_id = uuid.uuid4().hex[:6]

        scope["trace_id"] = trace_id
        scope["span_id"] = span_id

        start = _time.time()
        method = scope.get("method", "?")
        path = scope.get("path", "?")
        logger.info("--> %s %s [trace=%s span=%s]", method, path, trace_id, span_id)

        async def wrapped_send(msg):
            if msg.get("type") == "http.response.start":
                headers_list = list(msg.get("headers", []))
                headers_list.append((b"x-trace-id", trace_id.encode()))
                headers_list.append((b"x-span-id", span_id.encode()))
                msg["headers"] = headers_list
            await send(msg)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            logger.error("MIDDLEWARE_CRASH %s %s [trace=%s]", method, path, trace_id, exc_info=True)
            raise

        elapsed = (_time.time() - start) * 1000
        logger.info("<-- %s %s %.1fms [trace=%s]", method, path, elapsed, trace_id)

app.add_middleware(TraceIdMiddleware)

# [v7.1] Modular routers (split from main.py for maintainability)
try:
    from routers.static import router as static_router
    app.include_router(static_router)
    logger.info("Registered router: static")
except Exception:
    logger.warning("Failed to register router: static", exc_info=True)

try:
    from routers.bilibili import router as bili_router
    app.include_router(bili_router)
    logger.info("Registered router: bilibili")
except Exception:
    logger.warning("Failed to register router: bilibili", exc_info=True)

try:
    from routers.ai import router as ai_router
    app.include_router(ai_router)
    logger.info("Registered router: ai")
except Exception:
    logger.warning("Failed to register router: ai", exc_info=True)

try:
    from routers.kb import router as kb_router
    app.include_router(kb_router)
    logger.info("Registered router: kb")
except Exception:
    logger.warning("Failed to register router: kb", exc_info=True)

try:
    from routers.misc import router as misc_router
    app.include_router(misc_router)
    logger.info("Registered router: misc")
except Exception:
    logger.warning("Failed to register router: misc", exc_info=True)

# [v8.0] FIX: auth.py, export.py, favorites.py were previously unregistered
try:
    from routers.auth import router as auth_router
    app.include_router(auth_router)
    logger.info("Registered router: auth")
except Exception:
    logger.warning("Failed to register router: auth", exc_info=True)

try:
    from routers.export import router as export_router
    app.include_router(export_router)
    logger.info("Registered router: export")
except Exception:
    logger.warning("Failed to register router: export", exc_info=True)

try:
    from routers.favorites import router as fav_router
    app.include_router(fav_router)
    logger.info("Registered router: favorites")
except Exception:
    logger.warning("Failed to register router: favorites", exc_info=True)

# [v8.0] FIX: multi_search/integration.py was previously unregistered (dead code)
try:
    from multi_search.integration import router as multi_search_router
    app.include_router(multi_search_router)
    logger.info("Registered router: multi-search")
except Exception:
    logger.warning("Failed to register router: multi-search", exc_info=True)

# [v8.1] Error telemetry router: /api/errors/report, /summary, /alerts, /recent
try:
    from routers.errors import router as errors_router
    app.include_router(errors_router)
    logger.info("Registered router: errors")
except Exception:
    logger.warning("Failed to register router: errors", exc_info=True)

# [v9.0] Heartbeat v2 router: /api/heartbeat/status, /agents, /workflows, /alerts, /log
# Watchdog background task runs on a 30s interval, reading the JSONL journal.
try:
    from routers.heartbeat import router as heartbeat_router
    app.include_router(heartbeat_router)
    logger.info("Registered router: heartbeat")
except Exception:
    logger.warning("Failed to register router: heartbeat", exc_info=True)

# [v9.0] ASR model management router: /api/asr/models, /api/asr/models/install
try:
    from routers.asr import router as asr_router
    app.include_router(asr_router)
    logger.info("Registered router: asr")
except Exception:
    logger.warning("Failed to register router: asr", exc_info=True)

# Start the heartbeat watchdog background task on FastAPI startup
try:
    @app.on_event("startup")
    async def _start_heartbeat_watchdog():
        from heartbeat_v2 import start_watchdog
        start_watchdog()
        logger.info("Heartbeat watchdog started on app startup")

    @app.on_event("shutdown")
    async def _stop_heartbeat_watchdog():
        from heartbeat_v2 import stop_watchdog
        await stop_watchdog()
        logger.info("Heartbeat watchdog stopped on app shutdown")
except Exception:
    logger.warning("Heartbeat watchdog lifecycle registration failed", exc_info=True)

# CORS — restrict to localhost for Electron compatibility
# [v8.0] FIX: allow_credentials=True with "*" is invalid per CORS spec.
# Must use explicit origins when credentials are enabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:3000",
        "app://.",            # Electron renderer
        "file://",            # Electron file:// protocol
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# v7.1 — structured error handlers
try:
    from error_handlers import register_exception_handlers
    register_exception_handlers(app)
except ImportError:
    pass

# ==================== CSRF Protection (v8.0+) ====================
import secrets as _secrets_csrf
import hmac as _hmac_csrf
import time as _time_csrf

CSRF_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_EXEMPT_PATHS = frozenset({"/health", "/auth/qrcode", "/api/csrf-token", "/cookies/save", "/auth/qrcode/poll", "/auth/qrcode/poll/{qrcode_key}", "/api/rag/ask", "/api/rag/save", "/api/settings", "/api/chat/stream", "/api/export/ai-notes", "/api/export/zip", "/api/export/docx", "/api/feedback", "/api/errors/report", "/api/favorites/import-video", "/css/", "/js/", "/frontend/", "/api/favorites/sync", "/api/favorites/clean-invalid", "/api/kb/append", "/api/kb/delete", "/api/kb/classify-and-tag", "/api/kb/classify-batch", "/api/kb/push-obsidian", "/api/kb/init-obsidian", "/api/history/"})
CSRF_TOKEN_BYTES = 32
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_NAME = "bilisum_csrf"

_csrf_tokens: dict[str, float] = {}
_csrf_lock = asyncio.Lock()

async def _generate_csrf_token_async() -> str:
    async with _csrf_lock:
        token = _secrets_csrf.token_hex(CSRF_TOKEN_BYTES)
        _csrf_tokens.pop(token, None)
        # Clean expired tokens
        now = _time_csrf.time()
        expired = [t for t, exp in _csrf_tokens.items() if exp < now]
        for t in expired:
            _csrf_tokens.pop(t, None)
        return token

async def _validate_csrf_token_async(token: str) -> bool:
    async with _csrf_lock:
        if not token or len(token) != CSRF_TOKEN_BYTES * 2:
            return False
        expiry = _csrf_tokens.get(token)
        if expiry is None:
            return False
        if expiry < _time_csrf.time():
            _csrf_tokens.pop(token, None)
            return False
        _csrf_tokens.pop(token, None)
        return True

# [Sprint 5] Sync wrappers removed — all callers use await on async functions.
# These aliases returned coroutines instead of values when called without await.

@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    # [Sprint 5] Request timing + structured logging
    import time
    import uuid
    request.state.trace_id = uuid.uuid4().hex[:12]
    request.state.start_time = time.time()
    logger.info(f"--> {request.method} {request.url.path} [trace={request.state.trace_id}]")
    response = await call_next(request)
    elapsed = int((time.time() - request.state.start_time) * 1000)
    logger.info(f"<-- {request.method} {request.url.path} {elapsed}ms [trace={request.state.trace_id}]")
    return response

@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if any(request.url.path.startswith(p) for p in CSRF_EXEMPT_PATHS):
        return await call_next(request)

    if request.method in CSRF_SAFE_METHODS:
        response = await call_next(request)
        if CSRF_COOKIE_NAME not in request.cookies:
            _path = request.url.path.lower()
            if _path.endswith(('.css', '.js', '.png', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.map')):
                return response
            token = await _generate_csrf_token_async()
            response.set_cookie(
                key=CSRF_COOKIE_NAME, value=token,
                httponly=False, samesite="strict", secure=False,
                path="/", max_age=86400,
            )
        return response



    header_token = request.headers.get(CSRF_HEADER_NAME, "")
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME, "")

    if not header_token or not cookie_token:
        return JSONResponse(
            {"success": False, "error": "CSRF token missing", "code": "CSRF_MISSING"},
            status_code=403
        )
    if not _hmac_csrf.compare_digest(header_token, cookie_token):
        return JSONResponse(
            {"success": False, "error": "CSRF token mismatch", "code": "CSRF_MISMATCH"},
            status_code=403
        )
    if not await _validate_csrf_token_async(header_token):
        return JSONResponse(
            {"success": False, "error": "CSRF token expired", "code": "CSRF_EXPIRED"},
            status_code=403
        )

    return await call_next(request)


@app.get("/api/csrf-token")
async def get_csrf_token():
    token = await _generate_csrf_token_async()
    response = JSONResponse({"success": True, "token": token})
    response.set_cookie(
        key=CSRF_COOKIE_NAME, value=token,
        httponly=False, samesite="strict", secure=False,
        path="/", max_age=86400,
    )
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from constants import COOKIE_FILE, FRONTEND_DIR

# Load cookies on startup
try:
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            cookie = f.read().strip()
            if cookie:
                set_cookie(cookie)
except Exception:
    logger.warning("Failed to load cookies on startup", exc_info=True)


# ==================== Static Files ====================

FRONTEND_PAGES = ["browse.html", "summary.html", "kb.html", "tools.html", "favorites.html", "categories.html", "multi-platform.html", "index.html"]

@app.get("/health")
async def health_check():
    """增强健康检查 — 验证所有后端服务 (v8.1: adds actual HTTP B站 probe + disk space)"""
    checks = {
        "status": "ok",
        "service": "BiliSum",
        "version": "8.1",
        "checks": {},
        "timestamp": datetime.now().isoformat()
    }
    # Check 1: Database
    try:
        conn = db.get_db()
        conn.execute("SELECT 1")
        conn.execute("SELECT count(*) FROM history")
        checks["checks"]["database"] = "ok"
    except Exception as e:
        checks["checks"]["database"] = f"error: {str(e)[:100]}"
        checks["status"] = "degraded"
    # Check 2: B站 API actual HTTP reachability (replaces DNS-only check)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://api.bilibili.com/x/web-interface/popular?pn=1&ps=1",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if r.status_code == 200 and r.json().get("code") == 0:
                checks["checks"]["bilibili_api"] = f"ok ({r.elapsed.total_seconds():.1f}s)"
            else:
                checks["checks"]["bilibili_api"] = f"degraded (HTTP {r.status_code}, code={r.json().get('code')})"
                checks["status"] = "degraded"
    except Exception as e:
        checks["checks"]["bilibili_api"] = f"unreachable: {str(e)[:60]}"
        checks["status"] = "degraded"
    # Check 3: RAG / ChromaDB
    try:
        svc = get_rag_service()
        checks["checks"]["rag_service"] = "ok" if svc and svc.vector_store else "degraded"
    except Exception as e:
        checks["checks"]["rag_service"] = f"error: {str(e)[:100]}"
        checks["status"] = "degraded"
    # Check 4: KB directory + disk space
    kb_dir = db.KB_DIR
    if os.path.isdir(kb_dir):
        import shutil
        try:
            free_gb = shutil.disk_usage(kb_dir).free / (1024**3)
            if free_gb < 0.1:
                checks["checks"]["kb_directory"] = f"ok, low disk ({free_gb:.1f}GB free)"
                checks["status"] = "degraded"
            else:
                checks["checks"]["kb_directory"] = f"ok ({free_gb:.1f}GB free)"
        except Exception:
            checks["checks"]["kb_directory"] = "ok (disk space unknown)"
    else:
        checks["checks"]["kb_directory"] = "missing"
        checks["status"] = "degraded"
    # Check 5: AI API key configured
    api_key = db.get_setting("api_key", "")
    checks["checks"]["ai_api"] = "configured" if len(api_key) > 4 else "not configured"
    if len(api_key) <= 4:
        checks["status"] = "degraded"
    return JSONResponse(checks)

@app.get("/health/live")
async def health_live():
    """Liveness probe — minimal check for container orchestration."""
    return JSONResponse({"status": "alive", "timestamp": datetime.now().isoformat()})

@app.get("/ready")
async def readiness():
    """就绪探针 — 仅当所有服务就绪时返回 200"""
    try:
        db.get_db().execute("SELECT 1")
        return JSONResponse({"ready": True})
    except Exception:
        return JSONResponse({"ready": False}, status_code=503)

@app.get("/api/cost/dashboard")
async def api_cost_dashboard():
    """AI 成本追踪仪表板 (v7.1)"""
    try:
        from cost_tracker import get_cost_tracker, MODEL_PRICING
        return JSONResponse({
            "success": True,
            "data": get_cost_tracker().get_dashboard(),
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.post("/api/feedback")
async def api_feedback(request: Request):
    """Submit user feedback (v7.1)"""
    try:
        from feedback_collector import FeedbackCollector
        body = await request.json()
        collector = FeedbackCollector()
        collector.record(body.get("type", "general"), body.get("data", {}), body.get("rating", 0))
        return JSONResponse({"success": True})
    except ImportError:
        return JSONResponse({"success": False, "error": "Feedback module not loaded"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})



async def _call_llm_with_retry(api_url, api_key, model, messages, max_retries=3):
    """带指数退避重试的 LLM 调用"""
    is_anthropic = "anthropic.com" in api_url
    last_error = None
    for attempt in range(max_retries):
        try:
            if is_anthropic:
                async with httpx.AsyncClient(timeout=180) as client:
                    r = await client.post(api_url,
                        headers={"x-api-key":api_key,"anthropic-version":"2023-06-01","Content-Type":"application/json"},
                        json={"model":model,"max_tokens":4096,"messages":messages})
                    if r.status_code == 200:
                        content_blocks = r.json().get("content", [])
                        text_blocks = [b for b in content_blocks if b.get("type") == "text"]
                        if not text_blocks:
                            return {"success": False, "error": "No text block in Anthropic response"}
                        return {"success": True, "text": text_blocks[0]["text"]}
                    elif r.status_code in (429, 503, 502):
                        last_error = f"Rate limited ({r.status_code})"
                    else:
                        return {"success": False, "error": r.json().get("error",{}).get("message",f"API {r.status_code}")}
            else:
                async with httpx.AsyncClient(timeout=180) as client:
                    r = await client.post(f"{api_url}/chat/completions",
                        headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
                        json={"model":model,"messages":messages,"max_tokens":4096})
                    if r.status_code == 200:
                        return {"success": True, "text": r.json()["choices"][0]["message"]["content"]}
                    elif r.status_code in (429, 503, 502):
                        last_error = f"Rate limited ({r.status_code})"
                    else:
                        err = r.json().get("error",{})
                        return {"success": False, "error": err.get("message",f"API {r.status_code}")}
        except Exception as e:
            last_error = str(e)
        if attempt < max_retries - 1:
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    return {"success": False, "error": last_error or "Max retries exceeded"}

def clean_chinese_text(text: str) -> str:
    """DEPRECATED: Use text_utils.clean_chinese_text instead.

    This wrapper is kept for backward compatibility.
    """
    from text_utils import clean_chinese_text as _clean
    return _clean(text)


# ==================== Startup ====================

if __name__ == "__main__":
    import uvicorn
    print("READY|http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)

