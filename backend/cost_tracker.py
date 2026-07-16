"""
AI Cost Tracker v1.1 (v7.2)
Tracks token usage, calculates costs, provides dashboard data.

Changelog:
  v1.1 - Added missing models (fable-5, mythos-5, haiku-4-5-cache, opus-4-6,
         sonnet-4-6, Gemini, GPT o-series); improved fuzzy match; fixed
         bare except in _load_history.
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Cost per 1M tokens (USD) -- updated 2026-07
# Sources: Anthropic Pricing (Jul 2026), OpenAI Pricing (Jul 2026),
#          Google AI Studio (Jul 2026), DeepSeek Pricing (Jul 2026)
MODEL_PRICING = {
    # --- Claude Opus tier ---
    "claude-opus-4-8":        {"input": 15.00, "output": 75.00},
    "claude-opus-4-7":        {"input": 15.00, "output": 75.00},
    "claude-opus-4-6":        {"input": 15.00, "output": 75.00},
    # --- Claude Fable / Mythos tier ---
    "claude-fable-5":         {"input": 15.00, "output": 75.00},
    "claude-mythos-5":        {"input": 15.00, "output": 75.00},
    # --- Claude Sonnet tier ---
    "claude-sonnet-5":        {"input":  3.00, "output": 15.00},
    "claude-sonnet-4-6":      {"input":  3.00, "output": 15.00},
    # --- Claude Haiku tier ---
    "claude-haiku-4-5":       {"input":  0.80, "output":  4.00},
    "claude-haiku-4-5-cache": {"input":  0.08, "output":  0.40},  # prompt caching
    # --- Legacy Claude (keep for backward compat) ---
    "claude-3.5-sonnet":      {"input":  3.00, "output": 15.00},
    "claude-3.5-haiku":       {"input":  0.80, "output":  4.00},
    "claude-3-opus":          {"input": 15.00, "output": 75.00},
    # --- DeepSeek ---
    "deepseek-chat":          {"input":  0.27, "output":  1.10},
    "deepseek-reasoner":      {"input":  0.55, "output":  2.19},
    # --- GPT standard ---
    "gpt-5":                  {"input":  1.25, "output": 10.00},
    "gpt-5-mini":             {"input":  0.15, "output":  0.60},
    "gpt-4o":                 {"input":  2.50, "output": 10.00},
    "gpt-4o-mini":            {"input":  0.15, "output":  0.60},
    # --- GPT o-series (reasoning) ---
    "o3":                     {"input": 10.00, "output": 40.00},
    "o4-mini":                {"input":  1.10, "output":  4.40},
    # --- Gemini ---
    "gemini-2.5-pro":         {"input":  1.25, "output": 10.00},
    "gemini-2.5-flash":       {"input":  0.15, "output":  0.60},
    "gemini-2.5-flash-lite":  {"input":  0.075,"output":  0.30},
}

COST_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "cost_log.jsonl")


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> dict:
    """Estimate cost for a single API call."""
    pricing = MODEL_PRICING.get(model)
    if not pricing:
        # Fuzzy match: tokenize the model name and score against known models
        best_key, best_score = None, 0
        model_lower = model.lower()
        for k in MODEL_PRICING:
            score = _model_similarity(model_lower, k)
            if score > best_score:
                best_score, best_key = score, k
        if best_key and best_score >= 0.6:
            pricing = MODEL_PRICING[best_key]
            logger.debug("fuzzy-matched model %r -> %r (score=%.2f)", model, best_key, best_score)
    if not pricing:
        pricing = {"input": 1.0, "output": 5.0}  # conservative default
        logger.warning("no pricing for model %r; using conservative default", model)

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    total = input_cost + output_cost

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(total, 6),
    }


def _model_similarity(a: str, b: str) -> float:
    """Return a 0.0-1.0 similarity score for model-name fuzzy matching.

    Tokenises both strings on [- ._] and scores by:
      - exact token subset ratio (0.0-0.7)
      - trailing version-digit match bonus (+0.15)
      - starts-with bonus (+0.15)
    """
    import re
    tok_a = set(re.split(r"[- ._]+", a))
    tok_b = set(re.split(r"[- ._]+", b))
    if not tok_a or not tok_b:
        return 0.0
    intersection = tok_a & tok_b
    ratio = len(intersection) / max(len(tok_a), len(tok_b))

    score = ratio * 0.7

    # Trailing digits match (e.g. "4-8" vs "4.8")
    a_trail = re.search(r"(\d[\d.]*)$", a)
    b_trail = re.search(r"(\d[\d.]*)$", b)
    if a_trail and b_trail:
        a_num = a_trail.group(1).replace(".", "-")
        b_num = b_trail.group(1).replace(".", "-")
        if a_num == b_num:
            score += 0.15

    # One is a prefix of the other (e.g. "sonnet" in "sonnet-4-6")
    if a.startswith(b) or b.startswith(a):
        score += 0.15

    return min(score, 1.0)


class CostTracker:
    """Tracks and aggregates API usage costs."""

    def __init__(self):
        self._daily: dict = {}       # date_str -> {model: {tokens, cost}}
        self._total_tokens = 0
        self._total_cost = 0.0
        self._call_count = 0
        self._load_history()

    def _load_history(self):
        """Load cost history from log file."""
        if not os.path.exists(COST_LOG_FILE):
            logger.debug("cost log file not found: %s", COST_LOG_FILE)
            return
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        line_count = 0
        parse_errors = 0
        try:
            with open(COST_LOG_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", "") >= cutoff:
                            self._apply_entry(entry)
                        line_count += 1
                    except json.JSONDecodeError:
                        parse_errors += 1
                        continue
            if parse_errors:
                logger.warning("cost_log.jsonl: %d parse errors out of %d lines", parse_errors, line_count + parse_errors)
        except OSError as e:
            logger.error("failed to read cost log %s: %s", COST_LOG_FILE, e)
        except Exception:
            logger.exception("unexpected error loading cost history")

    def _apply_entry(self, entry: dict):
        """Apply a log entry to in-memory stats."""
        date_str = entry.get("timestamp", "")[:10]
        if date_str not in self._daily:
            self._daily[date_str] = {}
        model = entry.get("model", "unknown")
        if model not in self._daily[date_str]:
            self._daily[date_str][model] = {"tokens": 0, "cost": 0.0}
        tokens = entry.get("input_tokens", 0) + entry.get("output_tokens", 0)
        self._daily[date_str][model]["tokens"] += tokens
        self._daily[date_str][model]["cost"] += entry.get("total_cost_usd", 0)
        self._total_tokens += tokens
        self._total_cost += entry.get("total_cost_usd", 0)
        self._call_count += 1

    def track(self, model: str, input_tokens: int, output_tokens: int) -> dict:
        """Record a new API call and return cost estimate."""
        cost_info = estimate_cost(model, input_tokens, output_tokens)
        entry = {
            "timestamp": datetime.now().isoformat(),
            **cost_info,
        }
        # Append to log file
        try:
            os.makedirs(os.path.dirname(COST_LOG_FILE), exist_ok=True)
            with open(COST_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            logger.error("failed to write cost log entry: %s", e)
        except Exception:
            logger.exception("unexpected error writing cost log")
        self._apply_entry(entry)
        return cost_info

    def get_dashboard(self) -> dict:
        """Get cost dashboard data."""
        today = datetime.now().strftime("%Y-%m-%d")
        today_cost = sum(
            m.get("cost", 0)
            for m in self._daily.get(today, {}).values()
        )
        return {
            "total_tokens": self._total_tokens,
            "total_cost_usd": round(self._total_cost, 4),
            "total_calls": self._call_count,
            "today_cost_usd": round(today_cost, 4),
            "daily_breakdown": {
                date: {
                    model: {"tokens": data["tokens"], "cost_usd": round(data["cost"], 4)}
                    for model, data in models.items()
                }
                for date, models in sorted(self._daily.items(), reverse=True)[:7]
            },
            "pricing": MODEL_PRICING,
        }


# Singleton
_cost_tracker: Optional[CostTracker] = None


def get_cost_tracker() -> CostTracker:
    """Get or create the global cost tracker."""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker
