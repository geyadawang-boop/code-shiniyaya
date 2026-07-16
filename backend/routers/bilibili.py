"""
Router: B站 video info, search, popular, audio, download, multipart, count
"""
import os
import re
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from bilibili_client import (
    get_video_info, search_videos, get_popular_videos, get_video_parts,
    get_audio_url, get_full_subtitle, extract_bvid, get_danmaku
)

router = APIRouter(prefix="/api", tags=["bili"])


@router.get("/danmaku")
async def api_danmaku(bvid: str = Query("")):
    try:
        info = await get_video_info(bvid)
        dm = await get_danmaku(info.cid, info.duration or 0, info.owner_mid)
        return JSONResponse({"success": True, "data": {"danmaku": dm, "count": len(dm)}})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@router.get("/bili/info")
async def api_video_info(bvid: str = Query(...)):
    try:
        bvid = extract_bvid(bvid)
        info = await get_video_info(bvid)
        return JSONResponse({"success": True, "data": {
            "title": info.title, "author": info.owner_name, "pic": info.pic,
            "desc": info.desc, "duration": info.duration, "bvid": info.bvid,
            "aid": info.aid, "cid": info.cid, "videos_count": info.videos_count,
            "tname": info.tname, "tags": info.tags, "pubdate": info.pubdate,
            "stat": {
                "view": info.stat.view,
                "danmaku": info.stat.danmaku,
                "reply": info.stat.reply,
                "favorite": info.stat.favorite,
                "coin": info.stat.coin,
                "share": info.stat.share,
                "like": info.stat.like,
                "now_rank": info.stat.now_rank,
            }
        }})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/bili/search")
async def api_search(keyword: str = Query(...)):
    try:
        data = await search_videos(keyword)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"code": -1, "message": str(e)})


@router.get("/bili/popular")
async def api_popular(pn: int = Query(1), ps: int = Query(50)):
    try:
        import urllib.parse
        from wbi import sign_params
        from bilibili_client import _get_client, _get_headers
        client = await _get_client()
        params = await sign_params({"pn": str(pn), "ps": str(ps)})
        query = urllib.parse.urlencode(params)
        r = await client.get(
            f"https://api.bilibili.com/x/web-interface/popular?{query}",
            headers=_get_headers()
        )
        return JSONResponse(r.json())
    except Exception:
        data = await get_popular_videos()
        return JSONResponse(data)


@router.get("/bili/audio")
async def api_audio(bvid: str = Query(...)):
    try:
        bvid = extract_bvid(bvid)
        data = await get_audio_url(bvid)
        return JSONResponse({"success": True, "data": data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/video/download/{bvid}")
async def api_download_video(bvid: str):
    try:
        import subprocess
        import database as db
        bvid = extract_bvid(bvid)
        # Fetch title for human-readable folder name
        info = await get_video_info(bvid)
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', (info.title or bvid))[:60].rstrip('. ')
        folder_name = f"{safe_title}_{bvid}" if safe_title else bvid
        # Bug 2/3 fix: use configured download_dir (default {project}/downloads)
        download_root = db.get_setting("download_dir", "") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "downloads")
        outdir = os.path.join(download_root, folder_name)
        os.makedirs(outdir, exist_ok=True)
        cmd = ["yt-dlp", "--write-subs", "--write-auto-subs", "--sub-langs", "zh,en",
               "-o", f"{outdir}/%(title)s.%(ext)s", f"https://www.bilibili.com/video/{bvid}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return JSONResponse({"success": True, "data": {"output": result.stdout[-500:], "dir": outdir}})
    except subprocess.TimeoutExpired:
        return JSONResponse({"success": False, "error": "Download timed out"})
    except FileNotFoundError:
        return JSONResponse({"success": False, "error": "yt-dlp not installed"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/v2/multipart/{bvid}")
async def api_multipart_content(bvid: str):
    try:
        bvid = extract_bvid(bvid)
        parts = await get_video_parts(bvid)
        if len(parts) <= 1:
            return JSONResponse({"success": True, "data": {"is_multipart": False, "parts": []}})
        results = []
        for p in parts:
            cid = p.get("cid", 0)
            title = p.get("part", f"P{p.get('page', '?')}")
            text = ""
            try:
                # get_full_subtitle uses the first page's cid internally;
                # per-part cid is available as p["cid"] if we extend bilibili_client
                sub = await get_full_subtitle(bvid)
                if sub.body:
                    text = " ".join([x.content for x in sub.body[:100]])
            except Exception as e:
                logger.debug("Multi-P subtitle fetch failed for part %s: %s", p.get('cid', '?'), e)
            results.append({"cid": cid, "title": title, "duration": p.get("duration", 0), "has_content": len(text) > 10})
        return JSONResponse({"success": True, "data": {"is_multipart": True, "count": len(parts), "parts": results}})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/v2/count")
async def api_v2_count():
    import database as db
    kb = db.get_kb_stats()
    return JSONResponse({"success": True, "data": {"kb_videos": kb.get("totalVideos", 0), "kb_chunks": kb.get("totalChunks", 0)}})
