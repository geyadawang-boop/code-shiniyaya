# Headroom Compression -- Usage Guide

Last verified: 2026-07-18

## Verdict: Working but limited value for automated hooks

The headroom MCP tool **works** for manual invocation inside Claude Code, but has
three significant limitations that rule out the original auto-trigger plan:

1.  **Proxy unreachable.** The headroom HTTP proxy at `http://127.0.0.1:8787`
    always returns `ReadTimeout`. All compression happens via the embedded local
    path, not through an external API.
2.  **Low hit rate.** In this session, 8 calls were made -- 7 returned *zero*
    savings (`router:noop`). Only 1 call triggered actual compression, and that
    saved only 14.9% (107 tokens). The router is conservative by design.
3.  **Not callable from external scripts.** `mcp__headroom__headroom_compress`
    is a Claude Code MCP protocol tool, not an HTTP endpoint. A Node.js
    PostToolUse hook cannot invoke it.

**Bottom line:** headroom is a manual tool for squeezing extra tokens out of
truly large outputs (>2000 chars of dense prose). Automating it via hooks
provides negligible benefit because the router declines to compress most
content, and the savings when it does are modest.

---

## Manual invocation

```
mcp__headroom__headroom_compress({ content: "<your text here>" })
```

Returns:

```json
{
  "compressed": "<compressed text>",
  "hash": "0b8df59de5bdaa023934583a",
  "original_tokens": 716,
  "compressed_tokens": 609,
  "tokens_saved": 107,
  "savings_percent": 14.9,
  "transforms": ["router:mixed:0.75"],
  "note": "Original stored with hash=0b8df59de5bdaa023934583a."
}
```

## Retrieval by hash

```
mcp__headroom__headroom_retrieve({ hash: "0b8df59de5bdaa023934583a" })
```

Returns the full original content stored under that hash.

## Current stats

```
mcp__headroom__headroom_stats()
```

Shows session compression count, total tokens saved, estimated cost savings,
and recent event log.

## When to use (practical rules)

- **DO compress** when a tool output exceeds ~2000 characters of dense
  text and you need to reason over it. Call compress, read the compressed
  version, retrieve the original only for specific details.

- **DON'T compress** file listings, JSON metadata, or other sparse outputs
  -- the router will no-op these anyway.

- **DON'T build PostToolUse hooks** around it. The find-skills SKILL.md
  (a 1500-char Markdown file with frontmatter) saved only 14.9%. Most
  large Bash outputs (file trees, logs) are too repetitive/low-entropy
  for the router to engage.

## Integration points (for reference)

| Point | Feasible? | Why |
|---|---|---|
| PreToolUse (large grep) | Manual only | Can't hook into MCP tools from pre-tool hooks |
| PostToolUse (large Bash) | Manual only | Same constraint; see `hooks/headroom-bash.js` for the detection half |
| Inline before reasoning | Yes | This is the practical pattern |

## Artifacts created

- `hooks/headroom-bash.js` -- Detection helper that flags files over 2000 chars
  by writing a `.headroom.json` signal file. It cannot invoke compression itself
  but provides the decision signal for manual follow-up.

## Proxy note

The headroom MCP server configuration includes `proxy.url: "http://127.0.0.1:8787"`
which is unreachable. If you ever run a headroom proxy locally on that port
(e.g., for remote/GPU-accelerated compression), update `mcpServers.headroom`
in `settings.json`.
