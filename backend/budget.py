"""
budget.py — Token budget calculator v2

Replaces the fragile inline budget computation in summarizer.py:247-286.
Integrates with quality.py's compute_note_budget() output to produce precise
max_tokens values based on:
  - Content complexity (richness score from analyze_content)
  - Quality multiplier from stat data (view/like/favorite/coin/reply/danmaku)
  - Model context window safety margin
  - Mode-specific scaling (brief/detailed/keypoints/mindmap)

Usage:
  from budget import TokenBudgetCalculator
  calc = TokenBudgetCalculator()
  max_tokens = calc.compute(prompt, mode, quality_budget, richness)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class BudgetResult:
    """Output of TokenBudgetCalculator.compute()."""
    max_tokens: int
    safe_max_tokens: int          # after context-window safety margin
    prompt_tokens_est: int        # estimated prompt token count
    target_output_tokens: int     # quality-budget-derived target (before safety clamp)
    richness: float               # 0-10 content richness score
    multiplier: float             # quality multiplier from stat data
    mode_factor: float            # mode scaling factor
    model_context_limit: int      # model's context window
    reasoning: str                # human-readable budget rationale


class TokenBudgetCalculator:
    """
    Computes precise max_tokens for LLM summarization requests.

    Algorithm:
      1. Estimate prompt tokens via char/3 heuristic (or model-specific tokenizer).
      2. Compute base target from quality budget (if available) or richness.
      3. Apply mode factor (brief=0.25, keypoints=0.5, detailed=1.0, mindmap=0.75).
      4. Apply quality multiplier from stat data.
      5. Clamp to [256, output_cap] with context-window safety margin.
    """

    # Mode scaling factors
    MODE_FACTORS = {
        "brief": 0.25,
        "keypoints": 0.5,
        "detailed": 1.0,
        "mindmap": 0.75,
    }

    # Model context windows
    MODEL_CONTEXT_LIMITS = {
        "claude-opus-4-8": 1_000_000,
        "claude-opus-4-7": 1_000_000,
        "claude-sonnet-5": 1_000_000,
        "claude-sonnet-4-6": 1_000_000,
        "claude-haiku-4-5": 200_000,
        "gpt-5.2": 256_000,
        "gpt-4o": 128_000,
        "gpt-4o-mini": 128_000,
        "deepseek-chat": 128_000,
        "deepseek-reasoner": 128_000,
    }

    # Richness → base output token mapping
    RICHNESS_TARGETS = [
        (2, 1024),    # richness <= 2 → 1024 tokens
        (4, 2048),    # <= 4 → 2048
        (6, 4096),    # <= 6 → 4096
        (8, 6144),    # <= 8 → 6144
        (10, 8192),   # <= 10 → 8192
    ]

    DEFAULT_OUTPUT_CAP = 32_000
    MIN_TOKENS = 256
    SAFETY_MARGIN = 500

    def __init__(
        self,
        output_cap: int = DEFAULT_OUTPUT_CAP,
        safety_margin: int = SAFETY_MARGIN,
    ):
        self.output_cap = output_cap
        self.safety_margin = safety_margin

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        prompt: str,
        mode: str = "detailed",
        quality_budget: Optional[Dict] = None,
        richness: float = 5.0,
        model: str = "",
    ) -> BudgetResult:
        """
        Compute optimal max_tokens for a summarization request.

        Args:
          prompt: full prompt text (used for token estimation)
          mode: one of brief/keypoints/detailed/mindmap
          quality_budget: output from quality.compute_note_budget()
          richness: 0-10 content richness from analyze_content()
          model: model ID string (for context window lookup)

        Returns:
          BudgetResult with max_tokens and derivation details.
        """
        # 1. Estimate prompt tokens
        prompt_tokens = self._estimate_tokens(prompt)
        context_limit = self.MODEL_CONTEXT_LIMITS.get(model, 200_000)

        # 2. Base target from quality budget or richness
        derived_from_quality = False
        if quality_budget and quality_budget.get("deep_target"):
            # quality budget provides explicit deep_target / target_max
            if mode == "detailed":
                base_target = min(quality_budget["deep_target"] // 2, self.output_cap)
            else:
                base_target = min(quality_budget.get("target_max", 4096) // 2, self.output_cap // 2)
            derived_from_quality = True
        else:
            base_target = self._richness_to_target(richness)

        # 3. Apply mode factor
        mode_factor = self.MODE_FACTORS.get(mode, 1.0)
        target = int(base_target * mode_factor)

        # 4. Quality multiplier (0.5–2.0)
        # IMPORTANT: deep_target / target_max from quality.compute_note_budget()
        # already incorporate the quality_multiplier. Only apply when the base
        # target was derived from richness (not from quality_budget), or when
        # quality_budget is unavailable.
        if quality_budget and not derived_from_quality:
            multiplier = quality_budget.get("quality_multiplier", 1.0)
        elif not quality_budget:
            multiplier = 1.0
        else:
            multiplier = 1.0  # already baked into deep_target/target_max
        target = int(target * multiplier)

        # 5. Context-window safety clamp
        safe_max = max(self.MIN_TOKENS, context_limit - prompt_tokens - self.safety_margin)
        max_tokens = min(target, safe_max, self.output_cap)
        max_tokens = max(max_tokens, self.MIN_TOKENS)

        # Build reasoning
        parts = []
        parts.append(f"prompt_est={prompt_tokens} tokens")
        parts.append(f"richness={richness:.1f}/10")
        parts.append(f"mode={mode} (factor={mode_factor})")
        if quality_budget:
            parts.append(f"deep_target={quality_budget.get('deep_target', 'N/A')}")
            parts.append(f"quality_mult={multiplier:.2f}")
        parts.append(f"context_limit={context_limit:,}")
        parts.append(f"safe_max={safe_max:,}")
        parts.append(f"capped={max_tokens:,}")

        return BudgetResult(
            max_tokens=max_tokens,
            safe_max_tokens=safe_max,
            prompt_tokens_est=prompt_tokens,
            target_output_tokens=target,
            richness=richness,
            multiplier=multiplier,
            mode_factor=mode_factor,
            model_context_limit=context_limit,
            reasoning=" | ".join(parts),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast char/3 heuristic. Replace with count_tokens API for precision."""
        return max(1, len(text) // 3)

    def _richness_to_target(self, richness: float) -> int:
        """Map content richness score (0-10) to base output token budget."""
        for threshold, target in self.RICHNESS_TARGETS:
            if richness <= threshold:
                return target
        return self.RICHNESS_TARGETS[-1][1]


# ------------------------------------------------------------------
# Singleton convenience
# ------------------------------------------------------------------

_default_calc = TokenBudgetCalculator()


def compute_token_budget(
    prompt: str,
    mode: str = "detailed",
    quality_budget: Optional[Dict] = None,
    richness: float = 5.0,
    model: str = "",
) -> BudgetResult:
    """One-liner: compute max_tokens for a summarization request."""
    return _default_calc.compute(prompt, mode, quality_budget, richness, model)


def compute_token_budget_simple(
    prompt_len: int,
    text_len: int,
    richness: float = 5.0,
    mode: str = "detailed",
    context_limit: int = 200_000,
) -> int:
    """
    Fast budget: no quality.py dependency.
    Returns a safe max_tokens given raw lengths and a heuristic richness.
    """
    prompt_est = max(1, prompt_len // 3)
    if richness >= 8:
        base = 8192
    elif text_len > 8000:
        base = 6144
    elif text_len > 3000:
        base = 4096
    else:
        base = 2048

    mode_factor = TokenBudgetCalculator.MODE_FACTORS.get(mode, 1.0)
    target = int(base * mode_factor)
    safe_max = max(256, context_limit - prompt_est - 500)
    return min(target, safe_max)
