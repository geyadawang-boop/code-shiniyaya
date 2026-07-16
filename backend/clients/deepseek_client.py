"""
clients/deepseek_client.py — DeepSeek API client.

DeepSeek uses the OpenAI Chat Completions wire protocol with different:
  - Pricing (input/output per 1M tokens)
  - Model IDs (deepseek-chat, deepseek-reasoner)
  - Default base URL: https://api.deepseek.com/v1
"""

from __future__ import annotations

from typing import Dict, Optional

from .openai_client import OpenAIClient
from .base import ChatResponse, ChatRequest, CostInfo


class DeepSeekClient(OpenAIClient):
    """
    DeepSeek API client — OpenAI-compatible wire protocol, different pricing.

    Models: deepseek-chat, deepseek-reasoner
    URL: https://api.deepseek.com/v1
    """

    DEFAULT_URL = "https://api.deepseek.com/v1"

    # DeepSeek pricing (per 1M tokens)
    PRICING = {
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
    }

    def __init__(self, api_key: str = "", api_url: str = "", model: str = "", **kwargs):
        super().__init__(
            api_key=api_key,
            api_url=api_url or self.DEFAULT_URL,
            model=model or "deepseek-chat",
            **kwargs,
        )

    def _parse_response(self, raw: Dict, req: ChatRequest) -> ChatResponse:
        """Override to use DeepSeek provider label in CostInfo."""
        resp = super()._parse_response(raw, req)
        resp.cost.provider = "deepseek"
        return resp

    def _handle_usage_event(self, event: Dict) -> None:
        """Override to use DeepSeek provider label."""
        super()._handle_usage_event(event)
        if self._final_cost:
            self._final_cost.provider = "deepseek"

    def _extract_stream_cost(self, raw: Dict) -> CostInfo:
        """Override to use DeepSeek provider label and pricing."""
        usage = raw.get("usage", {})
        token_in = usage.get("prompt_tokens", 0)
        token_out = usage.get("completion_tokens", 0)
        return CostInfo(
            token_in=token_in,
            token_out=token_out,
            cost_usd=self._compute_cost(token_in, token_out),
            model=self.model,
            provider="deepseek",
        )

    def _extract_error(self, data: Dict, status_code: int) -> str:
        """DeepSeek error shape differs slightly from OpenAI."""
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", f"DeepSeek API error {status_code}")
        if isinstance(err, str) and err.strip():
            return err
        return f"DeepSeek API error {status_code}"
