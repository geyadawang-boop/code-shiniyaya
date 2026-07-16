"""
Thumbnail Generator — automatic thumbnail extraction for video previews
and BiliSum UI integration.

Features:
  - Single thumbnail at any timestamp
  - Grid layout (multi-frame storyboard)
  - B站封面-style overlay (title, duration badge, play button)
  - Base64 encoding for web embedding
  - Integration with bilibili_client.py (use B站 cover pic as fallback)
"""

import os
import base64
import subprocess
import shutil
import tempfile
import atexit
from io import BytesIO
from dataclasses import dataclass
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


@dataclass
class ThumbnailResult:
    """Result of a thumbnail generation."""
    file_path: str               # absolute path
    base64_data: str             # "data:image/jpeg;base64,..." for web
    timestamp_sec: float
    width: int
    height: int
    file_size: int
    title: str = ""


class ThumbnailGenerator:
    """
    Generates thumbnails from video frames with optional overlay styling.

    Usage:
        gen = ThumbnailGenerator(video_path="/path/to/video.mp4")
        result = gen.generate(timestamp=30.0, width=640)
        grid = gen.generate_grid(cols=4, rows=2)
        b64 = gen.to_base64(result)
    """

    def __init__(self, video_path: str, output_dir: Optional[str] = None):
        self.video_path = os.path.abspath(video_path)
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        self.output_dir = output_dir or tempfile.mkdtemp(prefix="bili_thumbs_")
        os.makedirs(self.output_dir, exist_ok=True)

        self._duration: Optional[float] = None
        self._cleaned = False

        # Register atexit cleanup as fallback for unclosed generators
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

    def _probe_duration(self) -> float:
        try:
            import json
            cmd = [FFMPEG, "-v", "quiet", "-print_format", "json",
                   "-show_format", self.video_path]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
        except Exception:
            pass
        return 0.0

    def _extract_frame(self, timestamp_sec: float, output_path: str,
                       width: int = 480, quality: int = 3) -> bool:
        """Extract a single frame with ffmpeg. Returns True on success."""
        ts = max(0, min(timestamp_sec, max(self.duration - 0.1, 0)))
        # Fast pre-seek (keyframe) before -i, then accurate seek after -i
        pre_seek = max(0, ts - 5)
        accurate_seek = ts - pre_seek
        cmd = [
            FFMPEG, "-y", "-v", "quiet",
            "-ss", str(pre_seek),
            "-i", self.video_path,
            "-ss", str(accurate_seek),
            "-vf", f"scale={width}:-1",
            "-q:v", str(quality),
            "-vframes", "1",
            output_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0 and os.path.exists(output_path)
        except subprocess.TimeoutExpired:
            return False
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def generate(
        self,
        timestamp_sec: Optional[float] = None,
        width: int = 480,
        quality: int = 3,
        overlay_title: str = "",
        overlay_duration: bool = True,
    ) -> Optional[ThumbnailResult]:
        """
        Generate a single thumbnail, optionally with overlay.

        Args:
            timestamp_sec: Position in video. Default = midpoint.
            width: Output image width.
            quality: JPEG quality (2-31, lower = better).
            overlay_title: Text to overlay on the image.
            overlay_duration: If True, add a duration badge.

        Returns:
            ThumbnailResult or None on failure.
        """
        if timestamp_sec is None:
            timestamp_sec = self.duration / 2.0

        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        ts_label = f"{timestamp_sec:.0f}s"
        raw_path = os.path.join(self.output_dir, f"{basename}_thumb_raw_{ts_label}.jpg")

        if not self._extract_frame(timestamp_sec, raw_path, width=width, quality=quality):
            return None

        final_path = raw_path
        img_width = width
        img_height = 0

        # Apply overlay if PIL is available
        if HAS_PIL and (overlay_title or overlay_duration):
            try:
                img = Image.open(raw_path)
                draw = ImageDraw.Draw(img)
                img_w, img_h = img.size
                img_width, img_height = img_w, img_h

                # Semi-transparent overlay bar at bottom
                bar_height = max(30, img_h // 8)
                overlay_color = (0, 0, 0, 160)
                overlay_img = Image.new("RGBA", (img_w, bar_height), overlay_color)
                img.paste(overlay_img, (0, img_h - bar_height), mask=overlay_img.split()[3] if overlay_img.mode == "RGBA" else None)

                draw = ImageDraw.Draw(img)

                # Duration badge (top-right)
                if overlay_duration and self.duration > 0:
                    dur_m = int(self.duration // 60)
                    dur_s = int(self.duration % 60)
                    dur_text = f"{dur_m}:{dur_s:02d}"
                    badge_w, badge_h = 70, 24
                    badge_x = img_w - badge_w - 8
                    badge_y = 8
                    draw.rounded_rectangle(
                        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
                        radius=6, fill=(0, 0, 0, 180)
                    )
                    try:
                        font_sm = ImageFont.truetype("arial.ttf", 14)
                    except Exception:
                        font_sm = ImageFont.load_default()
                    draw.text((badge_x + badge_w // 2 - 18, badge_y + 4), dur_text,
                              fill=(255, 255, 255), font=font_sm)

                # Title at bottom
                if overlay_title:
                    try:
                        font_title = ImageFont.truetype("simhei.ttf", 16)
                    except Exception:
                        try:
                            font_title = ImageFont.truetype("arial.ttf", 16)
                        except Exception:
                            font_title = ImageFont.load_default()
                    title_text = overlay_title[:50]
                    draw.text((10, img_h - bar_height + 8), title_text,
                              fill=(255, 255, 255), font=font_title)

                # Save overlaid version
                overlaid_path = os.path.join(self.output_dir, f"{basename}_thumb_{ts_label}.jpg")
                img.convert("RGB").save(overlaid_path, "JPEG", quality=max(1, min(quality + 10, 31)))
                final_path = overlaid_path
                img_width, img_height = img.size
            except Exception:
                pass

        file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0

        return ThumbnailResult(
            file_path=final_path,
            base64_data=self.to_base64(final_path),
            timestamp_sec=timestamp_sec,
            width=img_width,
            height=img_height,
            file_size=file_size,
            title=overlay_title,
        )

    def generate_grid(
        self,
        cols: int = 4,
        rows: int = 3,
        width: int = 160,
        quality: int = 5,
        title: str = "",
        duration_sec: float = 0,
    ) -> Optional[ThumbnailResult]:
        """
        Generate a grid thumbnail (storyboard layout).

        Extracts cols*rows frames evenly spaced across the video and
        arranges them into a single composite grid image with title overlay.

        Args:
            cols, rows: Grid size.
            width: Width of each cell.
            quality: JPEG quality per frame.
            title: Title text for top overlay.
            duration_sec: Duration for badge.

        Returns:
            ThumbnailResult of the composite image.
        """
        if not HAS_PIL:
            return None

        total = cols * rows
        dur = self.duration
        if dur <= 0:
            return None

        # Sample timestamps (skip first 5% and last 5%)
        start_ts = dur * 0.05
        end_ts = dur * 0.95
        interval = (end_ts - start_ts) / max(total, 1)

        cell_paths = []
        for i in range(total):
            ts = start_ts + i * interval
            cell_path = os.path.join(self.output_dir, f"grid_cell_{i:03d}.jpg")
            if self._extract_frame(ts, cell_path, width=width, quality=quality):
                cell_paths.append(cell_path)

        if not cell_paths:
            return None

        try:
            # Load first cell to get dimensions
            sample = Image.open(cell_paths[0])
            cell_w, cell_h = sample.size

            # Create canvas
            header_h = 50 if title else 0
            canvas_w = cols * cell_w
            canvas_h = rows * cell_h + header_h
            canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 20))

            # Paste cells
            for idx, cp in enumerate(cell_paths):
                if idx >= total:
                    break
                row, col = divmod(idx, cols)
                try:
                    cell_img = Image.open(cp)
                    canvas.paste(cell_img, (col * cell_w, header_h + row * cell_h))
                except Exception:
                    pass

            # Title overlay
            if title:
                draw = ImageDraw.Draw(canvas)
                try:
                    font_t = ImageFont.truetype("simhei.ttf", 20)
                except Exception:
                    font_t = ImageFont.load_default()
                draw.rectangle([(0, 0), (canvas_w, header_h)], fill=(30, 30, 30))
                draw.text((12, 12), title[:60], fill=(255, 255, 255), font=font_t)

            # Save composite
            basename = os.path.splitext(os.path.basename(self.video_path))[0]
            grid_path = os.path.join(self.output_dir, f"{basename}_grid_{cols}x{rows}.jpg")
            canvas.save(grid_path, "JPEG", quality=85)

            file_size = os.path.getsize(grid_path)

            return ThumbnailResult(
                file_path=grid_path,
                base64_data=self.to_base64(grid_path),
                timestamp_sec=0,
                width=canvas_w,
                height=canvas_h,
                file_size=file_size,
                title=title,
            )
        except Exception:
            return None

    def to_base64(self, file_path: str) -> str:
        """Encode an image file to base64 data URI."""
        if not file_path or not os.path.exists(file_path):
            return ""
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"

    def generate_multi_timestamp(
        self,
        timestamps: list[float],
        width: int = 320,
        quality: int = 3,
    ) -> list[ThumbnailResult]:
        """Generate thumbnails for multiple timestamps."""
        results = []
        for ts in timestamps:
            r = self.generate(timestamp_sec=ts, width=width, quality=quality)
            if r:
                results.append(r)
        return results

    def generate_bilibili_style_cover(
        self,
        timestamp_sec: Optional[float] = None,
        title: str = "",
        author: str = "",
        width: int = 480,
    ) -> Optional[ThumbnailResult]:
        """
        Generate a B站-style cover thumbnail with title and author overlay.
        Uses a darkened overlay with centered title text.
        """
        if not HAS_PIL:
            return self.generate(timestamp_sec=timestamp_sec, width=width, overlay_title=title)

        if timestamp_sec is None:
            timestamp_sec = self.duration / 2.0

        basename = os.path.splitext(os.path.basename(self.video_path))[0]
        ts_label = f"{timestamp_sec:.0f}s"
        raw_path = os.path.join(self.output_dir, f"{basename}_bili_raw_{ts_label}.jpg")

        if not self._extract_frame(timestamp_sec, raw_path, width=width, quality=2):
            return None

        try:
            img = Image.open(raw_path).convert("RGBA")
            img_w, img_h = img.size

            # Dark gradient overlay
            overlay = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
            draw_over = ImageDraw.Draw(overlay)

            # Bottom gradient
            for y in range(img_h // 2, img_h):
                alpha = int(180 * (y - img_h // 2) / (img_h // 2))
                draw_over.line([(0, y), (img_w, y)], fill=(0, 0, 0, alpha))

            img = Image.alpha_composite(img, overlay)

            draw = ImageDraw.Draw(img)

            # Title (centered, bottom third)
            if title:
                try:
                    font_t = ImageFont.truetype("simhei.ttf", max(14, img_w // 28))
                except Exception:
                    font_t = ImageFont.load_default()
                title_lines = self._wrap_text(title[:80], img_w - 40, font_t, draw)
                line_h = font_t.getbbox("A")[3] if hasattr(font_t, "getbbox") else 20
                y_start = img_h - 40 - len(title_lines) * line_h
                for line in title_lines:
                    w = draw.textlength(line, font=font_t) if hasattr(draw, "textlength") else len(line) * 10
                    draw.text(((img_w - w) // 2, y_start), line, fill=(255, 255, 255), font=font_t)
                    y_start += line_h

            # Author badge
            if author:
                try:
                    font_a = ImageFont.truetype("arial.ttf", 14)
                except Exception:
                    font_a = ImageFont.load_default()
                author_text = f"UP: {author[:20]}"
                draw.text((12, 12), author_text, fill=(255, 255, 255),
                          stroke_width=2, stroke_fill=(0, 0, 0), font=font_a)

            out_path = os.path.join(self.output_dir, f"{basename}_bili_cover_{ts_label}.png")
            img.convert("RGB").save(out_path, "JPEG", quality=90)

            return ThumbnailResult(
                file_path=out_path,
                base64_data=self.to_base64(out_path),
                timestamp_sec=timestamp_sec,
                width=img_w,
                height=img_h,
                file_size=os.path.getsize(out_path),
                title=title,
            )
        except Exception:
            return None

    def _wrap_text(self, text: str, max_width: int, font, draw) -> list[str]:
        """Wrap text to fit within max_width."""
        lines = []
        current = ""
        for ch in text:
            test = current + ch
            w = draw.textlength(test, font=font) if hasattr(draw, "textlength") else len(test) * 10
            if w > max_width and current:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
        return lines if lines else [text]

    def cleanup(self):
        """Remove generated thumbnails. Only removes directories created by this class
        (those whose basename starts with 'bili_thumbs_')."""
        if self._cleaned:
            return
        self._cleaned = True
        if not os.path.isdir(self.output_dir):
            return
        dir_basename = os.path.basename(self.output_dir)
        if dir_basename.startswith("bili_thumbs_"):
            shutil.rmtree(self.output_dir, ignore_errors=True)
