"""
clients/openai_client.py — OpenAI / OpenAI-compatible API client.

Wire protocol: POST {base_url}/chat/completions (OpenAI Chat Completions).
Supports: streaming SSE, cost tracking for GPT models.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import BaseLLMClient, ChatRequest, ChatResponse, CostInfo


class OpenAIClient(BaseLLMClient):
    """
    OpenAI Chat Completions API.

    Compatible with any OpenAI-compatible endpoint (OpenAI, local LLM proxies, etc.).
    For DeepSeek-specific handling (different pricing, different error shapes),
    use DeepSeekClient (subclass below).
    """

    DEFAULT_URL = "https://api.openai.com/v1"

    def __init__(self, api_key: str = "", api_url: str = "", model: str = "", **kwargs):
        super().__init__(
            api_key=api_key,
            api_url=api_url or self.DEFAULT_URL,
            model=model or "gpt-4o",
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_body(self, req: ChatRequest) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": req.messages,
        }

        # o-series models use max_completion_tokens instead of max_tokens
        model_lower = self.model.lower()
        if any(m in model_lower for m in ("o1", "o3", "o4")):
            body["max_completion_tokens"] = req.max_tokens
        else:
            body["max_tokens"] = req.max_tokens

        # reasoning_effort for o-series and GPT-5 (NOT thinking -- that is Anthropic-only)
        if req.reasoning_effort is not None:
            body["reasoning_effort"] = req.reasoning_effort

        if req.temperature is not None:
            body["temperature"] = req.temperature
        if req.top_p is not None:
            body["top_p"] = req.top_p
        if req.stop_sequences:
            body["stop"] = req.stop_sequences

        # Merge extra_body, stripping Anthropic-specific keys
        safe_extra = {
            k: v for k, v in req.extra_body.items()
            if k not in ("thinking", "output_config", "betas",
                         "system", "fallbacks", "anthropic_version")
        }
        body.update(safe_extra)
        return body

    def _parse_response(self, raw: Dict[str, Any], req: ChatRequest) -> ChatResponse:
        choices = raw.get("choices", [])
        if not choices:
            raise ValueError("No choices in OpenAI response")
        summary = choices[0].get("message", {}).get("content", "")
        finish_reason = choices[0].get("finish_reason", "")

        usage = raw.get("usage", {})
        token_in = usage.get("prompt_tokens", 0)
        token_out = usage.get("completion_tokens", 0)
        # OpenAI prompt caching: usage_details → cached_tokens
        usage_details = usage.get("prompt_tokens_details", {}) or usage.get(
            "completion_tokens_details", {}
        )
        cache_read = usage_details.get("cached_tokens", 0)

        cost = CostInfo(
            token_in=token_in,
            token_out=token_out,
            cache_read_tokens=cache_read,
            cost_usd=self._compute_cost(token_in, token_out),
            model=self.model,
            provider="openai",
        )

        return ChatResponse(
            content=summary,
            cost=cost,
            stop_reason=finish_reason,
            raw=raw,
        )

    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        """SSE: data: {...} → choices[0].delta.content"""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None

        choices = event.get("choices", [])
        if not choices:
            # May carry usage info even without choices
            usage = event.get("usage")
            if usage:
                self._handle_usage_event(event)
            return None

        delta = choices[0].get("delta", {})
        text = delta.get("content", "")

        # Track usage from final chunk
        if choices[0].get("finish_reason"):
            usage = event.get("usage")
            if usage:
                self._handle_usage_event(event)

        return text or None

    def _extract_stream_cost(self, raw: Dict[str, Any]) -> CostInfo:
        usage = raw.get("usage", {})
        token_in = usage.get("prompt_tokens", 0)
        token_out = usage.get("completion_tokens", 0)
        # OpenAI prompt caching in stream: usage → prompt_tokens_details.cached_tokens
        usage_details = usage.get("prompt_tokens_details", {}) or {}
        cache_read = usage_details.get("cached_tokens", 0)
        return CostInfo(
            token_in=token_in,
            token_out=token_out,
            cache_read_tokens=cache_read,
            cost_usd=self._compute_cost(token_in, token_out),
            model=self.model,
            provider="openai",
        )

    def _handle_usage_event(self, event: Dict[str, Any]) -> None:
        usage = event.get("usage", {})
        if not usage:
            return
        curr = self._final_cost or CostInfo(model=self.model, provider="openai")
        curr.token_in = usage.get("prompt_tokens", curr.token_in)
        curr.token_out = usage.get("completion_tokens", curr.token_out)
        # OpenAI prompt caching in stream
        cache_details = usage.get("prompt_tokens_details", {}) or {}
        curr.cache_read_tokens = cache_details.get("cached_tokens", curr.cache_read_tokens)
        curr.cost_usd = self._compute_cost(curr.token_in, curr.token_out)
        self._final_cost = curr

    def _resolve_url(self, req: ChatRequest) -> str:
        base = self.api_url.rstrip("/")
        return f"{base}/chat/completions"
