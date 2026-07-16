"""frame_text_service.py — keyframe extraction + vision-to-text for BiliSum.

Final implementation (v1.0). Pipeline (per video):
  1. Download-or-reuse: reuse an existing local video file / cached download
     under frames_cache/{bvid}/, else download via yt-dlp (<=720p).
  2. FrameExtractor: real I-frame keyframes + scene-change boundary frames
     (frame_extractor.FrameExtractor — ffmpeg based).
  3. Dedupe near-identical frames with a pure-stdlib byte-value histogram
     (cosine similarity over 256 bins; no PIL/cv2 hard dependency).
  4. Adaptive cap: frame budget scales with video duration (8/12/16/20/24),
     further bounded by vision_gating's frame budget when available.
  5. Base64 data-URI encoding via thumbnail_generator.ThumbnailGenerator.
  6. VLM describe: DashScope Qwen-VL SDK primary; OpenAI-compatible
     /chat/completions (UnifiedLLMClient) fallback. Chinese prompt (e14).
  7. Timestamped text blocks "[MM:SS] <text>" for summary-prompt injection.
  8. frames_cache/{bvid}/manifest.json persists frames, results and *gaps* —
     every per-frame or per-stage failure is recorded, never raised, so
     summarization always proceeds (degrading to text-only at worst).

Delete hook: importing this module registers cleanup of frames_cache/{bvid}/
for routers/kb.py's run_delete_hooks(bvid).
"""

from __future__ import annotations

import asyncio
import glob as _glob
import json
import logging
import math
import os
import shutil
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

logger = logging.getLogger("bilisum.frame_text")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRAMES_CACHE_DIRNAME = "frames_cache"

# Adaptive cap: (max_duration_sec, max_frames)
ADAPTIVE_CAPS: list[tuple[int, int]] = [
    (300, 8),      # <= 5 min
    (900, 12),     # <= 15 min
    (1800, 16),    # <= 30 min
    (3600, 20),    # <= 60 min
]
ADAPTIVE_CAP_DEFAULT = 24              # > 60 min
ABSOLUTE_MAX_FRAMES = 24               # hard ceiling regardless of gate/caller

DEDUPE_SIMILARITY = 0.985              # cosine sim above which frames are "same"
FRAME_SCALE_WIDTH = 640                # extraction width (vision-token economy)
SCENE_THRESHOLD = 0.35                 # ffmpeg scdet sensitivity

YTDLP_TIMEOUT = 300                    # matches constants.HTTP_TIMEOUT_DOWNLOAD
MIN_VIDEO_BYTES = 1024                 # sanity floor for a "real" video file

# VLM — DashScope Qwen-VL primary (native SDK), OpenAI-compatible fallback
DASHSCOPE_VL_MODEL = os.environ.get("BILISUM_VL_MODEL", "qwen-vl-plus")
FALLBACK_VL_MODEL = os.environ.get("BILISUM_VL_FALLBACK_MODEL", "qwen-vl-plus")
FALLBACK_API_URL = os.environ.get(
    "BILISUM_VL_FALLBACK_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
VISION_MAX_TOKENS = 300                # per-frame description budget
VISION_CONCURRENCY = 3                 # parallel frame-describe calls
VISION_TIMEOUT = 90.0                  # per-frame call timeout (seconds)

# Chinese prompt (finding e14): extract on-screen text + one-line description.
VISION_SYSTEM_PROMPT = (
    "你是视频画面分析助手。用简洁中文完成两件事：\n"
    "1. 提取画面中所有可见文字（字幕、标题、PPT/白板、代码、图表标注），"
    "保持原文，不要翻译，忽略水印和平台 logo；\n"
    "2. 用一句话描述画面核心内容（图表/代码/公式/界面操作要点明）。\n"
    "不要推测画面之外的内容。输出纯文本，格式：\n"
    "文字：<提取到的文字，无则写\"无\">\n"
    "画面：<一句话描述>"
)


def frames_cache_root() -> str:
    """Absolute path of frames_cache/ next to this module (backend/)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), FRAMES_CACHE_DIRNAME)


def frames_cache_dir(bvid: str) -> str:
    """frames_cache/{bvid}/ — one directory per video, keyed by BVID."""
    safe = "".join(c for c in bvid if c.isalnum() or c in "-_") or "unknown"
    return os.path.join(frames_cache_root(), safe)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Keyframe:
    """One selected keyframe."""
    path: str                          # absolute path inside frames_cache/{bvid}/
    timestamp_sec: float
    frame_type: str = "I"              # "I" (keyframe) or "scene" (boundary)
    description: str = ""              # filled by vision pass
    provider: str = ""                 # "dashscope" | "openai_compat"

    @property
    def timestamp_label(self) -> str:
        """MM:SS (or HH:MM:SS above one hour)."""
        s = max(0, int(self.timestamp_sec))
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


@dataclass
class FrameTextResult:
    """Final output of the service for one video."""
    bvid: str
    keyframes: list[Keyframe] = field(default_factory=list)
    text_blocks: list[str] = field(default_factory=list)   # "[MM:SS] desc"
    model: str = ""
    gated_off: bool = False
    gate_reason: str = ""
    cache_hit: bool = False
    gaps: list[dict] = field(default_factory=list)          # recorded failures
    manifest_path: str = ""

    def to_prompt_block(self) -> str:
        """Render timestamped lines for injection into the summary prompt."""
        if not self.text_blocks:
            return ""
        return "## 视频画面时间轴\n" + "\n".join(self.text_blocks)


# ---------------------------------------------------------------------------
# Delete-hook registry
# ---------------------------------------------------------------------------

_DELETE_HOOKS: list[Callable[[str], None]] = []


def register_delete_hook(hook: Callable[[str], None]) -> None:
    """Register a callable(bvid) invoked when a KB entry is deleted.

    routers/kb.py (api_kb_delete) calls run_delete_hooks(bvid) after
    db.delete_kb_entry succeeds; hooks must never raise.
    """
    if hook not in _DELETE_HOOKS:
        _DELETE_HOOKS.append(hook)


def run_delete_hooks(bvid: str) -> None:
    """Fire all registered hooks; log-and-continue on failure."""
    for hook in _DELETE_HOOKS:
        try:
            hook(bvid)
        except Exception as e:  # deletion must not fail because of cleanup
            logger.warning("delete hook %s failed for %s: %s", hook, bvid, e)


def _cleanup_frames_cache(bvid: str) -> None:
    """Default hook: remove frames_cache/{bvid}/ recursively."""
    d = frames_cache_dir(bvid)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        logger.info("frames_cache cleaned for %s", bvid)


# Self-registration at import time — importing this module is enough
# for kb-delete to clean up the frame cache.
register_delete_hook(_cleanup_frames_cache)


# ---------------------------------------------------------------------------
# Step 1: download-or-reuse video
# ---------------------------------------------------------------------------

def find_cached_video(bvid: str) -> Optional[str]:
    """Return a previously downloaded video under frames_cache/{bvid}/, if any."""
    d = frames_cache_dir(bvid)
    if not os.path.isdir(d):
        return None
    for ext in ("mp4", "mkv", "webm", "flv", "ts"):
        for path in sorted(_glob.glob(os.path.join(d, f"*.{ext}"))):
            try:
                if os.path.getsize(path) > MIN_VIDEO_BYTES:
                    return path
            except OSError:
                continue
    return None


def obtain_video(bvid: str, video_path: str = "", video_url: str = "") -> str:
    """Download-or-reuse. Order: caller-supplied file -> cache -> yt-dlp.

    Raises RuntimeError when no video can be obtained (the only stage
    allowed to abort the pipeline — everything downstream degrades).
    """
    if video_path and os.path.isfile(video_path) and os.path.getsize(video_path) > MIN_VIDEO_BYTES:
        return video_path

    cached = find_cached_video(bvid)
    if cached:
        logger.info("[frame_text] reuse cached video: %s", cached)
        return cached

    url = video_url or f"https://www.bilibili.com/video/{bvid}"
    cache_dir = frames_cache_dir(bvid)
    os.makedirs(cache_dir, exist_ok=True)
    out_tmpl = os.path.join(cache_dir, "video.%(ext)s")

    cmd = ["yt-dlp", "--no-playlist", "-f", "best[height<=720]/best", "-o", out_tmpl]
    cookies = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bili_cookies.txt")
    if os.path.exists(cookies):
        cmd += ["--cookies", cookies]
    cmd.append(url)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=YTDLP_TIMEOUT)
    except FileNotFoundError:
        raise RuntimeError("yt-dlp not installed (pip install yt-dlp)")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"yt-dlp download timed out after {YTDLP_TIMEOUT}s")

    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp exited {proc.returncode}: {(proc.stderr or '')[-400:]}")

    video = find_cached_video(bvid)
    if not video:
        raise RuntimeError("yt-dlp reported success but no video file found")
    return video


# ---------------------------------------------------------------------------
# Step 3: dedupe (stdlib histogram)
# ---------------------------------------------------------------------------

def _byte_histogram(path: str) -> list[int]:
    """256-bin byte-value histogram of the JPEG payload — pure stdlib.

    Coarse but effective for near-duplicate detection: visually identical
    frames compress to near-identical byte distributions.
    """
    counter: Counter = Counter()
    with open(path, "rb") as f:
        counter.update(f.read())
    return [counter.get(i, 0) for i in range(256)]


def _cosine_similarity(a: list[int], b: list[int]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def dedupe_frames(frames: list[Keyframe], threshold: float = DEDUPE_SIMILARITY) -> list[Keyframe]:
    """Drop frames whose histogram is nearly identical to an already-kept frame."""
    kept: list[Keyframe] = []
    kept_hists: list[list[int]] = []
    for fr in frames:
        try:
            hist = _byte_histogram(fr.path)
        except OSError as e:
            logger.debug("[frame_text] histogram failed for %s: %s", fr.path, e)
            continue
        if any(_cosine_similarity(hist, h) >= threshold for h in kept_hists):
            continue
        kept.append(fr)
        kept_hists.append(hist)
    return kept


# ---------------------------------------------------------------------------
# Step 4: adaptive cap
# ---------------------------------------------------------------------------

def adaptive_frame_cap(duration_sec: float) -> int:
    """Frame budget scaled by duration; see ADAPTIVE_CAPS."""
    for max_dur, cap in ADAPTIVE_CAPS:
        if duration_sec <= max_dur:
            return cap
    return ADAPTIVE_CAP_DEFAULT


def apply_cap(frames: list[Keyframe], cap: int) -> list[Keyframe]:
    """Keep at most `cap` frames, evenly spread across the timeline."""
    if cap <= 0 or len(frames) <= cap:
        return frames
    step = len(frames) / cap
    picked = [frames[min(int(i * step), len(frames) - 1)] for i in range(cap)]
    # de-dup indices that rounded to the same frame
    seen: set[str] = set()
    out: list[Keyframe] = []
    for fr in picked:
        if fr.path not in seen:
            seen.add(fr.path)
            out.append(fr)
    return out


# ---------------------------------------------------------------------------
# Step 2: extraction (FrameExtractor keyframes + scene frames)
# ---------------------------------------------------------------------------

def extract_candidate_frames(
    video_path: str,
    bvid: str,
    cap: int,
    gaps: list[dict],
) -> tuple[list[Keyframe], float]:
    """I-frame keyframes + scene-boundary frames via FrameExtractor.

    Stage failures are appended to `gaps`, never raised. Returns
    (timestamp-ordered candidates, duration_sec).
    """
    from frame_extractor import FrameExtractor

    frames_dir = os.path.join(frames_cache_dir(bvid), "frames")
    os.makedirs(frames_dir, exist_ok=True)

    candidates: list[Keyframe] = []
    duration = 0.0

    with FrameExtractor(video_path, output_dir=frames_dir) as ex:
        try:
            duration = ex.duration_sec
        except Exception as e:
            gaps.append({"stage": "probe", "error": str(e)})

        # Strategy 1: real I-frames (over-sample 2x, dedupe+cap trims later)
        try:
            for fi in ex.extract_keyframes(max_count=cap * 2, scale_width=FRAME_SCALE_WIDTH):
                candidates.append(Keyframe(path=fi.path, timestamp_sec=fi.timestamp_sec, frame_type="I"))
        except Exception as e:
            logger.warning("[frame_text] keyframe extraction failed: %s", e)
            gaps.append({"stage": "extract_keyframes", "error": str(e)})

        # Strategy 2: scene-change boundaries (pre_extract writes frames to disk)
        try:
            for b in ex.detect_scene_changes(
                threshold=SCENE_THRESHOLD, max_scenes=cap, pre_extract=True
            ):
                bpath = b.next_frame_path or b.prev_frame_path
                if bpath and os.path.exists(bpath):
                    candidates.append(Keyframe(path=bpath, timestamp_sec=b.timestamp_sec, frame_type="scene"))
        except Exception as e:
            logger.warning("[frame_text] scene detection failed: %s", e)
            gaps.append({"stage": "detect_scene_changes", "error": str(e)})

    candidates.sort(key=lambda fr: fr.timestamp_sec)
    return candidates, duration


# ---------------------------------------------------------------------------
# Steps 5-6: base64 (thumbnail_generator) + VLM (dashscope primary, fallback)
# ---------------------------------------------------------------------------

def encode_frame_base64(video_path: str, frame_path: str) -> str:
    """Base64 data-URI via ThumbnailGenerator.to_base64; '' on failure."""
    from thumbnail_generator import ThumbnailGenerator

    tg = ThumbnailGenerator(video_path, output_dir=os.path.dirname(frame_path))
    try:
        return tg.to_base64(frame_path)
    finally:
        try:
            tg.cleanup()
        except Exception:
            pass


def _resolve_dashscope_key() -> str:
    """Setting dashscope_api_key first, then DASHSCOPE_API_KEY env."""
    try:
        import database as db
        key = (db.get_setting("dashscope_api_key") or "").strip()
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("DASHSCOPE_API_KEY", "").strip()


def _vlm_dashscope_sync(data_uri: str, model: str = DASHSCOPE_VL_MODEL) -> str:
    """Primary: Qwen-VL via native dashscope SDK (sync; run in a thread)."""
    import dashscope

    api_key = _resolve_dashscope_key()
    if not api_key:
        raise RuntimeError("dashscope_api_key not configured")

    rsp = dashscope.MultiModalConversation.call(
        api_key=api_key,
        model=model,
        messages=[
            {"role": "system", "content": [{"text": VISION_SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"image": data_uri}, {"text": "请分析这张视频截图。"}]},
        ],
    )
    status = getattr(rsp, "status_code", 500)
    if status != 200:
        raise RuntimeError(f"dashscope status {status}: {getattr(rsp, 'message', '')}")
    content = rsp.output.choices[0].message.content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        ).strip()
    return str(content).strip()


async def _vlm_openai_compat(client, data_uri: str, timestamp_label: str) -> str:
    """Fallback: OpenAI-format image_url content block via UnifiedLLMClient."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": f"这是视频第 {timestamp_label} 处的画面，请分析。"},
            ],
        }
    ]
    resp = await client.complete(
        model=FALLBACK_VL_MODEL,
        messages=messages,
        system=VISION_SYSTEM_PROMPT,
        max_tokens=VISION_MAX_TOKENS,
        temperature=0.2,
        enable_cache=False,
    )
    return (getattr(resp, "text", "") or "").strip()


async def describe_frame(client, kf: Keyframe, video_path: str) -> tuple[str, str]:
    """Return (description, provider). Dashscope primary, OpenAI-compat fallback.

    Raises only when *both* providers fail (caller records the gap).
    """
    data_uri = await asyncio.to_thread(encode_frame_base64, video_path, kf.path)
    if not data_uri:
        raise RuntimeError("base64 encode returned empty")

    try:
        text = await asyncio.wait_for(
            asyncio.to_thread(_vlm_dashscope_sync, data_uri), timeout=VISION_TIMEOUT
        )
        return text, "dashscope"
    except Exception as e:
        logger.warning("[frame_text] dashscope VLM failed @%s (%s); trying fallback",
                       kf.timestamp_label, e)

    if client is None:
        raise RuntimeError("dashscope failed and no fallback client available")
    text = await asyncio.wait_for(
        _vlm_openai_compat(client, data_uri, kf.timestamp_label), timeout=VISION_TIMEOUT
    )
    return text, "openai_compat"


# ---------------------------------------------------------------------------
# Step 8: manifest
# ---------------------------------------------------------------------------

def _manifest_path(bvid: str) -> str:
    return os.path.join(frames_cache_dir(bvid), "manifest.json")


def load_manifest(bvid: str) -> Optional[dict]:
    """Load manifest.json; None when missing/corrupt or frame files vanished."""
    path = _manifest_path(bvid)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("results", []):
            if not os.path.exists(r.get("frame_path", "")):
                return None
        return data
    except (OSError, ValueError):
        return None


def save_manifest(bvid: str, manifest: dict) -> str:
    """Persist manifest.json; best-effort (a failed save is itself a gap)."""
    path = _manifest_path(bvid)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("[frame_text] manifest save failed: %s", e)
    return path


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

class FrameTextService:
    """Select keyframes, describe them via VLM, emit timestamped text."""

    def __init__(self, concurrency: int = VISION_CONCURRENCY):
        self.concurrency = concurrency

    async def run(
        self,
        bvid: str,
        video_path: str = "",
        video_url: str = "",
        duration_sec: float = 0.0,
        max_frames: Optional[int] = None,
    ) -> FrameTextResult:
        """Full pipeline. Never raises for gating/extraction/VLM failures —
        degrades to a gated-off / partial result so summarization proceeds
        text-only. Every failure is recorded in result.gaps and the manifest.
        """
        result = FrameTextResult(bvid=bvid, model=DASHSCOPE_VL_MODEL)
        manifest: dict = {
            "bvid": bvid,
            "created_at": time.time(),
            "model": DASHSCOPE_VL_MODEL,
            "video_path": "",
            "duration_sec": duration_sec,
            "frame_cap": 0,
            "frames_extracted": 0,
            "frames_deduped": 0,
            "frames_analyzed": 0,
            "results": [],
            "gaps": result.gaps,   # shared list: every gap lands in both
        }

        try:
            # 0. Manifest cache hit — reuse prior VLM results wholesale.
            cached = load_manifest(bvid)
            if cached and cached.get("results"):
                result.cache_hit = True
                result.model = cached.get("model", result.model)
                for r in cached["results"]:
                    result.keyframes.append(Keyframe(
                        path=r.get("frame_path", ""),
                        timestamp_sec=float(r.get("timestamp_sec", 0.0)),
                        frame_type=r.get("frame_type", "I"),
                        description=r.get("text", ""),
                        provider=r.get("provider", ""),
                    ))
                result.text_blocks = [
                    f"[{kf.timestamp_label}] {kf.description}"
                    for kf in result.keyframes if kf.description
                ]
                result.manifest_path = _manifest_path(bvid)
                return result

            # 0b. Cost/availability gate (settings toggle, key presence, length).
            gate = self._check_gate(duration_sec)
            if gate is not None and not getattr(gate, "allowed", True):
                result.gated_off = True
                result.gate_reason = getattr(gate, "reason", "gated")
                manifest["gaps"].append({"stage": "gate", "error": result.gate_reason})
                result.manifest_path = save_manifest(bvid, manifest)
                return result

            # 1. Download-or-reuse (the only hard-fail stage).
            video_path = await asyncio.to_thread(obtain_video, bvid, video_path, video_url)
            manifest["video_path"] = video_path
            result.manifest_path = save_manifest(bvid, manifest)  # early checkpoint

            # 2. FrameExtractor keyframes + scene frames.
            cap = self._frame_budget(gate, duration_sec, max_frames)
            manifest["frame_cap"] = cap
            candidates, probed_dur = await asyncio.to_thread(
                extract_candidate_frames, video_path, bvid, cap, manifest["gaps"]
            )
            if probed_dur > 0:
                manifest["duration_sec"] = probed_dur
                if duration_sec <= 0:
                    cap = self._frame_budget(gate, probed_dur, max_frames)
                    manifest["frame_cap"] = cap
            manifest["frames_extracted"] = len(candidates)

            # 3 + 4. Dedupe then adaptive cap.
            candidates = await asyncio.to_thread(dedupe_frames, candidates)
            manifest["frames_deduped"] = len(candidates)
            candidates = apply_cap(candidates, cap)

            if not candidates:
                result.gate_reason = "no_keyframes"
                manifest["gaps"].append({"stage": "select", "error": "no frames extracted"})
                result.manifest_path = save_manifest(bvid, manifest)
                return result

            result.keyframes = candidates

            # 5 + 6. Base64 + VLM, bounded concurrency, per-frame gap recording.
            await self._describe_all(candidates, video_path, manifest)

            # 7. Timestamped output.
            result.text_blocks = [
                f"[{kf.timestamp_label}] {kf.description}"
                for kf in candidates if kf.description
            ]

        except Exception as e:
            # Full-pipeline safety net: record, degrade, never propagate.
            logger.error("[frame_text] pipeline failed for %s: %s", bvid, e)
            manifest["gaps"].append({"stage": "pipeline", "error": str(e)})
            result.gate_reason = result.gate_reason or f"pipeline_error: {e}"

        # 8. Persist manifest (results + gaps) for reuse and diagnostics.
        result.manifest_path = save_manifest(bvid, manifest)
        return result

    # -- internals ----------------------------------------------------------

    def _check_gate(self, duration_sec: float):
        """Delegate to vision_gating.check_vision_gate; None if unavailable."""
        try:
            from vision_gating import check_vision_gate
            return check_vision_gate(duration_sec)
        except Exception as e:
            logger.warning("vision gate unavailable, proceeding ungated: %s", e)
            return None

    def _frame_budget(self, gate, duration_sec: float, max_frames: Optional[int]) -> int:
        """min(adaptive-by-duration, gate budget, caller cap, absolute max)."""
        cap = adaptive_frame_cap(duration_sec) if duration_sec > 0 else ADAPTIVE_CAPS[1][1]
        gate_budget = getattr(gate, "frame_count", 0) or 0
        if gate_budget > 0:
            cap = min(cap, gate_budget)
        if max_frames is not None and max_frames > 0:
            cap = min(cap, max_frames)
        return min(cap, ABSOLUTE_MAX_FRAMES)

    async def _describe_all(self, frames: list[Keyframe], video_path: str, manifest: dict) -> None:
        """Describe frames concurrently; per-frame failure becomes a manifest gap."""
        client = None
        client_cm = None
        try:
            try:
                from unified_llm_client import UnifiedLLMClient
                client_cm = UnifiedLLMClient(
                    api_key=_resolve_dashscope_key(),
                    api_url=FALLBACK_API_URL,
                    timeout=VISION_TIMEOUT,
                )
                client = await client_cm.__aenter__()
            except Exception as e:
                logger.warning("[frame_text] fallback client unavailable: %s", e)
                client = None

            sem = asyncio.Semaphore(self.concurrency)

            async def _one(kf: Keyframe) -> None:
                async with sem:
                    try:
                        kf.description, kf.provider = await describe_frame(client, kf, video_path)
                        manifest["results"].append({
                            "timestamp_sec": kf.timestamp_sec,
                            "timestamp_str": kf.timestamp_label,
                            "frame_path": kf.path,
                            "frame_type": kf.frame_type,
                            "text": kf.description,
                            "provider": kf.provider,
                        })
                        manifest["frames_analyzed"] += 1
                    except Exception as e:
                        logger.warning("vision describe failed @%s: %s", kf.timestamp_label, e)
                        manifest["gaps"].append({
                            "stage": "vlm",
                            "timestamp_sec": kf.timestamp_sec,
                            "timestamp_str": kf.timestamp_label,
                            "frame_path": kf.path,
                            "error": str(e),
                        })

            await asyncio.gather(*(_one(kf) for kf in frames))
            manifest["results"].sort(key=lambda r: r["timestamp_sec"])
        finally:
            if client_cm is not None and client is not None:
                try:
                    await client_cm.__aexit__(None, None, None)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

async def extract_frame_text(
    bvid: str,
    video_path: str = "",
    video_url: str = "",
    duration_sec: float = 0.0,
    max_frames: Optional[int] = None,
) -> FrameTextResult:
    """One-call entry point used by unified_pipeline / summarizer."""
    return await FrameTextService().run(
        bvid=bvid,
        video_path=video_path,
        video_url=video_url,
        duration_sec=duration_sec,
        max_frames=max_frames,
    )


def result_to_dict(result: FrameTextResult) -> dict:
    """JSON-safe dump of a FrameTextResult (for API responses / logging)."""
    return asdict(result)
