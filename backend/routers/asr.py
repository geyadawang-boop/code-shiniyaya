"""
ASR Model Management Router (v9.0)
GET  /api/asr/models        — list available faster-whisper model sizes, installed status, active model
POST /api/asr/models/install — pre-download a specific model size

Design reflects bilinote's /api/whisper-models + /api/whisper-models/install pattern,
but adapted for faster-whisper (Python native integration, CTranslate2 model format) rather
than whisper.cpp (subprocess + ggml .bin files).

Bilinote       | BiliSum (this router)
--------------|---------------------
whisper.cpp   | faster-whisper (CTranslate2)
.bin files    | HuggingFace hub cache
subprocess    | in-process Python
5 candidates  | 12 candidates (all faster-whisper sizes)
"""

import os
import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/asr", tags=["asr"])

logger = logging.getLogger("bilisum.asr")

# ---------------------------------------------------------------------------
# Static model catalogue — faster-whisper model sizes with approximate disk usage
# Sizes are for the CTranslate2-format models cached by the library.
# ---------------------------------------------------------------------------
WHISPER_MODEL_CATALOGUE = [
    {"id": "tiny",        "label": "Tiny",          "size_mb": 151,  "lang": "multilingual", "hint": "最快，适合短测试或清晰人声；准确率最低，CPU 也能轻松运行"},
    {"id": "tiny.en",     "label": "Tiny (English)", "size_mb": 151,  "lang": "english-only", "hint": "English-only tiny，比多语言版快但仅支持英文"},
    {"id": "base",        "label": "Base",           "size_mb": 290,  "lang": "multilingual", "hint": "轻量，适合普通短视频粗略笔记；资源占用很低"},
    {"id": "base.en",     "label": "Base (English)",  "size_mb": 290,  "lang": "english-only", "hint": "English-only base，比多语言版快但仅支持英文"},
    {"id": "small",       "label": "Small",          "size_mb": 967,  "lang": "multilingual", "hint": "速度和准确率均衡；适合大多数清晰课程/访谈"},
    {"id": "small.en",    "label": "Small (English)", "size_mb": 967,  "lang": "english-only", "hint": "English-only small，比多语言版快但仅支持英文"},
    {"id": "medium",      "label": "Medium",         "size_mb": 3070, "lang": "multilingual", "hint": "更稳，适合口音或嘈杂内容；转写速度明显更慢"},
    {"id": "medium.en",   "label": "Medium (English)","size_mb": 3070, "lang": "english-only", "hint": "English-only medium，比多语言版快但仅支持英文"},
    {"id": "large-v1",    "label": "Large v1",       "size_mb": 3090, "lang": "multilingual", "hint": "第一代大模型，准确率高但资源占用大"},
    {"id": "large-v2",    "label": "Large v2",       "size_mb": 3090, "lang": "multilingual", "hint": "第二代大模型，改进准确率"},
    {"id": "large-v3",    "label": "Large v3",       "size_mb": 3090, "lang": "multilingual", "hint": "第三代大模型，目前最准确的 whisper 开源模型"},
    {"id": "large-v3-turbo", "label": "Large v3 Turbo", "size_mb": 1630, "lang": "multilingual", "hint": "Large v3 量化版，接近 v3 准确率但资源占用更低"},
]


def _get_models_cache_dir() -> str:
    """Resolve the HuggingFace hub cache directory where faster-whisper stores models."""
    # faster-whisper uses huggingface_hub's default cache: ~/.cache/huggingface/hub
    # The actual model dirs are: models--Systran--faster-whisper-<size>
    hf_home = os.environ.get("HF_HOME", os.path.join(os.path.expanduser("~"), ".cache", "huggingface"))
    return os.path.join(hf_home, "hub")


def _get_model_cache_path(model_id: str) -> str:
    """Return the expected cache directory for a given model size."""
    # faster-whisper models are hosted at Systran/faster-whisper-<size> on HuggingFace
    repo_id = f"models--Systran--faster-whisper-{model_id}"
    return os.path.join(_get_models_cache_dir(), repo_id)


def _is_model_installed(model_id: str) -> bool:
    """Check whether a faster-whisper model is already cached on disk."""
    cache_path = _get_model_cache_path(model_id)
    if not os.path.isdir(cache_path):
        return False
    # A populated cache dir contains snapshots/ or blobs/ subdirectories
    snapshots = os.path.join(cache_path, "snapshots")
    blobs = os.path.join(cache_path, "blobs")
    if os.path.isdir(snapshots) and os.listdir(snapshots):
        return True
    if os.path.isdir(blobs) and os.listdir(blobs):
        return True
    return False


def _get_current_model() -> str:
    """Read the currently configured ASR model (env var or default)."""
    return os.environ.get("BILISUM_ASR_MODEL", "base")


def _set_current_model(model_id: str) -> None:
    """Update the BILISUM_ASR_MODEL environment variable and persist to settings DB."""
    os.environ["BILISUM_ASR_MODEL"] = model_id
    try:
        import database as db
        db.save_setting("asr_model", model_id)
    except Exception as e:
        logger.warning("Failed to persist asr_model setting: %s", e)


# ---------------------------------------------------------------------------
# GET /api/asr/models
# ---------------------------------------------------------------------------
@router.get("/models")
async def list_models():
    """
    List all available faster-whisper model sizes with install status and the
    currently active model. Matches bilinote /api/whisper-models response shape.
    """
    current = _get_current_model()
    models_dir = _get_models_cache_dir()

    # Also try to load persisted setting (takes precedence over env var default)
    try:
        import database as db
        persisted = db.get_setting("asr_model", "")
        if persisted and persisted in {m["id"] for m in WHISPER_MODEL_CATALOGUE}:
            current = persisted
    except Exception:
        pass

    models = []
    for candidate in WHISPER_MODEL_CATALOGUE:
        model_id = candidate["id"]
        installed = _is_model_installed(model_id)
        models.append({
            "id": model_id,
            "label": candidate["label"],
            "size_mb": candidate["size_mb"],
            "lang": candidate["lang"],
            "hint": candidate["hint"],
            "installed": installed,
            "active": model_id == current,
        })

    return JSONResponse({
        "success": True,
        "data": {
            "current_model": current,
            "models_dir": models_dir,
            "models": models,
        }
    })


# ---------------------------------------------------------------------------
# POST /api/asr/models/install
# ---------------------------------------------------------------------------
@router.post("/models/install")
async def install_model(request: Request):
    """
    Pre-download (cache) a faster-whisper model by size id.
    Also sets it as the active model for future transcriptions.

    Optional: set 'set_active': false in the body to download without activating.
    Body: {"id": "small", "set_active": true}
    """
    loop = asyncio.get_running_loop()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Invalid JSON body"}, status_code=400)

    model_id = str(body.get("id", "")).strip()
    if not model_id:
        return JSONResponse({"success": False, "error": "Missing 'id' field"}, status_code=400)

    # Validate model id
    valid_ids = {m["id"] for m in WHISPER_MODEL_CATALOGUE}
    if model_id not in valid_ids:
        return JSONResponse({
            "success": False,
            "error": f"Unknown model '{model_id}'. Valid options: {', '.join(sorted(valid_ids))}"
        }, status_code=400)

    set_active = body.get("set_active", True)

    # Check if already installed
    if _is_model_installed(model_id):
        if set_active:
            _set_current_model(model_id)
        return JSONResponse({
            "success": True,
            "data": {
                "id": model_id,
                "installed": True,
                "active": _get_current_model() if set_active else _get_current_model(),
                "message": f"Model '{model_id}' is already cached and ready."
            }
        })

    # Trigger download via faster-whisper (WhisperModel auto-downloads on creation)
    def _download_model() -> bool:
        try:
            from faster_whisper import WhisperModel
            # Creating a WhisperModel with download_root will trigger cache download
            # Use the default cache so future calls find it immediately
            _model = WhisperModel(model_id, device="cpu", compute_type="int8")
            # Access a property to force full load
            _ = _model.model
            return True
        except Exception as exc:
            logger.error("Failed to download model '%s': %s", model_id, exc)
            raise

    try:
        await loop.run_in_executor(None, _download_model)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"Model download failed: {str(e)[:300]}"
        }, status_code=500)

    # Verify installation
    if not _is_model_installed(model_id):
        return JSONResponse({
            "success": False,
            "error": f"Model '{model_id}' downloaded but cache directory not found. Check disk space."
        }, status_code=500)

    if set_active:
        _set_current_model(model_id)

    return JSONResponse({
        "success": True,
        "data": {
            "id": model_id,
            "installed": True,
            "active": _get_current_model(),
            "message": f"Model '{model_id}' installed successfully and set as active."
        }
    })


# ---------------------------------------------------------------------------
# GET /api/asr/status  — quick availability check (for frontend)
# ---------------------------------------------------------------------------
@router.get("/status")
async def asr_status():
    """Return whether a working ASR backend is available and which model is active."""
    try:
        from asr_service import is_asr_available
        available = is_asr_available()
    except ImportError:
        available = False

    current = _get_current_model()
    # Also check persisted setting
    try:
        import database as db
        persisted = db.get_setting("asr_model", "")
        if persisted:
            current = persisted
    except Exception:
        pass

    return JSONResponse({
        "success": True,
        "data": {
            "available": available,
            "backend": "faster-whisper",
            "current_model": current,
            "models_dir": _get_models_cache_dir(),
        }
    })
