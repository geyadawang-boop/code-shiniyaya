"""MemoryMessageCompactor — standalone token-aware message compaction.

Adapted from: reference_repos/vsummary/src/backend/agent/memory/messages.py
Simplified for BiliSum — no external agent framework dependencies.

Usage:
    compactor = MemoryMessageCompactor(max_tokens=8000)
    compacted = compactor.compact(messages)  # returns compacted list
"""

import tiktoken
from typing import List, Dict


class MemoryMessageCompactor:
    """Compacts conversation history to stay within a token budget."""

    def __init__(self, max_tokens: int = 8000, model: str = "gpt-4"):
        self.max_tokens = max_tokens
        try:
            self._enc = tiktoken.encoding_for_model(model)
        except Exception:
            self._enc = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(self, messages: List[Dict]) -> int:
        total = 0
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total += len(self._enc.encode(content))
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += len(self._enc.encode(block["text"]))
            total += 4  # role + formatting overhead
        return total + 2  # start/end tokens

    def compact(self, messages: List[Dict]) -> List[Dict]:
        """Keep most recent messages that fit within max_tokens."""
        if not messages:
            return messages
        result = []
        remaining = self.max_tokens
        # Always keep the first message (system prompt or context)
        if messages and messages[0].get("role") == "system":
            result.append(messages[0])
            remaining -= self._count_tokens([messages[0]])
            messages = messages[1:]
        # Keep messages from newest to oldest while within budget
        for m in reversed(messages):
            cost = self._count_tokens([m])
            if cost <= remaining:
                result.insert(1 if result and result[0].get("role") == "system" else 0, m)
                remaining -= cost
            else:
                break
        return result