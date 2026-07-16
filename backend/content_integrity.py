"""
=============================================================================
BiliSum Content Integrity Verification System (v1.0)
=============================================================================
KB import completeness checker across 9 content dimensions.
Ensures every KB entry has a self-auditing manifest tracking exactly what
was imported vs. what is missing, with per-dimension status and a weighted
completeness score.

Cross-reference designs:
  - bili-note: output/{bvid}/source.md manifest pattern
  - bilibili-rag: content_sources tracking (knowledge.py calibration loop)
  - BiliSum classifier: persist_to_entry pattern (write-back to KB JSON)

Problem this fixes:
  - eyemask video: AI Q&A said "源文本中没有列出5款型号" because OCR was
    never captured, ASR timed out at 6s, AI summary never persisted.

Usage:
    from content_integrity import verify_import_completeness, format_import_toast

    manifest, warnings, score = verify_import_completeness(
        info, sub, danmaku_lines, comment_list, ocr_text,
        ai_summary_text, multi_part_pages, classification_data
    )
    db.save_kb_entry(..., content_manifest=manifest)

=============================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================

class ContentStatus(str, Enum):
    """Per-dimension status after verification."""
    PRESENT = "present"     # data exists with meaningful content
    ABSENT  = "absent"      # data was not fetched or not available
    PARTIAL = "partial"     # data exists but is thin/incomplete
    ERROR   = "error"       # fetch was attempted but failed


class ContentDimension(str, Enum):
    """The 9 content dimensions every KB import should cover."""
    SUBTITLE       = "subtitle"        # CC字幕 or AI字幕
    ASR            = "asr"             # ASR语音转写 fallback
    DANMAKU        = "danmaku"         # 弹幕精华 (high-density segments)
    COMMENTS       = "comments"        # 热门评论 (top 40 by likes)
    OCR            = "ocr"             # 画面信息/OCR文字
    AI_SUMMARY     = "ai_summary"      # AI多维度详细总结
    MULTI_PART     = "multi_part"      # 多页视频全量 P1/P2/...
    METADATA       = "metadata"        # title, author, duration, tags, stats
    CLASSIFICATION = "classification"  # video_type/difficulty/language/topic/quality_tier


# ============================================================================
# Scoring weights — sum to 100
# ============================================================================

CONTENT_WEIGHTS: dict[ContentDimension, int] = {
    ContentDimension.SUBTITLE:       20,
    ContentDimension.ASR:            10,
    ContentDimension.DANMAKU:        10,
    ContentDimension.COMMENTS:       10,
    ContentDimension.OCR:            10,
    ContentDimension.AI_SUMMARY:     15,
    ContentDimension.MULTI_PART:      5,
    ContentDimension.METADATA:       10,
    ContentDimension.CLASSIFICATION: 10,
}

_MAX_SCORE = sum(CONTENT_WEIGHTS.values())  # 100

# When subtitle is present, ASR is redundant (still tracked, but flagged
# "not_needed" so it doesn't penalize the score). Only penalize ASR absence
# when subtitle is ALSO absent.
_ASR_WEIGHT_WHEN_SUBTITLE_PRESENT = 0  # no penalty

# Thresholds: minimum meaningful byte counts per dimension
_MIN_SUBTITLE_CHARS  = 20
_MIN_ASR_CHARS       = 20
_MIN_DANMAKU_ITEMS   = 3
_MIN_COMMENT_ITEMS   = 1
_MIN_OCR_CHARS       = 10
_MIN_AI_SUMMARY_CHARS = 40
_MIN_MULTI_PART_PAGES = 2   # only relevant when videos_count >= 2


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class DimensionResult:
    """Result of checking one content dimension."""
    dimension: str                # ContentDimension value
    status: ContentStatus
    detail: str = ""             # human-readable note
    byte_count: int = 0          # byte/char count of captured content
    item_count: int = 0          # count of discrete items (danmaku lines, comments, pages)
    weight: int = 0              # CONTENT_WEIGHTS[dimension]
    earned: float = 0.0          # actual score contribution


@dataclass
class ImportManifest:
    """Complete import manifest for a single video."""
    bvid: str
    title: str
    dimensions: list[dict] = field(default_factory=list)   # list of DimensionResult.to_dict()
    overall_score: float = 0.0
    max_score: int = _MAX_SCORE
    warnings: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)        # dimension names that are absent
    verified_at: str = ""                                    # ISO 8601

    def to_dict(self) -> dict:
        return {
            "bvid": self.bvid,
            "title": self.title,
            "dimensions": self.dimensions,
            "overall_score": round(self.overall_score, 1),
            "max_score": self.max_score,
            "warnings": self.warnings,
            "missing": self.missing,
            "verified_at": self.verified_at,
        }


# ============================================================================
# Core verification function
# ============================================================================

def verify_import_completeness(
    info,                              # VideoInfo from bilibili_client.get_video_info()
    sub,                               # SubtitleData from bilibili_client.get_full_subtitle()
    danmaku: Optional[list[str]],      # list of danmaku text lines
    comments: Optional[list],          # list of CommentEntry
    ocr_text: Optional[str],           # on-screen OCR text (None if not attempted)
    ai_summary: Optional[str],         # AI-generated multi-dimension summary
    multi_part_pages: Optional[list],  # list of page dicts from get_video_parts()
    classification: Optional[dict],    # classifier result dict or None
) -> tuple[ImportManifest, list[str], float]:
    """
    Verify completeness of a KB import across all 9 content dimensions.

    Args:
        info: VideoInfo from get_video_info()
        sub: SubtitleData from get_full_subtitle()
        danmaku: list of danmaku text strings, or None if not fetched
        comments: list of CommentEntry objects, or None if not fetched
        ocr_text: on-screen OCR text string, or None if not attempted
        ai_summary: AI-generated summary string, or None if not generated
        multi_part_pages: list of page dicts from get_video_parts(), or None
        classification: dict from classifier result, or None

    Returns:
        (manifest, warnings_list, score)
          - manifest: ImportManifest with full dimension details
          - warnings: list of human-readable warning strings
          - score: float 0-100 completeness percentage
    """
    warnings: list[str] = []
    dimensions: list[DimensionResult] = []

    # ------------------------------------------------------------------
    # 1. 字幕/文字稿 (subtitle/transcript)
    # ------------------------------------------------------------------
    sub_has_content = bool(sub and sub.text and len(sub.text) >= _MIN_SUBTITLE_CHARS)
    sub_all_channels_failed = getattr(sub, 'all_channels_failed', False)

    if sub_has_content:
        dim_sub = DimensionResult(
            dimension=ContentDimension.SUBTITLE.value,
            status=ContentStatus.PRESENT,
            detail=_describe_sub_source(sub),
            byte_count=len(sub.text),
            item_count=len(sub.body) if sub.body else 0,
            weight=CONTENT_WEIGHTS[ContentDimension.SUBTITLE],
            earned=CONTENT_WEIGHTS[ContentDimension.SUBTITLE],
        )
    elif sub is not None and sub.text is not None and len(sub.text) < _MIN_SUBTITLE_CHARS:
        dim_sub = DimensionResult(
            dimension=ContentDimension.SUBTITLE.value,
            status=ContentStatus.PARTIAL,
            detail=f"字幕文本过短 ({len(sub.text)}字符, 需要>={_MIN_SUBTITLE_CHARS})",
            byte_count=len(sub.text),
            item_count=len(sub.body) if sub.body else 0,
            weight=CONTENT_WEIGHTS[ContentDimension.SUBTITLE],
            earned=CONTENT_WEIGHTS[ContentDimension.SUBTITLE] * 0.5,
        )
        warnings.append("字幕文本内容不足，可能影响总结质量")
    elif sub_all_channels_failed:
        dim_sub = DimensionResult(
            dimension=ContentDimension.SUBTITLE.value,
            status=ContentStatus.ERROR,
            detail="所有字幕通道均失败",
            weight=CONTENT_WEIGHTS[ContentDimension.SUBTITLE],
            earned=0,
        )
        warnings.append("字幕获取失败 (所有通道)")
    else:
        dim_sub = DimensionResult(
            dimension=ContentDimension.SUBTITLE.value,
            status=ContentStatus.ABSENT,
            detail="视频无可用字幕",
            weight=CONTENT_WEIGHTS[ContentDimension.SUBTITLE],
            earned=0,
        )
        warnings.append("该视频无字幕，建议启用ASR语音转写")
    dimensions.append(dim_sub)

    # ------------------------------------------------------------------
    # 2. ASR语音转写 (ASR fallback)
    # ------------------------------------------------------------------
    # ASR is a fallback when subtitles are absent. If subtitle is present,
    # ASR absence is NOT penalized.
    dim_asr: DimensionResult
    subtitle_present = dim_sub.status == ContentStatus.PRESENT

    # Check if ASR was attempted (sub may have come from channel 5 ASR)
    sub_source_asr = _subtitle_came_from_asr(sub)

    if sub_source_asr:
        dim_asr = DimensionResult(
            dimension=ContentDimension.ASR.value,
            status=ContentStatus.PRESENT,
            detail="字幕文本来源于ASR语音转写",
            byte_count=len(sub.text) if sub and sub.text else 0,
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.ASR],
            earned=CONTENT_WEIGHTS[ContentDimension.ASR],
        )
    elif subtitle_present:
        dim_asr = DimensionResult(
            dimension=ContentDimension.ASR.value,
            status=ContentStatus.PRESENT,
            detail="有字幕，ASR转写不需要",
            weight=CONTENT_WEIGHTS[ContentDimension.ASR],
            earned=CONTENT_WEIGHTS[ContentDimension.ASR],  # full credit
        )
    elif ocr_text and len(ocr_text) >= _MIN_ASR_CHARS:
        # OCR can partially substitute for ASR (text from video frames)
        dim_asr = DimensionResult(
            dimension=ContentDimension.ASR.value,
            status=ContentStatus.PARTIAL,
            detail="无ASR转写，但有OCR文字可部分替代",
            byte_count=len(ocr_text),
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.ASR],
            earned=CONTENT_WEIGHTS[ContentDimension.ASR] * 0.4,
        )
        warnings.append("缺少ASR语音转写，仅有OCR画面文字作为补充")
    else:
        dim_asr = DimensionResult(
            dimension=ContentDimension.ASR.value,
            status=ContentStatus.ABSENT,
            detail="无ASR转写 (字幕通道失败且未启用语音识别)",
            weight=CONTENT_WEIGHTS[ContentDimension.ASR],
            earned=0,
        )
        if not subtitle_present:
            warnings.append("严重: 既无字幕也无ASR转写 — 知识库条目将缺少核心文字内容")
    dimensions.append(dim_asr)

    # ------------------------------------------------------------------
    # 3. 弹幕精华 (danmaku highlights)
    # ------------------------------------------------------------------
    danmaku_present = bool(danmaku and len(danmaku) >= _MIN_DANMAKU_ITEMS)
    if danmaku_present:
        dim_dm = DimensionResult(
            dimension=ContentDimension.DANMAKU.value,
            status=ContentStatus.PRESENT,
            detail=f"已获取弹幕精华, {len(danmaku)}条去重后文本",
            byte_count=sum(len(d) for d in danmaku),
            item_count=len(danmaku),
            weight=CONTENT_WEIGHTS[ContentDimension.DANMAKU],
            earned=CONTENT_WEIGHTS[ContentDimension.DANMAKU],
        )
    elif danmaku is not None and len(danmaku) < _MIN_DANMAKU_ITEMS:
        dim_dm = DimensionResult(
            dimension=ContentDimension.DANMAKU.value,
            status=ContentStatus.PARTIAL,
            detail=f"弹幕数量不足 ({len(danmaku)}条, 需要>={_MIN_DANMAKU_ITEMS})",
            byte_count=sum(len(d) for d in danmaku) if danmaku else 0,
            item_count=len(danmaku) if danmaku else 0,
            weight=CONTENT_WEIGHTS[ContentDimension.DANMAKU],
            earned=CONTENT_WEIGHTS[ContentDimension.DANMAKU] * 0.3,
        )
    else:
        dim_dm = DimensionResult(
            dimension=ContentDimension.DANMAKU.value,
            status=ContentStatus.ABSENT,
            detail="未获取弹幕 (可能视频弹幕量不足或API限制)",
            weight=CONTENT_WEIGHTS[ContentDimension.DANMAKU],
            earned=0,
        )
    dimensions.append(dim_dm)

    # ------------------------------------------------------------------
    # 4. 热门评论 (hot comments)
    # ------------------------------------------------------------------
    comments_present = bool(comments and len(comments) >= _MIN_COMMENT_ITEMS)
    if comments_present:
        total_likes = sum(getattr(c, 'likes', 0) for c in comments)
        dim_cmt = DimensionResult(
            dimension=ContentDimension.COMMENTS.value,
            status=ContentStatus.PRESENT,
            detail=f"已获取热门评论, {len(comments)}条 (共{total_likes}赞)",
            byte_count=sum(len(getattr(c, 'content', '')) for c in comments),
            item_count=len(comments),
            weight=CONTENT_WEIGHTS[ContentDimension.COMMENTS],
            earned=CONTENT_WEIGHTS[ContentDimension.COMMENTS],
        )
    elif comments is not None and len(comments) == 0:
        dim_cmt = DimensionResult(
            dimension=ContentDimension.COMMENTS.value,
            status=ContentStatus.ABSENT,
            detail="评论获取成功但视频无评论",
            weight=CONTENT_WEIGHTS[ContentDimension.COMMENTS],
            earned=CONTENT_WEIGHTS[ContentDimension.COMMENTS],  # not user's fault
        )
    else:
        dim_cmt = DimensionResult(
            dimension=ContentDimension.COMMENTS.value,
            status=ContentStatus.ABSENT,
            detail="未获取评论 (API失败或未尝试)",
            weight=CONTENT_WEIGHTS[ContentDimension.COMMENTS],
            earned=0,
        )
    dimensions.append(dim_cmt)

    # ------------------------------------------------------------------
    # 5. 画面信息/OCR文字 (on-screen text)
    # ------------------------------------------------------------------
    ocr_present = bool(ocr_text and len(ocr_text) >= _MIN_OCR_CHARS)
    if ocr_present:
        dim_ocr = DimensionResult(
            dimension=ContentDimension.OCR.value,
            status=ContentStatus.PRESENT,
            detail=f"已提取画面OCR文字, {len(ocr_text)}字符",
            byte_count=len(ocr_text),
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.OCR],
            earned=CONTENT_WEIGHTS[ContentDimension.OCR],
        )
    elif ocr_text is not None and len(ocr_text) < _MIN_OCR_CHARS:
        dim_ocr = DimensionResult(
            dimension=ContentDimension.OCR.value,
            status=ContentStatus.PARTIAL,
            detail=f"画面OCR文字过短 ({len(ocr_text)}字符)",
            byte_count=len(ocr_text),
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.OCR],
            earned=CONTENT_WEIGHTS[ContentDimension.OCR] * 0.3,
        )
    else:
        dim_ocr = DimensionResult(
            dimension=ContentDimension.OCR.value,
            status=ContentStatus.ABSENT,
            detail="未进行画面OCR提取 (需启用视频帧分析)",
            weight=CONTENT_WEIGHTS[ContentDimension.OCR],
            earned=0,
        )
        warnings.append("未启用画面OCR — 视频中的产品名/型号/标注文字可能缺失")
    dimensions.append(dim_ocr)

    # ------------------------------------------------------------------
    # 6. AI总结 (AI summary)
    # ------------------------------------------------------------------
    ai_summary_present = bool(ai_summary and len(ai_summary.strip()) >= _MIN_AI_SUMMARY_CHARS)
    if ai_summary_present:
        dim_ai = DimensionResult(
            dimension=ContentDimension.AI_SUMMARY.value,
            status=ContentStatus.PRESENT,
            detail=f"已生成AI多维度总结, {len(ai_summary)}字符",
            byte_count=len(ai_summary),
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.AI_SUMMARY],
            earned=CONTENT_WEIGHTS[ContentDimension.AI_SUMMARY],
        )
    elif ai_summary is not None and len(ai_summary.strip()) < _MIN_AI_SUMMARY_CHARS:
        dim_ai = DimensionResult(
            dimension=ContentDimension.AI_SUMMARY.value,
            status=ContentStatus.PARTIAL,
            detail=f"AI总结内容不足 ({len(ai_summary.strip())}字符, 需要>={_MIN_AI_SUMMARY_CHARS})",
            byte_count=len(ai_summary),
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.AI_SUMMARY],
            earned=CONTENT_WEIGHTS[ContentDimension.AI_SUMMARY] * 0.5,
        )
        warnings.append("AI总结内容不完整")
    else:
        dim_ai = DimensionResult(
            dimension=ContentDimension.AI_SUMMARY.value,
            status=ContentStatus.ABSENT,
            detail="未生成AI总结 (需在AI总结页生成后保存)",
            weight=CONTENT_WEIGHTS[ContentDimension.AI_SUMMARY],
            earned=0,
        )
        warnings.append("缺少AI总结 — 建议在AI总结页生成后重新保存")
    dimensions.append(dim_ai)

    # ------------------------------------------------------------------
    # 7. 多页视频全量 (multi-part video)
    # ------------------------------------------------------------------
    videos_count = getattr(info, 'videos_count', 1) or 1
    if videos_count <= 1:
        dim_mp = DimensionResult(
            dimension=ContentDimension.MULTI_PART.value,
            status=ContentStatus.PRESENT,
            detail="单页视频, 不需要多页处理",
            item_count=1,
            weight=CONTENT_WEIGHTS[ContentDimension.MULTI_PART],
            earned=CONTENT_WEIGHTS[ContentDimension.MULTI_PART],  # full credit
        )
    elif multi_part_pages and len(multi_part_pages) >= videos_count:
        dim_mp = DimensionResult(
            dimension=ContentDimension.MULTI_PART.value,
            status=ContentStatus.PRESENT,
            detail=f"已获取全部 {len(multi_part_pages)}/{videos_count} 页",
            item_count=len(multi_part_pages),
            weight=CONTENT_WEIGHTS[ContentDimension.MULTI_PART],
            earned=CONTENT_WEIGHTS[ContentDimension.MULTI_PART],
        )
    elif multi_part_pages and len(multi_part_pages) < videos_count:
        dim_mp = DimensionResult(
            dimension=ContentDimension.MULTI_PART.value,
            status=ContentStatus.PARTIAL,
            detail=f"仅获取 {len(multi_part_pages)}/{videos_count} 页",
            item_count=len(multi_part_pages),
            weight=CONTENT_WEIGHTS[ContentDimension.MULTI_PART],
            earned=CONTENT_WEIGHTS[ContentDimension.MULTI_PART] * (len(multi_part_pages) / videos_count),
        )
        warnings.append(f"多页视频仅导入了部分页面 ({len(multi_part_pages)}/{videos_count})")
    else:
        dim_mp = DimensionResult(
            dimension=ContentDimension.MULTI_PART.value,
            status=ContentStatus.ABSENT,
            detail=f"多页视频 ({videos_count}页) 仅导入了P1",
            item_count=1,
            weight=CONTENT_WEIGHTS[ContentDimension.MULTI_PART],
            earned=0,
        )
        warnings.append(f"多页视频 ({videos_count}页) 仅导入了第1页 — 需使用多页导入功能")
    dimensions.append(dim_mp)

    # ------------------------------------------------------------------
    # 8. 视频元数据 (metadata)
    # ------------------------------------------------------------------
    has_title  = bool(info and getattr(info, 'title', ''))
    has_author = bool(info and getattr(info, 'owner_name', ''))
    has_duration = bool(info and getattr(info, 'duration', 0))
    has_tags  = bool(info and getattr(info, 'tags', ''))
    has_stats = bool(info and getattr(info, 'stat', None) is not None)
    meta_bits = sum([has_title, has_author, has_duration, has_tags, has_stats])
    meta_max  = 5

    if meta_bits == meta_max:
        dim_meta = DimensionResult(
            dimension=ContentDimension.METADATA.value,
            status=ContentStatus.PRESENT,
            detail=f"完整元数据: 标题/作者/时长/标签/统计数据",
            item_count=meta_bits,
            weight=CONTENT_WEIGHTS[ContentDimension.METADATA],
            earned=CONTENT_WEIGHTS[ContentDimension.METADATA],
        )
    elif meta_bits >= 3:
        missing_meta = []
        if not has_title: missing_meta.append("标题")
        if not has_author: missing_meta.append("作者")
        if not has_duration: missing_meta.append("时长")
        if not has_tags: missing_meta.append("标签")
        if not has_stats: missing_meta.append("统计数据")
        dim_meta = DimensionResult(
            dimension=ContentDimension.METADATA.value,
            status=ContentStatus.PARTIAL,
            detail=f"部分元数据 ({meta_bits}/{meta_max}), 缺少: {', '.join(missing_meta)}",
            item_count=meta_bits,
            weight=CONTENT_WEIGHTS[ContentDimension.METADATA],
            earned=CONTENT_WEIGHTS[ContentDimension.METADATA] * (meta_bits / meta_max),
        )
        warnings.append(f"视频元数据不完整, 缺少: {', '.join(missing_meta)}")
    else:
        dim_meta = DimensionResult(
            dimension=ContentDimension.METADATA.value,
            status=ContentStatus.ERROR,
            detail=f"元数据严重缺失 ({meta_bits}/{meta_max})",
            item_count=meta_bits,
            weight=CONTENT_WEIGHTS[ContentDimension.METADATA],
            earned=0,
        )
        warnings.append("视频元数据严重缺失")
    dimensions.append(dim_meta)

    # ------------------------------------------------------------------
    # 9. 分类标签 (classification)
    # ------------------------------------------------------------------
    has_type  = bool(classification and classification.get("video_type"))
    has_diff  = bool(classification and classification.get("difficulty"))
    has_lang  = bool(classification and classification.get("language"))
    has_tier  = bool(classification and classification.get("quality_tier"))
    has_tags_list = bool(classification and classification.get("tags"))
    cls_bits = sum([has_type, has_diff, has_lang, has_tier, has_tags_list])
    cls_max  = 5

    if cls_bits >= 4:
        dim_cls = DimensionResult(
            dimension=ContentDimension.CLASSIFICATION.value,
            status=ContentStatus.PRESENT,
            detail=f"已分类: {classification.get('video_type', '?')} / {classification.get('difficulty', '?')} / {classification.get('quality_tier', '?')}",
            item_count=len(classification.get("tags", [])),
            weight=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION],
            earned=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION],
        )
    elif cls_bits >= 2:
        dim_cls = DimensionResult(
            dimension=ContentDimension.CLASSIFICATION.value,
            status=ContentStatus.PARTIAL,
            detail=f"部分分类 ({cls_bits}/{cls_max}维度)",
            item_count=len(classification.get("tags", [])) if classification else 0,
            weight=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION],
            earned=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION] * (cls_bits / cls_max),
        )
    elif classification is not None:
        dim_cls = DimensionResult(
            dimension=ContentDimension.CLASSIFICATION.value,
            status=ContentStatus.PARTIAL,
            detail=f"分类数据不足 ({cls_bits}/{cls_max}维度)",
            item_count=0,
            weight=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION],
            earned=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION] * 0.2,
        )
    else:
        dim_cls = DimensionResult(
            dimension=ContentDimension.CLASSIFICATION.value,
            status=ContentStatus.ABSENT,
            detail="未进行自动分类 (将在保存后异步分类)",
            weight=CONTENT_WEIGHTS[ContentDimension.CLASSIFICATION],
            earned=0,
        )
        # Not a warning — classification happens post-save
    dimensions.append(dim_cls)

    # ------------------------------------------------------------------
    # Assemble manifest
    # ------------------------------------------------------------------
    overall_score = sum(d.earned for d in dimensions)
    missing = [d.dimension for d in dimensions if d.status == ContentStatus.ABSENT]

    # Determine tier for human-readable summary
    if overall_score >= 85:
        tier = "excellent"
    elif overall_score >= 65:
        tier = "good"
    elif overall_score >= 40:
        tier = "fair"
    else:
        tier = "poor"

    manifest = ImportManifest(
        bvid=getattr(info, 'bvid', ''),
        title=getattr(info, 'title', ''),
        dimensions=[_dim_result_to_dict(d) for d in dimensions],
        overall_score=round(overall_score, 1),
        warnings=warnings,
        missing=missing,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )

    return manifest, warnings, overall_score


# ============================================================================
# Helpers
# ============================================================================

def _dim_result_to_dict(dr: DimensionResult) -> dict:
    return {
        "dimension": dr.dimension,
        "status": dr.status.value,
        "detail": dr.detail,
        "byte_count": dr.byte_count,
        "item_count": dr.item_count,
        "weight": dr.weight,
        "earned": round(dr.earned, 1),
    }


def _describe_sub_source(sub) -> str:
    """Return a human-readable description of which subtitle channel succeeded."""
    if sub is None:
        return "无字幕数据"
    text_len = len(sub.text) if sub.text else 0
    entry_count = len(sub.body) if sub.body else 0
    return f"已获取字幕, {text_len}字符, {entry_count}条时间轴条目"


def _subtitle_came_from_asr(sub) -> bool:
    """Heuristic: check if subtitle text likely came from ASR channel 5."""
    if sub is None:
        return False
    # Channel 5 ASR entries have synthetic from/to timestamps (i*5 intervals)
    if sub.body and len(sub.body) >= 2:
        first = sub.body[0]
        second = sub.body[1]
        # ASR entries: uniform ~5s intervals
        if (getattr(second, 'from_', 0) - getattr(first, 'from_', 0)) == 5:
            return True
    return False


def format_import_toast(manifest: ImportManifest, title: str = "") -> str:
    """
    Produce a one-line human-readable summary for a frontend toast.

    Example output:
      "已保存「xxx」· 完整性 75% · 缺少: AI总结, OCR文字"
      "已保存「xxx」· 完整性 92% · 内容完整"
    """
    name = title or manifest.title or manifest.bvid
    if len(name) > 30:
        name = name[:28] + "..."

    score = manifest.overall_score

    if score >= 85:
        tier_msg = "内容完整"
    elif score >= 65:
        tier_msg = f"基本完整 ({score:.0f}%)"
    elif score >= 40:
        tier_msg = f"完整性不足 ({score:.0f}%)"
    else:
        tier_msg = f"严重不完整 ({score:.0f}%)"

    if manifest.missing:
        missing_short = ", ".join(_dim_label(d) for d in manifest.missing[:4])
        if len(manifest.missing) > 4:
            missing_short += f"等{len(manifest.missing)}项"
        return f"✅ 已保存「{name}」· {tier_msg} · 缺少: {missing_short}"
    else:
        return f"✅ 已保存「{name}」· {tier_msg}"


def _dim_label(dim_key: str) -> str:
    """Map dimension enum value to short Chinese label."""
    labels = {
        "subtitle":       "字幕",
        "asr":            "语音转写",
        "danmaku":        "弹幕",
        "comments":       "评论",
        "ocr":            "画面OCR",
        "ai_summary":     "AI总结",
        "multi_part":     "多页视频",
        "metadata":       "元数据",
        "classification": "分类标签",
    }
    return labels.get(dim_key, dim_key)


def get_score_tier(score: float) -> str:
    """Return tier label for a completeness score."""
    if score >= 85:
        return "excellent"
    elif score >= 65:
        return "good"
    elif score >= 40:
        return "fair"
    else:
        return "poor"


def get_score_color(score: float) -> str:
    """Return CSS color for a completeness score badge."""
    if score >= 85:
        return "#52c41a"  # green
    elif score >= 65:
        return "#faad14"  # yellow
    elif score >= 40:
        return "#fa8c16"  # orange
    else:
        return "#ff4d4f"  # red


# ============================================================================
# FastAPI helper: build dimensions dict for the verify_import_completeness call
# from the router context
# ============================================================================

async def collect_dimensions_for_verification(
    info,
    sub,
    *,
    fetch_danmaku: bool = True,
    fetch_comments: bool = True,
    fetch_ocr: bool = False,       # OCR not yet implemented — future hook
    fetch_multi_part: bool = True,
) -> dict:
    """
    Gather all raw content dimensions from B站 APIs for integrity verification.

    Returns a dict suitable for splatting into verify_import_completeness().
    All fetches are best-effort — individual failures are logged but don't
    prevent the verification from running.

    Returns:
        {
            "danmaku": list[str] | None,
            "comments": list | None,
            "ocr_text": str | None,
            "multi_part_pages": list | None,
            "ai_summary": str | None,
        }
    """
    danmaku_lines: Optional[list[str]] = None
    comment_list: Optional[list] = None
    ocr_text: Optional[str] = None
    multi_part_pages: Optional[list] = None

    bvid = getattr(info, 'bvid', '')

    # Danmaku
    if fetch_danmaku:
        try:
            from bilibili_client import get_danmaku as _dm
            danmaku_lines = await _dm(
                getattr(info, 'cid', 0),
                getattr(info, 'duration', 0) or 0,
                getattr(info, 'owner_mid', 0),
            )
        except Exception:
            logger.debug("[%s] Danmaku fetch failed for integrity check", bvid, exc_info=True)

    # Comments
    if fetch_comments:
        try:
            from bilibili_client import get_comments as _cmt
            comment_list = await _cmt(bvid)
        except Exception:
            logger.debug("[%s] Comments fetch failed for integrity check", bvid, exc_info=True)

    # Multi-part pages
    if fetch_multi_part:
        try:
            from bilibili_client import get_video_parts as _vp
            multi_part_pages = await _vp(bvid)
        except Exception:
            logger.debug("[%s] Multi-part fetch failed for integrity check", bvid, exc_info=True)

    # OCR — not yet implemented; always None for now
    # (Future: integrate with video-frames skill for frame extraction + OCR)

    return {
        "danmaku": danmaku_lines,
        "comments": comment_list,
        "ocr_text": ocr_text,
        "multi_part_pages": multi_part_pages,
    }
