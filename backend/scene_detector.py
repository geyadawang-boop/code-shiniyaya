"""
SceneDetector — PIL/NumPy-based scene boundary detection via inter-frame
histogram comparison. Serves as a pure-Python fallback when ffmpeg's scdet
filter is unavailable, and provides per-frame complexity scores for the
visual dependency detector.

Algorithm:
  1. Sample frames at regular intervals (e.g., every 0.5 sec) using ffmpeg
  2. Compute HSV histograms for each frame
  3. Calculate chi-squared distance between adjacent frames
  4. Apply adaptive thresholding to locate scene boundaries
  5. Compute per-frame "complexity" via edge density (Sobel/Canny)
"""

import os
import tempfile
import subprocess
import shutil
import math
import atexit
from typing import Optional

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from PIL import Image, ImageFilter, ImageStat
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


class SceneDetector:
    """
    Pure-Python scene change detector using histogram comparison.

    Usage:
        det = SceneDetector(video_path="/path/to/video.mp4")
        boundaries = det.detect(threshold=0.30, sample_every=0.5)
        complexity_scores = det.compute_frame_complexity(boundaries)
    """

    def __init__(self, video_path: str, output_dir: Optional[str] = None):
        if not HAS_PIL:
            raise ImportError("SceneDetector requires Pillow: pip install Pillow")
        if not HAS_NUMPY:
            raise ImportError("SceneDetector requires NumPy: pip install numpy")

        self.video_path = os.path.abspath(video_path)
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        self.output_dir = output_dir or tempfile.mkdtemp(prefix="bili_scenes_")
        os.makedirs(self.output_dir, exist_ok=True)

        # Lazy video metadata
        self._duration: Optional[float] = None
        self._fps: Optional[float] = None
        self._cleaned = False

        # Register atexit cleanup as fallback for unclosed detectors
        atexit.register(self._atexit_cleanup)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def _atexit_cleanup(self):
        """Fallback cleanup: remove temp dir on process exit if not yet cleaned."""
        if not self._cleaned:
            self.cleanup()

    @property
    def duration(self) -> float:
        if self._duration is None:
            self._duration = self._probe_duration()
        return self._duration

    @property
    def fps(self) -> float:
        if self._fps is None:
            self._fps = self._probe_fps()
        return self._fps

    def _probe_duration(self) -> float:
        try:
            import json
            cmd = [FFMPEG, "-v", "quiet", "-print_format", "json",
                   "-show_format", self.video_path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                return float(data.get("format", {}).get("duration", 0))
        except Exception:
            pass
        return 0.0

    def _probe_fps(self) -> float:
        try:
            import json
            cmd = [FFMPEG, "-v", "quiet", "-print_format", "json",
                   "-show_streams", self.video_path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                data = json.loads(r.stdout)
                for s in data.get("streams", []):
                    if s.get("codec_type") == "video":
                        fps_s = s.get("r_frame_rate", "30/1")
                        if "/" in fps_s:
                            n, d = fps_s.split("/", 1)
                            return float(n) / max(float(d), 1)
                        return float(fps_s) or 30.0
        except Exception:
            pass
        return 30.0

    def _sample_frames(self, interval_sec: float = 0.5, max_frames: int = 2000) -> list[str]:
        """Extract frames at fixed intervals for analysis. Returns list of paths."""
        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        pattern = os.path.join(self.output_dir, f"{basename}_sample_%06d.jpg")

        fps_out = 1.0 / max(interval_sec, 0.1)
        cmd = [
            FFMPEG, "-y", "-v", "quiet",
            "-i", self.video_path,
            "-vf", f"fps={fps_out:.4f},scale=240:-1",
            "-q:v", "5",
            "-vsync", "vfr",
            "-frames:v", str(max_frames),
            pattern,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(
                    f"ffmpeg frame sampling failed (rc={result.returncode}): "
                    f"{result.stderr[:500]}"
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg frame sampling timed out after 300s")
        except FileNotFoundError:
            raise RuntimeError(f"ffmpeg not found at {FFMPEG}")

        import glob as _glob
        return sorted(_glob.glob(pattern.replace("%06d", "*")))

    def _image_histogram_hsv(self, img_path: str, bins: int = 32) -> np.ndarray:
        """Compute concatenated HSV histogram for an image."""
        img = Image.open(img_path).convert("HSV")
        img_arr = np.array(img)
        h_hist, _ = np.histogram(img_arr[:, :, 0], bins=bins, range=(0, 256))
        s_hist, _ = np.histogram(img_arr[:, :, 1], bins=bins, range=(0, 256))
        v_hist, _ = np.histogram(img_arr[:, :, 2], bins=bins, range=(0, 256))
        return np.concatenate([h_hist, s_hist, v_hist]).astype(np.float64)

    def _chi2_distance(self, h1: np.ndarray, h2: np.ndarray) -> float:
        """Chi-squared distance between two histograms. 0 = identical, higher = more different."""
        eps = 1e-10
        return float(np.sum(((h1 - h2) ** 2) / (h1 + h2 + eps)) * 0.5)

    def _adaptive_threshold(self, diffs: list[float], base_threshold: float = 0.30) -> list[tuple[int, float]]:
        """
        Adaptive threshold: scene boundaries are local maxima that exceed
        base_threshold * local_mean.
        """
        if not diffs:
            return []

        window = max(2, len(diffs) // 20)
        boundaries = []
        for i in range(1, len(diffs) - 1):
            # Local window mean
            lo = max(0, i - window)
            hi = min(len(diffs), i + window + 1)
            local_mean = sum(diffs[lo:hi]) / max(hi - lo, 1)
            adaptive_thresh = max(base_threshold, local_mean * 1.5)

            # Is it a local peak above threshold?
            if diffs[i] > adaptive_thresh and diffs[i] >= diffs[i - 1] and diffs[i] > diffs[i + 1]:
                boundaries.append((i, diffs[i]))

        return boundaries

    def detect(
        self,
        threshold: float = 0.30,
        sample_every: float = 0.5,
        min_scene_len: float = 2.0,
        max_scenes: int = 50,
    ) -> list[dict]:
        """
        Detect scene boundaries.

        Returns:
            List of dicts: {timestamp_sec, diff_score, confidence}
        """
        frames = self._sample_frames(interval_sec=sample_every)

        if len(frames) < 2:
            return []

        # Compute histograms
        histograms = []
        for fp in frames:
            try:
                histograms.append(self._image_histogram_hsv(fp))
            except Exception:
                histograms.append(None)

        # Compute pairwise differences
        diffs = []
        for i in range(1, len(histograms)):
            if histograms[i] is not None and histograms[i - 1] is not None:
                d = self._chi2_distance(histograms[i - 1], histograms[i])
                diffs.append(d)
            else:
                diffs.append(0.0)

        # Find boundaries with adaptive threshold
        raw_boundaries = self._adaptive_threshold(diffs, threshold)

        # Convert to timestamps
        boundaries = []
        for idx, diff_score in raw_boundaries:
            ts = (idx + 1) * sample_every  # +1 because diffs[0] is between frame 0 and 1
            confidence = min(1.0, diff_score / max(1.0, max(diffs)))
            boundaries.append({
                "timestamp_sec": ts,
                "diff_score": round(diff_score, 4),
                "confidence": round(confidence, 4),
            })

        # Filter by min scene length
        if min_scene_len > 0 and len(boundaries) > 1:
            filtered = [boundaries[0]]
            for b in boundaries[1:]:
                if (b["timestamp_sec"] - filtered[-1]["timestamp_sec"]) >= min_scene_len:
                    filtered.append(b)
            boundaries = filtered

        return boundaries[:max_scenes]

    def compute_frame_complexity(self, frame_paths: list[str]) -> list[dict]:
        """
        Compute per-frame visual complexity using edge density (Sobel via PIL).

        Returns:
            List of {path, edge_density, saturation_mean, brightness_std}
        """
        results = []
        for fp in frame_paths:
            try:
                img = Image.open(fp).convert("RGB")
                arr = np.array(img)

                # Edge density: apply simple horizontal + vertical gradient
                gray = np.dot(arr[..., :3], [0.2989, 0.5870, 0.1140])
                gy = np.abs(np.diff(gray, axis=0, prepend=gray[:1]))
                gx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1].reshape(-1, 1)))
                edge = (gx + gy) / 2.0
                edge_density = float(np.mean(edge > 15))

                # Saturation mean
                r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
                mx = np.maximum(np.maximum(r, g), b)
                mn = np.minimum(np.minimum(r, g), b)
                sat = np.where(mx > 0, (mx - mn) / (mx + 1e-10), 0.0)
                saturation_mean = float(np.mean(sat))

                # Brightness standard deviation
                brightness_std = float(np.std(gray))

                results.append({
                    "path": fp,
                    "edge_density": round(edge_density, 4),
                    "saturation_mean": round(saturation_mean, 4),
                    "brightness_std": round(brightness_std, 4),
                })
            except Exception:
                results.append({
                    "path": fp,
                    "edge_density": 0.0,
                    "saturation_mean": 0.0,
                    "brightness_std": 0.0,
                })

        return results

    def aggregate_complexity(self, frame_complexities: list[dict]) -> dict:
        """
        Aggregate frame complexity data into a summary for visual dependency scoring.

        Returns:
            {mean_edge_density, mean_saturation, mean_brightness_std,
             complex_ratio (fraction of frames with high edge density)}
        """
        if not frame_complexities:
            return {
                "mean_edge_density": 0.0,
                "mean_saturation": 0.0,
                "mean_brightness_std": 0.0,
                "complex_ratio": 0.0,
            }

        edges = [c["edge_density"] for c in frame_complexities]
        sats = [c["saturation_mean"] for c in frame_complexities]
        b_stds = [c["brightness_std"] for c in frame_complexities]

        complex_count = sum(1 for e in edges if e > 0.08)

        return {
            "mean_edge_density": round(np.mean(edges).item(), 4),
            "mean_saturation": round(np.mean(sats).item(), 4),
            "mean_brightness_std": round(np.mean(b_stds).item(), 4),
            "complex_ratio": round(complex_count / max(len(edges), 1), 4),
        }

    def cleanup(self):
        """Remove sampled frames. Only removes directories created by this class
        (those whose basename starts with 'bili_scenes_')."""
        if self._cleaned:
            return
        self._cleaned = True
        if not os.path.isdir(self.output_dir):
            return
        dir_basename = os.path.basename(self.output_dir)
        if dir_basename.startswith("bili_scenes_"):
            shutil.rmtree(self.output_dir, ignore_errors=True)
