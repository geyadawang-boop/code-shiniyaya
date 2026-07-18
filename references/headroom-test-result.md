# Headroom Compress MCP Tool Test Result

**Date:** 2026-07-18
**Test Input:** ~405 tokens of MEMORY.md content (~1,200 chars)

## Tool Call Parameters

```json
{
  "content": "# Memory Index for code-shiniyaya\n\nThis is the central memory index..."
}
```

## Result

```json
{
  "compressed": "<identical to input>",
  "hash": "dbf5bbdb5474a622c6f2772b",
  "original_tokens": 405,
  "compressed_tokens": 405,
  "tokens_saved": 0,
  "savings_percent": 0.0,
  "transforms": ["router:noop"],
  "proxy": {
    "url": "http://127.0.0.1:8787",
    "status": "unreachable",
    "error": "ReadTimeout: "
  },
  "warning": "Configured proxy http://127.0.0.1:8787 is unreachable (ReadTimeout: )."
}
```

## Verdict: NON-FUNCTIONAL

The headroom compression proxy at `http://127.0.0.1:8787` is not running. Every compress call falls through to `router:noop`, which returns the content unchanged with zero savings.

To make this work, the user needs to start the headroom backend service on port 8787. Without the proxy, `mcp__headroom__headroom_compress` is a pass-through no-op.
