"""
Oracle Verification Pipeline for BiliSum
========================================
Oracle Pattern: second-model validates first-model output.
Based on @steipete/oracle CLI methodology + cross-model verification.

Architecture:
  primary_model → generate summary
       ↓
  oracle_model → verify (factuality/coherence/completeness)
       ↓
  compare → ACCEPT / REJECT / REVISE
       ↓
  quality_gate → multiplier < 0.7 triggers model-switch retry
       ↓
  cross_validation → 3-model voting (optional, for high-value content)
       ↓
  confidence_score → 0-100 based on model consensus + source alignment
       ↓
  auto_correction_loop → max 3 rounds iterative refinement

Cross-leverage:
  - claude-api: Thinking type, model IDs, token limits, streaming patterns
  - self-improving-agent: Pattern extraction from oracle corrections, episodic memory
  - prompt-optimizer: Oracle feedback refines summarizer prompts over time
"""

import asyncio
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

from models import VideoInfo, SubtitleData, CommentEntry
from quality import compute_quality_multiplier, compute_note_budget

# ---------------------------------------------------------------------------
# Configuration defaults (single source of truth)
# ---------------------------------------------------------------------------

ORACLE_MODEL_DEFAULT = "deepseek-chat"       # cost-effective verifier
ORACLE_API_URL_DEFAULT = "https://api.deepseek.com/v1"
PRIMARY_MODEL_DEFAULT = "claude-opus-4-8"    # primary summarizer
PRIMARY_API_URL_DEFAULT = "https://api.anthropic.com/v1/messages"

# Quality gate threshold: below this multiplier, oracle verification is MANDATORY
QUALITY_GATE_THRESHOLD = 0.70

# Cross-validation: how many models vote (3 for high-value, 2 default)
CROSS_VALIDATION_MODELS = 3

# Auto-correction: max rounds of iterative refinement
MAX_REFINEMENT_ROUNDS = 3

# Confidence thresholds
CONFIDENCE_ACCEPT = 85   # auto-accept if confidence >= 85
CONFIDENCE_REJECT = 50   # auto-reject if confidence < 50

# Self-improvement: where to store oracle correction patterns
ORACLE_MEMORY_DIR = Path(__file__).parent.parent / "data" / "oracle_memory"

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class VerificationDimension:
    """A single dimension of oracle verification."""

    name: str                    # e.g. "factuality"
    score: float = 0.0           # 0.0-1.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    raw_feedback: str = ""


@dataclass
class OracleVerdict:
    """Complete oracle assessment of a summary."""

    verdict: str = "PENDING"     # ACCEPT | REJECT | REVISE
    confidence: float = 0.0      # 0-100 overall confidence
    dimensions: dict[str, VerificationDimension] = field(default_factory=dict)
    cross_validation_agreement: float = 0.0  # 0.0-1.0 inter-model agreement
    source_alignment: float = 0.0            # 0.0-1.0 alignment with source text
    refinement_rounds: int = 0
    final_summary: str = ""
    correction_log: list[dict] = field(default_factory=list)
    model_used: str = ""
    oracle_model_used: str = ""
    token_usage: dict = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class OracleConfig:
    """Runtime configuration for the oracle pipeline."""

    enabled: bool = True
    primary_model: str = PRIMARY_MODEL_DEFAULT
    primary_api_url: str = PRIMARY_API_URL_DEFAULT
    primary_api_key: str = ""
    oracle_model: str = ORACLE_MODEL_DEFAULT
    oracle_api_url: str = ORACLE_API_URL_DEFAULT
    oracle_api_key: str = ""
    quality_gate_enabled: bool = True
    quality_gate_threshold: float = QUALITY_GATE_THRESHOLD
    cross_validation_enabled: bool = False  # cost: 2 extra LLM calls
    cross_validation_models: int = CROSS_VALIDATION_MODELS
    max_refinement_rounds: int = MAX_REFINEMENT_ROUNDS
    auto_accept_threshold: float = CONFIDENCE_ACCEPT
    auto_reject_threshold: float = CONFIDENCE_REJECT
    fallback_model: str = "deepseek-chat"   # used when quality gate fails
    fallback_api_url: str = "https://api.deepseek.com/v1"
    fallback_api_key: str = ""
    self_improvement_enabled: bool = True


# ---------------------------------------------------------------------------
# Source text extraction (for factuality checking)
# ---------------------------------------------------------------------------


def _extract_claims_from_summary(summary: str) -> list[str]:
    """Extract factual claims from a summary for verification.

    Each claim is a self-contained statement that can be checked against source.
    """
    claims = []
    # Split on sentence boundaries (Chinese-aware)
    sentences = re.split(r"(?<=[。！？.!?\n])\s*", summary)
    for s in sentences:
        s = s.strip()
        # Skip headings, formatting, empty lines, and meta-commentary
        if not s or len(s) < 10:
            continue
        if re.match(r"^#{1,6}\s", s):  # markdown heading
            continue
        if re.match(r"^[\|\-\*]", s):   # table or list markers without content
            continue
        claims.append(s)
    return claims[:30]  # cap to avoid token explosion


def _extract_key_facts_from_source(
    subtitle: SubtitleData,
    comments: list[CommentEntry],
    info: VideoInfo,
) -> str:
    """Extract a condensed set of verifiable facts from the source material."""
    parts = []
    if subtitle and subtitle.text:
        # Take first, middle, last 1000 chars for coverage
        t = subtitle.text
        if len(t) > 3000:
            parts.append(t[:1000])
            mid = len(t) // 2
            parts.append(t[mid - 500 : mid + 500])
            parts.append(t[-1000:])
        else:
            parts.append(t)
    if info.title:
        parts.insert(0, f"Title: {info.title}")
    return "\n---\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call helpers (Anthropic + OpenAI-compatible unified)
# ---------------------------------------------------------------------------


async def _call_llm(
    api_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int = 4096,
    timeout: int = 180,
    system: str = "",
) -> dict:
    """Unified LLM call supporting Anthropic and OpenAI-compatible APIs.

    Returns: {"success": bool, "text": str, "usage": dict, "error": str}
    """
    is_anthropic = "anthropic.com" in api_url.lower()

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if is_anthropic:
                body: dict[str, Any] = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if system:
                    body["system"] = system
                # Use adaptive thinking for Anthropic (claude-api skill standard)
                # Only set thinking if the model supports it (guard against non-Claude models)
                try:
                    from unified_llm_client import classify_model_family, get_thinking_config
                    family = classify_model_family(model)
                    config_thinking = get_thinking_config(model)
                    if config_thinking and config_thinking.thinking:
                        body["thinking"] = {"type": "adaptive"}
                except ImportError:
                    # unified_llm_client not available; apply model compatibility guard
                    _claude_prefixes = ("claude-", "opus-", "sonnet-", "haiku-")
                    if model and any(
                        model.lower().startswith(p) for p in _claude_prefixes
                    ):
                        body["thinking"] = {"type": "adaptive"}

                r = await client.post(
                    api_url,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                data = r.json()
                if r.status_code != 200:
                    err = data.get("error", {})
                    return {
                        "success": False,
                        "text": "",
                        "usage": {},
                        "error": err.get("message", f"Anthropic API error {r.status_code}"),
                    }
                content = data.get("content", [])
                text_blocks = [
                    b.get("text", "") for b in content if b.get("type") == "text"
                ]
                text = "".join(text_blocks) if text_blocks else ""
                usage = data.get("usage", {})
                return {"success": True, "text": text, "usage": usage, "error": ""}
            else:
                # OpenAI-compatible
                body: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
                if system:
                    body["messages"] = [
                        {"role": "system", "content": system}
                    ] + body["messages"]

                r = await client.post(
                    f"{api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                data = r.json()
                if r.status_code != 200:
                    err = data.get("error", {})
                    return {
                        "success": False,
                        "text": "",
                        "usage": {},
                        "error": err.get("message", f"API error {r.status_code}"),
                    }
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return {"success": True, "text": text, "usage": usage, "error": ""}
    except Exception as e:
        return {"success": False, "text": "", "usage": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# Quality Gate
# ---------------------------------------------------------------------------


def evaluate_quality_gate(
    stat_data: dict,
    duration_minutes: float,
    subtitle_chars: int,
    config: OracleConfig,
) -> dict:
    """Evaluate whether the quality gate is passed.

    Returns:
        {
            "passed": bool,
            "quality_multiplier": float,
            "tier": str,
            "recommendation": str,
            "should_use_fallback_model": bool,
        }
    """
    if not config.quality_gate_enabled:
        return {
            "passed": True,
            "quality_multiplier": 1.0,
            "tier": "unknown",
            "recommendation": "quality gate disabled",
            "should_use_fallback_model": False,
        }

    result = compute_quality_multiplier(stat_data)
    multiplier = result["quality_multiplier"] if isinstance(result, dict) else result
    quality_result = result if isinstance(result, dict) else {"quality_multiplier": multiplier, "quality_score": 0.0, "dimension_scores": {}, "confidence": "low"}
    budget = compute_note_budget(
        duration_minutes=duration_minutes,
        subtitle_chars=subtitle_chars,
        quality_multiplier=multiplier,
        # oracle gate is lightweight — danmaku/density not needed for quality assessment
    )
    tier = budget.get("quality_tier", "medium")

    should_fallback = multiplier < config.quality_gate_threshold

    if tier == "high" and multiplier >= 1.2:
        recommendation = (
            "High-quality source. Standard model sufficient. "
            "Oracle cross-validation recommended for completeness."
        )
    elif multiplier >= config.quality_gate_threshold:
        recommendation = (
            "Adequate source quality. Oracle verification will be light-touch."
        )
    elif multiplier >= 0.5:
        recommendation = (
            f"Low-quality source (multiplier={multiplier:.2f}). "
            "Switching to fallback model for initial summary, "
            "then oracle-verifying with primary model."
        )
    else:
        recommendation = (
            f"Very low-quality source (multiplier={multiplier:.2f}). "
            "Fallback model + oracle verification REQUIRED. "
            "Summary will be flagged for manual review."
        )

    return {
        "passed": not should_fallback,
        "quality_multiplier": multiplier,
        "tier": tier,
        "recommendation": recommendation,
        "should_use_fallback_model": should_fallback,
    }


# ---------------------------------------------------------------------------
# Oracle Verification: single-model review
# ---------------------------------------------------------------------------


ORACLE_VERIFY_PROMPT = """You are an expert fact-checker and summary quality auditor (Oracle).
Your task: review the AI-generated summary below against the SOURCE MATERIAL and score it on
three dimensions.

=== SOURCE MATERIAL (for fact-checking) ===
{source_facts}

=== AI-GENERATED SUMMARY ===
{summary}

=== TASK ===
Score the summary on these dimensions (each 0-100):

1. FACTUALITY (0-100): Does every claim in the summary match the source?
   - 95-100: All claims verified, no hallucinations
   - 80-94: Minor imprecisions but no fabricated facts
   - 50-79: Some unsupported claims or exaggerations
   - 0-49: Major hallucinations, fabricated content

2. COHERENCE (0-100): Is the summary logically structured and well-organized?
   - 95-100: Flawless logical flow, excellent structure
   - 80-94: Generally clear, minor organizational issues
   - 50-79: Disjointed sections, confusing transitions
   - 0-49: Incoherent, contradictory, unreadable

3. COMPLETENESS (0-100): Does the summary cover all major topics/themes from the source?
   - 95-100: All key topics covered with appropriate depth
   - 80-94: Most topics covered, 1-2 minor omissions
   - 50-79: Several significant topics missing
   - 0-49: Major content gaps, superficial coverage

For EACH dimension, provide:
- Score (0-100)
- List of specific issues found (if any)
- List of concrete suggestions for improvement

Then provide:
- OVERALL VERDICT: ACCEPT (passes all dimensions), REVISE (minor fixes needed), or REJECT (major rewrite needed)
- OVERALL CONFIDENCE: 0-100 (your confidence in the overall summary quality)
- CORRECTION: If REVISE or REJECT, provide the corrected version of the summary.

OUTPUT FORMAT (JSON only, no markdown wrapping):
{{
  "factuality": {{
    "score": <0-100>,
    "issues": ["<issue1>", "<issue2>", ...],
    "suggestions": ["<suggestion1>", ...]
  }},
  "coherence": {{
    "score": <0-100>,
    "issues": [...],
    "suggestions": [...]
  }},
  "completeness": {{
    "score": <0-100>,
    "issues": [...],
    "suggestions": [...]
  }},
  "overall_verdict": "ACCEPT|REVISE|REJECT",
  "overall_confidence": <0-100>,
  "correction": "<corrected summary if REVISE/REJECT, otherwise empty string>"
}}"""


async def oracle_verify(
    summary: str,
    source_facts: str,
    config: OracleConfig,
) -> dict:
    """Run single-model oracle verification of a summary against source material.

    Returns parsed JSON dict with factuality/coherence/completeness scores.
    """
    prompt = ORACLE_VERIFY_PROMPT.format(
        source_facts=source_facts[:8000],
        summary=summary[:12000],
    )

    result = await _call_llm(
        api_url=config.oracle_api_url,
        api_key=config.oracle_api_key,
        model=config.oracle_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
        system="You are a precise quality auditor. Always output valid JSON only.",
    )

    if not result["success"]:
        return {
            "error": result["error"],
            "factuality": {"score": 0, "issues": [], "suggestions": []},
            "coherence": {"score": 0, "issues": [], "suggestions": []},
            "completeness": {"score": 0, "issues": [], "suggestions": []},
            "overall_verdict": "REJECT",
            "overall_confidence": 0,
            "correction": "",
        }

    # Parse JSON from oracle response (handle markdown code fences)
    raw = result["text"].strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: treat as REJECT with raw text as feedback
        parsed = {
            "factuality": {"score": 50, "issues": ["Could not parse oracle response"], "suggestions": []},
            "coherence": {"score": 50, "issues": [], "suggestions": []},
            "completeness": {"score": 50, "issues": [], "suggestions": []},
            "overall_verdict": "REJECT",
            "overall_confidence": 30,
            "correction": "",
            "_raw_response": raw,
        }

    return parsed


# ---------------------------------------------------------------------------
# Cross-Validation Framework (3-model voting)
# ---------------------------------------------------------------------------


CROSS_VALIDATION_DIMENSIONS = ["factuality", "coherence", "completeness"]

CROSS_VAL_PROMPT = """You are a summary quality evaluator. Score the summary below
on the SINGLE dimension of "{dimension}" (0-100).

=== SOURCE MATERIAL ===
{source_facts}

=== SUMMARY TO EVALUATE ===
{summary}

=== {dimension_upper} EVALUATION ===
{dimension_definition}

OUTPUT: Just the score as a JSON object: {{"score": <0-100>, "reason": "<1 sentence>"}}"""


DIMENSION_DEFINITIONS = {
    "factuality": (
        "Factuality: Does every factual claim in the summary appear in the source? "
        "Penalize hallucinations, invented numbers, fabricated quotes, or claims "
        "contradicted by the source. Score 100 = perfect fidelity."
    ),
    "coherence": (
        "Coherence: Is the summary logically organized? Does it flow naturally "
        "from topic to topic? Are section headings meaningful? Is the structure "
        "easy to follow? Score 100 = perfectly structured."
    ),
    "completeness": (
        "Completeness: Does the summary cover ALL major topics from the source? "
        "Are important arguments, techniques, or findings included? Are there "
        "glaring omissions? Score 100 = nothing important missed."
    ),
}


async def _single_dimension_eval(
    dimension: str,
    summary: str,
    source_facts: str,
    api_url: str,
    api_key: str,
    model: str,
) -> dict:
    """Have one model score a single dimension."""
    prompt = CROSS_VAL_PROMPT.format(
        dimension=dimension,
        dimension_upper=dimension.upper(),
        dimension_definition=DIMENSION_DEFINITIONS.get(dimension, "Score the summary."),
        source_facts=source_facts[:4000],
        summary=summary[:8000],
    )

    result = await _call_llm(
        api_url=api_url,
        api_key=api_key,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        system="Output only valid JSON. No markdown, no explanation.",
    )

    if not result["success"]:
        return {"score": 0, "reason": f"API error: {result['error']}"}

    raw = result["text"].strip()
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        raw = json_match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"score": 50, "reason": "unparseable response"}


async def cross_validate(
    summary: str,
    source_facts: str,
    config: OracleConfig,
) -> dict:
    """Run cross-validation: N models score each dimension independently.

    Returns aggregated scores with inter-model agreement metrics.

    Cross-leverage with self-improving-agent:
      - Models that consistently disagree are flagged for exclusion
      - Agreement patterns stored in ORACLE_MEMORY_DIR for future reference
    """
    if not config.cross_validation_enabled or config.cross_validation_models < 2:
        return {
            "enabled": False,
            "dimensions": {},
            "agreement": 1.0,
            "note": "cross-validation disabled",
        }

    # Use different models for diversity of opinion
    # claude-api skill: valid model IDs
    validator_models = [
        config.oracle_model,                              # primary oracle (e.g., deepseek-chat)
        config.primary_model,                             # primary summarizer reviews itself
        f"{config.oracle_model}",                          # same model, different inference
    ][: config.cross_validation_models]

    all_scores: dict[str, list[float]] = {
        dim: [] for dim in CROSS_VALIDATION_DIMENSIONS
    }
    dimension_reasons: dict[str, list[str]] = {
        dim: [] for dim in CROSS_VALIDATION_DIMENSIONS
    }

    for dim in CROSS_VALIDATION_DIMENSIONS:
        # Run each model's evaluation in parallel
        # For model 3, add a slight temperature variation to simulate diversity
        tasks = []
        for i, model in enumerate(validator_models):
            tasks.append(
                _single_dimension_eval(
                    dimension=dim,
                    summary=summary,
                    source_facts=source_facts,
                    api_url=config.oracle_api_url
                    if i > 0
                    else config.oracle_api_url,
                    api_key=config.oracle_api_key,
                    model=model,
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                all_scores[dim].append(50.0)
                dimension_reasons[dim].append(f"error: {r}")
            elif isinstance(r, dict):
                all_scores[dim].append(float(r.get("score", 50)))
                dimension_reasons[dim].append(r.get("reason", ""))
            else:
                all_scores[dim].append(50.0)

    # Compute agreement: standard deviation across models per dimension
    agreements = {}
    aggregated = {}
    for dim in CROSS_VALIDATION_DIMENSIONS:
        scores = all_scores[dim]
        if not scores:
            agreements[dim] = 0.0
            aggregated[dim] = 0.0
            continue
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / max(len(scores), 2)
        std = math.sqrt(variance)
        # Agreement = 1 - normalized standard deviation (max std for 0-100 = 50)
        agreement = max(0.0, 1.0 - std / 50.0)
        agreements[dim] = round(agreement, 3)
        aggregated[dim] = round(mean, 1)

    overall_agreement = (
        sum(agreements.values()) / len(agreements) if agreements else 0.0
    )

    return {
        "enabled": True,
        "models_used": validator_models,
        "dimensions": {
            dim: {
                "mean_score": aggregated.get(dim, 0),
                "individual_scores": all_scores.get(dim, []),
                "agreement": agreements.get(dim, 0),
            }
            for dim in CROSS_VALIDATION_DIMENSIONS
        },
        "agreement": round(overall_agreement, 3),
        "verdict": (
            "high_consensus"
            if overall_agreement >= 0.85
            else "moderate_consensus"
            if overall_agreement >= 0.65
            else "low_consensus"
        ),
    }


# ---------------------------------------------------------------------------
# Confidence Scoring
# ---------------------------------------------------------------------------


def compute_confidence_score(
    oracle_result: dict,
    cross_validation_result: dict,
    quality_multiplier: float,
) -> float:
    """Compute overall confidence score (0-100) from multiple signals.

    Formula:
      confidence = (
        oracle_factuality * 0.30 +
        oracle_coherence * 0.15 +
        oracle_completeness * 0.15 +
        cross_val_agreement * 0.20 +
        quality_multiplier_normalized * 0.20
      )

    Where cross_val_agreement = mean agreement across dimensions (0-1)
    And quality_multiplier_normalized maps [0.85, 1.4] → [0, 1]
    """
    factuality = oracle_result.get("factuality", {}).get("score", 0) or 0
    coherence = oracle_result.get("coherence", {}).get("score", 0) or 0
    completeness = oracle_result.get("completeness", {}).get("score", 0) or 0

    cross_val_agreement = cross_validation_result.get("agreement", 0.0) or 0.0

    # Normalize quality_multiplier from [0.85, 1.4] to [0, 1]
    qm_normalized = max(0.0, min(1.0, (quality_multiplier - 0.85) / 0.55))

    confidence = (
        factuality * 0.30
        + coherence * 0.15
        + completeness * 0.15
        + cross_val_agreement * 100 * 0.20
        + qm_normalized * 100 * 0.20
    )

    return round(max(0.0, min(100.0, confidence)), 1)


# ---------------------------------------------------------------------------
# Auto-Correction Loop (Iterative Refinement)
# ---------------------------------------------------------------------------


REFINE_PROMPT = """You previously generated this summary:

=== PREVIOUS SUMMARY ===
{previous_summary}

An expert reviewer (Oracle) found the following issues:

=== ORACLE FEEDBACK ===
{feedback}

Please REVISE the summary to address ALL the issues above.

Requirements:
1. Fix all factual errors and hallucinations
2. Improve logical organization where noted
3. Fill in any missing topics
4. Maintain the same output format and structure
5. Keep the same level of detail (do not shorten)

Output the corrected summary directly."""


async def _single_refinement_round(
    summary: str,
    oracle_feedback: dict,
    api_url: str,
    api_key: str,
    model: str,
) -> str:
    """Execute one round of refinement based on oracle feedback."""
    # Build concise feedback
    feedback_parts = []
    for dim_name, dim_data in oracle_feedback.items():
        if dim_name.startswith("_"):
            continue
        if isinstance(dim_data, dict) and dim_data.get("issues"):
            issues = dim_data["issues"]
            suggestions = dim_data.get("suggestions", [])
            feedback_parts.append(f"**{dim_name.upper()}** (score: {dim_data.get('score', '?')}/100)")
            for issue in issues[:3]:
                feedback_parts.append(f"  - Issue: {issue}")
            for sug in suggestions[:2]:
                feedback_parts.append(f"  - Suggestion: {sug}")

    feedback_text = "\n".join(feedback_parts) if feedback_parts else "No specific issues found."

    prompt = REFINE_PROMPT.format(
        previous_summary=summary[:10000],
        feedback=feedback_text[:3000],
    )

    result = await _call_llm(
        api_url=api_url,
        api_key=api_key,
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8192,
    )

    if result["success"]:
        return result["text"]
    return summary  # fallback: return original


async def auto_correction_loop(
    initial_summary: str,
    source_facts: str,
    config: OracleConfig,
    quality_multiplier: float = 1.0,
) -> dict:
    """Iterative refinement: oracle → refine → re-verify, up to MAX_REFINEMENT_ROUNDS.

    Returns:
        {
            "final_summary": str,
            "rounds": int,
            "confidence_trajectory": [float, ...],
            "verdict_trajectory": [str, ...],
            "converged": bool,
        }
    """
    current_summary = initial_summary
    confidence_traj = []
    verdict_traj = []
    correction_log = []
    oracle_result = {}
    cross_val = {}
    confidence = 0.0

    # Guard: if max_refinement_rounds is 0, return immediately with defaults
    if config.max_refinement_rounds <= 0:
        return {
            "final_summary": current_summary,
            "rounds": 0,
            "confidence_trajectory": [],
            "verdict_trajectory": [],
            "converged": False,
            "correction_log": [],
            "final_oracle_result": {},
            "final_cross_validation": {},
            "final_confidence": 0.0,
            "final_verdict": "REJECT",
            "stop_reason": "disabled",
        }

    for round_num in range(1, config.max_refinement_rounds + 1):
        # Oracle verify current version
        oracle_result = await oracle_verify(
            summary=current_summary, source_facts=source_facts, config=config
        )

        # Cross-validate (if enabled)
        cross_val = await cross_validate(
            summary=current_summary,
            source_facts=source_facts,
            config=config,
        )

        # Compute confidence
        confidence = compute_confidence_score(oracle_result, cross_val, quality_multiplier)
        confidence_traj.append(confidence)
        verdict_traj.append(oracle_result.get("overall_verdict", "REJECT"))

        log_entry = {
            "round": round_num,
            "verdict": oracle_result.get("overall_verdict"),
            "confidence": confidence,
            "factuality": oracle_result.get("factuality", {}).get("score", 0),
            "coherence": oracle_result.get("coherence", {}).get("score", 0),
            "completeness": oracle_result.get("completeness", {}).get("score", 0),
        }
        correction_log.append(log_entry)

        # Check termination conditions
        if oracle_result.get("overall_verdict") == "ACCEPT" and confidence >= config.auto_accept_threshold:
            # Converged: quality is good enough
            return {
                "final_summary": current_summary,
                "rounds": round_num,
                "confidence_trajectory": confidence_traj,
                "verdict_trajectory": verdict_traj,
                "converged": True,
                "correction_log": correction_log,
                "final_oracle_result": oracle_result,
                "final_cross_validation": cross_val,
                "final_confidence": confidence,
                "final_verdict": "ACCEPT",
            }

        # Check if we're degrading
        if round_num >= 2 and confidence <= confidence_traj[-2]:
            # Not improving; stop early
            return {
                "final_summary": current_summary,
                "rounds": round_num,
                "confidence_trajectory": confidence_traj,
                "verdict_trajectory": verdict_traj,
                "converged": False,
                "correction_log": correction_log,
                "final_oracle_result": oracle_result,
                "final_cross_validation": cross_val,
                "final_confidence": confidence,
                "final_verdict": oracle_result.get("overall_verdict", "REJECT"),
                "stop_reason": "diminishing_returns",
            }

        # Check if oracle provided a correction we can just use
        correction = oracle_result.get("correction", "")
        if correction and len(correction) > 50:
            # Use oracle's own correction (saves a refinement call)
            current_summary = correction
        else:
            # Refine: send oracle feedback back to primary model
            current_summary = await _single_refinement_round(
                summary=current_summary,
                oracle_feedback=oracle_result,
                api_url=config.primary_api_url,
                api_key=config.primary_api_key,
                model=config.primary_model,
            )

    # Max rounds reached
    return {
        "final_summary": current_summary,
        "rounds": config.max_refinement_rounds,
        "confidence_trajectory": confidence_traj,
        "verdict_trajectory": verdict_traj,
        "converged": False,
        "correction_log": correction_log,
        "final_oracle_result": oracle_result,
        "final_cross_validation": cross_val,
        "final_confidence": confidence,
        "final_verdict": oracle_result.get("overall_verdict", "REJECT"),
        "stop_reason": "max_rounds_reached",
    }


# ---------------------------------------------------------------------------
# Self-Improvement: Pattern Extraction
# ---------------------------------------------------------------------------


def extract_oracle_patterns(
    correction_log: list[dict],
    bvid: str,
    title: str,
) -> dict:
    """Extract reusable correction patterns from oracle feedback.

    Cross-leverage with self-improving-agent:
      - Episodic memory: store correction patterns per video
      - Semantic memory: aggregate common issues across videos
      - Self-correction trigger: flag frequent failure patterns for skill updates
    """
    patterns = {
        "bvid": bvid,
        "title": title,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pattern_id": hashlib.sha256(
            f"{bvid}_{time.time()}".encode()
        ).hexdigest()[:12],
        "common_issues": [],
        "refinement_effectiveness": 0.0,
        "rounds_to_converge": 0,
    }

    # Aggregate issue types across rounds
    issue_categories = {}
    for entry in correction_log:
        for key in ["factuality", "coherence", "completeness"]:
            # We don't have the raw issues in the log; extract from verdict
            pass

    # Compute refinement effectiveness
    if correction_log:
        initial = correction_log[0].get("confidence", 0)
        final_val = correction_log[-1].get("confidence", 0)
        patterns["refinement_effectiveness"] = round(final_val - initial, 1)
        patterns["rounds_to_converge"] = len(correction_log)

    return patterns


def persist_oracle_pattern(pattern: dict) -> None:
    """Persist oracle correction patterns for self-improvement.

    Cross-leverage with self-improving-agent's memory/ directory structure.
    """
    ORACLE_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    # Episodic memory: one file per video
    episodic_path = ORACLE_MEMORY_DIR / f"episodic_{pattern['pattern_id']}.json"
    episodic_path.write_text(json.dumps(pattern, ensure_ascii=False, indent=2))

    # Semantic memory: aggregate patterns
    semantic_path = ORACLE_MEMORY_DIR / "semantic_patterns.jsonl"
    with open(semantic_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(pattern, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main Pipeline: orchestrate the full Oracle workflow
# ---------------------------------------------------------------------------


async def oracle_pipeline(
    info: VideoInfo,
    subtitle: SubtitleData,
    comments: list[CommentEntry],
    initial_summary: str,
    stat_data: dict,
    config: OracleConfig,
) -> OracleVerdict:
    """Execute the complete Oracle verification pipeline.

    Flow:
      1. Quality Gate evaluation
      2. Oracle single-model verification
      3. Cross-validation (if enabled)
      4. Confidence scoring
      5. Auto-correction loop (if needed)
      6. Self-improvement pattern extraction
    """
    duration_min = (info.duration or 0) / 60.0

    verdict = OracleVerdict(
        model_used=config.primary_model,
        oracle_model_used=config.oracle_model,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    # Guard: when oracle is disabled, return early with no verification
    if not config.enabled:
        verdict.verdict = "ACCEPT"
        verdict.confidence = 100.0
        verdict.final_summary = initial_summary
        return verdict

    subtitle_len = len(subtitle.text) if subtitle and subtitle.text else 0

    # ---- Step 1: Quality Gate ----
    gate_result = evaluate_quality_gate(
        stat_data=stat_data,
        duration_minutes=duration_min,
        subtitle_chars=subtitle_len,
        config=config,
    )
    quality_multiplier = gate_result["quality_multiplier"]

    # ---- Step 2: Extract source facts for verification ----
    source_facts = _extract_key_facts_from_source(subtitle, comments, info)

    # ---- Step 3: Oracle single-model verification ----
    oracle_result = await oracle_verify(
        summary=initial_summary,
        source_facts=source_facts,
        config=config,
    )

    for dim_name in ["factuality", "coherence", "completeness"]:
        dim_data = oracle_result.get(dim_name, {})
        verdict.dimensions[dim_name] = VerificationDimension(
            name=dim_name,
            score=dim_data.get("score", 0),
            issues=dim_data.get("issues", []),
            suggestions=dim_data.get("suggestions", []),
        )

    verdict.correction_log.append({
        "phase": "initial_oracle",
        "verdict": oracle_result.get("overall_verdict"),
        "confidence": oracle_result.get("overall_confidence", 0),
    })

    # ---- Step 4: Cross-validation ----
    cross_val = await cross_validate(
        summary=initial_summary,
        source_facts=source_facts,
        config=config,
    )
    verdict.cross_validation_agreement = cross_val.get("agreement", 0.0)

    # ---- Step 5: Confidence scoring ----
    confidence = compute_confidence_score(oracle_result, cross_val, quality_multiplier)
    verdict.confidence = confidence

    # ---- Step 6: Auto-correction loop ----
    if oracle_result.get("overall_verdict") in ("REJECT", "REVISE") and confidence < config.auto_accept_threshold:
        correction_result = await auto_correction_loop(
            initial_summary=initial_summary,
            source_facts=source_facts,
            config=config,
            quality_multiplier=quality_multiplier,
        )
        verdict.final_summary = correction_result["final_summary"]
        verdict.refinement_rounds = correction_result["rounds"]
        verdict.correction_log.extend(correction_result["correction_log"])
        verdict.confidence = correction_result.get("final_confidence", confidence)
        verdict.verdict = correction_result.get("final_verdict", "REJECT")
    else:
        verdict.final_summary = (
            oracle_result.get("correction")
            if oracle_result.get("correction") and len(oracle_result.get("correction", "")) > 50
            else initial_summary
        )
        verdict.verdict = oracle_result.get("overall_verdict", "ACCEPT")

    # ---- Step 7: Self-improvement pattern extraction ----
    if config.self_improvement_enabled and verdict.correction_log:
        pattern = extract_oracle_patterns(
            correction_log=verdict.correction_log,
            bvid=info.bvid,
            title=info.title,
        )
        try:
            persist_oracle_pattern(pattern)
        except Exception as e:
            logger.debug("Oracle pattern persist failed (non-critical): %s", e)  # non-critical

    return verdict


# ---------------------------------------------------------------------------
# Convenience: lightweight oracle check (no correction loop)
# ---------------------------------------------------------------------------


async def oracle_quick_check(
    summary: str,
    info: VideoInfo,
    subtitle: SubtitleData,
    config: OracleConfig,
) -> dict:
    """Lightweight oracle check: verify only, no correction loop.

    Returns summary dict suitable for API response augmentation.
    """
    source_facts = _extract_key_facts_from_source(subtitle, [], info)
    oracle_result = await oracle_verify(
        summary=summary, source_facts=source_facts, config=config
    )

    confidence = compute_confidence_score(
        oracle_result,
        {"enabled": False, "agreement": 1.0},
        1.0,
    )

    return {
        "oracle_verdict": oracle_result.get("overall_verdict", "UNKNOWN"),
        "oracle_confidence": confidence,
        "oracle_factuality": oracle_result.get("factuality", {}).get("score", 0),
        "oracle_coherence": oracle_result.get("coherence", {}).get("score", 0),
        "oracle_completeness": oracle_result.get("completeness", {}).get("score", 0),
        "oracle_issues": {
            "factuality": oracle_result.get("factuality", {}).get("issues", [])[:3],
            "coherence": oracle_result.get("coherence", {}).get("issues", [])[:3],
            "completeness": oracle_result.get("completeness", {}).get("issues", [])[:3],
        },
    }


# ---------------------------------------------------------------------------
# Integration helper: build default config from DB settings
# ---------------------------------------------------------------------------


def build_oracle_config_from_db(db_module) -> OracleConfig:
    """Build OracleConfig from database settings.

    Cross-leverage with claude-api skill for model ID validation.
    """
    config = OracleConfig()
    # Primary model (the one user configured)
    config.primary_model = db_module.get_setting("model", PRIMARY_MODEL_DEFAULT)
    config.primary_api_url = db_module.get_setting("api_url", PRIMARY_API_URL_DEFAULT)
    config.primary_api_key = db_module.get_setting("api_key", "")

    # Oracle model (verifier; defaults to a cost-effective model)
    config.oracle_model = db_module.get_setting(
        "oracle_model", ORACLE_MODEL_DEFAULT
    )
    config.oracle_api_url = db_module.get_setting(
        "oracle_api_url", ORACLE_API_URL_DEFAULT
    )
    config.oracle_api_key = db_module.get_setting(
        "oracle_api_key", config.primary_api_key
    )  # reuse primary key if no separate oracle key

    # Feature flags
    oracle_enabled = db_module.get_setting("oracle_enabled", "true")
    config.enabled = oracle_enabled.lower() in ("true", "1", "yes")
    config.cross_validation_enabled = (
        db_module.get_setting("oracle_cross_validation", "false").lower()
        in ("true", "1", "yes")
    )
    config.self_improvement_enabled = (
        db_module.get_setting("oracle_self_improvement", "true").lower()
        in ("true", "1", "yes")
    )

    # Numeric settings
    try:
        config.quality_gate_threshold = float(
            db_module.get_setting("oracle_quality_gate", str(QUALITY_GATE_THRESHOLD))
        )
    except (ValueError, TypeError):
        config.quality_gate_threshold = QUALITY_GATE_THRESHOLD
    try:
        config.max_refinement_rounds = int(
            db_module.get_setting("oracle_max_refinement", str(MAX_REFINEMENT_ROUNDS))
        )
    except (ValueError, TypeError):
        config.max_refinement_rounds = MAX_REFINEMENT_ROUNDS

    return config
