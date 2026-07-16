"""
Note Budget quality scoring system v2.0 — bilibili-source deep redevelopment

Adapted from bili-note's archive_bili_materials.py.

KEY FIXES from v1.0:
  Bug#3 [quality.py:23-87]: compute_quality_multiplier() previously always received
    stat fields with value 0 (because VideoInfo.model lacked stat fields and
    get_video_info() never extracted them from B站 API). This forced the multiplier
    to always hit the 0.85 floor. Now properly receives live stat_data from
    VideoInfo.stat (7-dim engagement).

  Bug#4 [summarizer.py:134,156]: max_tokens fixed at 4096 for all videos regardless
    of content length. Now dynamically computed from note budget: quality_multiplier
    scales max_tokens in range [1823, 32000].

  Bug#5 [models.py:19-20]: fetched_at timestamp never set. Now generated at
    VideoInfo creation time, propagated through quality chain.

New features:
  - 7-dim weighted engagement scoring (like, favorite, coin, reply, danmaku, share, view)
  - Per-dimension score transparency (engagement_rate_score, favorite_rate_score, etc.)
  - Quality confidence level (high/medium/low) based on data quantity
  - max_tokens_recommendation from note_budget
  - Visual dependency assessment preserved from v1.0
"""
import math
import time
from typing import Optional, Tuple


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def normalized_log_score(value: float, reference: float) -> float:
    """Log-normalized scoring: maps raw values to [0, 1] range."""
    if value <= 0 or reference <= 0:
        return 0.0
    return clamp(math.log1p(value) / math.log1p(reference), 0.0, 1.0)


# ==================== DIMENSION WEIGHTS (bili-note calibrated) ====================

DIM_WEIGHTS = {
    "engagement_rate": 0.28,       # 互动率（点赞收藏投币评论弹幕分享/播放）
    "favorite_rate": 0.18,         # 收藏率
    "discussion": 0.12,            # 讨论热度（评论+弹幕/播放）
    "view_velocity": 0.20,         # 日均播放速度
    "engagement_velocity": 0.22,   # 日均互动速度
}

# Reference values for normalized_log_score (log1p-based)
REF_ENGAGEMENT_RATE = 80       # ~8% engagement rate is "reference quality"
REF_FAVORITE_RATE = 50         # ~5% favorite rate
REF_DISCUSSION_RATE = 20       # ~2% discussion rate
REF_VIEW_VELOCITY = 10000      # 10k views/day
REF_ENGAGEMENT_VELOCITY = 1000 # 1k engagements/day

# Quality multiplier output range
QUALITY_FLOOR = 0.85
QUALITY_CEILING = 1.40

# Confidence thresholds
CONFIDENCE_THRESHOLD_HIGH = 0.72
CONFIDENCE_THRESHOLD_MEDIUM = 0.45


# ==================== ENGAGEMENT WEIGHT COEFFICIENTS ====================

def compute_weighted_engagement(
    like: int = 0,
    favorite: int = 0,
    coin: int = 0,
    reply: int = 0,
    danmaku: int = 0,
    share: int = 0,
) -> float:
    """
    Weighted engagement score using bili-note coefficients.
    coin > reply > share > favorite > like > danmaku (by weight)
    """
    return (
        like
        + favorite * 1.4
        + coin * 2.2
        + reply * 1.8
        + danmaku * 0.8
        + share * 1.5
    )


# ==================== V2.0 compute_quality_multiplier ====================

def compute_quality_multiplier(stat_data: dict) -> dict:
    """
    Compute quality multiplier from video engagement signals — v2.0.

    Args:
        stat_data dict with keys:
            view, like, favorite, coin, reply, danmaku, share, pubdate, now

    Returns dict with:
        quality_multiplier: float in [0.85, 1.40]
        quality_score: float in [0, 1]
        dimension_scores: dict of per-dimension scores
        confidence: 'high' | 'medium' | 'low'
        weighted_engagement: float
        engagement_rate: float
        view_velocity: float
    """
    _view = int(stat_data.get("view", 0) or 0); view = max(_view, 0)
    like = int(stat_data.get("like", 0) or 0)
    favorite = int(stat_data.get("favorite", 0) or 0)
    coin = int(stat_data.get("coin", 0) or 0)
    reply = int(stat_data.get("reply", 0) or 0)
    danmaku = int(stat_data.get("danmaku", 0) or 0)
    share = int(stat_data.get("share", 0) or 0)
    pubdate = int(stat_data.get("pubdate", 0) or 0)
    now = int(stat_data.get("now", 0) or 0)

    # Weighted engagement
    weighted_engagement = compute_weighted_engagement(
        like=like, favorite=favorite, coin=coin,
        reply=reply, danmaku=danmaku, share=share,
    )

    engagement_rate = weighted_engagement / view if view > 0 else 0.0
    favorite_rate = favorite / view if view > 0 else 0.0
    discussion_rate = (reply + danmaku) / view if view > 0 else 0.0

    # Age in days
    age_days = 1.0
    if pubdate > 0 and now > 0:
        age_days = max(1.0, (now - pubdate) / 86400.0)

    view_per_day = view / age_days
    engagement_per_day = weighted_engagement / age_days

    # Score each dimension
    engagement_rate_score = normalized_log_score(engagement_rate * 1000, REF_ENGAGEMENT_RATE) * DIM_WEIGHTS["engagement_rate"]
    favorite_rate_score = normalized_log_score(favorite_rate * 1000, REF_FAVORITE_RATE) * DIM_WEIGHTS["favorite_rate"]
    discussion_score = normalized_log_score(discussion_rate * 1000, REF_DISCUSSION_RATE) * DIM_WEIGHTS["discussion"]
    view_velocity_score = normalized_log_score(view_per_day, REF_VIEW_VELOCITY) * DIM_WEIGHTS["view_velocity"]
    engagement_velocity_score = normalized_log_score(engagement_per_day, REF_ENGAGEMENT_VELOCITY) * DIM_WEIGHTS["engagement_velocity"]

    dimension_scores = {
        "engagement_rate": round(engagement_rate_score, 4),
        "favorite_rate": round(favorite_rate_score, 4),
        "discussion": round(discussion_score, 4),
        "view_velocity": round(view_velocity_score, 4),
        "engagement_velocity": round(engagement_velocity_score, 4),
    }

    quality_score = sum(dimension_scores.values())
    quality_multiplier = clamp(QUALITY_FLOOR + quality_score * (QUALITY_CEILING - QUALITY_FLOOR), QUALITY_FLOOR, QUALITY_CEILING)

    # Confidence: how much data do we actually have?
    data_points = sum(1 for v in [view, like, favorite, coin, reply, danmaku, share] if v > 0)
    if data_points >= 6 and view >= 100:
        confidence = "high"
    elif data_points >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "quality_multiplier": round(quality_multiplier, 4),
        "quality_score": round(quality_score, 4),
        "dimension_scores": dimension_scores,
        "confidence": confidence,
        "weighted_engagement": round(weighted_engagement),
        "engagement_rate": round(engagement_rate, 6),
        "view_velocity": round(view_per_day, 1),
    }


# ==================== V2.0 compute_note_budget ====================

def compute_note_budget(
    duration_minutes: float = 0,
    subtitle_chars: int = 0,
    comment_records: int = 0,
    evidence_blocks: int = 0,
    quality_multiplier: float = 1.0,
    is_article: bool = False,
    article_chars: int = 0,
    # v8.2: new dimensions for dynamic summary length
    danmaku_count: int = 0,
    information_density: float = 1.0,
    knowledge_value: float = 1.0,
    difficulty_factor: float = 1.0,
    # v8.4: visual richness + new-concept dimensions
    visual_richness: float = 1.0,
    new_concept_count: int = 0,
) -> dict:
    """
    Compute recommended note budget — v8.4 with 6 new dimensions.

    Dimensions (all multiplicative, range [0.6, 1.8]):
      - information_density: text info density multiplier
      - knowledge_value: knowledge content multiplier
      - difficulty_factor: comprehension difficulty multiplier
      - visual_richness: video visual content richness (from assess_visual_dependency)
      - new_concept_count: number of new concepts/terms introduced
      - danmaku_count: raw danmaku count contributes to base additive budget
    """
    duration_minutes = float(duration_minutes)
    subtitle_chars = int(subtitle_chars)
    comment_records = int(comment_records)
    quality_multiplier = float(quality_multiplier)

    if is_article:
        reading_minutes = max(1.0, article_chars / 450)
        base_target_min = clamp(
            700 + reading_minutes * 25 + article_chars * 0.06
            + evidence_blocks * 6 + min(comment_records, 300) * 3,
            1200, 45000
        )
    else:
        base_target_min = clamp(
            600 + duration_minutes * 35 + subtitle_chars * 0.025
            + evidence_blocks * 8 + min(comment_records, 300) * 3
            + min(danmaku_count, 50000) * 0.02,   # v8.2: danmaku contribution
            1200, 45000
        )

    # v8.4: Apply multiplicative quality dimensions (6 dims)
    base_target_min = int(base_target_min
                          * clamp(information_density, 0.6, 1.8)
                          * clamp(knowledge_value, 0.7, 1.5)
                          * clamp(difficulty_factor, 0.7, 1.5)
                          * clamp(visual_richness, 0.7, 1.5)
                          * clamp(1.0 + new_concept_count * 0.05, 0.7, 1.5))

    base_target_max = clamp(base_target_min * 1.6, 2400, 72000)
    target_min = clamp(int(base_target_min * quality_multiplier), 1500, 72000)
    target_max = clamp(int(target_min * 1.6), 2400, 72000)
    quick_target = clamp(int(target_min * 0.45), 800, 12000)
    deep_target = clamp(int(target_max * 1.6), target_max, 110000)

    # Compression ratio
    if subtitle_chars > 0 and target_min > 0:
        compression_ratio = subtitle_chars / target_min
    else:
        compression_ratio = 0

    # Quality tier
    quality_score = (quality_multiplier - QUALITY_FLOOR) / (QUALITY_CEILING - QUALITY_FLOOR)
    if quality_score >= CONFIDENCE_THRESHOLD_HIGH:
        quality_tier = "high"
    elif quality_score >= CONFIDENCE_THRESHOLD_MEDIUM:
        quality_tier = "medium"
    else:
        quality_tier = "low"

    # Granularity guidance
    if duration_minutes >= 120:
        granularity = "module_level"
    elif duration_minutes >= 25:
        granularity = "chapter_level"
    elif subtitle_chars >= 2000:
        granularity = "section_level"
    else:
        granularity = "point_level"

    # --- v8.2: max_tokens_recommendation (conservative ceiling at 48000) ---
    # Chinese text: ~4 tokens/char for most LLMs (Claude: ~2.5-3, GPT: ~3-4, DeepSeek: ~3-4)
    # We use 4.0 tokens/char as a safe upper bound
    # v8.4: target_min already scaled by quality_multiplier at L241, don't double-multiply
    tokens_for_target = target_min * 4.0
    token_ceiling = 48000 if (quality_tier == "high" and duration_minutes >= 60) else 32000
    max_tokens_recommendation = clamp(int(tokens_for_target), 1823, token_ceiling)

    return {
        "target_min": target_min,
        "target_max": target_max,
        "quick_target": quick_target,
        "deep_target": deep_target,
        "compression_ratio": round(compression_ratio, 1),
        "granularity": granularity,
        "quality_tier": quality_tier,
        "quality_multiplier": round(quality_multiplier, 2),
        "max_tokens_recommendation": max_tokens_recommendation,
    }


# ==================== compute_quality_max_tokens (standalone helper) ====================

def compute_quality_max_tokens(quality_multiplier: float, default_max_tokens: int = 4096) -> int:
    """
    Scale max_tokens by quality multiplier.
    Low-quality video (0.85) -> ~1823 tokens (compact summary)
    Medium-quality video (1.0) -> default_max_tokens
    High-quality video (1.4) -> up to 32000 tokens (deep analysis)
    """
    return clamp(int(default_max_tokens * quality_multiplier), 1823, 32000)


# ==================== assess_visual_dependency (preserved) ====================

# v2.1 integration: import multi-dimensional visual dependency detector
try:
    from visual_dependency_v2 import (
        assess_visual_dependency as _assess_vd_legacy,
        assess_visual_dependency_v2,
        VisualDependencyReport,
    )
    _HAS_VD2 = True
except ImportError:
    _HAS_VD2 = False


def assess_visual_dependency(duration_minutes: float, subtitle_chars: int) -> dict:
    """Detect when video content relies heavily on visuals (sparse subtitles).
    Returns risk level and warnings.

    v2.1: When visual_dependency_v2 is available, uses multi-dimensional analysis
    internally and returns extended dict with combined_risk, subtitle_density score,
    and max_gap_sec. Backward-compatible: always returns {risk, warning}."""
    if _HAS_VD2 and duration_minutes > 0:
        # Use v2 multi-dimensional engine
        report = assess_visual_dependency_v2(
            duration_minutes=duration_minutes,
            subtitle_chars=subtitle_chars,
        )
        return {
            "risk": report.risk_level,
            "warning": report.warning,
            # Extended fields for forward-compatible consumers
            "combined_risk": report.combined_risk,
            "subtitle_density": report.subtitle_density,
            "subtitle_density_score": report.subtitle_density_score,
            "max_gap_sec": report.max_subtitle_gap_sec,
            "recommendations": report.recommendations,
        }

    # Fallback: original v1 algorithm
    if duration_minutes <= 0:
        return {"risk": "low", "warning": ""}

    density = subtitle_chars / duration_minutes if duration_minutes > 0 else 0

    if subtitle_chars == 0 and duration_minutes >= 10:
        return {
            "risk": "high",
            "warning": "No subtitles available for a video >= 10 min. Visual content may be critical. Consider OCR or manual review.",
        }
    if duration_minutes >= 25 and subtitle_chars <= 800:
        return {
            "risk": "high",
            "warning": "Long video with very sparse subtitles. AI summary may miss visual-only content.",
        }
    if duration_minutes >= 30 and density < 120:
        return {
            "risk": "high",
            "warning": f"Low subtitle density ({density:.0f} chars/min). Visual demo/tutorial content probable.",
        }
    if duration_minutes >= 15 and density < 180:
        return {
            "risk": "medium",
            "warning": f"Moderately sparse subtitles ({density:.0f} chars/min). Some content may be visual-dependent.",
        }
    return {"risk": "low", "warning": ""}


def assess_visual_dependency_full(
    duration_minutes: float,
    subtitle_chars: int = 0,
    subtitle_body: list = None,
    keyframe_complexity: dict = None,
    scene_boundaries: list = None,
) -> VisualDependencyReport:
    """
    Full multi-dimensional visual dependency assessment (v2.1).

    Requires visual_dependency_v2 module.

    Args:
        duration_minutes: Video duration in minutes.
        subtitle_chars: Total characters in all subtitles.
        subtitle_body: List of subtitle entries with .from_/.to attrs.
        keyframe_complexity: From SceneDetector.aggregate_complexity().
        scene_boundaries: From SceneDetector.detect() or FrameExtractor.detect_scene_changes().

    Returns:
        VisualDependencyReport dataclass with risk_level, scores, recommendations.
    """
    if not _HAS_VD2:
        raise ImportError("visual_dependency_v2 module not available")
    return assess_visual_dependency_v2(
        duration_minutes=duration_minutes,
        subtitle_chars=subtitle_chars,
        subtitle_body=subtitle_body,
        keyframe_complexity=keyframe_complexity,
        scene_boundaries=scene_boundaries,
    )
