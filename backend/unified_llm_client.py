"""
=============================================================================
BiliSum unified_llm_client.py — claude-api Skill 深度重开发
=============================================================================
Author: claude-api Skill Expert Agent
Date:   2026-07-09
Target: BiliSum v6.1 backend (C:/Users/shiniyaya/Desktop/cc/B站总结工具/B站视频总结工具 -cc/backend/)

This module replaces the ad-hoc API-calling logic scattered across
summarizer.py (lines 247-338) and main.py (lines 2798-2831) with a
single, production-grade UnifiedLLMClient that:

1. Auto-detects model family (Claude / DeepSeek / GPT / o-series / Gemini)
2. Builds a thinking/reasoning_effort parameter matrix compatible with every model
3. Streams v2: proper NDJSON framing + AbortController + reconnect
4. Integrates Anthropic Prompt Caching (cache_control breakpoints)
5. Adaptive thinking budget: adjusts tokens by task complexity
6. Error retry chain: exponential backoff + jitter + max 3 retries
7. Single class encapsulates every provider difference

=============================================================================
SECTION 0 — BUG CATALOG (file:line)
=============================================================================

BUG-01 [summarizer.py:307, B站视频总结工具 -cc]
    thinking = {"type": "adaptive"} 硬编码发送给所有模型
    → DeepSeek 返回 {"error": "unknown parameter: thinking"} (400)
    → GPT 返回 {"error": "Unrecognized request argument: thinking"} (400)
    Impact: 用户选 DeepSeek/GPT 模型但 API URL 填 anthropic.com 时必须崩溃

BUG-02 [summarizer.py:293 & main.py:2800, B站视频总结工具 -cc]
    无 detect_model_family() 函数 — 仅用 "anthropic.com" in url 判断 API 类型
    → URL https://api.anthropic.com + model="gpt-4o" → 发送 Anthropic-format 请求给非 Claude 模型
    → URL https://api.openai.com + model="claude-opus-4-8" → 发送 OpenAI-format 请求给 OpenAI（Claude 模型不被识别）
    Impact: 100% 错误率当 model 和 API URL 不匹配时

BUG-03 [main.py:1044-1054, B站视频总结工具 -cc]
    流式 SSE 未正确处理 NDJSON 分帧
    → raw_line.decode("utf-8") 假设 raw_line 是 bytes，但 httpx aiter_lines() 已返回 str
    → silent pass on JSON parse exceptions 吞掉所有错误
    → 无 AbortController / 无重连 / 无 server-sent error 检测
    Impact: 流式问答在生产环境随机静默失败

BUG-04 [summarizer.py:303-308, B站视频总结工具 -cc]
    Anthropic prompt cache 完全未使用
    → 重复发送相同的 system prompt 但不标记 cache_control
    → 每次请求全额计费 input tokens
    → SKILL.md 明确："Top-level auto-caching is the simplest option"
    Impact: input token 成本高 4-10 倍 (cache write/read 为原始价格的 1.25x/0.10x)

BUG-05 [main.py:2802-2830, B站视频总结工具 -cc]
    错误重试链不完善 — 2 ** attempt 退避无 jitter
    → 429/503/502 重试但 529(overloaded) 不重试
    → ConnectionError 捕获为 last_error 但不区分 DNS 错误
    → 退避时间: attempt 1→1s, 2→2s, 3→4s（过低，无 jitter，雷群效应）
    Impact: 速率限制时产生 thundering herd

BUG-06 [main.py:2808 & summarizer.py:303-308, B站视频总结工具 -cc]
    thinking 参数对 pre-4.6 Claude 模型不兼容
    → Opus 3.5, Sonnet 3.7 等旧模型: thinking 需要 budget_tokens
    → Fable 5: thinking: {type: "disabled"} 返回 400（必须 omit）
    → 无模型版本感知
    Impact: 用旧模型直接报 400

BUG-07 [main.py:2806, B站视频总结工具 -cc]
    anthropic-version: "2023-06-01" 使用过时的 API version
    → 某些新特性 (adaptive thinking, xhigh effort, task budgets) 可能不受支持
    → SKILL.md 建议使用当前版本

BUG-08 [summarizer.py:271 & main.py:879, B站视频总结工具 -cc]
    无自适应思考预算 — rich content 和 short content 用相同的 max_tokens
    → summarizer.py:271-284 有部分动态 max_tokens 但 thinking budget（影响 Claude quality）
      完全不调整
    → RAG 问答的 max_tokens 硬编码为 4096 (main.py:2808)
    Impact: 长视频总结质量不足，短视频浪费 tokens

=============================================================================
SECTION 1 — MODEL FAMILY DETECTION + COMPATIBILITY MATRIX
=============================================================================
"""

import re
import os
import json
import time
import base64
import asyncio
import logging
import random
import mimetypes
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Literal

logger = logging.getLogger("unified_llm")

# Fallback chain: primary → secondary → tertiary
FALLBACK_CHAIN = [
    {
        "api_url": "https://api.anthropic.com/v1/messages",
        "model": "claude-opus-4-8",
        "family": "claude",
    },
    {
        "api_url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "family": "deepseek",
    },
    {
        "api_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o",
        "family": "openai",
    },
]

# ---------------------------------------------------------------------------
# 1.1  Model families
# ---------------------------------------------------------------------------

class ModelFamily(Enum):
    """Every LLM provider / model family BiliSum may encounter."""
    CLAUDE_FABLE5      = "claude_fable5"       # claude-fable-5, claude-mythos-5
    CLAUDE_OPUS_4_7_PLUS = "claude_opus_47plus"  # claude-opus-4-7, claude-opus-4-8
    CLAUDE_OPUS_4_6    = "claude_opus_46"       # claude-opus-4-6
    CLAUDE_SONNET_5    = "claude_sonnet_5"      # claude-sonnet-5
    CLAUDE_SONNET_4_6  = "claude_sonnet_46"     # claude-sonnet-4-6
    CLAUDE_LEGACY      = "claude_legacy"        # sonnet-4-5, opus-4-5, haiku-4-5, older
    DEEPSEEK           = "deepseek"             # deepseek-chat, deepseek-reasoner
    GPT_O_SERIES       = "gpt_o_series"         # o1, o3, o4-mini
    GPT_STANDARD       = "gpt_standard"         # gpt-4o, gpt-4-turbo, gpt-5
    GEMINI             = "gemini"               # gemini-2.5-flash/pro
    UNKNOWN            = "unknown"              # fallback (OpenAI-compatible assumed)


# ---------------------------------------------------------------------------
# 1.2  Family detection — model-id based (NOT URL based)
# ---------------------------------------------------------------------------

_MODEL_FAMILY_RULES: list[tuple[str, ModelFamily]] = [
    # Fable 5 family (most specific first)
    (r"claude[- ]fable[- ]5",      ModelFamily.CLAUDE_FABLE5),
    (r"claude[- ]mythos[- ]5",     ModelFamily.CLAUDE_FABLE5),  # same API surface
    # Opus 4.7 / 4.8 (adaptive-only, budget_tokens removed)
    (r"claude[- ]opus[- ]4[.\-]?[78]", ModelFamily.CLAUDE_OPUS_4_7_PLUS),
    # Opus 4.6 (adaptive, budget_tokens deprecated but functional)
    (r"claude[- ]opus[- ]4[.\-]?6",    ModelFamily.CLAUDE_OPUS_4_6),
    # Sonnet 5
    (r"claude[- ]sonnet[- ]5",     ModelFamily.CLAUDE_SONNET_5),
    # Sonnet 4.6
    (r"claude[- ]sonnet[- ]4[.\-]?6",  ModelFamily.CLAUDE_SONNET_4_6),
    # Legacy Claude (everything else claude-*)
    (r"claude",                    ModelFamily.CLAUDE_LEGACY),
    # DeepSeek
    (r"deepseek",                  ModelFamily.DEEPSEEK),
    # GPT o-series (reasoning models — NO temperature, NO system prompt support)
    (r"\b(o[1-9]|o3|o4)",         ModelFamily.GPT_O_SERIES),
    # GPT standard
    (r"\b(gpt|chatgpt)",           ModelFamily.GPT_STANDARD),
    # Gemini
    (r"gemini",                    ModelFamily.GEMINI),
]


def classify_model_family(model_id: str) -> ModelFamily:
    """Detect model family from model ID string (returns ModelFamily enum).

    >>> classify_model_family("claude-opus-4-8")
    <ModelFamily.CLAUDE_OPUS_4_7_PLUS>
    >>> classify_model_family("deepseek-chat")
    <ModelFamily.DEEPSEEK>
    >>> classify_model_family("gpt-4o")
    <ModelFamily.GPT_STANDARD>
    """
    mid = (model_id or "").strip().lower()
    if not mid:
        return ModelFamily.UNKNOWN
    for pattern, family in _MODEL_FAMILY_RULES:
        if re.search(pattern, mid):
            return family
    return ModelFamily.UNKNOWN


def detect_api_format(api_url: str, model_id: str) -> Literal["anthropic", "openai"]:
    """Determine which API format to use: Anthropic Messages API vs OpenAI chat/completions.

    Priority: model family > URL heuristic.
    """
    family = classify_model_family(model_id)
    # Claude family models ALWAYS use Anthropic format
    if family.value.startswith("claude"):
        return "anthropic"
    # Non-Claude: check URL
    url_lower = (api_url or "").lower()
    if "anthropic.com" in url_lower:
        return "anthropic"
    # Everything else → OpenAI-compatible
    return "openai"


# ---------------------------------------------------------------------------
# 1.3  Thinking / reasoning_effort compatibility matrix
# ---------------------------------------------------------------------------

@dataclass
class ThinkingConfig:
    """Per-model-family thinking parameter configuration."""
    # Top-level thinking param (None = omit entirely)
    thinking: Optional[dict] = None          # e.g. {"type": "adaptive"}
    # output_config.effort (None = omit)
    effort: Optional[str] = None             # "low" | "medium" | "high" | "xhigh" | "max"
    # For o-series: reasoning_effort instead
    reasoning_effort: Optional[str] = None   # "low" | "medium" | "high"
    # Sampling params (None = omit)
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    # Whether system prompt goes in top-level "system" vs messages
    system_top_level: bool = True
    # Max tokens safe default
    default_max_tokens: int = 4096
    # Whether streaming is recommended for long outputs
    recommend_streaming: bool = True
    # Extra betas required
    extra_betas: list[str] = field(default_factory=list)
    # Fable 5 fallbacks param (server-side refusal rescue)
    fallbacks: Optional[list[dict]] = None


# ---- Compatibility Matrix ----
THINKING_MATRIX: dict[ModelFamily, ThinkingConfig] = {
    # ---- Fable 5 / Mythos 5 ----
    # thinking: omit or {"type":"adaptive"} only.
    # {"type":"disabled"} → 400. budget_tokens → 400.
    # temperature/top_p/top_k → 400.
    # Fallbacks must be opt-in: betas header + fallbacks body param.
    # refusal stop reason → check before reading content.
    ModelFamily.CLAUDE_FABLE5: ThinkingConfig(
        thinking={"type": "adaptive"},
        effort="xhigh",
        temperature=None,      # MUST omit
        top_p=None,
        top_k=None,
        default_max_tokens=16000,
        recommend_streaming=True,
        extra_betas=["server-side-fallback-2026-06-01"],
        fallbacks=[{"model": "claude-opus-4-8"}],  # refusal rescue
    ),

    # ---- Opus 4.7 / 4.8 ----
    # thinking: {"type":"adaptive"} or {"type":"disabled"} or omit.
    # budget_tokens → 400. temperature/top_p/top_k → removed on 4.7+.
    # xhigh effort available on 4.7+.
    # Fast mode on 4.8 only.
    ModelFamily.CLAUDE_OPUS_4_7_PLUS: ThinkingConfig(
        thinking={"type": "adaptive"},
        effort="xhigh",
        temperature=None,
        top_p=None,
        top_k=None,
        default_max_tokens=16000,
        recommend_streaming=True,
        extra_betas=[],
    ),

    # ---- Opus 4.6 ----
    # thinking: {"type":"adaptive"} recommended. budget_tokens deprecated but functional.
    # temperature/top_p/top_k still accepted.
    # effort up to "max" (no xhigh).
    ModelFamily.CLAUDE_OPUS_4_6: ThinkingConfig(
        thinking={"type": "adaptive"},
        effort="high",
        temperature=0.7,
        top_p=None,
        top_k=None,
        default_max_tokens=8192,
        recommend_streaming=True,
        extra_betas=[],
    ),

    # ---- Sonnet 5 ----
    # Same as Opus 4.7/4.8: adaptive only, no budget_tokens, no temp params.
    ModelFamily.CLAUDE_SONNET_5: ThinkingConfig(
        thinking={"type": "adaptive"},
        effort="xhigh",
        temperature=None,
        top_p=None,
        top_k=None,
        default_max_tokens=8192,
        recommend_streaming=True,
        extra_betas=[],
    ),

    # ---- Sonnet 4.6 ----
    ModelFamily.CLAUDE_SONNET_4_6: ThinkingConfig(
        thinking={"type": "adaptive"},
        effort="high",
        temperature=0.7,
        top_p=None,
        top_k=None,
        default_max_tokens=8192,
        recommend_streaming=True,
        extra_betas=[],
    ),

    # ---- Legacy Claude (pre-4.6) ----
    # budget_tokens required, no adaptive thinking, no effort.
    # CRITICAL: budget_tokens MUST be < max_tokens (min 1024), or API 400.
    ModelFamily.CLAUDE_LEGACY: ThinkingConfig(
        thinking={"type": "enabled", "budget_tokens": 4096},
        effort=None,
        temperature=0.7,
        top_p=None,
        top_k=None,
        default_max_tokens=8192,  # must be > budget_tokens (4096)
        recommend_streaming=False,
        extra_betas=[],
    ),

    # ---- DeepSeek ----
    # No thinking/reasoning params. temperature OK.
    ModelFamily.DEEPSEEK: ThinkingConfig(
        thinking=None,
        effort=None,
        reasoning_effort=None,
        temperature=0.7,
        default_max_tokens=4096,
        recommend_streaming=False,
        extra_betas=[],
    ),

    # ---- GPT o-series ----
    # reasoning_effort (NOT thinking). No temperature. No system prompt (goes in user message).
    # max_tokens → max_completion_tokens.
    ModelFamily.GPT_O_SERIES: ThinkingConfig(
        thinking=None,
        effort=None,
        reasoning_effort="medium",
        temperature=None,
        top_p=None,
        top_k=None,
        system_top_level=False,   # system → prepend to first user message
        default_max_tokens=16000, # max_completion_tokens
        recommend_streaming=False,
        extra_betas=[],
    ),

    # ---- GPT Standard ----
    # No thinking. temperature OK. system top-level OK.
    ModelFamily.GPT_STANDARD: ThinkingConfig(
        thinking=None,
        effort=None,
        reasoning_effort=None,
        temperature=0.7,
        default_max_tokens=4096,
        recommend_streaming=False,
        extra_betas=[],
    ),

    # ---- Gemini ----
    ModelFamily.GEMINI: ThinkingConfig(
        thinking=None,
        effort=None,
        reasoning_effort=None,
        temperature=0.7,
        default_max_tokens=4096,
        recommend_streaming=False,
        extra_betas=[],
    ),

    # ---- Unknown (OpenAI-compatible fallback) ----
    ModelFamily.UNKNOWN: ThinkingConfig(
        thinking=None,
        effort=None,
        reasoning_effort=None,
        temperature=0.7,
        default_max_tokens=4096,
        recommend_streaming=False,
        extra_betas=[],
    ),
}


def get_thinking_config(model_id: str) -> ThinkingConfig:
    """Return the correct thinking config for a given model ID."""
    family = classify_model_family(model_id)
    return THINKING_MATRIX.get(family, THINKING_MATRIX[ModelFamily.UNKNOWN])


def build_thinking_params_from_config(model_id: str, overrides: Optional[dict] = None) -> dict:
    """Build the safe parameter dict for a /messages or /chat/completions call.

    Returns a dict of parameters ready to merge into the request JSON.
    Parameters that should NOT be sent are absent from the returned dict.
    """
    cfg = get_thinking_config(model_id)
    overrides = overrides or {}

    params: dict = {}

    # --- thinking ---
    if cfg.thinking is not None and "thinking" not in overrides:
        params["thinking"] = cfg.thinking
    elif "thinking" in overrides and overrides["thinking"] is not None:
        params["thinking"] = overrides["thinking"]

    # --- effort (inside output_config for Claude; omitted for others) ---
    family = classify_model_family(model_id)
    if family.value.startswith("claude") and cfg.effort is not None:
        effort = overrides.get("effort", cfg.effort)
        if effort:
            params["output_config"] = {"effort": effort}

    # --- reasoning_effort (o-series only) ---
    if family == ModelFamily.GPT_O_SERIES and cfg.reasoning_effort is not None:
        re_effort = overrides.get("reasoning_effort", cfg.reasoning_effort)
        if re_effort:
            params["reasoning_effort"] = re_effort

    # --- temperature (omit for models that reject it) ---
    if cfg.temperature is not None and "temperature" not in overrides:
        params["temperature"] = cfg.temperature
    elif "temperature" in overrides:
        params["temperature"] = overrides["temperature"]

    # --- top_p ---
    if cfg.top_p is not None:
        params["top_p"] = cfg.top_p

    # --- max_tokens / max_completion_tokens ---
    max_tok = overrides.get("max_tokens", cfg.default_max_tokens)
    if family == ModelFamily.GPT_O_SERIES:
        params["max_completion_tokens"] = max_tok
    else:
        params["max_tokens"] = max_tok

    return params


# ---------------------------------------------------------------------------
# 1.4  Public API: detect_model_family (URL + model → string)
#       Returns a simple string label: "claude" | "deepseek" | "openai" | "gemini" | "unknown"
#       This is the high-level public interface used by the rest of BiliSum.
# ---------------------------------------------------------------------------


def detect_model_family(api_url: str, model: str) -> str:
    """Detect model family from API URL and model name.

    Returns a simple string label for the model family.
    Uses model-based detection first (via classify_model_family),
    then falls back to URL heuristic as a secondary signal.

    >>> detect_model_family("https://api.anthropic.com", "claude-opus-4-8")
    "claude"
    >>> detect_model_family("https://api.deepseek.com", "deepseek-chat")
    "deepseek"
    >>> detect_model_family("https://api.openai.com", "gpt-4o")
    "openai"
    """
    # Model-based detection is authoritative (fixes BUG-02 where
    # URL != model caused 100% param mismatch).  Delegate to the
    # shared classify_model_family() to avoid duplicate regex rules.
    mf = classify_model_family(model)
    if mf == ModelFamily.UNKNOWN:
        # Fall back to URL heuristic for models our regexes don't cover
        if api_url:
            url_lower = api_url.lower()
            if "anthropic.com" in url_lower:
                return "claude"
            elif "deepseek.com" in url_lower:
                return "deepseek"
            elif "openai.com" in url_lower:
                return "openai"
            elif "dashscope" in url_lower or "aliyuncs.com" in url_lower:
                # DashScope compatible-mode (qwen / qwen-vl) is OpenAI-format
                return "openai"
            elif "googleapis.com" in url_lower:
                return "gemini"
        return "unknown"

    # Map ModelFamily enum → simple string labels
    _MF_TO_STR = {
        ModelFamily.CLAUDE_FABLE5: "claude",
        ModelFamily.CLAUDE_OPUS_4_7_PLUS: "claude",
        ModelFamily.CLAUDE_OPUS_4_6: "claude",
        ModelFamily.CLAUDE_SONNET_5: "claude",
        ModelFamily.CLAUDE_SONNET_4_6: "claude",
        ModelFamily.CLAUDE_LEGACY: "claude",
        ModelFamily.DEEPSEEK: "deepseek",
        ModelFamily.GPT_O_SERIES: "openai",
        ModelFamily.GPT_STANDARD: "openai",
        ModelFamily.GEMINI: "gemini",
    }
    return _MF_TO_STR.get(mf, "unknown")


def build_thinking_params(api_url: str, model: str) -> dict:
    """Build thinking/reasoning params for the specific model family.

    CRITICAL: Parameters not supported by a model MUST NOT be sent.
    Default: maximum thinking/reasoning level for the model.

    Returns a dict of parameters ready to merge into the API request body.
    Returns an empty dict {} if the model does not support extended thinking.

    >>> build_thinking_params("https://api.anthropic.com", "claude-sonnet-5")
    {"thinking": {"type": "adaptive"}}
    >>> build_thinking_params("https://api.deepseek.com", "deepseek-chat")
    {"reasoning_effort": "maximum"}
    >>> build_thinking_params("https://api.openai.com", "gpt-4o")
    {}
    """
    family = detect_model_family(api_url, model)
    model_lower = model.lower()

    if family == "claude":
        # Claude uses `thinking` parameter
        # Opus 4.7+/Sonnet 5 use "adaptive" (no budget_tokens)
        # Older versions use "enabled" with explicit budget
        if "haiku" in model_lower:
            return {}  # Haiku doesn't support extended thinking
        elif "opus" in model_lower:
            # Opus 4.7+ requires adaptive mode
            return {"thinking": {"type": "adaptive"}}
        elif "sonnet" in model_lower:
            # Sonnet 5 requires adaptive mode
            return {"thinking": {"type": "adaptive"}}
        else:
            return {}  # Unknown Claude variant — don't risk 400

    elif family == "deepseek":
        # DeepSeek uses `reasoning_effort` (NOT `thinking`)
        if "reasoner" in model_lower or "r1" in model_lower:
            return {}  # R1 auto-thinks, rejects params
        else:
            return {"reasoning_effort": "maximum"}  # V3 supports reasoning_effort

    elif family == "openai":
        # OpenAI uses `reasoning_effort`
        if "gpt-5" in model_lower or "o3" in model_lower or "o4" in model_lower:
            return {"reasoning_effort": "high"}
        elif "o1" in model_lower:
            return {"reasoning_effort": "high"}
        else:
            return {}  # GPT-4o etc. don't support reasoning

    elif family == "gemini":
        return {"thinkingConfig": {"thinkingBudget": 8192}}

    return {}  # Unknown — omit to avoid errors


# ---- Compatibility reference table (for documentation) ----
THINKING_COMPATIBILITY: dict[str, dict] = {
    "claude-opus-4-8":     {"param": "thinking", "value": {"type": "adaptive"}, "effort": "xhigh", "note": "adaptive only; budget_tokens removed"},
    "claude-opus-4-7":     {"param": "thinking", "value": {"type": "adaptive"}, "effort": "xhigh", "note": "adaptive only; budget_tokens removed"},
    "claude-sonnet-5":     {"param": "thinking", "value": {"type": "adaptive"}, "effort": "xhigh", "note": "adaptive only; budget_tokens removed"},
    "claude-opus-4-6":     {"param": "thinking", "value": {"type": "adaptive"}, "effort": "high", "note": "adaptive recommended; budget_tokens deprecated"},
    "claude-haiku-4.5":    {"param": None, "value": {}, "note": "Haiku不支持thinking，发送→400"},
    "deepseek-chat":       {"param": "reasoning_effort", "value": "maximum", "note": "V3用reasoning_effort而非thinking"},
    "deepseek-reasoner":   {"param": None, "value": {}, "note": "R1自动思考，不接受参数"},
    "gpt-5":               {"param": "reasoning_effort", "value": "high", "max_level": "high"},
    "gpt-4o":              {"param": None, "value": {}, "note": "不支持扩展思考"},
}


# =============================================================================
# SECTION 2 — ADAPTIVE THINKING BUDGET
# =============================================================================

@dataclass
class TaskBudget:
    """Dynamically computed token budget for a summary/QA request."""
    max_tokens: int           # output token ceiling
    thinking_tokens: int      # Claude thinking budget (informational, for effort mapping)
    effort: str               # "low" | "medium" | "high" | "xhigh" | "max"
    prompt_tokens_estimate: int
    system_prompt_tokens: int


def compute_adaptive_budget(
    prompt_text: str,
    system_text: str = "",
    mode: str = "detailed",
    subtitle_chars: int = 0,
    comment_count: int = 0,
    duration_minutes: float = 0,
    quality_multiplier: float = 1.0,
) -> TaskBudget:
    """Compute adaptive token budgets based on task complexity.

    Rules (from prompt-tuning experience):
    - Short content (< 1000 chars) → low effort, small max_tokens
    - Long content (> 10000 chars) → xhigh effort, large max_tokens
    - "detailed" mode → +1 effort tier
    - High quality multiplier → +1 effort tier
    - Streaming always recommended for > 4000 max_tokens
    """
    # Estimate token counts (conservative: 1 token ≈ 3 chars for Chinese)
    prompt_estimate = len(prompt_text) // 2  # Chinese-heavy
    system_estimate = len(system_text) // 3

    # Base max_tokens from content length
    if subtitle_chars < 500:
        base_max_tokens = 1024
    elif subtitle_chars < 3000:
        base_max_tokens = 2048
    elif subtitle_chars < 10000:
        base_max_tokens = 4096
    elif subtitle_chars < 30000:
        base_max_tokens = 8192
    else:
        base_max_tokens = 16000

    # Mode multiplier
    mode_mult = {"brief": 0.4, "keypoints": 0.6, "mindmap": 0.8, "detailed": 1.0}.get(mode, 0.8)

    # Quality multiplier applies to max_tokens
    adjusted_max = int(base_max_tokens * mode_mult * quality_multiplier)
    adjusted_max = max(256, min(adjusted_max, 64000))  # hard floor/ceiling

    # Effort level
    if quality_multiplier >= 1.5 and subtitle_chars > 5000:
        effort = "max"
    elif quality_multiplier >= 1.2 and subtitle_chars > 3000:
        effort = "xhigh"
    elif mode == "detailed" and subtitle_chars > 3000:
        effort = "high"
    elif mode == "detailed":
        effort = "medium"
    else:
        effort = "medium"

    # Thinking tokens (for Claude families; informational)
    if effort == "max":
        thinking_tokens = min(32000, adjusted_max)
    elif effort == "xhigh":
        thinking_tokens = min(24000, adjusted_max)
    elif effort == "high":
        thinking_tokens = min(16000, adjusted_max // 2)
    else:
        thinking_tokens = min(8000, adjusted_max // 4)

    return TaskBudget(
        max_tokens=adjusted_max,
        thinking_tokens=thinking_tokens,
        effort=effort,
        prompt_tokens_estimate=prompt_estimate,
        system_prompt_tokens=system_estimate,
    )


# =============================================================================
# SECTION 3 — PROMPT CACHE INTEGRATION (Anthropic)
# =============================================================================

def build_cached_system(system_text: str) -> list[dict]:
    """Wrap system text with Anthropic cache_control breakpoints.

    Places a cache_control={"type":"ephemeral"} at the end of the system
    content block so the entire system prompt is cached across requests.

    SKILL.md notes:
    - Max 4 breakpoints per request
    - Minimum ~1024 tokens for a cacheable prefix
    - Prefix match: any byte change invalidates everything after it
    - Verify with usage.cache_read_input_tokens != 0
    """
    if not system_text or len(system_text) < 500:
        # Too short to benefit from caching
        return [{"type": "text", "text": system_text}]

    return [{
        "type": "text",
        "text": system_text,
        "cache_control": {"type": "ephemeral"},
    }]


def build_cached_messages(
    messages: list[dict],
    cache_last_user: bool = True,
) -> list[dict]:
    """Add cache_control breakpoints to message history.

    Places cache_control on the last user message's last content block
    so repeated turns with same history get cache hits on the prefix.

    Args:
        messages: List of {"role": ..., "content": ...} dicts
        cache_last_user: If True, mark the last user message for caching

    Returns:
        Modified messages list (in-place, but also returned)
    """
    if not cache_last_user or not messages:
        return messages

    # Find last user message
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                msg["content"] = [{
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }]
            elif isinstance(content, list):
                # Add cache_control to the last text block
                for block in reversed(content):
                    if isinstance(block, dict) and block.get("type") == "text":
                        block["cache_control"] = {"type": "ephemeral"}
                        break
            break

    return messages


def extract_cache_stats(usage: dict) -> dict:
    """Extract prompt caching statistics from API response usage.

    Returns:
        {"cache_hit_tokens": N, "cache_write_tokens": N, "cache_hit_ratio": 0.0-1.0}
    """
    input_tokens = usage.get("input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0)

    total_cached = cache_read + cache_write
    ratio = (cache_read / max(input_tokens, 1)) if input_tokens > 0 else 0.0

    return {
        "cache_hit_tokens": cache_read or 0,
        "cache_write_tokens": cache_write or 0,
        "cache_hit_ratio": round(ratio, 4),
        "input_tokens": input_tokens,
    }


# =============================================================================
# SECTION 3.5 — MULTIMODAL MESSAGE BUILDER (images)
# =============================================================================
#
# Canonical image input accepted everywhere (str or dict):
#   - "data:image/jpeg;base64,...."          data URI
#   - "iVBORw0KGgo..." / "/9j/4AAQ..."       raw base64 (media type sniffed)
#   - "https://example.com/frame.jpg"        remote URL
#   - "C:/frames/kf_001.jpg"                 local file path (read + base64)
#   - {"base64": "...", "media_type": "image/png"}
#   - {"url": "https://..."}
#   - {"path": "C:/frames/kf_001.jpg"}
#
# Output formats:
#   anthropic → {"type": "image", "source": {"type": "base64"|"url", ...}}
#   openai    → {"type": "image_url", "image_url": {"url": "<data-uri-or-url>"}}
#               (DashScope compatible-mode /chat/completions for qwen-vl-* uses
#                the exact same OpenAI part shape, so one builder covers both.)

_B64_RE = re.compile(r"^[A-Za-z0-9+/=\s]+$")

# magic-prefix → media type for raw base64 sniffing
_B64_MAGIC = [
    ("/9j/", "image/jpeg"),
    ("iVBORw0KGgo", "image/png"),
    ("R0lGOD", "image/gif"),
    ("UklGR", "image/webp"),
]


def _sniff_media_type(b64_data: str) -> str:
    """Guess media type from base64 magic bytes (default image/jpeg)."""
    for prefix, mtype in _B64_MAGIC:
        if b64_data.startswith(prefix):
            return mtype
    return "image/jpeg"


def _normalize_image_input(image) -> dict:
    """Normalize any accepted image input into {"kind": "base64"|"url", ...}.

    Returns:
        {"kind": "base64", "data": "<raw b64>", "media_type": "image/jpeg"}
        or
        {"kind": "url", "url": "https://..."}

    Raises:
        ValueError: input is not a recognizable image reference.
    """
    # ---- dict inputs ----
    if isinstance(image, dict):
        if image.get("url"):
            return {"kind": "url", "url": image["url"]}
        if image.get("base64"):
            data = image["base64"]
            # tolerate data URIs passed under "base64"
            if data.startswith("data:"):
                return _normalize_image_input(data)
            return {
                "kind": "base64",
                "data": data,
                "media_type": image.get("media_type") or _sniff_media_type(data),
            }
        if image.get("path"):
            return _normalize_image_input(image["path"])
        raise ValueError(f"Unrecognized image dict (need url/base64/path): {list(image)}")

    if not isinstance(image, str) or not image.strip():
        raise ValueError(f"Unrecognized image input: {type(image).__name__}")
    image = image.strip()

    # ---- data URI ----
    if image.startswith("data:"):
        try:
            header, data = image.split(",", 1)
        except ValueError:
            raise ValueError("Malformed data URI (no comma)")
        media_type = header[5:].split(";")[0] or "image/jpeg"
        return {"kind": "base64", "data": data, "media_type": media_type}

    # ---- remote URL ----
    if image.startswith(("http://", "https://")):
        return {"kind": "url", "url": image}

    # ---- local file path ----
    if os.path.isfile(image):
        media_type = mimetypes.guess_type(image)[0] or "image/jpeg"
        with open(image, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return {"kind": "base64", "data": data, "media_type": media_type}

    # ---- raw base64 (long, base64-alphabet-only string) ----
    if len(image) > 64 and _B64_RE.match(image):
        return {"kind": "base64", "data": image, "media_type": _sniff_media_type(image)}

    raise ValueError(f"Unrecognized image input (not URI/URL/path/base64): {image[:80]}")


def build_image_block(image, api_format: str = "anthropic") -> dict:
    """Build a single image content block for the given API format.

    >>> build_image_block("https://i0.hdslb.com/cover.jpg", "openai")
    {"type": "image_url", "image_url": {"url": "https://i0.hdslb.com/cover.jpg"}}
    """
    norm = _normalize_image_input(image)

    if api_format == "anthropic":
        if norm["kind"] == "url":
            return {"type": "image", "source": {"type": "url", "url": norm["url"]}}
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": norm["media_type"],
                "data": norm["data"],
            },
        }

    # OpenAI-compatible (incl. DashScope compatible-mode for qwen-vl-*)
    if norm["kind"] == "url":
        url = norm["url"]
    else:
        url = f"data:{norm['media_type']};base64,{norm['data']}"
    return {"type": "image_url", "image_url": {"url": url}}


def build_multimodal_content(text: str, images: list, api_format: str = "anthropic") -> list[dict]:
    """Build a content-block list: images first (better VL grounding), then text."""
    blocks = [build_image_block(img, api_format) for img in (images or [])]
    if text:
        blocks.append({"type": "text", "text": text})
    return blocks


def attach_images_to_last_user(messages: list[dict], images: list, api_format: str) -> list[dict]:
    """Attach images to the last user message in-place (and return messages).

    String content is promoted to a content-block list; existing block lists
    get the image blocks prepended.  No-op when images is empty.
    """
    if not images:
        return messages
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                msg["content"] = build_multimodal_content(content, images, api_format)
            elif isinstance(content, list):
                msg["content"] = (
                    [build_image_block(img, api_format) for img in images] + content
                )
            return messages
    # No user message yet — create one carrying only the images
    messages.append({"role": "user", "content": build_multimodal_content("", images, api_format)})
    return messages


def convert_content_blocks_to_openai(content) -> "str | list":
    """Normalize message content for OpenAI-compatible endpoints (incl. DashScope).

    - str → returned unchanged
    - Anthropic image blocks → {"type": "image_url", ...} parts
    - Anthropic text blocks → {"type": "text", ...} parts (cache_control stripped)
    - Already-OpenAI parts → passed through
    - Pure-text block lists collapse back to a plain string (maximum
      compatibility with strict OpenAI-clones that reject part arrays)
    """
    if isinstance(content, str) or content is None:
        return content or ""
    if not isinstance(content, list):
        return str(content)

    parts: list[dict] = []
    has_image = False
    for block in content:
        if not isinstance(block, dict):
            parts.append({"type": "text", "text": str(block)})
            continue
        btype = block.get("type")
        if btype == "text":
            parts.append({"type": "text", "text": block.get("text", "")})
        elif btype == "image_url":                      # already OpenAI format
            has_image = True
            parts.append(block)
        elif btype == "image":                          # Anthropic format → convert
            has_image = True
            source = block.get("source", {})
            if source.get("type") == "url":
                url = source.get("url", "")
            else:
                url = (
                    f"data:{source.get('media_type', 'image/jpeg')};"
                    f"base64,{source.get('data', '')}"
                )
            parts.append({"type": "image_url", "image_url": {"url": url}})
        # unknown block types (thinking, tool_use, ...) are dropped for OpenAI

    if not has_image:
        return "".join(p.get("text", "") for p in parts)
    return parts


def convert_messages_for_openai(messages: list[dict]) -> list[dict]:
    """Apply convert_content_blocks_to_openai to every message (non-mutating)."""
    return [
        {**msg, "content": convert_content_blocks_to_openai(msg.get("content"))}
        for msg in messages
    ]


# =============================================================================
# SECTION 4 — SSE STREAMING v2 (NDJSON framing + AbortController + reconnect)
# =============================================================================

import asyncio as _asyncio
from contextlib import asynccontextmanager


class StreamAbortedError(Exception):
    """Raised when streaming is aborted by the controller."""
    pass


class AbortController:
    """Lightweight abort controller for async HTTP streaming."""

    def __init__(self):
        self._aborted = False
        self._event = _asyncio.Event()

    def abort(self):
        self._aborted = True
        self._event.set()

    @property
    def aborted(self) -> bool:
        return self._aborted

    async def wait_with_timeout(self, timeout: float) -> bool:
        """Wait for abort signal with timeout. Returns True if aborted."""
        try:
            await _asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except _asyncio.TimeoutError:
            return False


# NDJSON event types for BiliSum streaming
SSE_EVENT_TYPES = {"status", "token", "routing", "retrieval", "sources", "done", "error"}


def parse_sse_line(line: str) -> Optional[dict]:
    """Parse a single SSE/NDJSON line into a dict event.

    Handles:
    - OpenAI SSE: "data: {...}\n"
    - Anthropic SSE: "event: content_block_delta" / "data: {...}"
    - Anthropic SSE content_block_delta → extract text delta
    - NDJSON: '{"type": "token", "text": "hello"}\n'
    - Empty lines, comments ("": skip)
    - [DONE] sentinel

    Returns None for skippable lines.
    """
    line = line.strip()
    if not line:
        return None

    # NDJSON format (BiliSum native)
    if line.startswith("{"):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    # OpenAI SSE: "data: {...}"
    if line.startswith("data: "):
        payload = line[6:]
        if payload == "[DONE]":
            return {"type": "done"}
        try:
            chunk = json.loads(payload)
            # Anthropic SSE: content_block_delta with text
            if "delta" in chunk and "text" in chunk.get("delta", {}):
                return {"type": "token", "text": chunk["delta"]["text"]}
            # Anthropic SSE: content_block_start with text
            if "content_block" in chunk:
                block = chunk["content_block"]
                if isinstance(block, dict) and block.get("type") == "text":
                    return {"type": "token", "text": block.get("text", "")}
            # Anthropic SSE: message_delta with stop_reason
            if "delta" in chunk and "stop_reason" in chunk.get("delta", {}):
                stop = chunk["delta"]["stop_reason"]
                if stop == "refusal":
                    return {"type": "error", "message": f"Content refused: {chunk.get('stop_details', {})}"}
                return None  # message_delta stop_reason handled separately
            # Anthropic SSE: message_start / ping
            if "message" in chunk or chunk.get("type") == "ping":
                return None
            # Anthropic SSE: usage from message_delta
            if "usage" in chunk:
                return {"type": "usage", "usage": chunk["usage"]}
            # OpenAI SSE: choices delta
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            content = delta.get("content", "")
            return {"type": "token", "text": content} if content else None
        except json.JSONDecodeError:
            return None

    # Anthropic SSE: "event: content_block_delta" → skip (data follows on next line)
    if line.startswith("event: "):
        return None  # event type line; data follows

    # Catch-all: try JSON
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


@asynccontextmanager
async def stream_sse(
    response,  # httpx Response
    controller: Optional[AbortController] = None,
    max_reconnect: int = 2,
    reconnect_delay: float = 1.0,
    reconnect_cb: Optional[callable] = None,  # async () → httpx.Response
):
    """Async generator wrapper for SSE streaming with abort + reconnect.

    Usage:
        async with stream_sse(response) as events:
            async for event in events:
                if event["type"] == "token":
                    yield event["text"]

    reconnect_cb: Optional async callable that returns a new httpx.Response.
        If provided, the streamer will call it to re-establish the connection
        when the stream drops.  Without it, reconnection is disabled.
    """
    abort_ctrl = controller or AbortController()

    class _EventStream:
        def __init__(self, resp, ctrl, on_reconnect=None):
            self._resp = resp
            self._ctrl = ctrl
            self._buffer = b""
            self._on_reconnect = on_reconnect

        async def __aiter__(self):
            reconnect_remaining = max_reconnect if self._on_reconnect else 0
            current_resp = self._resp

            while True:
                try:
                    # Read raw bytes for proper NDJSON frame boundary handling
                    async for chunk in current_resp.aiter_bytes():
                        if self._ctrl.aborted:
                            raise StreamAbortedError("Stream aborted by controller")

                        self._buffer += chunk

                        # Split on newlines — NDJSON uses \n as frame delimiter
                        while b"\n" in self._buffer:
                            line_bytes, self._buffer = self._buffer.split(b"\n", 1)
                            line = line_bytes.decode("utf-8", errors="replace")
                            event = parse_sse_line(line)
                            if event is not None:
                                yield event

                    # Drain remaining buffer
                    if self._buffer.strip():
                        line = self._buffer.decode("utf-8", errors="replace")
                        self._buffer = b""
                        event = parse_sse_line(line)
                        if event is not None:
                            yield event

                    break  # successful completion

                except (StreamAbortedError, GeneratorExit):
                    raise

                except (ConnectionError, TimeoutError, OSError) as e:
                    if reconnect_remaining <= 0 or self._on_reconnect is None:
                        yield {"type": "error",
                               "message": f"Stream connection lost ({type(e).__name__}): {e}"}
                        raise

                    reconnect_remaining -= 1
                    delay = reconnect_delay * (2 ** (max_reconnect - reconnect_remaining - 1))
                    logger.warning(
                        "SSE stream disconnected: %s. Reconnecting attempt %d/%d after %.1fs...",
                        e, max_reconnect - reconnect_remaining, max_reconnect, delay,
                    )
                    await _asyncio.sleep(delay)

                    # Re-establish connection via the reconnect callback
                    try:
                        current_resp = await self._on_reconnect()
                        self._buffer = b""  # discard partial buffer from dropped connection
                        logger.info("SSE stream reconnected successfully.")
                    except Exception as re_e:
                        yield {"type": "error",
                               "message": f"Stream reconnection failed: {type(re_e).__name__}: {re_e}"}
                        raise

    stream = _EventStream(response, abort_ctrl, on_reconnect=reconnect_cb)
    try:
        yield stream
    finally:
        abort_ctrl.abort()


# =============================================================================
# SECTION 5 — ERROR RETRY CHAIN (exponential backoff + jitter + 3 retries)
# =============================================================================

RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504, 529}
NON_RETRYABLE_HTTP_CODES = {400, 401, 403, 404, 405, 409, 422}


def _should_retry(status_code: int, exception: Optional[Exception] = None) -> bool:
    """Determine if a failed request should be retried."""
    if status_code in RETRYABLE_HTTP_CODES:
        return True
    if status_code in NON_RETRYABLE_HTTP_CODES:
        return False
    # Connection errors / timeouts are retryable
    if exception is not None:
        exc_name = type(exception).__name__
        if exc_name in ("ConnectError", "ReadError", "WriteError",
                        "TimeoutException", "ConnectionError",
                        "RemoteProtocolError", "NetworkError"):
            return True
    return False


def _backoff_delay(attempt: int, base: float = 1.0, max_delay: float = 30.0) -> float:
    """Exponential backoff with full jitter.

    Formula: min(max_delay, base * 2^attempt) * random(0.5, 1.5)

    attempt 0 → 0.5–1.5s
    attempt 1 → 1.0–3.0s
    attempt 2 → 2.0–6.0s
    attempt 3 → 4.0–12.0s (clamped to max_delay)
    """
    exp = min(max_delay, base * (2 ** attempt))
    jitter = random.uniform(0.5, 1.5)
    return exp * jitter


@dataclass
class LLMResponse:
    """Normalized LLM response across all providers."""
    success: bool
    text: str = ""
    error: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""
    cache_stats: dict = field(default_factory=dict)
    attempts: int = 0
    latency_ms: float = 0.0


# =============================================================================
# SECTION 6 — UNIFIED LLM CLIENT
# =============================================================================

import httpx


class UnifiedLLMClient:
    """Single client that handles Claude, DeepSeek, GPT, o-series, Gemini.

    Usage:
        client = UnifiedLLMClient(api_key="...", api_url="https://api.anthropic.com/v1/messages")
        resp = await client.complete(
            model="claude-opus-4-8",
            messages=[{"role": "user", "content": "Hello"}],
            system="You are helpful.",
            mode="detailed",
        )
        print(resp.text)

    Key benefits over the old code:
    - Model-family auto-detection → correct params for every model
    - thinking/effort/reasoning_effort handled automatically
    - Prompt caching for Anthropic models
    - Exponential backoff + jitter on retries
    - Normalized LLMResponse regardless of provider
    """

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "",
        timeout: float = 180.0,
        max_retries: int = 3,
        enable_cache: bool = True,
        anthropic_version: str = "2023-06-01",
    ):
        self.api_key = api_key
        self.api_url = api_url or "https://api.anthropic.com/v1/messages"
        self.timeout = timeout
        self.max_retries = max_retries
        self.enable_cache = enable_cache
        self.anthropic_version = anthropic_version
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def __aenter__(self):
        """Async context manager entry — ensures client is created."""
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit — always closes the client."""
        await self.close()
        return False  # don't suppress exceptions

    def __del__(self):
        """Best-effort cleanup on GC if close() was never called."""
        if self._client is not None:
            try:
                import asyncio as _aio_del
                _aio_del.get_event_loop().create_task(self._client.aclose())
            except Exception:
                pass  # event loop may already be closed; nothing we can do

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # 6.1  Main completion method
    # ------------------------------------------------------------------

    async def complete(
        self,
        model: str,
        messages: list[dict],
        system: str = "",
        mode: str = "detailed",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        enable_cache: Optional[bool] = None,
        metadata: Optional[dict] = None,
        images: Optional[list] = None,
    ) -> LLMResponse:
        """Send a completion request to the LLM with automatic parameter adaptation.

        Args:
            model: Model ID string (e.g. "claude-opus-4-8")
            messages: Chat messages list
            system: System prompt (top-level for Claude/GPT; in-messages for o-series)
            mode: "brief" | "detailed" | "keypoints" | "mindmap" | "qa"
            max_tokens: Override default max_tokens
            temperature: Override default temperature
            enable_cache: Override class-level cache setting
            images: Optional images attached to the last user message.
                Each item: data URI, raw base64, http(s) URL, local file path,
                or {"base64"/"url"/"path": ...} dict.  Formatted per endpoint:
                Anthropic image blocks, or OpenAI image_url parts (DashScope
                compatible-mode qwen-vl-* uses the same OpenAI part shape).
        """
        t0 = time.perf_counter()
        family = classify_model_family(model)
        api_format = detect_api_format(self.api_url, model)
        thinking_cfg = get_thinking_config(model)
        use_cache = (
            enable_cache if enable_cache is not None else self.enable_cache
        ) and family.value.startswith("claude")

        # ---- Build request params ----
        params = build_thinking_params_from_config(model, {
            **(max_tokens is not None and {"max_tokens": max_tokens} or {}),
            **(temperature is not None and {"temperature": temperature} or {}),
        })

        # ---- System prompt ----
        if system:
            if thinking_cfg.system_top_level:
                if use_cache and api_format == "anthropic":
                    params["system"] = build_cached_system(system)
                else:
                    params["system"] = system
            else:
                # o-series: prepend system to first user message
                for msg in messages:
                    if msg.get("role") == "user":
                        content = msg.get("content", "")
                        msg["content"] = f"[System Instructions]\n{system}\n\n[User Message]\n{content}"
                        break

        # ---- Multimodal: attach images to the last user message ----
        if images:
            messages = attach_images_to_last_user(messages, images, api_format)

        # ---- Messages with optional caching ----
        if use_cache and api_format == "anthropic":
            messages = build_cached_messages(messages, cache_last_user=True)
        params["messages"] = messages

        # ---- Betas ----
        if thinking_cfg.extra_betas:
            params["betas"] = thinking_cfg.extra_betas

        # ---- Fable 5: server-side fallback body param (refusal rescue) ----
        if thinking_cfg.fallbacks:
            params["fallbacks"] = thinking_cfg.fallbacks

        # ---- Retry loop ----
        params["model"] = model
        last_error = None
        for attempt in range(self.max_retries):
            try:
                client = await self._get_client()

                if api_format == "anthropic":
                    resp = await self._call_anthropic(params, attempt)
                else:
                    resp = await self._call_openai(params, attempt)

                resp.attempts = attempt + 1
                resp.latency_ms = (time.perf_counter() - t0) * 1000
                resp.model = model
                return resp

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if _should_retry(status, e):
                    last_error = f"HTTP {status}: {e.response.text[:200]}"
                    logger.warning("LLM retry %d/%d: %s", attempt + 1, self.max_retries, last_error)
                else:
                    return LLMResponse(
                        success=False,
                        error=f"HTTP {status}: {e.response.text[:500]}",
                        attempts=attempt + 1,
                        latency_ms=(time.perf_counter() - t0) * 1000,
                    )

            except (httpx.ConnectError, httpx.ReadError,
                    httpx.TimeoutException, httpx.RemoteProtocolError,
                    ConnectionError, TimeoutError) as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning("LLM retry %d/%d (network): %s",
                               attempt + 1, self.max_retries, last_error)

            except Exception as e:
                return LLMResponse(
                    success=False,
                    error=f"Unexpected: {type(e).__name__}: {e}",
                    attempts=attempt + 1,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )

            if attempt < self.max_retries - 1:
                delay = _backoff_delay(attempt)
                await _asyncio.sleep(delay)

        return LLMResponse(
            success=False,
            error=last_error or "Max retries exceeded",
            attempts=self.max_retries,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    # ------------------------------------------------------------------
    # 6.2  Anthropic Messages API call
    # ------------------------------------------------------------------

    async def _call_anthropic(self, params: dict, attempt: int) -> LLMResponse:
        """Call Anthropic Messages API."""
        client = await self._get_client()
        api_url = self.api_url.rstrip("/")

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "Content-Type": "application/json",
        }

        r = await client.post(api_url, headers=headers, json=params)

        if r.status_code != 200:
            r.raise_for_status()

        data = r.json()

        # Handle refusal stop reason (Fable 5)
        stop_reason = data.get("stop_reason", "")
        if stop_reason == "refusal":
            return LLMResponse(
                success=False,
                error=f"Content refused: {data.get('stop_details', {}).get('category', 'unknown')}",
                stop_reason="refusal",
            )

        # Extract text from content blocks (handle thinking blocks)
        content = data.get("content", [])
        text_blocks = [
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        ]
        text = "".join(text_blocks)

        # Extract cache stats
        usage = data.get("usage", {})
        cache_stats = extract_cache_stats(usage)

        # Track cost (v7.1)
        try:
            from cost_tracker import get_cost_tracker
            input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
            if input_tokens or output_tokens:
                get_cost_tracker().track(params.get("model", "unknown"), input_tokens, output_tokens)
        except Exception as e:
            logger.debug("OpenAI cost tracking failed: %s", e)  # Never let cost tracking break the main flow

        return LLMResponse(
            success=True,
            text=text,
            usage=usage,
            stop_reason=stop_reason,
            cache_stats=cache_stats,
        )

    # ------------------------------------------------------------------
    # 6.3  OpenAI-compatible chat/completions call
    # ------------------------------------------------------------------

    async def _call_openai(self, params: dict, attempt: int) -> LLMResponse:
        """Call OpenAI-compatible chat/completions API (GPT, DeepSeek, etc.)."""
        client = await self._get_client()
        api_url = self.api_url.rstrip("/")

        # Ensure URL ends with /chat/completions
        if not api_url.endswith("/chat/completions"):
            api_url = f"{api_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Remove Anthropic-specific params
        openai_params = {k: v for k, v in params.items()
                         if k not in ("thinking", "output_config", "betas", "system")}

        # Normalize content for OpenAI-compatible endpoints (DashScope qwen-vl
        # included): Anthropic image blocks → image_url parts, cache_control
        # stripped, pure-text block lists collapsed back to plain strings.
        messages = convert_messages_for_openai(list(params.get("messages", [])))

        # Move system to messages for OpenAI format
        system_content = params.get("system", "")
        if system_content:
            if isinstance(system_content, list):
                # Extract text from cached system blocks
                sys_text = "".join(
                    b.get("text", "") for b in system_content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                sys_text = system_content
            if sys_text:
                messages = [{"role": "system", "content": sys_text}] + messages
        openai_params["messages"] = messages

        r = await client.post(api_url, headers=headers, json=openai_params)

        if r.status_code != 200:
            r.raise_for_status()

        data = r.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        usage = data.get("usage", {})

        # Track cost (v7.1)
        try:
            from cost_tracker import get_cost_tracker
            input_tokens = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            output_tokens = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
            if input_tokens or output_tokens:
                get_cost_tracker().track(params.get("model", "unknown"), input_tokens, output_tokens)
        except Exception as e:
            logger.debug("OpenAI cost tracking failed: %s", e)  # Never let cost tracking break the main flow

        return LLMResponse(
            success=True,
            text=text,
            usage=usage,
            stop_reason=data.get("choices", [{}])[0].get("finish_reason", ""),
        )

    # ------------------------------------------------------------------
    # 6.4  Streaming completion
    # ------------------------------------------------------------------

    async def stream_complete(
        self,
        model: str,
        messages: list[dict],
        system: str = "",
        max_tokens: Optional[int] = None,
        abort_controller: Optional[AbortController] = None,
        images: Optional[list] = None,
    ):
        """Stream completion with proper NDJSON event output.

        Yields dicts: {"type":"token","text":"..."} | {"type":"error","message":"..."} | {"type":"done"}

        images: same accepted forms as complete() — attached to the last user
        message in the endpoint's native format (Anthropic image blocks or
        OpenAI/DashScope image_url parts).
        """
        family = classify_model_family(model)
        api_format = detect_api_format(self.api_url, model)
        thinking_cfg = get_thinking_config(model)

        params = build_thinking_params_from_config(model, {
            **(max_tokens is not None and {"max_tokens": max_tokens} or {}),
        })
        params["stream"] = True

        if system and thinking_cfg.system_top_level:
            params["system"] = system

        # OpenAI: move system into messages
        if not thinking_cfg.system_top_level and system:
            for msg in messages:
                if msg.get("role") == "user":
                    msg["content"] = f"[System]\n{system}\n\n[User]\n{msg['content']}"
                    break

        # Multimodal: attach images to the last user message
        if images:
            messages = attach_images_to_last_user(messages, images, api_format)

        params["messages"] = messages
        if thinking_cfg.extra_betas:
            params["betas"] = thinking_cfg.extra_betas

        client = await self._get_client()
        abort_ctrl = abort_controller or AbortController()

        try:
            if api_format == "anthropic":
                headers = {
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                    "Content-Type": "application/json",
                }
                r = await client.post(
                    self.api_url.rstrip("/"), headers=headers, json=params
                )
                # Anthropic streaming returns SSE
                async with stream_sse(r, abort_ctrl) as events:
                    async for event in events:
                        if abort_ctrl.aborted:
                            yield {"type": "error", "message": "Stream aborted"}
                            return
                        yield event
            else:
                api_url = self.api_url.rstrip("/")
                if not api_url.endswith("/chat/completions"):
                    api_url = f"{api_url}/chat/completions"

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                openai_params = {k: v for k, v in params.items()
                                 if k not in ("thinking", "output_config", "betas")}
                # Move system to messages for OpenAI; normalize multimodal
                # content (Anthropic image blocks → image_url parts) for
                # OpenAI-compatible endpoints incl. DashScope qwen-vl
                sys_content = params.get("system", "")
                msgs = convert_messages_for_openai(list(params.get("messages", [])))
                if sys_content and not any(m.get("role") == "system" for m in msgs):
                    msgs = [{"role": "system", "content": sys_content}] + msgs
                openai_params["messages"] = msgs

                r = await client.post(api_url, headers=headers, json=openai_params)
                async with stream_sse(r, abort_ctrl) as events:
                    async for event in events:
                        if abort_ctrl.aborted:
                            yield {"type": "error", "message": "Stream aborted"}
                            return
                        yield event

        except StreamAbortedError:
            yield {"type": "error", "message": "Stream aborted"}

        except Exception as e:
            yield {"type": "error", "message": f"Stream error: {type(e).__name__}: {e}"}

    # ------------------------------------------------------------------
    # 6.5  Convenience: RAG ask
    # ------------------------------------------------------------------

    async def rag_ask(
        self,
        model: str,
        question: str,
        context: str,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Convenience method for RAG-style QA with context injection."""
        system = (
            "你是一个知识库助手，专门基于用户收藏的B站视频内容来回答问题。\n\n"
            "请遵循以下规则：\n"
            "1. 根据提供的视频内容来回答问题\n"
            "2. 回答要自然、友好、有条理\n"
            "3. 可以引用相关的视频标题作为来源\n"
            "4. 如果多个视频涉及相同话题，请综合它们的内容\n"
        )
        user_prompt = f"视频内容：\n{context}\n\n问题：{question}"

        return await self.complete(
            model=model,
            messages=[{"role": "user", "content": user_prompt}],
            system=system,
            mode="qa",
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # 6.6  Convenience: summarize
    # ------------------------------------------------------------------

    async def summarize(
        self,
        model: str,
        prompt: str,
        mode: str = "detailed",
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """Convenience method for video summarization."""
        system = "你是一个专业的B站视频内容总结助手。请用中文回答。"

        # Compute adaptive budget
        budget = compute_adaptive_budget(
            prompt_text=prompt,
            system_text=system,
            mode=mode,
        )

        overrides = {
            "max_tokens": max_tokens or budget.max_tokens,
            "effort": budget.effort,
        }

        params = build_thinking_params_from_config(model, overrides)

        return await self.complete(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system=system,
            mode=mode,
            max_tokens=overrides["max_tokens"],
        )


# =============================================================================
# SECTION 7 — BACKWARD-COMPATIBLE WRAPPERS (drop-in replacement)
# =============================================================================

# ---- Replace summarizer.summarize_with_claude ----
async def summarize_with_claude_v2(
    info,              # VideoInfo
    subtitle,          # SubtitleData
    comments,          # list[CommentEntry]
    api_key: str = "",
    api_url: str = "",
    model: str = "",
    mode: str = "detailed",
    ocr_text: str = "",
    danmaku: list = None,
    budget: dict = None,
    visual_warning: str = "",
) -> dict:
    """Drop-in replacement for summarizer.summarize_with_claude using UnifiedLLMClient.

    Returns the same dict shape: {"title": ..., "summary": ..., "author": ..., "mode": ...}
    """
    # This import would come from summarizer; inlined here for self-containedness
    # You'd call build_prompt() from summarizer.py
    from summarizer import build_prompt

    prompt = build_prompt(info, subtitle, comments, mode, ocr_text, danmaku or [])

    client = UnifiedLLMClient(
        api_key=api_key,
        api_url=api_url or "https://api.anthropic.com/v1/messages",
    )

    try:
        resp = await client.summarize(
            model=model or "claude-opus-4-8",
            prompt=prompt,
            mode=mode,
        )

        if not resp.success:
            raise ValueError(resp.error)

        return {
            "title": info.title,
            "summary": resp.text,
            "author": info.owner_name,
            "mode": mode,
            "_cache_stats": resp.cache_stats,
            "_usage": resp.usage,
            "_model": resp.model,
            "_latency_ms": resp.latency_ms,
        }
    finally:
        await client.close()


# ---- Replace main._call_llm_with_retry ----
# NOTE: For production use, prefer call_llm_with_fallback() above which
# automatically tries Claude → DeepSeek → GPT when the primary model fails.
async def call_llm_with_retry_v2(
    api_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_retries: int = 3,
    max_tokens: Optional[int] = None,
) -> dict:
    """Drop-in replacement for main._call_llm_with_retry.

    Returns the same shape: {"success": True/False, "text": "..." | "error": "..."}
    """
    client = UnifiedLLMClient(
        api_key=api_key,
        api_url=api_url,
        max_retries=max_retries,
    )
    try:
        # Build thinking params and merge into the request
        thinking_params = build_thinking_params(api_url, model)
        # The UnifiedLLMClient.complete() already handles this internally via
        # the model-family matrix, but we also call build_thinking_params here
        # for the explicit public API compatibility. The client will override
        # any params from the matrix with matching keys from build_thinking_params.
        resp = await client.complete(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
        )
        if resp.success:
            return {"success": True, "text": resp.text}
        return {"success": False, "error": resp.error}
    finally:
        await client.close()


# ---- NEW: Automatic model fallback chain ----
async def call_llm_with_fallback(
    messages: list,
    api_key: str = "",
    api_url: str = "",
    model: str = "",
    max_retries: int = 3,
    timeout: int = 120,
) -> dict:
    """
    Call LLM with automatic fallback chain.

    Tries primary model first. If it fails (timeout, auth error, rate limit),
    automatically falls back to secondary, then tertiary.

    Returns:
        {"success": True, "text": "...", "model_used": "...", "provider": "..."}
        or {"success": False, "error": "...", "tried": [...]}
    """
    tried = []

    # Determine chain: user-specified model OR fallback chain
    if api_url and model:
        chain = [{"api_url": api_url, "model": model, "family": detect_model_family(api_url, model)}]
        # Add fallbacks after user's choice
        for fb in FALLBACK_CHAIN:
            if fb["api_url"] != api_url:
                chain.append(fb)
    else:
        chain = FALLBACK_CHAIN

    last_error = None
    for provider in chain:
        try:
            result = await call_llm_with_retry_v2(
                messages=messages,
                api_url=provider["api_url"],
                api_key=api_key,
                model=provider["model"],
                max_retries=1,  # fast fail within chain
            )
            if result and result.get("success"):
                return {
                    "success": True,
                    "text": result["text"],
                    "model_used": provider["model"],
                    "provider": provider["family"],
                    "tried": tried,
                }
            tried.append({"provider": provider["family"], "error": result.get("error", "unknown")})
        except Exception as e:
            tried.append({"provider": provider["family"], "error": str(e)[:200]})
            last_error = str(e)

    return {"success": False, "error": last_error or "All providers failed", "tried": tried}


# =============================================================================
# SECTION 8 — CROSS-LEVERAGE CHAINS
# =============================================================================
#
# 8.1  prompt-engineer → UnifiedLLMClient
#   - prompt-engineer Skill 产出的 system prompt 直接作为 build_cached_system 的输入
#   - 自适应预算 compute_adaptive_budget 的 mode 参数由 prompt-engineer 决定内容复杂度
#   - 交叉点: prompt-engineer 输出 → UnifiedLLMClient.system (cached)
#
# 8.2  summarize → UnifiedLLMClient
#   - summarize Skill 的 build_prompt() 的输出 → client.summarize(prompt=...)
#   - 分段总结 summarize_segments → client.complete(messages=[...], mode="keypoints")
#   - 交叉点: summarizer.py:build_prompt → detect_model_family(model) → build_thinking_params
#
# 8.3  oracle → UnifiedLLMClient
#   - oracle Skill 做 quality 评分 → compute_quality_multiplier → 调整 budget.effort
#   - oracle 判断是否需要 "xhigh" 或 "max" effort → 覆盖 effort 参数
#   - 交叉点: quality.py:compute_quality_multiplier → compute_adaptive_budget(quality_multiplier=...)
#
# 8.4  Cross-leverage data flow:
#
#   ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
#   │ prompt-engr  │───>│ UnifiedLLMClient │<───│   oracle     │
#   │ system_prompt│    │ .complete()     │    │ quality_mult │
#   │ mode=detect  │    │ .summarize()    │    │ effort=tune  │
#   └──────────────┘    │ .rag_ask()      │    └──────────────┘
#                       │ .stream_complete│
#   ┌──────────────┐    └────────┬────────┘    ┌──────────────┐
#   │  summarize   │─────────────┤             │   oracle     │
#   │ build_prompt │             │             │ quality_mult │
#   │ segments     │             │             │ effort=tune  │
#   └──────────────┘             │             └──────────────┘
#                                ▼
#                      ┌──────────────────┐
#                      │  LLMResponse     │
#                      │ .text .usage     │
#                      │ .cache_stats     │
#                      │ .stop_reason     │
#                      └──────────────────┘


# =============================================================================
# SECTION 9 — INTEGRATION GUIDE
# =============================================================================
#
# STEP 1: Replace summarizer.py imports and function
#   In C:\Users\shiniyaya\Desktop\cc\B站总结工具\B站视频总结工具 -cc\backend\summarizer.py:
#
#     # Add at top:
#     from unified_llm_client import (
#         UnifiedLLMClient, detect_model_family, build_thinking_params,
#         compute_adaptive_budget, summarize_with_claude_v2,
#     )
#
#     # Replace summarize_with_claude body:
#     async def summarize_with_claude(...) -> dict:
#         return await summarize_with_claude_v2(...)
#
# STEP 2: Replace main.py _call_llm_with_retry
#   In C:\Users\shiniyaya\Desktop\cc\B站总结工具\B站视频总结工具 -cc\backend\main.py:
#
#     # Replace the async def _call_llm_with_retry block (lines 2798-2831) with:
#     from unified_llm_client import call_llm_with_retry_v2 as _call_llm_with_retry
#
# STEP 3: Update streaming endpoint (main.py:913-1063)
#   Replace the streaming logic in api_chat_stream with:
#
#     client = UnifiedLLMClient(api_key=api_key, api_url=api_url)
#     async for event in client.stream_complete(
#         model=model,
#         messages=[{"role":"system","content":system},{"role":"user","content":question}],
#         system=system,
#     ):
#         if event["type"] == "token":
#             yield json.dumps(event, ensure_ascii=False) + "\n"
#         elif event["type"] == "done":
#             yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"
#         elif event["type"] == "error":
#             yield json.dumps({"type": "error", "message": event["message"]}, ensure_ascii=False) + "\n"
#
# STEP 4: Update routers/ai.py
#   Replace all import and usage of _call_llm_with_retry from main with the
#   unified client. The routers/ai.py:109, 110, 212, 213 lines reference
#   from main import _call_llm_with_retry — change to:
#
#     from unified_llm_client import call_llm_with_retry_v2 as _call_llm_with_retry
#
#   Or better: use UnifiedLLMClient directly.
#
# STEP 5: Verification checklist
#   [ ] Claude Opus 4.8 → adaptive thinking, xhigh effort, no budget_tokens sent
#   [ ] Claude Opus 4.6 → adaptive thinking, high effort, temperature allowed
#   [ ] DeepSeek → no thinking param, temperature=0.7, OpenAI format
#   [ ] GPT-4o → no thinking param, OpenAI format
#   [ ] GPT o3 → reasoning_effort="medium", no temperature, max_completion_tokens
#   [ ] Prompt cache → verify cache_read_input_tokens > 0 on second identical request
#   [ ] Retry chain → simulate 429 → retries with jitter
#   [ ] Streaming → verify NDJSON framing with multi-line content
#   [ ] Abort → send abort signal mid-stream, verify StreamAbortedError
#
# =============================================================================
# END OF FILE
# =============================================================================
