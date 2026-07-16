"""
clients/anthropic_client.py — Anthropic Messages API client.

Uses httpx (raw HTTP) by project convention.
Supports: adaptive thinking, streaming SSE, cost tracking.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import BaseLLMClient, ChatRequest, ChatResponse, CostInfo


class AnthropicClient(BaseLLMClient):
    """
    Anthropic Messages API (https://api.anthropic.com/v1/messages).

    Features:
      - Adaptive thinking on Opus 4.8 / 4.7 / Sonnet 5
      - 128K max_tokens via streaming
      - Prompt caching (cache_control breakpoints)
      - Cost tracking from usage block
    """

    DEFAULT_URL = "https://api.anthropic.com/v1/messages"
    ANTHROPIC_VERSION = "2023-06-01"

    def __init__(self, api_key: str = "", api_url: str = "", model: str = "", **kwargs):
        super().__init__(api_key=api_key, api_url=api_url or self.DEFAULT_URL, model=model, **kwargs)

    # ------------------------------------------------------------------
    # Contract
    # ------------------------------------------------------------------

    def _build_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    def _build_body(self, req: ChatRequest) -> Dict[str, Any]:
        # Split system message(s) from the conversation messages array.
        # Anthropic Messages API requires system as a top-level field,
        # NOT inside the messages list.
        messages: List[Dict] = []
        system_blocks: List[Dict] = []
        for m in req.messages:
            if m.get("role") == "system":
                content = m.get("content", "")
                if isinstance(content, list):
                    system_blocks.extend(content)
                elif isinstance(content, str) and content.strip():
                    system_blocks.append({"type": "text", "text": content})
            else:
                messages.append(m)

        body: Dict[str, Any] = {
            "model": self.model or "claude-opus-4-8",
            "max_tokens": req.max_tokens,
            "messages": messages,
        }

        # Attach system prompt top-level if any system blocks were extracted.
        if system_blocks:
            body["system"] = system_blocks if len(system_blocks) > 1 else system_blocks[0]

        # Adaptive thinking (Opus 4.8 / 4.7 / Sonnet 5 / Fable 5 / Mythos 5)
        if req.thinking is not None:
            body["thinking"] = req.thinking
        elif self.model and any(m in self.model for m in ("opus-4-8", "opus-4-7", "sonnet-5", "fable-5", "mythos-5")):
            body["thinking"] = {"type": "adaptive"}

        if req.stop_sequences:
            body["stop_sequences"] = req.stop_sequences

        # Merge extra_body (e.g. betas, speed, output_config)
        body.update(req.extra_body)

        return body

    def _parse_response(self, raw: Dict[str, Any], req: ChatRequest) -> ChatResponse:
        content = raw.get("content", [])
        # Collect all text blocks (skip thinking blocks)
        text_blocks = [
            b.get("text", "") for b in content if b.get("type") == "text"
        ]
        if text_blocks:
            summary = "".join(text_blocks)
        elif content and isinstance(content[0], dict):
            summary = content[0].get("text", "")
        else:
            summary = ""

        usage = raw.get("usage", {})
        token_in = usage.get("input_tokens", 0)
        token_out = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)

        cost = CostInfo(
            token_in=token_in,
            token_out=token_out,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=self._compute_cost(token_in, token_out),
            model=self.model,
            provider="anthropic",
        )

        return ChatResponse(
            content=summary,
            cost=cost,
            stop_reason=raw.get("stop_reason", ""),
            raw=raw,
        )

    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        """SSE: data: {...} → content_block_delta.text or content_block_start.text"""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None

        etype = event.get("type", "")

        # Track usage from message_delta or message_stop
        if etype in ("message_delta", "message_stop"):
            self._handle_usage_event(event)

        # Content block delta (text)
        if etype == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")

        # Content block start (may contain text in some cases)
        if etype == "content_block_start":
            block = event.get("content_block", {})
            if block.get("type") == "text":
                return block.get("text", "")

        return None

    def _extract_stream_cost(self, raw: Dict[str, Any]) -> CostInfo:
        usage = raw.get("usage", {})
        token_in = usage.get("input_tokens", 0)
        token_out = usage.get("output_tokens", 0)
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        return CostInfo(
            token_in=token_in,
            token_out=token_out,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=self._compute_cost(token_in, token_out),
            model=self.model,
            provider="anthropic",
        )

    def _handle_usage_event(self, event: Dict[str, Any]) -> None:
        """Accumulate usage from streaming events."""
        usage = event.get("usage", {})
        curr = self._final_cost or CostInfo(model=self.model, provider="anthropic")
        curr.token_in = usage.get("input_tokens", curr.token_in)
        curr.token_out = usage.get("output_tokens", curr.token_out)
        curr.cost_usd = self._compute_cost(curr.token_in, curr.token_out)
        self._final_cost = curr

    def _resolve_url(self, req: ChatRequest) -> str:
        """Anthropic uses the same URL for stream and non-stream."""
        return self.api_url

    def _extract_error(self, data: Dict[str, Any], status_code: int) -> str:
        err = data.get("error", {})
        if isinstance(err, dict):
            err_type = err.get("type", "")
            err_msg = err.get("message", f"HTTP {status_code}")
            return f"[{err_type}] {err_msg}"
        return super()._extract_error(data, status_code)

    # ------------------------------------------------------------------
    # Anthropic-specific: compact helper
    # ------------------------------------------------------------------

    def build_messages(
        self,
        system: Optional[str] = None,
        user_content: str = "",
        history: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """Convenience: build messages list including optional system prompt.

        The system prompt is inserted as a top-level "system" role message so
        that _build_body() can extract it into Anthropic's top-level system field.
        """
        msgs: List[Dict] = list(history or [])
        if system:
            msgs.insert(0, {"role": "system", "content": system})
        msgs.append({"role": "user", "content": user_content})
        return msgs
