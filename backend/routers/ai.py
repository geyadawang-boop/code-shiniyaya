"""
Router: AI Summary, segments, QA, subtitle endpoints
"""
import re
import os
import asyncio
import time as _time
import json
import logging
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from summarizer import summarize_with_claude, summarize_segments, _sanitize_llm_field, _wrap_field
from bilibili_client import get_video_info, get_full_subtitle, get_full_subtitle_multi, get_comments, extract_bvid, get_danmaku
import database as db

from constants import DEFAULT_MODEL, DEFAULT_DEEPSEEK_MODEL, DEFAULT_DEEPSEEK_URL, FRAMES_CACHE_DIR

router = APIRouter(prefix="/api", tags=["ai"])
logger = logging.getLogger("bilisum.ai")


def _safe_error(exc: Exception, max_len: int = 200) -> str:
    """Extract a safe, non-sensitive error message from an exception.
    Redacts API keys, auth tokens, and internal file-system paths."""
    import re as _re2
    msg = str(exc)
    # Redact API key patterns
    msg = _re2.sub(r'sk-[a-zA-Z0-9]{20,}', '[API_KEY]', msg)
    msg = _re2.sub(r'Bearer\s+[a-zA-Z0-9._\-]+', 'Bearer [TOKEN]', msg)
    msg = _re2.sub(r'(?:api_key|apikey|secret|token|password|passwd)\s*[=:]\s*\S+',
                   r'\1=[SECRET]', msg)
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    return msg


async def _oracle_enrich_summary(
    info, subtitle, comments, summary: str, stat_data: dict, config: "OracleConfig",
) -> dict:
    """Run oracle verification and enrichment on a summary. Non-blocking wrapper."""
    try:
        from oracle import oracle_quick_check
        oracle_report = await oracle_quick_check(
            summary=summary, info=info, subtitle=subtitle, config=config,
        )
        return oracle_report
    except Exception:
        return None


_VIDEO_EXTS = (".mp4", ".mkv", ".flv", ".webm", ".m4v", ".mov")


def _first_video_in(folder: str) -> str:
    """Return the first video file inside folder (deterministic order), or ""."""
    if not os.path.isdir(folder):
        return ""
    for f in sorted(os.listdir(folder)):
        if f.lower().endswith(_VIDEO_EXTS):
            return os.path.join(folder, f)
    return ""


def _find_downloaded_video(bvid: str) -> str:
    """Return a video already downloaded for bvid via /api/video/download.

    Mirrors the layout written by routers/bilibili.py (download_root/{title}_{bvid}/)
    and the matcher used by database.delete_kb_entry (entry == bvid or entry
    endswith _{bvid}). Returns "" if nothing is found.
    """
    download_root = db.get_setting("download_dir", "") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "downloads")
    if not os.path.isdir(download_root):
        return ""
    for entry in sorted(os.listdir(download_root)):
        if entry != bvid and not entry.endswith(f"_{bvid}"):
            continue
        found = _first_video_in(os.path.join(download_root, entry))
        if found:
            return found
    return ""


def _get_shared_video(bvid: str) -> str:
    """Shared download: resolve a local video file for bvid without re-downloading.

    Resolution order:
      1. User's download_dir (full download from /api/video/download — reused, never touched)
      2. frames_cache hit (data/frames_cache/{bvid}/ — persisted across summarize calls)
      3. yt-dlp 720p download into frames_cache (cleaned up by database.delete_kb_entry)

    Blocking (subprocess.run) — call via run_in_executor. Returns "" on any failure.
    """
    import subprocess, shutil

    existing = _find_downloaded_video(bvid)
    if existing:
        return existing

    cache_dir = os.path.join(FRAMES_CACHE_DIR, bvid)
    cached = _first_video_in(cache_dir)
    if cached:
        return cached

    os.makedirs(cache_dir, exist_ok=True)
    cmd = [
        "yt-dlp", "--no-playlist", "-f", "best[height<=720]",
        "--no-warnings", "-o", f"{cache_dir}/%(id)s.%(ext)s",
        f"https://www.bilibili.com/video/{bvid}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("yt-dlp unavailable or timed out for shared download: %s", e)
        shutil.rmtree(cache_dir, ignore_errors=True)
        return ""
    if result.returncode != 0:
        logger.warning("yt-dlp download failed for visual context: %s",
                       result.stderr[:200] if result.stderr else "unknown error")
        shutil.rmtree(cache_dir, ignore_errors=True)
        return ""
    found = _first_video_in(cache_dir)
    if not found:
        logger.warning("No video file found after yt-dlp download")
        shutil.rmtree(cache_dir, ignore_errors=True)
        return ""
    return found


async def _build_visual_context(bvid: str, title: str, duration_sec: int, logger) -> tuple:
    """Extract keyframes and build AI visual context via FrameExtractor + VisualReferenceBuilder.

    Only activates for videos >= 2 minutes. Resolves the video through _get_shared_video
    (download_dir reuse -> frames_cache hit -> one-time 720p download into frames_cache),
    extracts 3-5 keyframes, detects scene boundaries, and renders a prompt-ready
    visual context block. The cached video is removed by database.delete_kb_entry.

    Returns (visual_context_text, frame_ocr_text):
      - visual_context_text: heuristic scene/keyframe block -> visual_context_text param
      - frame_ocr_text: timestamped vision descriptions from frame_text_service
        ("[MM:SS] desc" lines) -> ocr_text param of build_prompt
    Either element is "" on failure (visual analysis is best-effort, never blocks summarization).
    """
    if not bvid or (duration_sec or 0) < 120:
        return "", ""
    try:
        from frame_extractor import FrameExtractor
        from visual_reference import VisualReferenceBuilder

        loop = asyncio.get_event_loop()
        video_path = await loop.run_in_executor(None, _get_shared_video, bvid)
        if not video_path:
            return "", ""

        # v2.2: Frame text (vision timestamped descriptions) -> ocr_text param.
        # Best-effort: gated/failed extraction degrades to "" and never blocks.
        frame_text = ""
        try:
            from frame_text_service import extract_frame_text
            ft = await extract_frame_text(video_path, bvid, float(duration_sec or 0))
            if ft.gated_off:
                logger.info("Frame text gated off for %s: %s", bvid, ft.gate_reason)
            else:
                frame_text = ft.to_prompt_block()
                logger.info("Frame text built: %d blocks, %d chars (model=%s, cache_hit=%s)",
                            len(ft.text_blocks), len(frame_text), ft.model, ft.cache_hit)
        except Exception as fe:
            logger.warning("Frame text extraction failed (non-fatal): %s", fe)

        # Extract 3-5 keyframes + scene boundaries (frame images go to FrameExtractor's
        # own tempdir, removed on __exit__; the source video stays cached for reuse)
        with FrameExtractor(video_path=video_path) as extractor:
            keyframes = extractor.extract_keyframes(max_count=5)
            scene_boundaries = extractor.detect_scene_changes(
                threshold=0.35, max_scenes=5, pre_extract=False,
            )

        if not keyframes:
            logger.info("No keyframes extracted from video")
            return "", frame_text

        # Build visual context block
        builder = VisualReferenceBuilder(mode="heuristic")
        block = builder.build(
            keyframes=keyframes,
            scene_boundaries=scene_boundaries,
            video_title=title,
            duration_sec=float(duration_sec),
        )

        prompt_text = builder.render_to_prompt(block)
        logger.info("Visual context built: %d keyframes, %d scenes, %d chars",
                    len(keyframes), len(scene_boundaries), len(prompt_text))
        return prompt_text, frame_text
    except Exception as e:
        logger.warning("Visual context build failed (non-fatal): %s", e)
        return "", ""


@router.get("/summarize")
async def api_summarize(url: str = Query(...), mode: str = Query("detailed")):
    try:
        bvid = extract_bvid(url)
        info = await get_video_info(bvid)
        sub = await get_full_subtitle_multi(bvid)
        comments = await get_comments(bvid)
        danmaku = await get_danmaku(info.cid, info.duration or 0, info.owner_mid)

        api_key = db.get_setting("api_key", "")
        api_url = db.get_setting("api_url", "")
        api_model = db.get_setting("model", DEFAULT_MODEL)

        # Collect multi-part danmaku if video has multiple pages
        from quality import compute_quality_multiplier, compute_note_budget, assess_visual_dependency, clamp
        _stat = info.stat if hasattr(info, 'stat') and info.stat else None
        stat_data = {
            "view": _stat.view if _stat else 0,
            "like": _stat.like if _stat else 0,
            "favorite": _stat.favorite if _stat else 0,
            "coin": _stat.coin if _stat else 0,
            "reply": _stat.reply if _stat else 0,
            "danmaku": _stat.danmaku if _stat else 0,
            "share": _stat.share if _stat else 0,
            "pubdate": info.pubdate if hasattr(info, 'pubdate') else 0,
            "now": int(_time.time())
        }
        quality_result = compute_quality_multiplier(stat_data)
        quality_multiplier = quality_result["quality_multiplier"]
        duration_min = (info.duration or 0) / 60
        subtitle_len = len(sub.text) if sub and sub.text else 0
        # v8.4: compute dynamic content dimensions for summary length
        visual_risk = assess_visual_dependency(duration_min, subtitle_len)
        from summarizer import analyze_content
        analysis = analyze_content(info, sub, comments) if sub else {}
        # Information density: chars/min normalized
        info_density = clamp((subtitle_len / max(duration_min, 0.1)) / 2000, 0.6, 1.8)
        # Knowledge value: tech terms mapped to [0.7, 1.5]
        tech_terms = analysis.get("tech_terms", 0)
        knowledge_val = clamp(0.7 + tech_terms * 0.08, 0.7, 1.5) if tech_terms > 0 else 1.0
        # Difficulty factor: richness mapped to [0.7, 1.5]
        richness = analysis.get("richness", 0)
        difficulty = clamp(0.7 + richness * 0.1, 0.7, 1.5) if richness > 0 else 1.0
        # Visual richness: map risk level to multiplier (high=more visuals=deeper desc needed)
        visual_richness = {"high": 1.5, "medium": 1.2, "low": 1.0}.get(
            visual_risk.get("risk", "low"), 1.0)
        # New concept count: tech terms above threshold
        new_concepts = max(0, tech_terms - 3)
        note_budget = compute_note_budget(
            duration_minutes=duration_min, subtitle_chars=subtitle_len,
            comment_records=len(comments) if comments else 0,
            quality_multiplier=quality_multiplier,
            danmaku_count=len(danmaku) if danmaku else 0,
            information_density=info_density,
            knowledge_value=knowledge_val,
            difficulty_factor=difficulty,
            visual_richness=visual_richness,
            new_concept_count=new_concepts,
        )

        # ---- Quality Gate: auto-switch model on low-quality source ----
        from oracle import build_oracle_config_from_db, OracleConfig
        oracle_config = build_oracle_config_from_db(db)

        effective_model = api_model
        effective_url = api_url
        effective_api_key = api_key
        quality_gate_note = ""

        if oracle_config.enabled and oracle_config.quality_gate_enabled:
            from oracle import evaluate_quality_gate
            gate = evaluate_quality_gate(stat_data, duration_min, subtitle_len, oracle_config)
            quality_gate_note = gate["recommendation"]
            if gate.get("should_use_fallback_model"):
                effective_model = oracle_config.fallback_model
                effective_url = oracle_config.fallback_api_url
                effective_api_key = oracle_config.fallback_api_key or api_key
                quality_gate_note += (
                    f" [Switched to {effective_model} due to low source quality "
                    f"(multiplier={gate['quality_multiplier']:.2f}).]"
                )

        # ---- Build visual context from keyframes (best-effort, non-blocking) ----
        visual_context_text, frame_ocr_text = await _build_visual_context(
            bvid=bvid, title=info.title, duration_sec=info.duration or 0, logger=logger,
        )

        # ---- v2.3: 章节解析 (view_points → gap → slice, best-effort) ----
        chapters, chapter_source = [], "none"
        try:
            from chapter_service import resolve_chapters
            _ch = await resolve_chapters(
                bvid, cid=info.cid, duration=info.duration or 0,
                subtitle_body=sub.body if sub else None,
            )
            chapters, chapter_source = _ch["chapters"], _ch["source"]
            logger.info("[%s] chapters resolved: source=%s count=%d",
                        bvid, chapter_source, len(chapters))
        except Exception:
            logger.warning("chapter resolution failed (non-fatal)", exc_info=True)

        # ---- Primary summarization ----
        result = await summarize_with_claude(
            info=info, subtitle=sub, comments=comments,
            api_key=effective_api_key, api_url=effective_url, model=effective_model, mode=mode,
            max_tokens_recommendation=note_budget.get("max_tokens_recommendation"),
            danmaku=danmaku, visual_context_text=visual_context_text,
            ocr_text=frame_ocr_text,
            chapters=chapters, chapter_source=chapter_source,
        )

        # ---- Oracle Verification (async, non-blocking) ----
        oracle_report = None
        if oracle_config.enabled:
            oracle_report = await _oracle_enrich_summary(
                info=info, subtitle=sub, comments=comments,
                summary=result["summary"],
                stat_data=stat_data,
                config=oracle_config,
            )

        db.save_history(bvid=bvid, title=info.title, author=info.owner_name,
                        mode=mode, summary=result["summary"])

        response_data = {
            **result,
            "quality_gate": quality_gate_note or None,
            "quality_multiplier": round(quality_multiplier, 2),
            "chapters": chapters or None,
            "chapter_source": chapter_source,
        }
        if oracle_report:
            response_data["oracle"] = oracle_report

        return JSONResponse({"success": True, "data": response_data})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/segments")
async def api_segments(url: str = Query(...)):
    try:
        bvid = extract_bvid(url)
        sub = await get_full_subtitle(bvid)
        if not sub.body:
            return JSONResponse({"success": False, "error": "无字幕内容"})
        api_key = db.get_setting("api_key", "")
        api_url = db.get_setting("api_url", "")
        api_model = db.get_setting("model", DEFAULT_DEEPSEEK_MODEL)

        # v2.3: 章节边界分段 (official view_points 优先, best-effort)
        chapters = []
        try:
            from chapter_service import resolve_chapters
            info = await get_video_info(bvid)
            _ch = await resolve_chapters(
                bvid, cid=info.cid, duration=info.duration or 0, subtitle_body=sub.body,
            )
            chapters = _ch["chapters"]
        except Exception:
            logger.warning("segments: chapter resolution failed (non-fatal)", exc_info=True)

        result = await summarize_segments(sub, api_key, api_url, api_model, chapters=chapters)
        return JSONResponse({"success": True, "data": result})
    except Exception as e:
        logger.error("api_segments failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/qa")
async def api_qa(bvid: str = Query(""), url: str = Query(""), question: str = Query(...)):
    try:
        import httpx, asyncio
        bvid = extract_bvid(bvid or url)
        q = question.strip()
        if not q:
            return JSONResponse({"success": False, "error": "请输入问题"})

        api_key = db.get_setting("api_key", "")
        api_url = db.get_setting("api_url", DEFAULT_DEEPSEEK_URL)
        api_model = db.get_setting("model", DEFAULT_DEEPSEEK_MODEL)
        if not api_key:
            return JSONResponse({"success": False, "error": "请先配置API密钥"})

        text = ""
        kb_entry = db.get_kb_entry(bvid)
        if kb_entry:
            text = kb_entry.get("text", "")
        if not text or len(text) < 20:
            try:
                sub = await get_full_subtitle(bvid)
                if sub.body:
                    text = " ".join([x.content for x in sub.body])
            except Exception:
                logger.warning("Subtitle fetch failed for QA", exc_info=True)
        if not text or len(text) < 20:
            return JSONResponse({"success": False, "error": "无可用文字"})

        prompt = (
            "请根据以下字幕文字稿，用中文回答用户的问题。"
            "如果文字稿中不包含答案，请直接说明。\n\n"
            f"{_wrap_field('transcript', text[:8000])}\n\n"
            f"{_wrap_field('question', q)}"
        )
        # Use _call_llm_with_retry from unified_llm_client (avoids circular import from main)
        from unified_llm_client import call_llm_with_retry_v2 as _call_llm_with_retry
        result = await _call_llm_with_retry(api_url, api_key, api_model, [{"role": "user", "content": prompt}])
        if not result["success"]:
            return JSONResponse({"success": False, "error": result["error"]})
        return JSONResponse({"success": True, "data": {"answer": result["text"], "context": f"bvid={bvid}"}})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


# =====================================================================
# Oracle Verification Endpoints (full pipeline + quick check + stats)
# =====================================================================


@router.get("/summarize/oracle")
async def api_summarize_with_oracle(url: str = Query(...), mode: str = Query("detailed")):
    """Full Oracle pipeline: summarize → verify → correct → re-verify.

    When enabled, the oracle pipeline runs:
      1. Quality gate (auto-switch model if source quality < threshold)
      2. Oracle single-model verification (factuality/coherence/completeness)
      3. Cross-validation (3-model voting, if enabled)
      4. Confidence scoring (0-100)
      5. Auto-correction loop (up to 3 rounds of iterative refinement)
      6. Self-improvement pattern extraction

    Returns the FULL pipeline result including intermediate verification data.
    """
    try:
        bvid = extract_bvid(url)
        info = await get_video_info(bvid)
        sub = await get_full_subtitle_multi(bvid)
        comments = await get_comments(bvid)

        api_key = db.get_setting("api_key", "")
        api_url = db.get_setting("api_url", "")
        api_model = db.get_setting("model", DEFAULT_MODEL)

        from quality import compute_quality_multiplier, compute_note_budget, assess_visual_dependency, clamp
        from oracle import (
            oracle_pipeline, build_oracle_config_from_db, evaluate_quality_gate,
        )

        oracle_config = build_oracle_config_from_db(db)

        danmaku_oracle = await get_danmaku(info.cid, info.duration or 0, info.owner_mid)

        _stat2 = info.stat if hasattr(info, 'stat') and info.stat else None
        stat_data = {
            "view": _stat2.view if _stat2 else 0,
            "like": _stat2.like if _stat2 else 0,
            "favorite": _stat2.favorite if _stat2 else 0,
            "coin": _stat2.coin if _stat2 else 0,
            "reply": _stat2.reply if _stat2 else 0,
            "danmaku": _stat2.danmaku if _stat2 else 0,
            "share": _stat2.share if _stat2 else 0,
            "pubdate": info.pubdate if hasattr(info, 'pubdate') else 0,
            "now": int(_time.time()),
        }
        quality_result = compute_quality_multiplier(stat_data)
        quality_multiplier = quality_result["quality_multiplier"]
        duration_min = (info.duration or 0) / 60.0
        subtitle_len = len(sub.text) if sub and sub.text else 0

        # v8.4: compute dynamic content dimensions
        visual_risk = assess_visual_dependency(duration_min, subtitle_len)
        from summarizer import analyze_content
        analysis = analyze_content(info, sub, comments) if sub else {}
        info_density = clamp((subtitle_len / max(duration_min, 0.1)) / 2000, 0.6, 1.8)
        tech_terms = analysis.get("tech_terms", 0)
        knowledge_val = clamp(0.7 + tech_terms * 0.08, 0.7, 1.5) if tech_terms > 0 else 1.0
        richness = analysis.get("richness", 0)
        difficulty = clamp(0.7 + richness * 0.1, 0.7, 1.5) if richness > 0 else 1.0
        visual_richness = {"high": 1.5, "medium": 1.2, "low": 1.0}.get(
            visual_risk.get("risk", "low"), 1.0)
        new_concepts = max(0, tech_terms - 3)

        note_budget = compute_note_budget(
            duration_minutes=duration_min,
            subtitle_chars=subtitle_len,
            comment_records=len(comments) if comments else 0,
            quality_multiplier=quality_multiplier,
            danmaku_count=len(danmaku_oracle) if danmaku_oracle else 0,
            information_density=info_density,
            knowledge_value=knowledge_val,
            difficulty_factor=difficulty,
            visual_richness=visual_richness,
            new_concept_count=new_concepts,
        )

        # Quality gate: determine effective model
        gate = evaluate_quality_gate(stat_data, duration_min, subtitle_len, oracle_config)
        effective_model = api_model
        effective_url = api_url
        effective_api_key = api_key
        if gate.get("should_use_fallback_model"):
            effective_model = oracle_config.fallback_model
            effective_url = oracle_config.fallback_api_url
            effective_api_key = oracle_config.fallback_api_key or api_key

        # ---- Build visual context from keyframes (best-effort, non-blocking) ----
        visual_context_text, frame_ocr_text = await _build_visual_context(
            bvid=bvid, title=info.title, duration_sec=info.duration or 0, logger=logger,
        )

        # Step 1: Primary summarization
        raw_result = await summarize_with_claude(
            info=info, subtitle=sub, comments=comments,
            danmaku=danmaku_oracle,
            api_key=effective_api_key, api_url=effective_url, model=effective_model,
            mode=mode,
            max_tokens_recommendation=note_budget.get("max_tokens_recommendation"),
            visual_context_text=visual_context_text,
            ocr_text=frame_ocr_text,
        )

        # Step 2: Full Oracle pipeline
        verdict = await oracle_pipeline(
            info=info, subtitle=sub, comments=comments,
            initial_summary=raw_result["summary"],
            stat_data=stat_data, config=oracle_config,
        )

        db.save_history(
            bvid=bvid, title=info.title, author=info.owner_name,
            mode=mode, summary=verdict.final_summary or raw_result["summary"],
        )

        return JSONResponse({
            "success": True,
            "data": {
                "title": info.title,
                "author": info.owner_name,
                "mode": mode,
                "summary": verdict.final_summary or raw_result["summary"],
                "raw_summary": raw_result["summary"],
                "oracle": {
                    "verdict": verdict.verdict,
                    "confidence": verdict.confidence,
                    "refinement_rounds": verdict.refinement_rounds,
                    "cross_validation_agreement": verdict.cross_validation_agreement,
                    "dimensions": {
                        name: {
                            "score": d.score,
                            "issues": d.issues[:3],
                            "suggestions": d.suggestions[:3],
                        }
                        for name, d in verdict.dimensions.items()
                    },
                    "correction_log": verdict.correction_log,
                    "model_used": verdict.model_used,
                    "oracle_model_used": verdict.oracle_model_used,
                    "token_usage": verdict.token_usage,
                    "timestamp": verdict.timestamp,
                },
                "quality_gate": {
                    "quality_multiplier": round(quality_multiplier, 2),
                    "recommendation": gate["recommendation"],
                    "effective_model": effective_model,
                },
            },
        })
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/oracle/verify")
async def api_oracle_verify_only(url: str = Query(...)):
    """Verify an existing summary without regenerating.

    Fetches the last saved summary for this video and runs oracle verification.
    """
    try:
        bvid = extract_bvid(url)
        info = await get_video_info(bvid)
        sub = await get_full_subtitle(bvid)

        from oracle import oracle_quick_check, build_oracle_config_from_db
        oracle_config = build_oracle_config_from_db(db)

        # Find existing summary
        existing = db.get_history_for_bvid(bvid)
        if not existing:
            return JSONResponse({"success": False, "error": "No existing summary found for this video"})

        summary = existing[0].get("summary", "") if existing else ""
        if not summary:
            return JSONResponse({"success": False, "error": "Existing summary is empty"})

        oracle_report = await oracle_quick_check(
            summary=summary, info=info, subtitle=sub, config=oracle_config,
        )
        return JSONResponse({"success": True, "data": oracle_report})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/oracle/correction-log")
async def api_oracle_correction_log(bvid: str = Query(""), limit: int = Query(20)):
    """Retrieve oracle correction logs for self-improvement analysis.

    Cross-leverage with self-improving-agent:
      - Episodic memory: correction patterns per video
      - Pattern frequency analysis for prompt-optimizer
    """
    try:
        from oracle import ORACLE_MEMORY_DIR
        import glob

        episodic_pattern = (
            f"episodic_*.json" if not bvid
            else f"episodic_*{bvid}*.json"
        )

        paths = sorted(
            Path(str(ORACLE_MEMORY_DIR)).glob("episodic_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:limit]

        results = []
        for p in paths:
            try:
                results.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue

        # Also read semantic aggregate
        semantic_path = ORACLE_MEMORY_DIR / "semantic_patterns.jsonl"
        semantic_count = 0
        if semantic_path.exists():
            with open(semantic_path, encoding="utf-8") as f:
                semantic_count = sum(1 for _ in f)

        return JSONResponse({
            "success": True,
            "data": {
                "episodic": results,
                "total_semantic_entries": semantic_count,
                "memory_dir": str(ORACLE_MEMORY_DIR),
            },
        })
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/oracle/stats")
async def api_oracle_stats():
    """Aggregate oracle statistics for monitoring and self-improvement.

    Returns:
      - Acceptance rate
      - Average confidence
      - Most common issue categories
      - Refinement effectiveness distribution
    """
    try:
        from oracle import ORACLE_MEMORY_DIR

        semantic_path = ORACLE_MEMORY_DIR / "semantic_patterns.jsonl"
        if not semantic_path.exists():
            return JSONResponse({"success": True, "data": {"entries": 0, "message": "No oracle data yet"}})

        entries = []
        with open(semantic_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        if not entries:
            return JSONResponse({"success": True, "data": {"entries": 0}})

        refinements = [e.get("refinement_effectiveness", 0) for e in entries]
        rounds_list = [e.get("rounds_to_converge", 0) for e in entries]

        total = len(entries)
        improved = sum(1 for r in refinements if r > 0)
        avg_effectiveness = sum(refinements) / total if total else 0
        avg_rounds = sum(rounds_list) / total if total else 0

        return JSONResponse({
            "success": True,
            "data": {
                "total_verifications": total,
                "improvement_rate": f"{improved / total * 100:.1f}%" if total else "0%",
                "avg_refinement_effectiveness": round(avg_effectiveness, 1),
                "avg_rounds_to_converge": round(avg_rounds, 1),
                "distribution_rounds": {
                    "1_round": sum(1 for r in rounds_list if r <= 1),
                    "2_rounds": sum(1 for r in rounds_list if r == 2),
                    "3_rounds": sum(1 for r in rounds_list if r >= 3),
                },
            },
        })
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


# Subtitle endpoints
@router.get("/transcript")
async def api_transcript(url: str = Query(...)):
    try:
        bvid = extract_bvid(url)
        sub = await get_full_subtitle(bvid)
        return JSONResponse({"success": True, "data": {
            "bvid": bvid,
            "title": (await get_video_info(bvid)).title,
            "text": sub.text, "tags": sub.tags, "desc": sub.desc
        }})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/timed-text")
async def api_timed_text(url: str = Query(...)):
    try:
        bvid = extract_bvid(url)
        sub = await get_full_subtitle(bvid)
        entries = []
        for item in sub.body:
            m1, s1 = int(item.from_ // 60), int(item.from_ % 60)
            entries.append({"time": f"{m1:02d}:{s1:02d}", "from": item.from_, "to": item.to, "content": item.content})
        return JSONResponse({"success": True, "data": {
            "bvid": bvid, "title": (await get_video_info(bvid)).title,
            "count": len(entries), "entries": entries
        }})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


# Comments endpoints
@router.get("/v2/comments")
async def api_v2_comments(bvid: str = Query(...)):
    try:
        bvid = extract_bvid(bvid)
        comments = await get_comments(bvid)
        return JSONResponse({"success": True, "data": {
            "bvid": bvid, "total": len(comments),
            "comments": [{"user": c.user, "content": c.content, "likes": c.likes,
                          "replies": [{"user": r.user, "content": r.content, "likes": r.likes} for r in (c.replies or [])]}
                         for c in comments]
        }})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/v2/comments/md")
async def api_v2_comments_md(bvid: str = Query(...)):
    try:
        import httpx
        bvid = extract_bvid(bvid)
        comments = await get_comments(bvid)
        info = await get_video_info(bvid)
        md = f"# {info.title}\n\n> {info.owner_name}\n\n## 评论({len(comments)}条)\n\n"
        for c in comments:
            md += f"- **{c.user}** (+{c.likes}): {c.content}\n"
            for r in (c.replies or []):
                md += f"  - {r.user} (+{r.likes}): {r.content}\n"
        return Response(md, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={bvid}_comments.md"})
    except Exception as e:
        logger.error("api_summarize failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"总结失败: {_safe_error(e)}"})


@router.get("/v2/comments/ai")
async def api_v2_comments_ai(bvid: str = Query(...)):
    try:
        import httpx, asyncio
        bvid = extract_bvid(bvid)
        from bilibili_client import get_all_comments as gac
        all_c = await gac(bvid, max_pages=10)
        info = await get_video_info(bvid)
        logger.info("get_all_comments for %s returned %s comments", bvid, len(all_c))
        if not all_c:
            return JSONResponse({"success": False,
                "error": "无可读取的评论。可能原因：1) 该视频暂无评论 2) 未登录B站(评论按时间排序需要登录) 3) 该视频关闭了评论区。请在设置页扫码登录B站后重试，或尝试其他视频。"})

        # --- PRE-PROCESSING ---
        # (1) Sort by likes descending
        all_c.sort(key=lambda c: c.likes, reverse=True)

        # (2) Deduplicate identical (user, content) pairs, keep highest-likes copy (already sorted)
        seen = set()
        deduped = []
        for c in all_c:
            key = (c.user, c.content)
            if key not in seen:
                seen.add(key)
                deduped.append(c)

        # (3) Sort by relevance to video content + likes, split into two groups
        # Group A: content-relevant (top 20 by keyword match + likes)
        # Group B: hot (top 20 by likes, excluding already selected)
        info_keywords = set()
        if hasattr(info, 'title') and info.title:
            info_keywords.update([w for w in re.findall(r'[一-鿿]{2,}|\w{3,}', info.title.lower())])
        if hasattr(info, 'desc') and info.desc:
            info_keywords.update([w for w in re.findall(r'[一-鿿]{2,}|\w{3,}', info.desc.lower()[:500])])

        def _relevance_score(c):
            score = 0
            content_lower = (c.content or "").lower()
            for kw in info_keywords:
                if kw.lower() in content_lower:
                    score += 1
            return score

        # Sort by likes for initial ranking
        all_c.sort(key=lambda c: c.likes, reverse=True)

        # (4) Deduplicate identical (user, content) pairs, keep highest-likes copy (already sorted)
        seen = set()
        deduped = []
        for c in all_c:
            key = (c.user, c.content)
            if key not in seen:
                seen.add(key)
                deduped.append(c)

        # Score relevance and split into two groups
        for c in deduped:
            c._relevance = _relevance_score(c)
        # Group A: content-relevant (relevance > 0, sorted by likes)
        relevant = [c for c in deduped if c._relevance > 0]
        relevant.sort(key=lambda c: c.likes, reverse=True)
        group_a = relevant[:20]
        # Group B: hot comments not in group A
        group_a_ids = {(c.user, c.content) for c in group_a}
        hot_rest = [c for c in deduped if (c.user, c.content) not in group_a_ids]
        hot_rest.sort(key=lambda c: c.likes, reverse=True)
        group_b = hot_rest[:20]
        # Merge: A first (content-relevant), then B (hot)
        selected = group_a + group_b

        # (5) Sanitize & build lines, marking UP主 comments and popular comments
        up_name = (info.owner_name or "").strip()
        for c in selected:
            c.content = _sanitize_llm_field(c.content[:300], 'comment')
            c.user = _sanitize_llm_field(c.user[:50], 'username')
        comments_lines = []
        for i, c in enumerate(selected):
            tag = ""
            if up_name and c.user == up_name:
                tag = "[UP主] "
            elif c.likes >= 100:
                tag = "[热门] "
            comments_lines.append(f"[{i+1}] {tag}+{c.likes} {c.user}: {c.content}")
            if c.replies:
                for sr in c.replies[:15]:
                    tag_r = "[热门] " if sr.likes >= 50 else ""
                    sr_user = _sanitize_llm_field(sr.user[:50], 'username')
                    sr_content = _sanitize_llm_field(sr.content[:300], 'reply')
                    comments_lines.append(f"    -> {tag_r}{sr_user}: {sr_content}")

        c_text = "\n".join(comments_lines)
        api_key = db.get_setting("api_key", "")
        api_url = db.get_setting("api_url", "")
        model = db.get_setting("model", DEFAULT_MODEL)
        if not api_key:
            return JSONResponse({"success": False, "error": "请配置API密钥"})

        # --- ENHANCED PROMPT ---
        prompt = (
            "你是B站评论数据分析师。请用中文从以下评论中提取最有信息量的内容，按主题聚类，标注情感倾向，"
            "并以结构化JSON格式输出。\n\n"
            f"{_wrap_field('video_title', info.title)}\n"
            f"{_wrap_field('video_description', info.desc[:200]) if hasattr(info, 'desc') and info.desc else '<video_description>无</video_description>'}\n\n"
            "任务：\n"
            "1. 主题聚类：将评论归入2-5个主题组（如：内容讨论、技术提问、争议观点、弹幕梗、粉丝互动等）\n"
            "2. 情感标注：每条精选评论标注 sentiment（positive/neutral/negative）\n"
            "3. 精华提炼：每个主题组精选3-8条最能代表该主题的评论，保留原始对话线索\n"
            "4. 忽略无意义评论（纯表情、单字回复、刷屏等）\n\n"
            "请严格按以下JSON格式输出（不要输出任何其他内容）：\n"
            "```json\n"
            "{\n"
            '  "topics": [\n'
            '    {\n'
            '      "name": "主题名称",\n'
            '      "summary": "本主题下评论的概括（一句话）",\n'
            '      "sentiment": "positive/neutral/negative/mixed",\n'
            '      "comments": [\n'
            '        {"user": "用户名", "content": "评论内容", "sentiment": "positive", "reason": "为什么精选这条"}\n'
            '      ]\n'
            '    }\n'
            '  ],\n'
            '  "overall_sentiment": "positive/neutral/negative/mixed",\n'
            '  "hot_topics": ["讨论最多的话题1", "讨论最多的话题2"],\n'
            '  "notable_ids": ["值得关注的用户ID列表，如有"]\n'
            "}\n"
            "```\n\n"
            "全部评论:\n" + c_text[:12000]
        )
        from unified_llm_client import call_llm_with_retry_v2 as _call_llm_with_retry
        result = await _call_llm_with_retry(api_url, api_key, model, [{"role": "user", "content": prompt}])
        if not result["success"]:
            return JSONResponse({"success": False, "error": result["error"]})

        # --- POST-PROCESSING: defensive JSON extraction ---
        raw_text = result["text"]
        structured = None
        try:
            # Extract JSON from ```json ... ``` code fence
            import re as _re
            m = _re.search(r'```(?:json)?\s*([\s\S]*?)```', raw_text)
            json_str = m.group(1).strip() if m else raw_text.strip()
            structured = json.loads(json_str)
        except (json.JSONDecodeError, AttributeError):
            structured = None

        return JSONResponse({"success": True, "data": {
            "bvid": bvid, "title": info.title,
            "total": len(all_c), "deduped": len(deduped),
            "ai_analysis": raw_text,
            "structured": structured
        }})
    except Exception as e:
        logger.error("api_v2_comments_ai failed", exc_info=True)
        return JSONResponse({"success": False, "error": f"评论分析失败: {_safe_error(e)}"})

