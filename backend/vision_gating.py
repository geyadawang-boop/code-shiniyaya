"""
vision_gating.py — failure/cost gating for vision-based frame analysis.

Vision (画面抓取 + vision API frame description) runs ONLY when ALL of:
  (a) a vision API key is configured (settings `vision_api_key`, falling back
      to `dashscope_api_key` setting, then DASHSCOPE_API_KEY env var);
  (b) the video is shorter than 30 minutes (cost ceiling);
  (c) the user-facing 画面抓取 setting (`enable_frame_capture`) is ON.
      Default when the setting has never been written: ON if a dashscope key
      exists, OFF otherwise.

Adaptive frame budget when the gate passes:
    duration < 5 min   -> 6 frames
    duration < 15 min  -> 10 frames
    otherwise (<30min) -> 12 frames

Usage (e.g. in unified_pipeline.py / routers/ai.py):

    from vision_gating import check_vision_gate

    gate = check_vision_gate(duration_sec)
    if gate.allowed:
        builder = VisualReferenceBuilder(
            mode="vision_api",
            api_key=gate.api_key,
            max_description_frames=gate.frame_count,
        )
    else:
        # fall back to heuristic mode (no vision API cost)
        builder = VisualReferenceBuilder(mode="heuristic")
        logger.info("vision gated off: %s", gate.reason)
"""

import os
from dataclasses import dataclass

import database as db

# ---------------------------------------------------------------------------
# Constants (no magic numbers inline)
# ---------------------------------------------------------------------------

VISION_MAX_DURATION_SEC = 30 * 60      # (b) hard cost ceiling: 30 minutes

FRAME_TIER_SHORT_SEC = 5 * 60          # < 5 min
FRAME_TIER_MEDIUM_SEC = 15 * 60        # < 15 min

FRAMES_SHORT = 6
FRAMES_MEDIUM = 10
FRAMES_LONG = 12

SETTING_VISION_API_KEY = "vision_api_key"        # dedicated vision key
SETTING_DASHSCOPE_KEY = "dashscope_api_key"      # shared dashscope key
SETTING_FRAME_CAPTURE = "enable_frame_capture"   # 画面抓取 toggle ("1"/"0")

_TRUTHY = {"1", "true", "on", "yes"}
_FALSY = {"0", "false", "off", "no"}


# ---------------------------------------------------------------------------
# Decision object
# ---------------------------------------------------------------------------

@dataclass
class VisionGateDecision:
    """Outcome of the vision gate for one video."""
    allowed: bool
    reason: str                 # machine-readable: ok | setting_off | no_api_key | too_long
    reason_zh: str              # user-facing Chinese explanation
    frame_count: int = 0        # adaptive budget, 0 when gated off
    duration_sec: float = 0.0
    api_key: str = ""           # resolved key (empty when gated off)


# ---------------------------------------------------------------------------
# Key + setting resolution
# ---------------------------------------------------------------------------

def _dashscope_key() -> str:
    """Dashscope key from settings, else the SDK's env var."""
    return (
        db.get_setting(SETTING_DASHSCOPE_KEY, "").strip()
        or os.environ.get("DASHSCOPE_API_KEY", "").strip()
    )


def get_vision_api_key() -> str:
    """Resolve the key used for vision calls.

    Dedicated `vision_api_key` setting wins; otherwise reuse the dashscope
    key (qwen-vl models accept it).
    """
    return db.get_setting(SETTING_VISION_API_KEY, "").strip() or _dashscope_key()


def frame_capture_enabled() -> bool:
    """(c) 画面抓取 user setting.

    Explicit value wins. If the user has never touched the setting,
    default ON when a dashscope key exists, OFF otherwise — so users
    without a key never pay a failed-vision-call penalty.
    """
    raw = db.get_setting(SETTING_FRAME_CAPTURE, "").strip().lower()
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return bool(_dashscope_key())  # unset -> keyed default


# ---------------------------------------------------------------------------
# Adaptive frame budget
# ---------------------------------------------------------------------------

def adaptive_frame_count(duration_sec: float) -> int:
    """Frame budget scaled to video length (only meaningful under 30 min)."""
    if duration_sec < FRAME_TIER_SHORT_SEC:
        return FRAMES_SHORT
    if duration_sec < FRAME_TIER_MEDIUM_SEC:
        return FRAMES_MEDIUM
    return FRAMES_LONG


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def check_vision_gate(duration_sec: float) -> VisionGateDecision:
    """Decide whether vision frame analysis may run for this video.

    Checks are ordered cheapest-first and by most-actionable feedback:
    user toggle -> key presence -> duration ceiling.
    Never raises; a gated-off decision is a normal outcome.
    """
    duration_sec = max(0.0, float(duration_sec or 0))

    # (c) user toggle (画面抓取)
    if not frame_capture_enabled():
        return VisionGateDecision(
            allowed=False,
            reason="setting_off",
            reason_zh="画面抓取已关闭（可在设置中开启）",
            duration_sec=duration_sec,
        )

    # (a) vision API key configured
    api_key = get_vision_api_key()
    if not api_key:
        return VisionGateDecision(
            allowed=False,
            reason="no_api_key",
            reason_zh="未配置视觉模型 API Key（vision_api_key / DashScope Key）",
            duration_sec=duration_sec,
        )

    # (b) cost ceiling: strictly under 30 minutes
    if duration_sec >= VISION_MAX_DURATION_SEC:
        return VisionGateDecision(
            allowed=False,
            reason="too_long",
            reason_zh=(
                f"视频时长 {duration_sec / 60:.0f} 分钟，超过画面分析上限 "
                f"{VISION_MAX_DURATION_SEC // 60} 分钟，已跳过以控制成本"
            ),
            duration_sec=duration_sec,
        )

    return VisionGateDecision(
        allowed=True,
        reason="ok",
        reason_zh="画面分析已启用",
        frame_count=adaptive_frame_count(duration_sec),
        duration_sec=duration_sec,
        api_key=api_key,
    )
