"""
FrameExtractor - ffmpeg-based video frame extraction with three strategies:
  1. Keyframe (I-frame) extraction — fastest, lossless reference points
  2. Uniform sampling — evenly spaced thumbnails at configurable intervals
  3. Scene-change detection — boundary frames where visual content shifts

Requirements: ffmpeg must be on PATH or configured via FFMPEG_BIN.

Change log (v7.2):
  - atexit + __del__ + context-manager auto-cleanup of temp directories
  - subprocess.run() return codes now checked; non-zero raises RuntimeError
  - scene log file cleaned up alongside frame output directory
  - `import glob` moved to module level
"""

import subprocess
import os
import re
import json
import tempfile
import shutil
import atexit
import glob as _glob
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable


FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"


@dataclass
class FrameInfo:
    """Metadata for a single extracted frame."""
    path: str                          # absolute path to .jpg file
    timestamp_sec: float               # seconds from video start
    frame_type: str = "I"              # I, P, B (ffmpeg pict_type) or "uniform"/"scene"
    file_size: int = 0                 # bytes
    width: int = 0
    height: int = 0


@dataclass
class SceneBoundary:
    """A detected scene change boundary."""
    timestamp_sec: float
    confidence: float                  # 0.0-1.0, higher = more likely a real cut
    prev_frame_path: str = ""
    next_frame_path: str = ""
    diff_score: float = 0.0            # raw histogram difference


@dataclass
class ExtractionResult:
    """Aggregated result from a frame extraction run."""
    video_path: str
    duration_sec: float
    total_frames: int
    fps: float
    keyframes: list[FrameInfo] = field(default_factory=list)
    uniform_frames: list[FrameInfo] = field(default_factory=list)
    scene_boundaries: list[SceneBoundary] = field(default_factory=list)
    thumbnails: list[FrameInfo] = field(default_factory=list)


class FrameExtractor:
    """
    Extracts frames from a video file using ffmpeg.

    Usage:
        extractor = FrameExtractor(video_path="/path/to/video.mp4", output_dir="/tmp/frames")
        result = extractor.extract_keyframes(max_count=20)
        result = extractor.extract_uniform(interval_sec=30)
        boundaries = extractor.detect_scene_changes(threshold=0.35)
        thumb = extractor.generate_thumbnail(timestamp=10.5)
        extractor.cleanup()  # or use as context manager / let atexit handle it

    Cleanup is automatic in three ways:
        1. ``with FrameExtractor(...) as fe:`` (context manager)
        2. ``__del__`` garbage-collector hook
        3. ``atexit`` registration (best-effort; only for tempdir-owned dirs)
    """

    _atexit_cleanups: set[str] = set()  # class-level registry to avoid double-cleanup

    def __init__(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        ffmpeg_bin: str = FFMPEG_BIN,
        ffprobe_bin: str = FFPROBE_BIN,
    ):
        self.video_path = os.path.abspath(video_path)
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        self._owns_tempdir = False
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="bili_frames_")
            self._owns_tempdir = True
            FrameExtractor._atexit_cleanups.add(output_dir)

        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

        self.ffmpeg = ffmpeg_bin
        self.ffprobe = ffprobe_bin

        # Lazy-loaded probe data
        self._probe: Optional[dict] = None
        self._duration: Optional[float] = None
        self._fps: Optional[float] = None
        self._total_frames: Optional[int] = None
        self._width: Optional[int] = None
        self._height: Optional[int] = None

        self._cleaned = False  # prevent double-cleanup from __del__ + atexit

    # ------------------------------------------------------------------
    # Context manager + auto-cleanup
    # ------------------------------------------------------------------

    def __enter__(self) -> "FrameExtractor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()
        return False

    def __del__(self) -> None:
        self.cleanup()

    @classmethod
    def _atexit_flush(cls) -> None:
        """Remove all temp directories registered at class level."""
        for d in list(cls._atexit_cleanups):
            if os.path.isdir(d):
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass
            cls._atexit_cleanups.discard(d)

    # ------------------------------------------------------------------
    # Probe helpers
    # ------------------------------------------------------------------

    def _run_ffprobe(self) -> dict:
        """Run ffprobe -show_streams -show_format and return parsed JSON."""
        cmd = [
            self.ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            self.video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr[:500]}")
        return json.loads(result.stdout)

    @property
    def probe(self) -> dict:
        if self._probe is None:
            self._probe = self._run_ffprobe()
        return self._probe

    @property
    def duration_sec(self) -> float:
        if self._duration is None:
            fmt = self.probe.get("format", {})
            dur_str = fmt.get("duration")
            if dur_str:
                self._duration = float(dur_str)
            else:
                # Fallback: sum stream durations
                self._duration = sum(
                    float(s.get("duration", 0))
                    for s in self.probe.get("streams", [])
                    if "duration" in s
                )
        return self._duration or 0.0

    @property
    def video_stream(self) -> dict:
        for s in self.probe.get("streams", []):
            if s.get("codec_type") == "video":
                return s
        return {}

    @property
    def fps(self) -> float:
        if self._fps is None:
            vs = self.video_stream
            fps_str = vs.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = fps_str.split("/", 1)
                self._fps = float(num) / max(float(den), 1)
            else:
                self._fps = float(fps_str) or 30.0
        return self._fps

    @property
    def total_frames(self) -> int:
        if self._total_frames is None:
            vs = self.video_stream
            nb = vs.get("nb_frames")
            if nb:
                self._total_frames = int(nb)
            else:
                self._total_frames = int(self.duration_sec * self.fps)
        return self._total_frames

    @property
    def width(self) -> int:
        if self._width is None:
            self._width = self.video_stream.get("width", 0)
        return self._width

    @property
    def height(self) -> int:
        if self._height is None:
            self._height = self.video_stream.get("height", 0)
        return self._height

    # ------------------------------------------------------------------
    # Strategy 1: Keyframe (I-frame) extraction
    # ------------------------------------------------------------------

    def extract_keyframes(
        self,
        max_count: int = 30,
        quality: int = 2,
        scale_width: int = 640,
    ) -> list[FrameInfo]:
        """
        Extract actual I-frames (keyframes) from the video.
        Uses ffmpeg's `select='eq(pict_type,I)'` filter — lossless, fastest.

        Args:
            max_count: Cap number of keyframes (0 = unlimited).
            quality: JPEG quality 2-31 (2 = best).
            scale_width: Resize width maintaining aspect ratio.

        Returns:
            List of FrameInfo for each extracted keyframe.
        """
        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        pattern = os.path.join(self.output_dir, f"{basename}_kf_%04d.jpg")

        vf_parts = [
            f"select='eq(pict_type,I)'",
            f"scale={scale_width}:-1",
        ]
        vf = ",".join(vf_parts)

        cmd = [
            self.ffmpeg,
            "-y",
            "-v", "quiet",
            "-skip_frame", "nokey",
            "-i", self.video_path,
            "-vsync", "vfr",
            "-vf", vf,
            "-q:v", str(quality),
            "-frame_pts", "1",
        ]
        if max_count > 0:
            cmd.extend(["-frames:v", str(max_count)])
        cmd.append(pattern)

        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)

        return self._collect_frames(pattern.replace("%04d", "*"), "I")

    # ------------------------------------------------------------------
    # Strategy 2: Uniform sampling
    # ------------------------------------------------------------------

    def extract_uniform(
        self,
        interval_sec: float = 30.0,
        max_count: int = 60,
        quality: int = 3,
        scale_width: int = 640,
    ) -> list[FrameInfo]:
        """
        Extract frames at uniform intervals across the entire video.

        Args:
            interval_sec: Seconds between each sampled frame.
            max_count: Hard cap on number of frames.
            quality: JPEG compression quality 2-31.
            scale_width: Resize width.

        Returns:
            List of FrameInfo in chronological order.
        """
        dur = self.duration_sec
        if dur <= 0:
            return []

        # If the video is short, reduce interval
        n_planned = max(1, int(dur / interval_sec))
        if n_planned > max_count:
            interval_sec = dur / max_count

        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        pattern = os.path.join(self.output_dir, f"{basename}_uf_%04d.jpg")

        # Use fps filter for precise uniform sampling
        target_fps = 1.0 / max(interval_sec, 0.5)
        vf = f"fps={target_fps:.4f},scale={scale_width}:-1"

        cmd = [
            self.ffmpeg,
            "-y",
            "-v", "quiet",
            "-i", self.video_path,
            "-vf", vf,
            "-q:v", str(quality),
            "-vsync", "vfr",
            "-frame_pts", "1",
        ]
        if max_count > 0:
            cmd.extend(["-frames:v", str(max_count)])
        cmd.append(pattern)

        subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=True)

        return self._collect_frames(pattern.replace("%04d", "*"), "uniform")

    # ------------------------------------------------------------------
    # Strategy 3: Scene change detection via histogram comparison
    # ------------------------------------------------------------------

    def detect_scene_changes(
        self,
        threshold: float = 0.35,
        min_scene_len_sec: float = 2.0,
        max_scenes: int = 50,
        scale_width: int = 320,
        pre_extract: bool = True,
    ) -> list[SceneBoundary]:
        """
        Detect scene changes using ffmpeg's scene filter (histogram differencing).

        Uses the `scdet` filter which computes a score between 0.0 and 1.0 for
        each frame's visual difference from the previous. A high score means
        a likely scene cut.

        Args:
            threshold: Scene detection sensitivity (0.0-1.0, lower = more sensitive).
            min_scene_len_sec: Minimum scene duration to avoid false positives.
            max_scenes: Cap on number of detected scenes.
            scale_width: Width for diff computation (lower = faster).
            pre_extract: If True, also extract the boundary keyframes to disk.

        Returns:
            List of SceneBoundary objects sorted by timestamp.
        """
        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        scene_log = os.path.join(self.output_dir, f"{basename}_scenes.txt")

        if pre_extract:
            scene_frame_pattern = os.path.join(self.output_dir, f"{basename}_sc_%04d.jpg")
            vf = (
                f"scale={scale_width}:-1,"
                f"scdet=threshold={threshold:.4f}:sc_pass=1,"
                f"metadata=print:file='{scene_log.replace(os.sep, '/')}'"
            )
            cmd = [
                self.ffmpeg,
                "-y",
                "-v", "quiet",
                "-i", self.video_path,
                "-vf", vf,
                "-vsync", "vfr",
                "-an",
                "-frame_pts", "1",
                "-f", "null",
                "-",
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)
        else:
            # Faster: only log scene changes, no frame output
            vf = (
                f"scdet=threshold={threshold:.4f}:sc_pass=1,"
                f"metadata=print:file='{scene_log.replace(os.sep, '/')}'"
            )
            cmd = [
                self.ffmpeg,
                "-y",
                "-v", "quiet",
                "-i", self.video_path,
                "-vf", vf,
                "-vsync", "vfr",
                "-an",
                "-f", "null",
                "-",
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)

        # Parse scene log
        boundaries = self._parse_scene_log(scene_log)

        # Filter by min scene length
        if min_scene_len_sec > 0 and len(boundaries) > 1:
            filtered = [boundaries[0]]
            for b in boundaries[1:]:
                if (b.timestamp_sec - filtered[-1].timestamp_sec) >= min_scene_len_sec:
                    filtered.append(b)
            boundaries = filtered

        return boundaries[:max_scenes]

    def _parse_scene_log(self, log_path: str) -> list[SceneBoundary]:
        """Parse ffmpeg scdet metadata log into SceneBoundary objects."""
        boundaries: list[SceneBoundary] = []
        if not os.path.exists(log_path):
            return boundaries

        current_ts = 0.0
        current_score = 0.0

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                # frame:XXX pts:XXXX pts_time:XX.XXXX
                m_pts = re.search(r"pts_time:([0-9.]+)", line)
                if m_pts:
                    current_ts = float(m_pts.group(1))
                # lavfi.scd.score=0.XXXXXX
                m_score = re.search(r"lavfi\.scd\.score=([0-9.]+)", line)
                if m_score:
                    current_score = float(m_score.group(1))
                    if current_score >= 0.01:  # any non-trivial change
                        boundaries.append(SceneBoundary(
                            timestamp_sec=current_ts,
                            confidence=min(current_score, 1.0),
                            diff_score=current_score,
                        ))

        return boundaries

    # ------------------------------------------------------------------
    # Strategy 4: Thumbnail generation
    # ------------------------------------------------------------------

    def generate_thumbnail(
        self,
        timestamp_sec: Optional[float] = None,
        quality: int = 2,
        width: int = 480,
    ) -> Optional[FrameInfo]:
        """
        Generate a single thumbnail at a specific timestamp.
        If timestamp is None, uses the video's midpoint.

        Args:
            timestamp_sec: Timestamp in seconds. None = midpoint.
            quality: JPEG quality 2-31.
            width: Output width in pixels.

        Returns:
            FrameInfo or None if extraction failed.
        """
        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        ts_label = f"{timestamp_sec:.1f}s" if timestamp_sec else "mid"
        out_path = os.path.join(self.output_dir, f"{basename}_thumb_{ts_label}.jpg")

        if timestamp_sec is None:
            timestamp_sec = self.duration_sec / 2.0

        timestamp_sec = max(0, min(timestamp_sec, self.duration_sec))

        cmd = [
            self.ffmpeg,
            "-y",
            "-v", "quiet",
            "-ss", str(timestamp_sec),
            "-i", self.video_path,
            "-vf", f"scale={width}:-1",
            "-q:v", str(quality),
            "-vframes", "1",
            "-vsync", "vfr",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode != 0 or not os.path.exists(out_path):
            return None

        return FrameInfo(
            path=out_path,
            timestamp_sec=timestamp_sec,
            frame_type="thumbnail",
            file_size=os.path.getsize(out_path),
            width=width,
            height=int(width * self.height / max(self.width, 1)),
        )

    def generate_thumbnails_grid(
        self,
        cols: int = 4,
        rows: int = 2,
        interval_sec: Optional[float] = None,
        quality: int = 3,
        width: int = 320,
    ) -> list[FrameInfo]:
        """
        Generate a grid of thumbnails from evenly-spaced timestamps.

        Args:
            cols, rows: Grid dimensions (total = cols * rows thumbnails).
            interval_sec: Spacing between thumbnails. Auto-computed if None.
            quality, width: Passed to generate_thumbnail.

        Returns:
            List of FrameInfo in chronological order.
        """
        total = cols * rows
        dur = self.duration_sec
        if interval_sec is None:
            # Skip first and last 5% to avoid intros/outros
            effective_dur = dur * 0.9
            interval_sec = effective_dur / max(total, 1)

        thumbnails = []
        start = dur * 0.05  # skip 5% intro
        end = dur * 0.95    # skip 5% outro

        for i in range(total):
            ts = start + i * interval_sec
            if ts > end:
                break
            info = self.generate_thumbnail(timestamp_sec=ts, quality=quality, width=width)
            if info:
                thumbnails.append(info)

        return thumbnails

    # ------------------------------------------------------------------
    # Convienience: full extraction pipeline
    # ------------------------------------------------------------------

    def run_full_extraction(
        self,
        keyframe_count: int = 15,
        uniform_interval: float = 60.0,
        scene_threshold: float = 0.35,
        thumbnail_count: int = 8,
        on_progress: Optional[Callable[[str, float], None]] = None,
    ) -> ExtractionResult:
        """
        Run all extraction strategies and return a consolidated result.

        Args:
            keyframe_count: Max keyframes to extract.
            uniform_interval: Seconds between uniform samples.
            scene_threshold: Sensitivity for scene detection.
            thumbnail_count: Number of thumbnails in grid.
            on_progress: Optional callback(step_name, progress_0_to_1).

        Returns:
            ExtractionResult with all collected data.
        """
        result = ExtractionResult(
            video_path=self.video_path,
            duration_sec=self.duration_sec,
            total_frames=self.total_frames,
            fps=self.fps,
        )

        steps = [
            ("Extracting keyframes", lambda: setattr(result, 'keyframes',
                self.extract_keyframes(max_count=keyframe_count))),
            ("Sampling uniform frames", lambda: setattr(result, 'uniform_frames',
                self.extract_uniform(interval_sec=uniform_interval))),
            ("Detecting scene changes", lambda: setattr(result, 'scene_boundaries',
                self.detect_scene_changes(threshold=scene_threshold))),
            ("Generating thumbnails", lambda: setattr(result, 'thumbnails',
                self.generate_thumbnails_grid(cols=4, rows=max(1, thumbnail_count // 4)))),
        ]

        for i, (label, fn) in enumerate(steps):
            if on_progress:
                on_progress(label, (i + 0.5) / len(steps))
            try:
                fn()
            except Exception as e:
                if on_progress:
                    on_progress(f"  (skipped: {e})", (i + 1) / len(steps))
            if on_progress:
                on_progress(label, (i + 1) / len(steps))

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_frames(self, glob_pattern: str, frame_type: str) -> list[FrameInfo]:
        """Collect frame files matching a glob pattern into FrameInfo list."""
        files = sorted(_glob.glob(glob_pattern))
        frames = []
        for f in files:
            stat = os.stat(f)
            # Try to infer timestamp from filename or set to 0
            ts = 0.0
            m = re.search(r"_(\d+)\.(?:jpg|png)$", os.path.basename(f))
            if m:
                idx = int(m.group(1))
                # Approximate: assume 1 frame per output
                ts = idx / self.fps if self.fps > 0 else 0
            frames.append(FrameInfo(
                path=f,
                timestamp_sec=ts,
                frame_type=frame_type,
                file_size=stat.st_size,
                width=self.width,
                height=self.height,
            ))
        return frames

    def cleanup(self):
        """Remove the output directory and all extracted frames (only if we own it)."""
        if self._cleaned:
            return
        self._cleaned = True
        if self._owns_tempdir and os.path.isdir(self.output_dir) and "bili_frames_" in self.output_dir:
            shutil.rmtree(self.output_dir, ignore_errors=True)
            FrameExtractor._atexit_cleanups.discard(self.output_dir)


# ---------------------------------------------------------------------------
# Register atexit handler (best-effort cleanup for temp dirs)
# ---------------------------------------------------------------------------
atexit.register(FrameExtractor._atexit_flush)
