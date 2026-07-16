"""
AI Visual Reference — injects keyframe descriptions and visual context into
the AI summarization prompt so the model can reference actual video frames.

Architecture:
  1. Extract keyframes (via FrameExtractor) and scene boundaries
  2. (Optional) Call a vision-capable model to generate frame descriptions
  3. Build a structured "visual context block" for injection into the prompt
  4. Annotate timestamps so the summary can reference specific frames

Cross-leverage points:
  - FrameExtractor: source of keyframes and scene boundaries
  - ThumbnailGenerator: base64 images for vision model consumption
  - summarizer.build_prompt(): receives the visual_context_block
  - quality.py / visual_dependency_v2: determines IF visual reference is needed
  - bili-note: can embed frame references in knowledge notes
"""

import base64
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FrameDescription:
    """A text description of a video frame (AI-generated or heuristic)."""
    timestamp_sec: float
    timestamp_label: str                    # "MM:SS"
    description: str                        # AI-generated or rule-based
    frame_path: str = ""                    # local path to jpg
    base64: str = ""                        # for vision API
    scene_type: str = "unknown"             # "keyframe", "scene_change", "uniform"
    confidence: float = 0.0                 # scene change confidence if applicable
    edge_density: float = 0.0               # visual complexity indicator


@dataclass
class VisualContextBlock:
    """A structured block of visual information for prompt injection."""
    video_title: str = ""
    duration_label: str = ""                # "12:34"
    total_frames: int = 0
    keyframe_count: int = 0
    scene_count: int = 0
    visual_risk: str = "low"

    # Core content
    frame_descriptions: list[FrameDescription] = field(default_factory=list)

    # Metadata
    scene_timeline: list[dict] = field(default_factory=list)
    thumbnail_base64: str = ""
    visual_summary: str = ""                # high-level visual summary

    @property
    def is_empty(self) -> bool:
        return len(self.frame_descriptions) == 0 and not self.visual_summary


class VisualReferenceBuilder:
    """
    Builds a visual context block for prompt injection.

    Two modes:
      1. heuristic — uses edge density / scene stats (no vision API needed)
      2. vision_api — calls a vision model to describe each keyframe

    Usage:
        builder = VisualReferenceBuilder(mode="heuristic")
        block = builder.build(keyframes, scene_boundaries, complexity_data)
        prompt_section = builder.render_to_prompt(block)
    """

    def __init__(
        self,
        mode: str = "heuristic",            # "heuristic" | "vision_api"
        api_key: str = "",
        api_url: str = "",
        model: str = "",
        max_description_frames: int = 6,
    ):
        self.mode = mode
        self.api_key = api_key
        self.api_url = api_url
        self.model = model or "claude-haiku-3-5"
        self.max_frames = max_description_frames

    def build(
        self,
        keyframes: list = None,
        scene_boundaries: list = None,
        complexity_data: dict = None,
        video_title: str = "",
        duration_sec: float = 0,
        thumbnail_base64: str = "",
    ) -> VisualContextBlock:
        """
        Build a visual context block from frame data.

        Args:
            keyframes: List of FrameInfo from FrameExtractor.
            scene_boundaries: List of SceneBoundary or dict from SceneDetector.
            complexity_data: Output from SceneDetector.aggregate_complexity().
            video_title: Video title for context.
            duration_sec: Total duration in seconds.
            thumbnail_base64: Optional cover thumbnail in base64.

        Returns:
            VisualContextBlock ready for prompt injection.
        """
        block = VisualContextBlock(
            video_title=video_title,
            duration_label=self._format_duration(duration_sec),
            thumbnail_base64=thumbnail_base64,
        )

        if keyframes:
            block.keyframe_count = len(keyframes)
        if scene_boundaries:
            block.scene_count = len(scene_boundaries)

        # Build scene timeline
        if scene_boundaries:
            block.scene_timeline = self._build_scene_timeline(scene_boundaries, duration_sec)
            block.total_frames = len(scene_boundaries) + 1  # rough

        # Build frame descriptions
        frame_descriptions = []

        # Priority 1: Scene change boundaries (most informative)
        if scene_boundaries:
            top_boundaries = self._select_top_scenes(scene_boundaries, max_count=self.max_frames // 2)
            for b in top_boundaries:
                ts = b.get("timestamp_sec", 0) if isinstance(b, dict) else getattr(b, "timestamp_sec", 0)
                conf = b.get("confidence", 0) if isinstance(b, dict) else getattr(b, "confidence", 0)
                frame_descriptions.append(FrameDescription(
                    timestamp_sec=ts,
                    timestamp_label=self._format_duration(ts),
                    scene_type="scene_change",
                    confidence=round(conf, 3),
                    description=""
                ))

        # Priority 2: Keyframes (use timestamps to deduplicate against scenes)
        if keyframes:
            scene_ts_set = {fd.timestamp_sec for fd in frame_descriptions}
            deduped_keyframes = []
            for kf in keyframes[:self.max_frames]:
                kf_ts = getattr(kf, "timestamp_sec", 0)
                # Check if within 2 seconds of an existing scene boundary
                too_close = any(abs(kf_ts - t) < 2.0 for t in scene_ts_set)
                if not too_close:
                    deduped_keyframes.append(kf)

            remaining_slots = self.max_frames - len(frame_descriptions)
            for kf in deduped_keyframes[:max(0, remaining_slots)]:
                kf_ts = getattr(kf, "timestamp_sec", 0)
                kf_path = getattr(kf, "path", "")
                frame_descriptions.append(FrameDescription(
                    timestamp_sec=kf_ts,
                    timestamp_label=self._format_duration(kf_ts),
                    scene_type="keyframe",
                    frame_path=kf_path,
                    base64=self._encode_image(kf_path) if kf_path else "",
                ))

        # Generate descriptions
        if self.mode == "vision_api" and self.api_key:
            block.frame_descriptions = self._generate_vision_descriptions(frame_descriptions)
        else:
            block.frame_descriptions = self._generate_heuristic_descriptions(
                frame_descriptions, complexity_data
            )

        # Build visual summary
        block.visual_summary = self._build_visual_summary(block)

        # Set visual risk
        block.visual_risk = self._assess_risk_from_context(block)

        return block

    # ------------------------------------------------------------------
    # Timeline builder
    # ------------------------------------------------------------------

    def _build_scene_timeline(self, boundaries: list, duration: float) -> list[dict]:
        """Build a human-readable scene timeline."""
        timeline = []
        prev_ts = 0.0
        for i, b in enumerate(boundaries):
            ts = b.get("timestamp_sec", 0) if isinstance(b, dict) else getattr(b, "timestamp_sec", 0)
            conf = b.get("confidence", 0) if isinstance(b, dict) else getattr(b, "confidence", 0)
            duration_seg = ts - prev_ts
            timeline.append({
                "segment": i + 1,
                "start": self._format_duration(prev_ts),
                "end": self._format_duration(ts),
                "duration_sec": round(duration_seg, 1),
                "confidence": round(conf, 3),
            })
            prev_ts = ts

        if duration > prev_ts:
            timeline.append({
                "segment": len(boundaries) + 1,
                "start": self._format_duration(prev_ts),
                "end": self._format_duration(duration),
                "duration_sec": round(duration - prev_ts, 1),
                "confidence": 0,
            })

        return timeline

    def _select_top_scenes(self, boundaries: list, max_count: int) -> list:
        """Select the most significant scene boundaries by confidence."""
        sorted_b = sorted(
            boundaries,
            key=lambda b: b.get("confidence", 0) if isinstance(b, dict) else getattr(b, "confidence", 0),
            reverse=True,
        )
        return sorted_b[:max_count]

    # ------------------------------------------------------------------
    # Description generators
    # ------------------------------------------------------------------

    def _generate_heuristic_descriptions(
        self,
        frame_descriptions: list[FrameDescription],
        complexity_data: dict = None,
    ) -> list[FrameDescription]:
        """Generate heuristic descriptions based on position and complexity."""
        for fd in frame_descriptions:
            if fd.scene_type == "scene_change":
                fd.description = (
                    f"Scene transition at {fd.timestamp_label} "
                    f"(confidence: {fd.confidence:.0%})"
                )
            elif fd.scene_type == "keyframe":
                fd.description = (
                    f"Keyframe at {fd.timestamp_label} — visual reference point"
                )
            else:
                fd.description = f"Frame at {fd.timestamp_label}"

        # Enrich with complexity context if available
        if complexity_data and frame_descriptions:
            edge_d = complexity_data.get("mean_edge_density", 0)
            sat = complexity_data.get("mean_saturation", 0)
            complex_r = complexity_data.get("complex_ratio", 0)

            for fd in frame_descriptions:
                fd.edge_density = edge_d
                if complex_r > 0.4:
                    fd.description += " [visually complex: likely demo/tutorial content]"
                elif edge_d < 0.03:
                    fd.description += " [low complexity: likely slides/text content]"

        return frame_descriptions

    def _generate_vision_descriptions(
        self,
        frame_descriptions: list[FrameDescription],
    ) -> list[FrameDescription]:
        """
        Stub for vision API integration. In production, this calls an LLM
        with vision capabilities (Claude, GPT-4V) to describe each frame.

        Implementation pattern (non-blocking):
        ```
        async def _call_vision_api(frame: FrameDescription) -> str:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{self.api_url}/...",
                    json={
                        "model": self.model,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "image", "source": {"type": "base64",
                                 "media_type": "image/jpeg", "data": frame.base64}},
                                {"type": "text", "text": "Describe this video frame in one sentence in Chinese. Focus on what is being shown, demonstrated, or explained visually."}
                            ]
                        }]
                    }
                )
                return r.json()["content"][0]["text"]
        ```
        """
        for fd in frame_descriptions:
            fd.description = (
                f"[Frame at {fd.timestamp_label}] "
                f"Visual content at this timestamp. "
                f"{'Scene transition detected.' if fd.scene_type == 'scene_change' else 'Key reference frame.'}"
            )
        return frame_descriptions

    # ------------------------------------------------------------------
    # Visual summary
    # ------------------------------------------------------------------

    def _build_visual_summary(self, block: VisualContextBlock) -> str:
        """Generate a high-level visual summary paragraph."""
        if block.is_empty:
            return ""

        parts = [f"视频共检测到 {block.scene_count} 个场景切换，提取了 {block.keyframe_count} 个关键帧。"]

        # Summarize scene timeline
        if block.scene_timeline:
            parts.append("场景时间线：")
            for seg in block.scene_timeline[:8]:
                parts.append(
                    f"  - 片段{seg['segment']}: {seg['start']}-{seg['end']} "
                    f"({seg['duration_sec']:.0f}秒)"
                )
            if len(block.scene_timeline) > 8:
                parts.append(f"  ... (共{len(block.scene_timeline)}个片段)")

        # Frame reference points
        if block.frame_descriptions:
            parts.append("关键时间点：")
            for fd in block.frame_descriptions:
                parts.append(f"  - [{fd.timestamp_label}] {fd.description}")

        return "\n".join(parts)

    def _assess_risk_from_context(self, block: VisualContextBlock) -> str:
        """Quick risk assessment from context data."""
        if block.scene_count <= 1 and block.keyframe_count > 0:
            return "high"  # few scene changes = potentially visual-heavy content
        if block.scene_count >= 10:
            return "low"   # frequent changes = self-explanatory pacing
        return "medium"

    # ------------------------------------------------------------------
    # Prompt rendering
    # ------------------------------------------------------------------

    def render_to_prompt(self, block: VisualContextBlock) -> str:
        """
        Convert a VisualContextBlock into a string for prompt injection.

        The output is designed to be prepended or appended to the existing
        summarizer.build_prompt() output.
        """
        if block.is_empty and not block.visual_summary:
            return ""

        lines = ["\n\n=== VISUAL CONTEXT (video frames analysis) ==="]

        if block.visual_summary:
            lines.append(block.visual_summary)

        if block.frame_descriptions:
            lines.append("\n视觉参考帧描述：")
            for i, fd in enumerate(block.frame_descriptions):
                lines.append(
                    f"  Frame {i+1} [{fd.timestamp_label}] [{fd.scene_type}]: "
                    f"{fd.description}"
                )

        if block.scene_timeline:
            lines.append(f"\n场景结构：{len(block.scene_timeline)} 个片段")

        lines.append("\nINSTRUCTIONS: When summarizing, reference these timestamps")
        lines.append("when the visual context adds meaning to the transcript.")
        lines.append("If a scene transition coincides with a topic change, note it.")
        lines.append("=== END VISUAL CONTEXT ===\n")

        return "\n".join(lines)

    def render_to_note(self, block: VisualContextBlock) -> str:
        """
        Render visual context as a Markdown note section (for bili-note integration).
        """
        if block.is_empty:
            return ""

        lines = [
            "\n## 视频画面分析",
            "",
            f"> 场景切换: {block.scene_count} | 关键帧: {block.keyframe_count} | 视觉依赖风险: {block.visual_risk}",
            "",
        ]

        if block.scene_timeline:
            lines.append("### 场景时间线")
            lines.append("| 片段 | 时间 | 时长 |")
            lines.append("|------|------|------|")
            for seg in block.scene_timeline[:10]:
                lines.append(f"| {seg['segment']} | {seg['start']}-{seg['end']} | {seg['duration_sec']}s |")
            lines.append("")

        if block.frame_descriptions:
            lines.append("### 关键帧参考")
            for fd in block.frame_descriptions:
                lines.append(f"- **[{fd.timestamp_label}]** {fd.description}")
            lines.append("")

        if block.visual_summary:
            lines.append(f"> {block.visual_summary}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format seconds as MM:SS or HH:MM:SS."""
        s = max(0, int(seconds))
        h, m, s = s // 3600, (s % 3600) // 60, s % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    @staticmethod
    def _encode_image(path: str) -> str:
        """Encode image file to base64 (without data URI prefix)."""
        if not path or not os.path.exists(path):
            return ""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
