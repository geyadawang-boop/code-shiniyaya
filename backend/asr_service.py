"""
ASR Service v1.1 (v7.2)
Automatic Speech Recognition fallback for videos without subtitles.
Uses faster-whisper (CTranslate2) for 4x faster transcription vs openai-whisper.

Changelog v1.1:
  - _download_audio() runs subprocess in executor to avoid blocking event loop
  - WhisperModel loading + transcription offloaded to executor
  - torch import moved to module level (avoids slow first import in async context)
  - yt-dlp return code now checked; non-zero exit logged as warning
"""

import os
import asyncio
import logging
import tempfile
import subprocess
from typing import Optional, List

ASR_MODEL_SIZE = os.environ.get("BILISUM_ASR_MODEL", "base")  # tiny/base/small/medium/large


def _read_persisted_model_size() -> str:
    """Read the ASR model size from the database, falling back to the env var.

    This lets the model management UI (routers/asr.py) drive the runtime.
    """
    try:
        import database as db
        persisted = db.get_setting("asr_model", "")
        if persisted:
            return persisted
    except Exception:
        pass
    return ASR_MODEL_SIZE


def get_model_size() -> str:
    """Return the currently active model size, preferring DB over env var."""
    return _read_persisted_model_size()
AUDIO_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "asr_cache")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy torch import at module level (may be absent; checked at call sites)
# ---------------------------------------------------------------------------
try:
    import torch
except ImportError:  # pragma: no cover
    torch = None


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _download_audio(bvid: str, cid: int = 0) -> Optional[str]:
    """
    Download audio from B站 video using yt-dlp.
    Returns path to audio file or None on failure.
    """
    os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
    output_path = os.path.join(AUDIO_CACHE_DIR, f"{bvid}_{cid}.m4a")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        logger.info(f"[ASR] Using cached audio: {output_path}")
        return output_path

    url = f"https://www.bilibili.com/video/{bvid}"
    try:
        result = subprocess.run(
            ["yt-dlp", "-f", "worstaudio[ext=m4a]/worstaudio",
             "--extract-audio", "--audio-format", "m4a",
             "-o", output_path, url, "--no-playlist",
             "--no-warnings", "--quiet"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            logger.warning(
                "[ASR] yt-dlp exited with code %d: %s",
                result.returncode, result.stderr[:300] if result.stderr else "(no stderr)"
            )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            logger.info(f"[ASR] Downloaded audio: {output_path}")
            return output_path
    except FileNotFoundError:
        logger.warning("[ASR] yt-dlp not found. Install: pip install yt-dlp")
    except Exception as e:
        logger.warning(f"[ASR] Download failed: {e}")

    return None


async def transcribe_video(bvid: str, cid: int = 0) -> Optional[str]:
    """
    Transcribe a B站 video using faster-whisper ASR.

    Args:
        bvid: B站 video ID
        cid: Video part ID (for multi-P videos)

    Returns:
        Transcribed text or None if transcription failed.
    """
    loop = asyncio.get_running_loop()

    # Step 1: Try importing faster-whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("[ASR] faster-whisper not installed. pip install faster-whisper")
        # Fallback to openai-whisper
        try:
            import whisper
            return await _transcribe_with_openai_whisper(bvid, cid)
        except ImportError:
            logger.error("[ASR] No whisper implementation available")
            return None

    # Step 2: Download audio (offload subprocess to executor)
    audio_path = await loop.run_in_executor(None, _download_audio, bvid, cid)
    if not audio_path:
        return None

    # Step 3: Transcribe (offload model loading + transcription to executor)
    def _do_transcribe() -> str:
        if torch is None:
            raise RuntimeError("PyTorch is required for faster-whisper. Install: pip install torch")

        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        model_size = get_model_size()
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _info = model.transcribe(audio_path, beam_size=5, language="zh")

        text_parts = []
        for segment in segments:
            text_parts.append(f"[{segment.start:.1f}s] {segment.text.strip()}")

        return "\n".join(text_parts)

    try:
        full_text = await loop.run_in_executor(None, _do_transcribe)
        logger.info(f"[ASR] Transcription complete: {len(full_text.split(chr(10)))} segments, {len(full_text)} chars")
        return full_text

    except Exception as e:
        logger.error(f"[ASR] Transcription error: {e}")
        return None


async def _transcribe_with_openai_whisper(bvid: str, cid: int = 0) -> Optional[str]:
    """Fallback transcription using openai-whisper.  Offloads blocking work to executor."""
    import whisper

    loop = asyncio.get_running_loop()
    audio_path = await loop.run_in_executor(None, _download_audio, bvid, cid)
    if not audio_path:
        return None

    def _do_transcribe() -> str:
        model_size = get_model_size()
        model = whisper.load_model(model_size)
        result = model.transcribe(audio_path, language="zh")
        segments = result.get("segments", [])
        text_parts = [f"[{s['start']:.1f}s] {s['text'].strip()}" for s in segments]
        return "\n".join(text_parts)

    try:
        return await loop.run_in_executor(None, _do_transcribe)
    except Exception as e:
        logger.error(f"[ASR] OpenAI whisper error: {e}")
        return None


def is_asr_available() -> bool:
    """Check if any ASR backend is available."""
    try:
        from faster_whisper import WhisperModel
        return True
    except ImportError:
        try:
            import whisper
            return True
        except ImportError:
            return False


# ---------------------------------------------------------------------------
# Tier-3 visual fallback support (v8): video download for keyframe extraction
# ---------------------------------------------------------------------------

VIDEO_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "frame_video_cache")


def _download_video(bvid: str, cid: int = 0) -> Optional[str]:
    """Download the lowest-quality video stream for Tier-3 keyframe extraction.
    Cache-first, same conventions as _download_audio()."""
    os.makedirs(VIDEO_CACHE_DIR, exist_ok=True)
    output_path = os.path.join(VIDEO_CACHE_DIR, f"{bvid}_{cid}.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
        logger.info(f"[VisualTier] Using cached video: {output_path}")
        return output_path

    url = f"https://www.bilibili.com/video/{bvid}"
    try:
        result = subprocess.run(
            ["yt-dlp", "-f", "worstvideo[ext=mp4]/worstvideo/worst",
             "-o", output_path, url, "--no-playlist",
             "--no-warnings", "--quiet"],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            logger.warning("[VisualTier] yt-dlp exited with code %d: %s",
                           result.returncode, result.stderr[:300] if result.stderr else "(no stderr)")
        if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
            logger.info(f"[VisualTier] Downloaded video: {output_path}")
            return output_path
    except FileNotFoundError:
        logger.warning("[VisualTier] yt-dlp not found. Install: pip install yt-dlp")
    except Exception as e:
        logger.warning(f"[VisualTier] Video download failed: {e}")
    return None


async def download_video_for_frames(bvid: str, cid: int = 0) -> Optional[str]:
    """Async wrapper: offload yt-dlp video download to executor (never blocks event loop)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _download_video, bvid, cid)


def cleanup_video_cache(bvid: str) -> None:
    """Delete-hook target: remove cached Tier-3 videos for a KB entry (register via
    frame_text_service.register_delete_hook(cleanup_video_cache) at app startup)."""
    import glob
    for f in glob.glob(os.path.join(VIDEO_CACHE_DIR, f"{bvid}_*.mp4")):
        try:
            os.remove(f)
        except OSError:
            pass
