"""
BiliSum Favorites Router - B站 favorites sync, import, clean
"""
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
import httpx, uuid, asyncio, os, logging
import json as _json
from constants import COOKIE_FILE

router = APIRouter()

_fav_sync_tasks = {}

# Configurable total cap per sync to prevent runaway imports
MAX_VIDEOS_PER_SYNC = 500

async def _do_sync(task_id: str, folder_ids: list):
    _fav_sync_tasks[task_id] = {
        "status": "running", "folder_ids": folder_ids, "videos_synced": 0,
        "total_videos": 0, "processed_videos": 0, "skipped_videos": 0,
        "progress": 0, "current_step": "正在获取收藏夹列表...",
        "current_video_title": "", "message": "",
    }
    total = 0
    try:
        from bilibili_client import get_all_favorite_videos, get_video_info, get_full_subtitle
        import database as _db
        # First pass: count total videos across all selected folders
        all_videos = []
        for fid in folder_ids:
            _fav_sync_tasks[task_id]["current_step"] = f"正在获取收藏夹 {fid} 的视频列表..."
            videos = await get_all_favorite_videos(int(fid))
            all_videos.extend([(fid, v) for v in videos])
            if len(all_videos) >= MAX_VIDEOS_PER_SYNC:
                all_videos = all_videos[:MAX_VIDEOS_PER_SYNC]
                break
        _fav_sync_tasks[task_id]["total_videos"] = len(all_videos)
        # v8.5: Skip already-imported videos (KB-level dedup)
        existing_bvids = {e["bvid"] for e in _db.get_kb_list()}
        to_process = [(fid, v) for fid, v in all_videos if v.get("bvid", "") not in existing_bvids]
        skipped = len(all_videos) - len(to_process)
        _fav_sync_tasks[task_id]["skipped_videos"] = skipped
        if not all_videos:
            _fav_sync_tasks[task_id]["status"] = "completed"
            _fav_sync_tasks[task_id]["progress"] = 100
            _fav_sync_tasks[task_id]["current_step"] = "导入完成"
            _fav_sync_tasks[task_id]["message"] = "未获取到任何视频。可能原因：1) 未登录B站 2) 收藏夹为空 3) 收藏夹隐私设置。请检查设置页扫码登录。"
            _fav_sync_tasks[task_id]["videos_synced"] = 0
            return
        _fav_sync_tasks[task_id]["current_step"] = f"跳过 {skipped} 个已导入, 剩余 {len(to_process)} 个" if skipped else f"共 {len(to_process)} 个视频，开始导入..."

        for fid, v in to_process:
            bvid = v.get("bvid", "")
            if not bvid:
                total += 1
                _fav_sync_tasks[task_id]["processed_videos"] = total
                _fav_sync_tasks[task_id]["progress"] = int(total / max(len(to_process), 1) * 100)
                continue
            # v8.5: Per-video ChromaDB skip (already vectorized but KB entry missing edge case)
            try:
                from main import get_rag_service
                rag = get_rag_service()
                if rag and rag.has_video(bvid):
                    skipped += 1
                    total += 1
                    _fav_sync_tasks[task_id]["skipped_videos"] = skipped
                    _fav_sync_tasks[task_id]["processed_videos"] = total
                    _fav_sync_tasks[task_id]["progress"] = int(total / max(len(to_process), 1) * 100)
                    continue
            except Exception:
                pass
            try:
                _fav_sync_tasks[task_id]["current_video_title"] = v.get("title", bvid)
                _fav_sync_tasks[task_id]["current_step"] = f"正在导入: {v.get('title', bvid)[:40]}..."
                info = await get_video_info(bvid)
                sub = await get_full_subtitle(bvid)
                text = sub.text if sub and sub.text else ""
                if not text or len(text) < 20:
                    text = "[" + str(info.title) + "]\n" + str(info.desc or "") + "\nUP: " + str(info.owner_name)
                _db.save_kb_entry(bvid=bvid, title=info.title, author=info.owner_name, pic=info.pic, text=text, source="favorites",
                    desc=info.desc or "", duration=info.duration or 0, pubdate=info.pubdate or "",
                    tags=info.tags or "", tname=info.tname or "",
                    stat=info.stat.model_dump() if info.stat else {}, owner_mid=info.owner_mid or 0)
                _db.save_chunks(bvid, info.title, text)
                # v8.4: Index into ChromaDB for RAG Q&A (previously only FTS5 was populated)
                try:
                    from main import get_rag_service
                    rag = get_rag_service()
                    if rag:
                        rag.add_video(bvid, info.title, text, info.owner_name or "", info.desc or "", info.duration or 0)
                except Exception as _rag_e:
                    logger.warning("ChromaDB index failed for %s (non-fatal): %s", bvid, _rag_e)
                # v8.5: Auto-classify on favorites import (previously only manual save did this)
                try:
                    from classifier import get_classifier
                    clf = get_classifier()
                    api_key = _db.get_setting("api_key", "")
                    clf_result = await clf.classify(
                        bvid=bvid, title=info.title, text=text,
                        duration_seconds=info.duration or 0, author=info.owner_name,
                        llm_api_key=api_key,
                        llm_api_url=_db.get_setting("api_url", ""),
                        llm_model=_db.get_setting("model", ""),
                    )
                    clf.persist_to_entry(bvid)
                except Exception as _cls_e:
                    logger.info("Auto-classify in favorites import failed (non-fatal): %s", _cls_e)
                total += 1
                _fav_sync_tasks[task_id]["videos_synced"] = total
                _fav_sync_tasks[task_id]["processed_videos"] = total
                _fav_sync_tasks[task_id]["progress"] = int(total / max(len(to_process), 1) * 100)
            except Exception:
                _fav_sync_tasks[task_id]["current_step"] = f"导入失败: {v.get('title', bvid)[:40]}，跳过..."
            await asyncio.sleep(0.2)
        _fav_sync_tasks[task_id]["status"] = "completed"
        _fav_sync_tasks[task_id]["progress"] = 100
        _fav_sync_tasks[task_id]["current_step"] = "导入完成"
        _fav_sync_tasks[task_id]["message"] = f"成功导入 {total - skipped} 个视频" + (f"，跳过 {skipped} 个已导入" if skipped else "")
    except Exception as e:
        _fav_sync_tasks[task_id]["status"] = "error"
        _fav_sync_tasks[task_id]["error"] = str(e)
        _fav_sync_tasks[task_id]["message"] = f"导入中断: {str(e)}"
    _fav_sync_tasks[task_id]["videos_synced"] = total

logger = logging.getLogger("bilisum.favorites")

def _get_bili_headers():
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36","Referer":"https://www.bilibili.com/"}
    # Priority: in-memory cookie from bilibili_client (set via /auth endpoints), then file cookie
    try:
        from bilibili_client import _get_headers as _bili_h
        _hdr = _bili_h()
        if _hdr.get("Cookie"): headers["Cookie"] = _hdr["Cookie"]
    except Exception:
        logger.debug("bilibili_client._get_headers not available", exc_info=True)
    # Fallback: cookie file if in-memory is empty
    if not headers.get("Cookie"):
        try:
            if os.path.exists(COOKIE_FILE):
                with open(COOKIE_FILE,"r",encoding="utf-8") as f:
                    ck = f.read().strip()
                    if ck: headers["Cookie"] = ck
        except Exception:
            logger.warning("Cookie file not readable", exc_info=True)
    return headers

@router.get("/api/v2/favorites/nav")
async def api_favorites_nav():
    try:
        headers = _get_bili_headers()
        has_cookie = bool(headers.get("Cookie", "").strip())
        logger.info("favorites_nav: has_cookie=%s", has_cookie)
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get("https://api.bilibili.com/x/web-interface/nav", headers=headers)
            d = r.json()
            code = d.get("code")
            is_login = d.get("data", {}).get("isLogin") if code == 0 else False
            logger.info("favorites_nav: code=%s isLogin=%s", code, is_login)
            if code == 0 and is_login:
                return JSONResponse({"success":True,"data":{"isLogin":True,"mid":d["data"].get("mid",0),"uname":d["data"].get("uname",""),"face":d["data"].get("face","")}})
            return JSONResponse({"success":True,"data":{"isLogin":False}})
    except Exception as e:
        logger.error("favorites_nav exception: %s", e)
        return JSONResponse({"success":False,"error":str(e)})

@router.get("/api/v2/favorites/folders")
async def api_favorites_folders(mid: str = Query("")):
    try:
        if not mid: return JSONResponse({"success":False,"error":"no mid"})
        headers = _get_bili_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://api.bilibili.com/x/v3/fav/folder/created/list?up_mid={mid}&pn=1&ps=50", headers=headers)
            d = r.json()
            if d.get("code")!=0: return JSONResponse({"success":False,"error":d.get("message","")})
            folders = [{"id":f.get("id",0),"title":f.get("title",""),"media_count":f.get("media_count",0)} for f in d.get("data",{}).get("list",[])]
            return JSONResponse({"success":True,"data":{"folders":folders,"count":len(folders)}})
    except Exception as e:
        return JSONResponse({"success":False,"error":str(e)})

@router.get("/api/v2/favorites/videos")
async def api_favorites_videos(mediaId: str = Query(""), pn: int = Query(1)):
    try:
        if not mediaId: return JSONResponse({"success":False,"error":"no mediaId"})
        headers = _get_bili_headers()
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://api.bilibili.com/x/v3/fav/resource/list?media_id={mediaId}&pn={pn}&ps=20&platform=web", headers=headers)
            d = r.json()
            if d.get("code")!=0: return JSONResponse({"success":False,"error":d.get("message","")})
            medias = d.get("data",{}).get("medias",[])
            videos = [{"bvid":m.get("bvid",""),"title":m.get("title",""),"pic":m.get("cover",m.get("pic","")),"author":m.get("upper",{}).get("name",m.get("author","")),"duration":m.get("duration",0)} for m in medias]
            return JSONResponse({"success":True,"data":{"videos":videos,"count":len(videos),"has_more":d.get("data",{}).get("has_more",False)}})
    except Exception as e:
        return JSONResponse({"success":False,"error":str(e)})

@router.post("/api/favorites/clean-invalid")
async def api_clean_invalid(request: Request):
    try:
        body = await request.json()
        media_id = body.get("mediaId","")
        headers = _get_bili_headers()
        jct = ""
        for pair in headers.get("Cookie","").split(";"):
            pair = pair.strip()
            if pair.startswith("bili_jct="):
                jct = pair.split("bili_jct=",1)[1].strip()
                break
        if not jct: return JSONResponse({"success":False,"error":"Need login"})
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://api.bilibili.com/x/v3/fav/resource/clean", headers={**headers,"Content-Type":"application/x-www-form-urlencoded"}, data={"media_id":media_id,"csrf":jct})
            d = r.json()
            return JSONResponse({"success":d.get("code")==0,"data":d})
    except Exception as e:
        return JSONResponse({"success":False,"error":str(e)})


@router.get("/api/favorites/folder-videos")
async def api_folder_videos(mediaId: str = Query(""), all: str = Query("false")):
    try:
        if not mediaId: return JSONResponse({"success": False, "error": "no mediaId"})
        headers = _get_bili_headers()
        from bilibili_client import get_all_favorite_videos
        videos_list = await get_all_favorite_videos(int(mediaId))
        import database as _db_in
        for v in videos_list:
            entry = _db_in.get_kb_entry(v["bvid"])
            v["in_kb"] = entry is not None
            if entry:
                v["textLen"] = len(entry.get("text", "") or "")
                v["textLength"] = v["textLen"]
            # Normalize pic field: get_all_favorite_videos returns "cover", frontend uses "pic"
            if not v.get("pic") and v.get("cover"):
                v["pic"] = v["cover"]
        return JSONResponse({"success": True, "data": {"videos": videos_list, "count": len(videos_list)}})
    except Exception as e:
        return JSONResponse({"success": False, "error": "操作失败，请稍后重试"})

@router.post("/api/favorites/sync")
async def api_favorites_sync(request: Request):
    try:
        body = await request.json()
        folder_ids = body.get("folder_ids", [])
        task_id = str(uuid.uuid4())
        asyncio.create_task(_do_sync(task_id, folder_ids))
        return JSONResponse({"success": True, "data": {"task_id": task_id, "syncing": True}})
    except Exception as e:
        return JSONResponse({"success": False, "error": "操作失败，请稍后重试"})

@router.get("/api/favorites/sync/status/{task_id}")
async def api_sync_status(task_id: str):
    task = _fav_sync_tasks.get(task_id, {"status": "not_found"})
    return JSONResponse({"success": True, "data": task})

@router.post("/api/favorites/import-video")
async def api_favorites_import(request: Request):
    try:
        body = await request.json()
        bvid = body.get("bvid", "").strip()
        sources = body.get("sources", ["subtitle"])  # [P1-07] multi-source
        if not bvid:
            return JSONResponse({"success": False, "error": "missing bvid"})
        from bilibili_client import get_video_info, get_full_subtitle, get_comments, get_danmaku
        import database as _db2
        info = await get_video_info(bvid)
        parts = []
        if "subtitle" in sources:
            sub = await get_full_subtitle(bvid)
            t = sub.text if sub and sub.text else ""
            if t and len(t) >= 20:
                parts.append(t)
        if "comment" in sources:
            comments = await get_comments(bvid)
            if comments:
                parts.append("\n".join(f"[{c.user}] {c.content}" for c in comments[:30]))
        if "danmaku" in sources:
            dm = await get_danmaku(info.cid, info.duration or 0, info.owner_mid)
            if dm:
                parts.append("??:\n" + "\n".join(dm[:50]))
        text = "\n\n".join(parts) if parts else ""
        if not text or len(text) < 20:
            text = "[" + str(info.title) + "]\n" + str(info.desc or "") + "\nUP: " + str(info.owner_name)
        _db2.save_kb_entry(bvid=bvid, title=info.title, author=info.owner_name, pic=info.pic, text=text, source="favorites",
            desc=info.desc or "", duration=info.duration or 0, pubdate=info.pubdate or "",
            tags=info.tags or "", tname=info.tname or "",
            stat=info.stat.model_dump() if info.stat else {}, owner_mid=info.owner_mid or 0)
        _db2.save_chunks(bvid, info.title, text)
        # v8.4: Index into ChromaDB for RAG Q&A
        try:
            from main import get_rag_service as _get_rag
            _rag = _get_rag()
            if _rag:
                _rag.add_video(bvid, info.title, text, info.owner_name or "", info.desc or "", info.duration or 0)
        except Exception as _rag_e:
            logger.warning("ChromaDB index failed for %s (non-fatal): %s", bvid, _rag_e)
        # v8.5: Auto-classify on favorites import
        try:
            from classifier import get_classifier
            clf_single = get_classifier()
            _api_key = _db2.get_setting("api_key", "")
            await clf_single.classify(
                bvid=bvid, title=info.title, text=text,
                duration_seconds=info.duration or 0, author=info.owner_name,
                llm_api_key=_api_key,
                llm_api_url=_db2.get_setting("api_url", ""),
                llm_model=_db2.get_setting("model", ""),
            )
            clf_single.persist_to_entry(bvid)
        except Exception as _cls_e:
            logger.info("Auto-classify in favorites import failed (non-fatal): %s", _cls_e)
        return JSONResponse({"success": True, "data": {"bvid": bvid, "title": info.title, "textLen": len(text)}})
    except Exception as e:
        return JSONResponse({"success": False, "error": "操作失败，请稍后重试"})
