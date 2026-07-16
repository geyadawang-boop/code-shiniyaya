"""
clients/base.py — Abstract base for all LLM provider clients.

Defines:
  - ChatRequest / ChatResponse / CostInfo dataclasses
  - BaseLLMClient ABC with dual-mode (stream / non-stream) interface
  - Token counting hook
"""

from __future__ import annotations

import abc
import json
import time as _time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class CostInfo:
    """CodexBar-compatible cost tracking."""
    token_in: int = 0
    token_out: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model: str = ""
    provider: str = ""

    def to_log_line(self) -> str:
        """Single-line log format compatible with CodexBar parser."""
        return (
            f"[cost] model={self.model} provider={self.provider} "
            f"token_in={self.token_in} token_out={self.token_out} "
            f"cache_read={self.cache_read_tokens} cache_write={self.cache_write_tokens} "
            f"cost_usd={self.cost_usd:.6f} latency_ms={self.latency_ms:.0f}"
        )


@dataclass
class ChatRequest:
    """Normalized request across all providers."""
    messages: List[Dict[str, Any]]
    max_tokens: int = 4096
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: bool = False
    thinking: Optional[Dict[str, Any]] = None
    reasoning_effort: Optional[str] = None
    stop_sequences: Optional[List[str]] = None
    extra_body: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Normalized response across all providers."""
    content: str
    cost: CostInfo
    stop_reason: str = ""
    raw: Optional[Dict[str, Any]] = None


class BaseLLMClient(abc.ABC):
    """
    Abstract LLM client with unified streaming/non-streaming interface.

    Subclasses implement:
      - _build_headers() → dict
      - _build_body(request) → dict
      - _parse_response(raw_data, request) → ChatResponse
      - _parse_stream_chunk(raw_line) → Optional[str] (delta text or None)
      - _parse_stream_cost(raw_data) → CostInfo

    Public API:
      - chat(request) → ChatResponse          (non-streaming)
      - chat_stream(request) → AsyncIterator[str], finalize → ChatResponse
    """

    # Pricing table: (input_price_per_1M, output_price_per_1M)
    PRICING: Dict[str, tuple] = {
        "claude-opus-4-8": (5.0, 25.0),
        "claude-opus-4-7": (5.0, 25.0),
        "claude-sonnet-5": (3.0, 15.0),
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-haiku-4-5": (1.0, 5.0),
        "gpt-5.2": (2.5, 10.0),
        "gpt-4o": (2.5, 10.0),
        "gpt-4o-mini": (0.15, 0.6),
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
    }

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "",
        model: str = "",
        timeout: int = 120,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Subclass contract
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def _build_headers(self) -> Dict[str, str]:
        """Return HTTP headers for the provider's API."""
        ...

    @abc.abstractmethod
    def _build_body(self, request: ChatRequest) -> Dict[str, Any]:
        """Build provider-specific JSON body from normalized ChatRequest."""
        ...

    @abc.abstractmethod
    def _parse_response(self, raw: Dict[str, Any], request: ChatRequest) -> ChatResponse:
        """Parse provider-specific HTTP response into ChatResponse + CostInfo."""
        ...

    @abc.abstractmethod
    def _parse_stream_chunk(self, line: str) -> Optional[str]:
        """
        Parse one SSE line; return delta text (str) or None.
        Called only in streaming mode.
        """
        ...

    def _extract_stream_cost(self, raw: Dict[str, Any]) -> CostInfo:
        """Extract CostInfo from a stream event containing a usage block.

        Default implementation extracts from generic usage block.
        Subclasses may override for provider-specific usage shapes.
        Note: chat_stream() uses _handle_usage_event for inline accumulation;
        this method is provided for subclasses/adapters that use a different pattern.
        """
        usage = raw.get("usage", {})
        token_in = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        token_out = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        return CostInfo(
            token_in=token_in,
            token_out=token_out,
            cost_usd=self._compute_cost(token_in, token_out),
            model=self.model,
            provider=self.__class__.__name__,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _handle_usage_event(self, event: Dict[str, Any]) -> None:
        """Accumulate usage from streaming events.

        Called by _parse_stream_chunk during streaming. Subclasses may override
        to handle provider-specific usage shapes (Anthropic message_delta,
        OpenAI usage delta, etc.).
        """
        usage = event.get("usage", {})
        if not usage:
            return
        curr = self._final_cost or CostInfo(model=self.model, provider=self.__class__.__name__)
        curr.token_in = usage.get("prompt_tokens", curr.token_in) or usage.get("input_tokens", curr.token_in)
        curr.token_out = usage.get("completion_tokens", curr.token_out) or usage.get("output_tokens", curr.token_out)
        curr.cost_usd = self._compute_cost(curr.token_in, curr.token_out)
        self._final_cost = curr

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Fast char/3 heuristic; use count_tokens API for precision."""
        return max(1, len(text) // 3)

    def _get_pricing(self) -> tuple:
        """(input_$pm, output_$pm) for configured model, defaulting to (5,25)."""
        return self.PRICING.get(self.model, (5.0, 25.0))

    def _compute_cost(self, token_in: int, token_out: int) -> float:
        in_pm, out_pm = self._get_pricing()
        return (token_in / 1_000_000) * in_pm + (token_out / 1_000_000) * out_pm

    def _resolve_url(self, request: ChatRequest) -> str:
        """Return the endpoint URL (may differ for streaming)."""
        return self.api_url

    # ------------------------------------------------------------------
    # Public: non-streaming
    # ------------------------------------------------------------------

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Single-turn, non-streaming call."""
        import httpx

        t0 = _time.time()
        url = self._resolve_url(request)
        headers = self._build_headers()
        body = self._build_body(request)
        body["stream"] = False

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(url, headers=headers, json=body)
            if not r.text:
                raise ValueError(f"Empty API response (status={r.status_code})")
            try:
                data = r.json()
            except Exception as _je:
                raise ValueError(f"Invalid API response: {_je}") from _je
            if r.status_code != 200:
                err_msg = self._extract_error(data, r.status_code)
                raise ValueError(err_msg)

        resp = self._parse_response(data, request)
        resp.cost.latency_ms = (_time.time() - t0) * 1000
        return resp

    # ------------------------------------------------------------------
    # Public: streaming
    # ------------------------------------------------------------------

    async def chat_stream(self, request: ChatRequest):
        """
        Async generator yielding (delta_text: str | None, is_final: bool).
        On the final yield, the 2-tuple is (None, True); retrieve .final_cost
        from this client instance after the generator exhausts.
        """
        import httpx

        self._final_cost: Optional[CostInfo] = None
        t0 = _time.time()
        url = self._resolve_url(request)
        headers = self._build_headers()
        body = self._build_body(request)
        body["stream"] = True

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    body_bytes = await resp.aread()
                    try:
                        err = json.loads(body_bytes)
                    except Exception:
                        err = {"error": {"message": body_bytes.decode(errors="replace")}}
                    raise ValueError(self._extract_error(err, resp.status_code))

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        cost = self._final_cost or CostInfo(
                            model=self.model, provider=self.__class__.__name__
                        )
                        cost.latency_ms = (_time.time() - t0) * 1000
                        self._final_cost = cost
                        yield (None, True)
                        return
                    delta = self._parse_stream_chunk(data_str)
                    if delta is not None:
                        yield (delta, False)

        # If we exited without [DONE], yield final
        cost = self._final_cost or CostInfo(
            model=self.model, provider=self.__class__.__name__
        )
        cost.latency_ms = (_time.time() - t0) * 1000
        self._final_cost = cost
        yield (None, True)

    @property
    def final_cost(self) -> Optional[CostInfo]:
        return getattr(self, "_final_cost", None)

    # ------------------------------------------------------------------
    # Error extraction
    # ------------------------------------------------------------------

    def _extract_error(self, data: Dict[str, Any], status_code: int) -> str:
        err = data.get("error", {})
        if isinstance(err, dict):
            return err.get("message", f"API error {status_code}")
        return str(err or f"API error {status_code}")
