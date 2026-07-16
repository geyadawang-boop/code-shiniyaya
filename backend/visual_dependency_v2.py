"""
Visual Dependency Detector v2 — multi-dimensional analysis for detecting
video content that relies on visuals, not just subtitles.

Dimensions:
  1. Subtitle density (chars/min) — original quality.py metric
  2. Keyframe complexity (edge density, saturation, brightness variance)
  3. Scene change frequency (cuts per minute, burstiness)
  4. Subtitle gap analysis (max gap between consecutive subtitles)
  5. Combined visual risk score (weighted ensemble)

This replaces the single-dimension assess_visual_dependency() in quality.py.
"""

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VisualDependencyReport:
    """Complete multi-dimensional visual dependency assessment."""

    # Subtitle density dimension
    subtitle_chars: int = 0
    subtitle_density: float = 0.0            # chars/min
    subtitle_density_score: float = 0.0      # 0-1 (0 = dense text, 1 = sparse)

    # Keyframe complexity dimension
    mean_edge_density: float = 0.0
    mean_saturation: float = 0.0
    mean_brightness_std: float = 0.0
    complex_frame_ratio: float = 0.0          # fraction of frames above edge threshold
    complexity_score: float = 0.0             # 0-1 (0 = simple slides, 1 = complex visuals)

    # Scene change dimension
    scene_count: int = 0
    scenes_per_minute: float = 0.0
    scene_change_score: float = 0.0           # 0-1 (0 = static, 1 = very dynamic)

    # Subtitle gap dimension
    max_subtitle_gap_sec: float = 0.0
    avg_subtitle_gap_sec: float = 0.0
    gap_score: float = 0.0                    # 0-1 (0 = continuous speech, 1 = large gaps)

    # Combined
    combined_risk: float = 0.0                # 0-1 overall risk
    risk_level: str = "low"                   # "low", "medium", "high", "critical"
    warning: str = ""

    # Metadata
    duration_minutes: float = 0.0
    keyframe_count: int = 0

    # Actionable advice
    recommendations: list[str] = field(default_factory=list)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _sigmoid(x: float, midpoint: float = 0.5, steepness: float = 8.0) -> float:
    """Sigmoid mapping for smooth scoring [0,1]."""
    try:
        return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))
    except OverflowError:
        return 0.0 if x < midpoint else 1.0


def assess_visual_dependency_v2(
    duration_minutes: float,
    subtitle_chars: int = 0,
    subtitle_body: list = None,
    keyframe_complexity: Optional[dict] = None,
    scene_boundaries: list = None,
) -> VisualDependencyReport:
    """
    Multi-dimensional visual dependency assessment.

    Args:
        duration_minutes: Video duration in minutes.
        subtitle_chars: Total characters in all subtitles.
        subtitle_body: List of SubtitleEntry with .from_ and .to attributes.
        keyframe_complexity: Output from SceneDetector.aggregate_complexity().
        scene_boundaries: List of scene boundary dicts from SceneDetector.detect().

    Returns:
        VisualDependencyReport with risk level and recommendations.
    """
    report = VisualDependencyReport()
    report.duration_minutes = duration_minutes

    # ------------------------------------------------------------------
    # Dimension 1: Subtitle density
    # ------------------------------------------------------------------
    report.subtitle_chars = subtitle_chars
    if duration_minutes > 0:
        report.subtitle_density = round(subtitle_chars / duration_minutes, 1)
    else:
        report.subtitle_density = 0.0

    # Score: 0 = dense (good), 1 = sparse (concerning)
    if subtitle_chars <= 0 and duration_minutes >= 0.5:
        report.subtitle_density_score = 1.0
    elif report.subtitle_density < 50:
        report.subtitle_density_score = 1.0
    elif report.subtitle_density >= 50 and report.subtitle_density < 120:
        # Sigmoid: ~0.85 at 50, ~0.15 at 120 (smooth decreasing risk with more chars)
        report.subtitle_density_score = _sigmoid(report.subtitle_density, midpoint=85, steepness=-0.05)
    elif report.subtitle_density < 300:
        # Continuous from sigmoid tail at 120 (~0.15) down to 0.05 at 300
        sigmoid_at_120 = _sigmoid(120.0, midpoint=85, steepness=-0.05)
        report.subtitle_density_score = clamp(
            sigmoid_at_120 - (report.subtitle_density - 120) * (sigmoid_at_120 - 0.05) / 180,
            0.05, sigmoid_at_120,
        )
    else:
        report.subtitle_density_score = 0.05  # dense enough

    # ------------------------------------------------------------------
    # Dimension 2: Keyframe complexity
    # ------------------------------------------------------------------
    if keyframe_complexity:
        report.mean_edge_density = keyframe_complexity.get("mean_edge_density", 0.0)
        report.mean_saturation = keyframe_complexity.get("mean_saturation", 0.0)
        report.mean_brightness_std = keyframe_complexity.get("mean_brightness_std", 0.0)
        report.complex_frame_ratio = keyframe_complexity.get("complex_ratio", 0.0)

        # High edge density + high saturation + low brightness std = rich visuals
        # Score: 0 = simple (slides/whiteboard), 1 = complex (real footage/demos)
        edge_term = _sigmoid(report.mean_edge_density, midpoint=0.06, steepness=80.0)
        sat_term = _sigmoid(report.mean_saturation, midpoint=0.15, steepness=15.0)
        # Inverse: low brightness std means uniform slides (high risk)
        bstd_term = 1.0 - _sigmoid(report.mean_brightness_std, midpoint=35.0, steepness=0.1)

        report.complexity_score = round(
            0.45 * edge_term + 0.25 * sat_term + 0.30 * bstd_term, 4
        )
    else:
        # No frame data available
        report.complexity_score = 0.5  # neutral

    # ------------------------------------------------------------------
    # Dimension 3: Scene change frequency
    # ------------------------------------------------------------------
    if scene_boundaries and duration_minutes > 0:
        report.scene_count = len(scene_boundaries)
        report.scenes_per_minute = round(report.scene_count / max(duration_minutes, 0.1), 2)

        # Dynamic videos (many cuts) often have more visual information
        # But very few cuts can mean slides/static content (high visual dep)
        # Score: 0 = many cuts (self-explanatory), 1 = few cuts (visual-dependent)
        if report.scenes_per_minute < 0.5:
            report.scene_change_score = 0.9  # very static, high visual dependency
        elif report.scenes_per_minute < 1.5:
            report.scene_change_score = _sigmoid(report.scenes_per_minute, midpoint=1.0, steepness=-4.0)
        elif report.scenes_per_minute < 5.0:
            report.scene_change_score = max(0.05, 0.6 - (report.scenes_per_minute - 1.5) * 0.15)
        else:
            report.scene_change_score = 0.05  # frequent cuts, self-explanatory
    else:
        report.scene_change_score = 0.5  # neutral

    # ------------------------------------------------------------------
    # Dimension 4: Subtitle gap analysis
    # ------------------------------------------------------------------
    if subtitle_body and len(subtitle_body) > 1:
        gaps = []
        for i in range(1, len(subtitle_body)):
            prev = subtitle_body[i - 1]
            cur = subtitle_body[i]

            # Robust attribute access: prefer .to / .from_, fall back to .end / .start
            # Use explicit None-check rather than 'or' chaining which treats 0 as falsy.
            prev_end = getattr(prev, 'to', None)
            if prev_end is None:
                prev_end = getattr(prev, 'end', None)
            if prev_end is None:
                prev_end = 0.0

            cur_start = getattr(cur, 'from_', None)
            if cur_start is None:
                cur_start = getattr(cur, 'start', None)
            if cur_start is None:
                cur_start = 0.0

            gap = max(0.0, cur_start - prev_end)
            gaps.append(gap)

        if gaps:
            report.max_subtitle_gap_sec = round(max(gaps), 1)
            report.avg_subtitle_gap_sec = round(sum(gaps) / len(gaps), 1)

        # Large gaps = periods of silence = likely visual-only content
        if report.max_subtitle_gap_sec > 120:
            report.gap_score = 0.95
        elif report.max_subtitle_gap_sec > 60:
            # Sigmoid that reaches 0.95 at x=120 (continuous with band above)
            report.gap_score = _sigmoid(report.max_subtitle_gap_sec, midpoint=90, steepness=0.08)
        elif report.max_subtitle_gap_sec > 30:
            report.gap_score = clamp((report.max_subtitle_gap_sec - 30) / 90, 0.1, 0.8)
        elif report.max_subtitle_gap_sec > 10:
            report.gap_score = 0.15
        else:
            report.gap_score = 0.05
    else:
        # No subtitle body data
        if subtitle_chars == 0 and duration_minutes >= 3:
            report.gap_score = 1.0  # No subtitles at all
        else:
            report.gap_score = 0.02

    # ------------------------------------------------------------------
    # Combined risk score (weighted average)
    # ------------------------------------------------------------------
    weights = {
        "density": 0.35,
        "complexity": 0.25,
        "scene": 0.20,
        "gap": 0.20,
    }

    report.combined_risk = round(
        weights["density"] * report.subtitle_density_score
        + weights["complexity"] * report.complexity_score
        + weights["scene"] * report.scene_change_score
        + weights["gap"] * report.gap_score,
        4,
    )

    # --- Risk level ---
    if report.combined_risk >= 0.75:
        report.risk_level = "critical"
    elif report.combined_risk >= 0.55:
        report.risk_level = "high"
    elif report.combined_risk >= 0.35:
        report.risk_level = "medium"
    else:
        report.risk_level = "low"

    # --- Warning message ---
    warnings = []
    if report.subtitle_density_score >= 0.8:
        if subtitle_chars == 0:
            warnings.append("No subtitles available. All content may be visual-only.")
        else:
            warnings.append(f"Extremely sparse subtitles ({report.subtitle_density:.0f} chars/min). AI summary will miss most visual content.")
    if report.gap_score >= 0.7:
        warnings.append(f"Large subtitle gaps detected (max {report.max_subtitle_gap_sec:.0f}s). Silent sections likely contain unreferenced visual demonstrations.")
    if report.complexity_score >= 0.6 and report.subtitle_density_score >= 0.5:
        warnings.append("Complex visuals + sparse speech detected. This is likely a tutorial/demo with heavy visual dependence.")
    if report.scene_change_score >= 0.7:
        warnings.append(f"Very few scene changes ({report.scenes_per_minute:.1f}/min). Content may be static slides or single-scene demonstrations.")
    if report.subtitle_density_score >= 0.5 and report.gap_score >= 0.6:
        warnings.append("Combined sparse text and large gaps. High probability of missing key visual information.")

    if warnings:
        report.warning = " | ".join(warnings)
    elif report.risk_level == "low":
        report.warning = ""
    else:
        report.warning = "Moderate visual dependency detected. Consider reviewing keyframes."

    # --- Recommendations ---
    if report.risk_level in ("high", "critical"):
        report.recommendations.append("Enable keyframe extraction to inject visual context into AI summary.")
        report.recommendations.append("Generate visual scene descriptions using a vision-capable model.")
        report.recommendations.append("Lower scene detection threshold to capture more visual boundaries.")
    if report.complexity_score >= 0.6:
        report.recommendations.append("Extract high-complexity keyframes for AI visual reference.")
    if report.gap_score >= 0.5:
        report.recommendations.append("Flag silent segments for manual review or OCR processing.")

    return report


# ------------------------------------------------------------------
# Legacy compatibility wrapper (replaces quality.py's original)
# ------------------------------------------------------------------

def assess_visual_dependency(
    duration_minutes: float,
    subtitle_chars: int,
    subtitle_body: list = None,
) -> dict:
    """
    Legacy-compatible wrapper. Returns the same dict format as the original
    quality.py function but powered by v2 multi-dimensional analysis.

    Accepts optional subtitle_body to enable gap analysis.
    """
    report = assess_visual_dependency_v2(
        duration_minutes=duration_minutes,
        subtitle_chars=subtitle_chars,
        subtitle_body=subtitle_body,
    )
    return {
        "risk": report.risk_level,
        "warning": report.warning,
        # Extended fields (forward-compatible)
        "combined_risk": report.combined_risk,
        "subtitle_density": report.subtitle_density,
        "subtitle_density_score": report.subtitle_density_score,
        "max_gap_sec": report.max_subtitle_gap_sec,
        "recommendations": report.recommendations,
    }
