"""
BiliSum UnifiedPipeline v1.0

Design: A SINGLE pipeline that ALL import paths go through, modeled on bilinote's
pattern (upload/URL -> extract audio/subtitle -> transcribe -> summarize -> save).

This replaces 3 fragmented text-assembly paths:
  P1: kb.py api_rag_save           (lines 145-214) — subtitle+danmaku+comments
  P2: favorites.py _do_sync        (lines 17-123)  — subtitle OR metadata fallback
  P3: favorites.py api_favorites_import (lines 253-309) — multi-source selection

Bugs fixed by unification:
  H7 (multi-P): P1 doesn't set desc/duration/pubdate/tags/tname/stat/owner_mid
                 but P2/P3 do — unified schema for all paths.
  H9 (silent failures): P1 swallows ALL exceptions with generic "保存失败" — unified
                 error reporting with structured trace.

bilinote reference: /tmp/bilinote/server/server.ts processLocalVideoJob / processOnlineVideoJob
                     plus transcriber.ts, summarizer.ts, jobs.ts, video.ts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Awaitable

# ---------------------------------------------------------------------------
# Pipeline stages (mirrors bilinote JobStatus)
# ---------------------------------------------------------------------------

class Stage(Enum):
    """Ordered stages every import goes through.  Backward-compatible with
    bilinote's JobStatus: queued -> extracting_audio -> transcribing ->
    summarizing -> done | failed."""
    QUEUED = "queued"
    EXTRACTING = "extracting_audio"   # subtitle fetch + optional audio download
    TRANSCRIBING = "transcribing"     # ASR fallback when subtitle is missing
    CORRECTING = "correcting"         # LLM text correction (bilinote: correctTranscriptSegments)
    SUMMARIZING = "summarizing"       # LLM summary generation
    SAVING = "saving"                 # persist to KB/FTS5/ChromaDB/classifier
    DONE = "done"
    FAILED = "failed"


class SourceKind(str, Enum):
    """Where the import was initiated from — drives source field in KB JSON."""
    MANUAL_SAVE = "manual"        # P1: kb.py save button
    FAVORITES_SYNC = "favorites"  # P2: batch sync
    FAVORITES_IMPORT = "favorites_import"  # P3: single import from favorites
    URL_IMPORT = "url"            # new: direct URL import (bilinote pattern)
    LOCAL_FILE = "local"          # future: local video upload
    REIMPORT = "reimport"         # re-process existing KB entry


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class VideoMetadata:
    """Normalized video info — the single source of truth for save_kb_entry.

    Every pipeline path MUST populate all fields (no optional None drift like
    the current P1 vs P2/P3 mismatch)."""
    bvid: str
    title: str = ""
    author: str = ""
    pic: str = ""
    desc: str = ""
    duration: int = 0
    pubdate: str = ""
    tags: str = ""
    tname: str = ""           # partition name (科技/娱乐/...)
    stat: Dict[str, Any] = field(default_factory=dict)
    owner_mid: int = 0
    cid: int = 0
    page_url: str = ""

    @classmethod
    def from_video_info(cls, info) -> VideoMetadata:
        """Hydrate from a bilibili_client VideoInfo model."""
        return cls(
            bvid=info.bvid if hasattr(info, "bvid") else "",
            title=getattr(info, "title", ""),
            author=getattr(info, "owner_name", ""),
            pic=getattr(info, "pic", ""),
            desc=getattr(info, "desc", "") or "",
            duration=getattr(info, "duration", 0) or 0,
            pubdate=str(getattr(info, "pubdate", "")) if getattr(info, "pubdate", None) else "",
            tags=getattr(info, "tags", "") or "",
            tname=getattr(info, "tname", "") or "",
            stat=info.stat.model_dump() if hasattr(info, "stat") and info.stat else {},
            owner_mid=getattr(info, "owner_mid", 0) or 0,
            cid=getattr(info, "cid", 0) or 0,
            page_url=f"https://www.bilibili.com/video/{getattr(info, 'bvid', '')}",
        )


@dataclass
class TextSources:
    """Multi-source content assembly — subtitle + danmaku + comments.

    Instead of 3 different assembly functions, ONE struct with well-defined
    priority and truncation rules."""
    subtitle_text: str = ""     # full subtitle (get_full_subtitle)
    danmaku_lines: List[str] = field(default_factory=list)
    comment_lines: List[str] = field(default_factory=list)
    # Flags controlling which sources to include (from request params)
    include_subtitle: bool = True
    include_danmaku: bool = True
    include_comments: bool = True

    def assemble(self, metadata: VideoMetadata, min_length: int = 20) -> str:
        """Single assembly method used by ALL import paths.

        Priority:
          1. subtitle text (if >= min_length chars)
          2. danmaku (top 100 lines)
          3. comments (top 40 lines)
          4. metadata fallback: title + desc + author
        """
        parts: List[str] = []

        # 1. Subtitle
        if self.include_subtitle and self.subtitle_text and len(self.subtitle_text) >= min_length:
            parts.append(self.subtitle_text)

        # 2. Danmaku
        if self.include_danmaku and self.danmaku_lines:
            parts.append("\n\n## 弹幕精华\n\n" + "\n".join(self.danmaku_lines[:100]))

        # 3. Comments
        if self.include_comments and self.comment_lines:
            parts.append("\n\n## 热门评论\n\n" + "\n".join(self.comment_lines[:40]))

        # 4. Metadata fallback (always appended if subtitle is thin)
        if not parts or (len(parts[0]) < min_length and parts):
            fallback = f"# {metadata.title}\n\nUP主: {metadata.author}\n\n{metadata.desc or ''}"
            if not parts:
                parts.append(fallback)
            else:
                parts.insert(0, fallback)

        text = "\n\n".join(parts)
        if not text or len(text) < min_length:
            text = f"[{metadata.title}]\n{metadata.desc or ''}\nUP: {metadata.author}"
        return text


@dataclass
class PipelineProgress:
    """Progress state emitted at every stage transition."""
    stage: Stage
    progress_pct: int       # 0-100
    message: str
    detail: Optional[str] = None
    bvid: str = ""
    title: str = ""
    elapsed_ms: float = 0.0


@dataclass
class PipelineResult:
    """Final output of a successful pipeline run."""
    bvid: str
    title: str
    text: str               # assembled text
    text_length: int
    chunk_count: int
    stage_history: List[PipelineProgress] = field(default_factory=list)
    transcript_source: str = "subtitle"  # "subtitle" | "whisper_asr"
    summary_generated: bool = False
    total_elapsed_ms: float = 0.0


@dataclass
class PipelineError:
    """Structured error — no more generic '保存失败，请稍后重试'."""
    stage: Stage
    message: str
    detail: str = ""
    recoverable: bool = True  # True = caller can retry, False = fatal
    bvid: str = ""


# ---------------------------------------------------------------------------
# Progress callback type (so callers can stream SSE / update a task dict)
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[PipelineProgress], Awaitable[None]]


# ---------------------------------------------------------------------------
# The UnifiedPipeline
# ---------------------------------------------------------------------------

class UnifiedPipeline:
    """Single entry-point for ALL BiliSum import paths.

    Usage:
        pipeline = UnifiedPipeline()
        result = await pipeline.run(
            bvid="BV1xx411c7mD",
            source_kind=SourceKind.MANUAL_SAVE,
            on_progress=my_sse_callback,
        )
    """

    def __init__(self):
        self.logger = logging.getLogger("bilisum.pipeline")
        self._cancel_events: Dict[str, asyncio.Event] = {}

    # -- Public API ----------------------------------------------------------

    async def run(
        self,
        *,
        bvid: str,
        source_kind: SourceKind = SourceKind.MANUAL_SAVE,
        sources: Optional[TextSources] = None,
        generate_summary: bool = True,
        classify: bool = True,
        folder_name: str = "",
        on_progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> PipelineResult:
        """Execute the full pipeline for a single BVID.

        Args:
            bvid: Bilibili video ID (BV...).
            source_kind: Where this import came from (drives KB source field).
            sources: Pre-configured text sources.  If None, defaults to
                     subtitle+danmaku+comments.
            generate_summary: Whether to run AI summarization.
            classify: Whether to run smart-classifier after save.
            folder_name: KB folder name for organization.
            on_progress: Async callback for progress events (SSE / task dict).
            cancel_event: Set to cancel a running pipeline.

        Returns:
            PipelineResult with assembled text, chunk count, etc.

        Raises:
            PipelineError on unrecoverable failures.
        """
        t0 = time.monotonic()
        stage_history: List[PipelineProgress] = []
        cancel = cancel_event or asyncio.Event()

        async def progress(stage: Stage, pct: int, msg: str, detail: str = None):
            pe = PipelineProgress(
                stage=stage, progress_pct=pct, message=msg, detail=detail,
                bvid=bvid, title="", elapsed_ms=(time.monotonic() - t0) * 1000,
            )
            stage_history.append(pe)
            if on_progress:
                await on_progress(pe)

        try:
            # ---- STAGE 1: EXTRACTING (fetch video info + subtitle) ----
            await progress(Stage.EXTRACTING, 5, "正在获取视频信息...")
            self._check_cancel(cancel)

            from bilibili_client import get_video_info, get_full_subtitle, extract_bvid
            bvid_clean = extract_bvid(bvid)
            info = await get_video_info(bvid_clean)
            metadata = VideoMetadata.from_video_info(info)

            await progress(Stage.EXTRACTING, 15, "正在提取字幕...",
                           detail=f"标题: {metadata.title[:40]}")

            sub = await get_full_subtitle(bvid_clean)
            subtitle_text = sub.text if sub and sub.text else ""

            # ---- STAGE 1b: Fetch danmaku + comments (best-effort) ----
            danmaku_lines: List[str] = []
            comment_lines: List[str] = []

            if sources is None or sources.include_danmaku:
                try:
                    from bilibili_client import get_danmaku as _dm
                    dm = await _dm(metadata.cid, metadata.duration or 0, metadata.owner_mid)
                    if dm:
                        danmaku_lines = dm
                except Exception:
                    self.logger.debug("Danmaku not available for %s", bvid_clean, exc_info=True)

            if sources is None or sources.include_comments:
                try:
                    from bilibili_client import get_comments as _cmt
                    comments = await _cmt(bvid_clean)
                    if comments:
                        comment_lines = [
                            f"[{c.user}] +{c.likes}: {c.content}"
                            for c in comments[:40]
                        ]
                except Exception:
                    self.logger.debug("Comments not available for %s", bvid_clean, exc_info=True)

            # ---- STAGE 2: ASSEMBLE TEXT (unified, not 3 different versions) ----
            await progress(Stage.EXTRACTING, 30, "正在组装文本内容...")

            ts = sources or TextSources(
                subtitle_text=subtitle_text,
                danmaku_lines=danmaku_lines,
                comment_lines=comment_lines,
            )
            text = ts.assemble(metadata)

            # ---- STAGE 3: ASR fallback (no subtitle -> whisper) ----
            transcript_source = "subtitle"
            if (not subtitle_text or len(subtitle_text) < 20) and (
                sources is None or sources.include_subtitle
            ):
                await progress(Stage.TRANSCRIBING, 35,
                               "字幕为空，尝试语音识别...")
                try:
                    from asr_service import transcribe_bilibili_video
                    asr_text = await transcribe_bilibili_video(bvid_clean, metadata.cid)
                    if asr_text and len(asr_text) > len(text):
                        text = asr_text
                        transcript_source = "whisper_asr"
                        await progress(Stage.TRANSCRIBING, 55,
                                       f"语音识别完成 ({len(text)} 字)",
                                       detail="使用 faster-whisper 转写")
                except Exception as e:
                    self.logger.warning(
                        "ASR fallback failed for %s: %s", bvid_clean, e
                    )
                    await progress(Stage.TRANSCRIBING, 40,
                                   "语音识别不可用，使用已有文本",
                                   detail=str(e)[:120])
            else:
                # Skip transcribing stage if we have good subtitles
                await progress(Stage.TRANSCRIBING, 40, "字幕可用，跳过语音识别")

            # ---- STAGE 4: SUMMARIZING (optional AI summary) ----
            if generate_summary:
                await progress(Stage.SUMMARIZING, 60, "正在生成AI总结...")
                summary_success = False
                try:
                    from summarizer import summarize_text_unified
                    summary_result = await summarize_text_unified(
                        title=metadata.title,
                        text=text,
                        metadata=metadata,
                    )
                    if summary_result:
                        text = text + "\n\n【AI详细总结】\n" + summary_result
                        summary_success = True
                except Exception as e:
                    self.logger.warning(
                        "Summarization failed for %s: %s", bvid_clean, e
                    )
                    await progress(Stage.SUMMARIZING, 70,
                                   "AI总结生成失败（非致命）",
                                   detail=str(e)[:120])
                await progress(
                    Stage.SUMMARIZING, 75,
                    "AI总结完成" if summary_success else "跳过AI总结",
                )
            else:
                await progress(Stage.SUMMARIZING, 75, "跳过AI总结（按请求）")

            # ---- STAGE 5: SAVING (unified persistence) ----
            await progress(Stage.SAVING, 80, "正在保存到知识库...")
            await self._persist(
                bvid=bvid_clean,
                metadata=metadata,
                text=text,
                source=source_kind.value if isinstance(source_kind, SourceKind) else source_kind,
                folder_name=folder_name,
                classify=classify,
            )
            await progress(Stage.SAVING, 95, "索引构建完成",
                           detail=f"FTS5 + ChromaDB + JSON")

            # ---- STAGE 6: DONE ----
            chunk_count = len(self._split_text(text))
            await progress(Stage.DONE, 100, "导入完成",
                           detail=f"{chunk_count} chunks, {len(text)} 字")

            return PipelineResult(
                bvid=bvid_clean,
                title=metadata.title,
                text=text,
                text_length=len(text),
                chunk_count=chunk_count,
                stage_history=stage_history,
                transcript_source=transcript_source,
                summary_generated=generate_summary,
                total_elapsed_ms=(time.monotonic() - t0) * 1000,
            )

        except asyncio.CancelledError:
            await progress(Stage.FAILED, 0, "导入已取消")
            raise
        except PipelineError:
            raise
        except Exception as e:
            self.logger.error("Pipeline failed for %s at stage: %s",
                              bvid, stage_history[-1].stage if stage_history else "unknown",
                              exc_info=True)
            raise PipelineError(
                stage=stage_history[-1].stage if stage_history else Stage.FAILED,
                message=str(e),
                detail=repr(e),
                recoverable=self._is_recoverable(e),
                bvid=bvid,
            ) from e

    async def run_batch(
        self,
        bvids: List[str],
        *,
        source_kind: SourceKind = SourceKind.FAVORITES_SYNC,
        max_concurrent: int = 3,
        on_progress: Optional[ProgressCallback] = None,
        cancel_event: Optional[asyncio.Event] = None,
        skip_existing: bool = True,
    ) -> List[PipelineResult]:
        """Run the pipeline for multiple BVIDs with concurrency control.

        Replaces favorites.py _do_sync's ad-hoc loop.
        """
        import database as db

        cancel = cancel_event or asyncio.Event()
        sem = asyncio.Semaphore(max_concurrent)
        results: List[PipelineResult] = []
        errors: List[PipelineError] = []

        if skip_existing:
            existing = {e["bvid"] for e in db.get_kb_list()}
            bvids = [b for b in bvids if b not in existing]

        total = len(bvids)

        async def process_one(bvid: str, index: int):
            async with sem:
                if cancel.is_set():
                    return
                try:
                    result = await self.run(
                        bvid=bvid,
                        source_kind=source_kind,
                        on_progress=on_progress,
                        cancel_event=cancel,
                    )
                    results.append(result)
                except PipelineError as e:
                    errors.append(e)
                    self.logger.error("Batch pipeline error for %s: %s", bvid, e.message)
                except Exception as e:
                    errors.append(PipelineError(
                        stage=Stage.FAILED, message=str(e), bvid=bvid,
                    ))

        tasks = [process_one(bvid, i) for i, bvid in enumerate(bvids)]
        await asyncio.gather(*tasks, return_exceptions=True)

        if errors and len(errors) == total:
            raise PipelineError(
                stage=Stage.FAILED,
                message=f"所有 {total} 个视频导入失败",
                detail=errors[0].message,
                recoverable=False,
            )

        return results

    # -- Persistence (unified save) -----------------------------------------

    async def _persist(
        self,
        bvid: str,
        metadata: VideoMetadata,
        text: str,
        source: str,
        folder_name: str,
        classify: bool,
    ):
        """Single persistence path replacing 3 different save_kb_entry call-sites."""
        import database as db

        # 1. Save KB JSON (ALL fields, no P1 vs P2/P3 mismatch)
        db.save_kb_entry(
            bvid=bvid,
            title=metadata.title,
            author=metadata.author,
            pic=metadata.pic,
            text=text,
            folder_name=folder_name,
            source=source,
            desc=metadata.desc,
            duration=metadata.duration,
            pubdate=metadata.pubdate,
            tags=metadata.tags,
            tname=metadata.tname,
            stat=metadata.stat,
            owner_mid=metadata.owner_mid,
        )

        # 2. Save FTS5 chunks
        db.save_chunks(bvid, metadata.title, text)

        # 3. ChromaDB vector index
        try:
            from main import get_rag_service
            rag = get_rag_service()
            if rag:
                rag.add_video(
                    bvid, metadata.title, text,
                    metadata.author, metadata.desc, metadata.duration,
                )
        except Exception:
            self.logger.warning("ChromaDB index failed for %s (non-fatal)", bvid, exc_info=True)

        # 4. Auto-classify (best-effort)
        if classify:
            try:
                from classifier import get_classifier
                clf = get_classifier()
                api_key = db.get_setting("api_key", "")
                result = await clf.classify(
                    bvid=bvid,
                    title=metadata.title,
                    text=text,
                    duration_seconds=metadata.duration,
                    author=metadata.author,
                    llm_api_key=api_key,
                    llm_api_url=db.get_setting("api_url", ""),
                    llm_model=db.get_setting("model", ""),
                )
                clf.persist_to_entry(bvid)
            except Exception:
                self.logger.info(
                    "Auto-classify failed for %s (non-fatal)", bvid, exc_info=True,
                )

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _split_text(text: str) -> List[str]:
        """Split text into chunk-sized pieces for FTS5 indexing."""
        import database as db
        return db._split_text(text) if hasattr(db, "_split_text") else [text]

    @staticmethod
    def _check_cancel(cancel_event: asyncio.Event):
        if cancel_event.is_set():
            raise PipelineError(
                stage=Stage.FAILED,
                message="任务已取消",
                recoverable=False,
            )

    @staticmethod
    def _is_recoverable(error: Exception) -> bool:
        """Determine if the error is transient (retry-safe) or permanent."""
        msg = str(error).lower()
        transient = {"timeout", "connection", "rate limit", "429", "503", "502", "504",
                     "too many requests", "retry"}
        return any(t in msg for t in transient)


# ---------------------------------------------------------------------------
# Router integration (FastAPI endpoint refactor)
# ---------------------------------------------------------------------------

# OLD (kb.py line 145-214):
#   @router.post("/rag/save")
#   async def api_rag_save(request: Request):
#       # 70 lines of inline text assembly ...
#
# NEW:
#   @router.post("/rag/save")
#   async def api_rag_save(request: Request):
#       body = await request.json()
#       bvid = extract_bvid(body.get("bvid", ""))
#       pipeline = UnifiedPipeline()
#       try:
#           result = await pipeline.run(bvid=bvid, source_kind=SourceKind.MANUAL_SAVE)
#           return JSONResponse({"success": True, "data": {
#               "bvid": result.bvid,
#               "title": result.title,
#               "chunks": result.chunk_count,
#               "textLength": result.text_length,
#               "transcriptSource": result.transcript_source,
#           }})
#       except PipelineError as e:
#           return JSONResponse({"success": False, "error": e.message, "stage": e.stage.value})


# OLD (favorites.py line 17-123, _do_sync inner loop):
#   # 50 lines of per-video try/except ...
#
# NEW (favorites.py _do_sync inner loop):
#   pipeline = UnifiedPipeline()
#   try:
#       result = await pipeline.run(bvid=bvid, source_kind=SourceKind.FAVORITES_SYNC)
#       total += 1
#       # update task dict ...
#   except PipelineError as e:
#       logger.warning("Skipping %s: %s", bvid, e.message)


# OLD (favorites.py line 253-309, api_favorites_import):
#   # 60 lines of inline import ...
#
# NEW:
#   pipeline = UnifiedPipeline()
#   result = await pipeline.run(
#       bvid=bvid,
#       source_kind=SourceKind.FAVORITES_IMPORT,
#       sources=TextSources(include_danmaku=("danmaku" in srcs),
#                           include_comments=("comment" in srcs)),
#   )


# ---------------------------------------------------------------------------
# Future extensions (trivial with unified pipeline)
# ---------------------------------------------------------------------------

# Local video upload (bilinote's processLocalVideoJob pattern):
#   async def run_local(self, filepath: str, ...):
#       extract_audio(filepath) -> transcribe -> assemble -> summarize -> persist

# URL import (bilinote's processOnlineVideoJob pattern):
#   async def run_url(self, url: str, ...):
#       resolve_metadata(url) -> fetch_subtitle_or_download_audio -> ...
"""
