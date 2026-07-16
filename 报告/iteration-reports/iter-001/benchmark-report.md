# Benchmark Report — Iter#1 Pipe vs Mono

| Metric | Pipeline (5-agent) | Monolithic (1-agent) | Winner |
|--------|-------------------|---------------------|--------|
| Issues found | 21 (6+15) | — | pipeline |
| P0 issues | 2 | — | — |
| P1 issues | 6 | — | — |
| P2 issues | 7 | — | — |
| Checkpoints | 5 | 1 | pipeline |

**Verdict**: Pipeline confirmed. 5 agents returned 21 issues (2 P0). Monolithic ran but was one agent in a pool. Pipeline preserves diversity of findings across dimensions.

**Key P0 findings from benchmark**:
1. workflow_context injection to Agent system prompt lacks sanitization — leads to instruction poisoning
2. JSON serialization format breaks checksum determinism — non-canonical key ordering
