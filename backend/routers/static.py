"""
Router: Static pages, health check, CSS/JS serving
Extracted from main.py for maintainability
"""
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response

router = APIRouter(tags=["static"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
FRONTEND_PAGES = ["browse.html", "summary.html", "kb.html", "tools.html", "favorites.html", "categories.html", "multi-platform.html", "upload.html", "index.html"]


def _safe_path(base: str, filename: str) -> str:
    """Resolve and validate a path stays within base directory (path traversal protection)."""
    resolved = os.path.normpath(os.path.join(base, os.path.basename(filename)))
    expected_prefix = os.path.normpath(base) + os.sep
    # Windows: normalize case to prevent case-sensitivity bypass
    if not os.path.normcase(resolved).startswith(os.path.normcase(expected_prefix)):
        raise ValueError("Path traversal denied")
    return resolved


def serve_page(filename):
    """Serve an HTML page with path traversal protection."""
    try:
        filepath = _safe_path(FRONTEND_DIR, filename)
    except ValueError:
        return HTMLResponse("<h1>Forbidden</h1>", status_code=403)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse(f"<h1>{filename} not found</h1>", status_code=404)


# /health is defined in main.py (enhanced v7.1 with DB/RAG/B站 API checks)


@router.get("/")
async def serve_index():
    return serve_page("browse.html")


@router.get("/frontend/{filename}")
async def serve_frontend(filename: str):
    safe_name = os.path.basename(filename)
    if safe_name not in FRONTEND_PAGES:
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    return serve_page(safe_name)


@router.get("/browse")
async def serve_browse(): return serve_page("browse.html")

@router.get("/summary")
async def serve_summary(): return serve_page("summary.html")

@router.get("/kb")
async def serve_kb(): return serve_page("kb.html")

@router.get("/tools")
async def serve_tools(): return serve_page("tools.html")

@router.get("/favorites")
async def serve_favorites(): return serve_page("favorites.html")

@router.get("/categories")
async def serve_categories(): return serve_page("categories.html")

@router.get("/multi-platform")
async def serve_multi_platform(): return serve_page("multi-platform.html")

@router.get("/upload")
async def serve_upload(): return serve_page("upload.html")


@router.get("/css/{filename}")
async def serve_css(filename: str):
    try:
        filepath = _safe_path(os.path.join(FRONTEND_DIR, "css"), filename)
    except ValueError:
        return HTMLResponse("", status_code=404)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return Response(f.read(), media_type="text/css; charset=utf-8")
    return HTMLResponse("", status_code=404)


@router.get("/js/{filename}")
async def serve_js(filename: str):
    try:
        filepath = _safe_path(os.path.join(FRONTEND_DIR, "js"), filename)
    except ValueError:
        return HTMLResponse("", status_code=404)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return Response(f.read(), media_type="application/javascript; charset=utf-8")
    return HTMLResponse("", status_code=404)


@router.get("/sw.js")
async def serve_sw():
    """Service Worker — MUST be served from root so it controls the whole /bili/proxy scope."""
    sw_path = os.path.join(FRONTEND_DIR, "sw.js")
    if os.path.exists(sw_path):
        with open(sw_path, "r", encoding="utf-8") as f:
            return Response(f.read(), media_type="application/javascript; charset=utf-8")
    return HTMLResponse("", status_code=404)
