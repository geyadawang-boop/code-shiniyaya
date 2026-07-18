# Token Optimization Audit — code-shiniyaya

**Date:** 2026-07-18
**Scope:** RTK availability, headroom compress, hook configuration, journal token analysis

---

## 1. RTK CLI Token Optimization Tool

**Status: NOT INSTALLED.**

- `rtk` command not found in PATH.
- `npm list -g rtk` returns empty (no global rtk package).
- `which rtk` and `where rtk` both return "not found".

**Conclusion:** RTK is not available and has never been installed. No token savings from this tool.

---

## 2. Alternative Compact/Token npm Packages

**Status: NONE FOUND.**

- `npm list -g | grep -iE "compact|compress|token|rtk"` returned no matches.
- No globally installed npm packages provide token optimization.

---

## 3. Settings.json Hook Analysis

**No compact, rtk, or token-compression hooks exist in settings.json.**

Current hooks registered:
| Hook | Matcher | Command |
|------|---------|---------|
| PreToolUse | `Bash` | `echo-guard.js` — blocks wasteful echo patterns, limits to 8 readonly Bash/turn |
| Stop | (all) | `stop-guard.js` — stall detection, pre-launch gate, convergence checking |
| SessionStart | `startup\|resume\|clear\|compact` | `bearings.js` — injects snapshot context on session start/resume |
| Notification | (all) | `claude-code-zh-cn` notification hook |

The `startup|resume|clear|compact` matcher on SessionStart means bearings.js fires after `/compact` — this is the closest thing to compact-related optimization, but it does NOT compress or reduce tokens; it injects snapshot state back into context.

---

## 4. Headroom Compress MCP Tool Test

**Result: NON-FUNCTIONAL (no-op).**

Tested with ~405 tokens of MEMORY.md content:

```json
{
  "original_tokens": 405,
  "compressed_tokens": 405,
  "tokens_saved": 0,
  "savings_percent": 0.0,
  "transforms": ["router:noop"],
  "proxy": {
    "url": "http://127.0.0.1:8787",
    "status": "unreachable",
    "error": "ReadTimeout: "
  }
}
```

The headroom compression backend proxy at `http://127.0.0.1:8787` is unreachable. The tool falls back to a `router:noop` pass-through, returning the original content unchanged. **Zero token savings in practice.**

---

## 5. Journal Token Usage Analysis

Sampled 4 workflow journals from `C:\Users\shiniyaya\.claude\projects\D---claude\599a9a0b-b50c-408a-8971-13091a6783bd\subagents\workflows\`:

### Workflow wf_385f9de3-c71 (Scan14, Jul 18 08:25)
- **8 subagents** dispatched in 2 parallel batches
- First batch (5 agents): dimension-specific audits (config consistency, git stability, anchor validation, hook verification)
- Second batch (3 agents): adversarial review of first-batch findings
- **Token estimate:** ~10-20K tokens in subagent results + adversarial reviews

### Workflow wf_9810e020-485 (Scan13, Jul 18 08:25)
- **10 subagents** dispatched in 2 parallel batches
- First batch (6 agents): README alignment, trigger coverage, autodream source analysis, journal mechanism audit, convergence audit
- Second batch (4 agents): adversarial review of first-batch findings
- **Token estimate:** ~15-25K tokens in subagent results + reviews

### Workflow wf_c3bb1d7c-199 (Cross-source verify, Jul 18 08:43)
- **20+ subagents** across multiple batches (103 total files in directory)
- Multi-source perspectives: autodream, autoresearch, ponytail, autonomous-coding
- Each source perspective spawns its own set of verification agents
- Adversarial review cascade: findings from wave 1 reviewed by wave 2
- **Token estimate:** ~30-60K tokens (largest workflow sampled)

### Workflow wf_0970835b-999 (Scan12, Jul 18 07:42)
- **12 subagents** dispatched in 3 batches
- First batch (6 agents): dimension scans (convergence rules, hooks.test.js audit, config.json consistency, journal recovery, git diff audit)
- Second batch (5 agents): adversarial reviews of first-batch claims
- Third batch (1 agent): additional scan
- **Token estimate:** ~15-30K tokens

### Token Distribution Pattern

| Metric | Range |
|--------|-------|
| Subagents per workflow | 8-20+ |
| Result size per agent | 0.5-5K tokens (empty findings vs rich results) |
| Adversarial review overhead | 30-50% of total agent count |
| Estimated tokens per workflow | 15-60K |
| Agent metadata | Minimal (`agentType`, `spawnDepth` only) — no token counts stored |

**Key observation:** Every workflow follows a two-wave pattern:
1. **Wave 1** — Find: multiple agents scan for issues across different dimensions
2. **Wave 2** — Verify: adversarial review agents check whether Wave 1 findings are `refuted: true` or `refuted: false`

This means ~40% of dispatched agents are dedicated to verifying the output of the other 60%. The adversarial review agents produce findings that are themselves subject to further review in some cases.

### Where Tokens Are Consumed

1. **Subagent dispatch context** — each subagent receives full task description + file paths (~500-1500 tokens each)
2. **Subagent results** — JSON findings arrays returned to main agent (0-5K tokens each, depends on findings count)
3. **Adversarial review** — review agents re-read the same files plus the original findings (double-read cost)
4. **Main agent aggregation** — all results are concatenated into the main agent's context

No token counting metadata exists in the journal or agent `.meta.json` files — actual token consumption is not tracked.

---

## 6. Summary of Findings

| Tool/Method | Status | Token Savings |
|-------------|--------|--------------|
| RTK CLI | Not installed | 0 |
| npm compact packages | None found | 0 |
| settings.json hooks | No compression hooks | 0 (bearings injects state, does not compress) |
| headroom_compress MCP | Backend offline, no-op fallback | 0 |
| Caveman compression (skill) | Installed as skill, not in hooks | Unknown (manual invocation only) |
| Echo-guard hook | Active (Bash call limiting) | Indirect (prevents waste, not compression) |

### Action Items

1. **Start headroom proxy** — the compression backend at `127.0.0.1:8787` needs to be running for `headroom_compress` to work. Without it, every call is a no-op.
2. **Install RTK** — if RTK CLI provides measurable gains, install it globally via npm and add a SessionStart or PostToolUse hook.
3. **Wire caveman into hooks** — the caveman skill claims 65% token savings. If its compress endpoint can be called programmatically, add a hook to compress large outputs before they enter context.
4. **Track actual token usage** — journal files have no token-count metadata. Consider adding a hook or plugin that logs per-agent token consumption for visibility.
5. **Reduce adversarial review overhead** — ~40% of subagents verify other subagents. If headroom/caveman compression were functional, the double-read cost could be mitigated by compressing first-wave results before review.
