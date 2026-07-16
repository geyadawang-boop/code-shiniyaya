# autodream-src Context Management Patterns -- Code-Shiniyaya Gap Analysis
# Generated: 2026-07-16 | Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src
# Target files: SKILL.md (STEP 4), anti-hang-v2.md, high-impact-patterns.md

## DIMENSION: Context management -- head-tail truncation, explicit caps on every LLM input, index-content separation

================================================================================
PATTERN 1: Explicit MAX_* Caps as Module-Level Constants
================================================================================

Source: auto_dream.py:32-47
```python
MAX_RECENT_SESSIONS = 8
MAX_SESSION_CHARS = 4000
MAX_EXISTING_MEMORY_FILES = 24
MAX_EXISTING_MEMORY_CHARS = 2500
MAX_RECENT_VECTOR_MEMORIES = 16
MAX_RECENT_VECTOR_MEMORY_CHARS = 700
MAX_RELATED_VECTOR_MEMORIES = 12
MAX_RELATED_VECTOR_MEMORY_CHARS = 700
MAX_VECTOR_QUERY_COUNT = 8
MAX_VECTOR_QUERY_CHARS = 220
MAX_ORPHAN_CANDIDATES = 4
MAX_INDEX_PROMPT_CHARS = 6000
AUTO_DREAM_LOG_MAX_ENTRIES = 40
RELATED_VECTOR_THRESHOLD = 0.58
RELATED_VECTOR_PER_QUERY = 4
MIN_ORPHAN_OVERLAP = 0.5
```

WHY THIS MATTERS:  Every data source that enters an LLM prompt has a hard, named,
module-level cap. No cap = silent context overflow = truncated reasoning = wrong
conclusions (especially under the 10+ Agent x 7 dimension fan-out of STEP 4).

GAP in code-shiniyaya:  STEP 4 ("10+ Agent, 7 dimensions") has ZERO explicit caps.
- No limit on how many findings per dimension (each of 10 agents could return 200 lines)
- No limit on Codex feedback size pasted by user (could be 5000+ tokens)
- No limit on source file content loaded into cross-validation prompt
- No limit on total assembly size before LLM evaluation

Every agent output, every Codex message, every source file -- all enter the STEP 4
verification prompt unbounded. With 10 agents x 7 dimensions, the prompt can easily
exceed the model's context window, causing silent truncation and missed contradictions.

CONCRETE FIX for SKILL.md (insert after STEP 4 header, before trigger line):

```
### STEP 4 -- INPUT CAPS (P0 mandatory)

Every data source entering a STEP 4 verification prompt MUST be bounded by an
explicit cap. These caps are enforced at prompt-assembly time, not at collection time.

| Cap constant | Value | Applies to |
|---|---|---|
| MAX_FINDINGS_PER_DIMENSION | 8 | Agent findings per verification dimension |
| MAX_FINDING_CHARS | 600 | Per-finding character limit (truncated head-tail) |
| MAX_CODEX_FEEDBACK_CHARS | 8000 | Total Codex feedback pasted by user |
| MAX_SOURCE_FILE_CHARS | 2000 | Per source file loaded for cross-reference |
| MAX_VERIFY_PROMPT_CHARS | 12000 | Total assembled STEP 4 prompt |
| MAX_DIMENSION_AGENTS | 3 | Max agents contributing findings per dimension |
| MAX_CONTRADICTION_PAIRS | 12 | Max CC-vs-Codex conflicts to surface |

CAP ENFORCEMENT ORDER (at prompt assembly):
1. Truncate each agent finding to MAX_FINDING_CHARS (head-tail)
2. Sort findings by severity (P0 > P1 > P2), take top MAX_FINDINGS_PER_DIMENSION
3. If more than MAX_DIMENSION_AGENTS contributed, keep the 3 with most P0 findings
4. Truncate Codex feedback to MAX_CODEX_FEEDBACK_CHARS (head-tail)
5. Assemble prompt; if >MAX_VERIFY_PROMPT_CHARS, trim P2 findings first, then P1
6. Log any trimmed findings to STEP4_TRIM_LOG.md for manual review

VIOLATION:  Exceeding any cap without explicit user approval = Gate FAIL.
```

================================================================================
PATTERN 2: Head-Tail Truncation (truncate_for_prompt)
================================================================================

Source: auto_dream.py:1246-1252
```python
def truncate_for_prompt(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head - 9
    return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()
```

WHY THIS MATTERS:  Unlike naive prefix truncation (which keeps only the beginning
and loses conclusions), head-tail preserves both context AND conclusions. The
"\n...\n" marker is a universal signal to the LLM that content was elided -- it
can reason about what was omitted and flag uncertainty.

The 60/40 split is deliberate: 60% for context (how we got here), 40% for
conclusions/results. This is applied systematically at every point where content
enters a prompt (sessions, memories, vector memories, index).

GAP in code-shiniyaya:  SKILL.md has no truncation function. When agent outputs
are large, they either enter the prompt in full (overflow) or are truncated
naively (losing the conclusion where the critical finding lives). STEP 3 has a
"10000 tokens" threshold but no mechanism for how to truncate -- it says "P0优先,
<=8000/部分" but does not specify how.

CONCRETE FIX for SKILL.md (add as new section in Agent编排 or as utility):

```
### Content Truncation Protocol (head-tail, 60/40)

ALL content entering an LLM prompt through code-shiniyaya flows MUST be
truncated using head-tail truncation, never prefix-only:

```
function truncate_for_prompt(text, max_chars):
    if len(text) <= max_chars: return text
    head = int(max_chars * 0.6)
    tail = max_chars - head - 9  // 9 = len("\n...\n")
    return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()
```

APPLIED TO:
- Agent findings before STEP 1 dedup merge (MAX_FINDING_CHARS=600)
- Agent findings before STEP 4 cross-validation (MAX_FINDING_CHARS=600)
- Codex feedback pasted by user (MAX_CODEX_FEEDBACK_CHARS=8000)
- Source files loaded for verification (MAX_SOURCE_FILE_CHARS=2000)
- Memory file content when included in prompts (2500 chars, matches autodream)
- Session transcripts in anti-hang context recovery (4000 chars, matches autodream)

NON-APPLICATION (content preserved in full):
- FOR_CODEX report files (user manually copies these; CC does not truncate)
- State JSON files (structured data, not prompt input)
- DAG files (structured data)
```

================================================================================
PATTERN 3: Index Separate from Content (MEMORY.md Pattern)
================================================================================

Source: auto_dream.py:27, auto_dream.py:921-944, README.md:27-29
```
AUTO_DREAM_INDEX_FILE = "MEMORY.md"
```
README.md:
"MEMORY.md is an index, not the memory itself. The real durable content lives
in the sibling markdown files under autodream/memories/."

render_memory_index() (auto_dream.py:921-944):
- Takes line_limit (default 120 from config)
- Each entry: `- [title](memories/file.md): description`
- Hidden entries: "Additional memories hidden to respect the line limit: N"
- Index is regenerated from file metadata after every dream run

WHY THIS MATTERS:  The index is a COMPACT MAP -- it tells the LLM what exists
and where to find it, without loading all the content into context. When the
LLM needs a specific memory, it can request that file. This is the fundamental
pattern that prevents context bloat in RAG and agent memory systems: metadata
in context, content on disk.

The line_limit constraint (default 120) means the index itself cannot grow
unbounded -- when it would exceed the limit, entries are truncated and a
"hidden count" note is appended.

GAP in code-shiniyaya:  code-shiniyaya's MEMORY.md is a flat list of file paths
("所有记忆文件位于...") with no structured index, no line limit, and no
separation between index metadata and content. The high-impact-patterns.md file
includes full pattern descriptions inline (1-2 paragraphs each), which will
grow unbounded as more patterns are discovered.

Most critically: STEP 4 agent findings are assembled inline into the
cross-validation prompt -- there is no index layer. All 10+ agent conclusions
compete for context with Codex feedback and source files.

CONCRETE FIX for SKILL.md STEP 4:

```
### STEP 4 -- Finding Index (MEMORY.md Pattern)

Before assembling the cross-validation prompt, CC writes a findings INDEX
that separates metadata from content:

STRUCTURE:
  .claude/memory/code-shiniyaya/findings/
    INDEX.md              -- Compact map: dimension -> finding files (max 80 lines)
    accuracy/
      finding-001.md      -- Full agent finding content
      ...
    code-reuse/
      finding-001.md
      ...
    ... (one subdir per dimension)

INDEX.md FORMAT (max 80 lines, regenerated each STEP 4 run):
  # STEP 4 Findings Index -- Session {sessionId[:8]}
  ## Accuracy (4 findings)
  - [P0] line 142 assertion mismatch (accuracy/finding-001.md)
  - [P1] type coercion edge case (accuracy/finding-002.md)
  ...
  ## Code Reuse (2 findings)
  ...

PROMPT ASSEMBLY:  The STEP 4 cross-validation prompt receives ONLY:
  1. INDEX.md (full, 80-line cap)
  2. Top-3 highest-severity findings per dimension (in full, each capped at
     MAX_FINDING_CHARS via head-tail truncation)
  3. Codex feedback (capped at MAX_CODEX_FEEDBACK_CHARS)
  4. CC->Codex comparison table template

FINDINGS NOT IN TOP-3: Referenced by file path in INDEX.md. The LLM can
request specific files if needed ("Read accuracy/finding-004.md for details").

This pattern prevents the "10 agents x 7 dimensions x 200 lines each = 14000
lines" explosion that silently overflows context.
```

================================================================================
PATTERN 4: Per-Input Caps at Prompt Assembly (Systematic Application)
================================================================================

Source: auto_dream.py:186-238 (the _run_auto_dream prompt assembly)

Every data source is capped BEFORE it is JSON-serialized into the prompt template:
```python
# Session transcripts capped:
for session in recent_sessions[:MAX_RECENT_SESSIONS]  # max 8 sessions

# Existing memory content capped:
truncate_for_prompt(item.content, MAX_EXISTING_MEMORY_CHARS)  # 2500 chars each

# Existing memory count capped:
for item in existing_files[:MAX_EXISTING_MEMORY_FILES]  # max 24 files

# Recent vector memories capped:
recent[:MAX_RECENT_VECTOR_MEMORIES]  # max 16, each capped at 700 chars

# Related vector memories capped:
if len(related) >= MAX_RELATED_VECTOR_MEMORIES: return related  # max 12

# Index capped:
truncate_for_prompt(read_memory_index(memory_subdir), MAX_INDEX_PROMPT_CHARS)  # 6000

# Orphan candidates capped:
candidates[:MAX_ORPHAN_CANDIDATES]  # max 4
```

This is the key insight: caps are applied at the DATA LAYER, not the prompt
layer. Each data source is independently bounded. The prompt template then
receives already-capped data, so the total prompt size is the sum of known,
bounded components.

GAP in code-shiniyaya:  No per-source capping in STEP 4. Agent findings, Codex
feedback, and source files are assembled in a single pass with no intermediate
bounds. Even if a total prompt cap exists, intermediate sources can dominate
and crowd out other sources before the total cap is hit.

CONCRETE FIX for SKILL.md (add to the CAP ENFORCEMENT ORDER from Pattern 1):

```
### STEP 4 -- Per-Source Capping Order

Caps are applied at the DATA LAYER (when collecting each source), not at
assembly time. This ensures no single source starves others:

COLLECTION PHASE (before prompt assembly):
1. Agent findings: each capped at MAX_FINDING_CHARS via head-tail truncation
2. Per-dimension: sort by severity, keep top MAX_FINDINGS_PER_DIMENSION
3. Codex feedback: truncated to MAX_CODEX_FEEDBACK_CHARS head-tail
4. Source files: each capped at MAX_SOURCE_FILE_CHARS, max 5 files per dimension
5. Previous round findings (round 2+): capped at 50% of round-1 caps

ASSEMBLY PHASE (after collection):
6. Assemble prompt template with capped sources
7. If total > MAX_VERIFY_PROMPT_CHARS: trim P2, then P1, keep all P0
8. Log trimmed items to STEP4_TRIM_LOG.md with file:line references
```

================================================================================
PATTERN 5: Checksum-Based Idempotency (Skip Unchanged)
================================================================================

Source: auto_dream.py:535-538
```python
checksum = hashlib.md5(text.encode("utf-8")).hexdigest()
tracked = file_map.get(file_name, {})
if tracked.get("checksum") == checksum and tracked_ids:
    continue  # skip -- content unchanged, no re-indexing needed
```

WHY THIS MATTERS:  Between verification rounds, most agent findings don't
change. Without checksums, every round re-processes all content, amplifying
context pressure. With checksums, unchanged findings are skipped at the data
layer and only delta content enters the prompt.

GAP in code-shiniyaya:  STEP 7 bidirectional verification can enter a 2nd round
on dispute. In that 2nd round, the full set of agent findings is re-loaded
and re-evaluated, even though 90% of findings from round 1 are unchanged.
This wastes context on redundant verification.

CONCRETE FIX for SKILL.md STEP 7:

```
### STEP 7 -- Round-2 Delta Verification

Before reassembling the round-2 verification prompt:
1. Compute SHA-256 of each agent finding from round 1
2. Store in session state: `round1Hashes: {finding_id: sha256}`
3. In round 2: re-hash each finding, compare to round1Hashes
4. Unchanged findings: SKIP re-verification (reference by ID only)
5. Changed findings + new findings: full re-verification
6. Assembly: INDEX.md (all findings) + full content (delta only)

This reduces round-2 prompt size by ~80% (typical: 10% of findings change).
```

================================================================================
PATTERN 6: Two-Phase Processing (Learn + Consolidation)
================================================================================

Source: auto_dream.py:264-315
```python
# Phase 1: Learn -- synthesize new memories from recent sessions
result = await apply_auto_dream_plan(...)

# Phase 2: Consolidate -- merge overlapping, prune redundant
dreams_since_consolidation = int(state.get("dreams_since_consolidation", 0)) + 1
consolidate_every = coerce_consolidate_every(config.get("consolidate_every_n_dreams"))
if consolidate_every > 0 and dreams_since_consolidation >= consolidate_every:
    dreams_since_consolidation = 0
    # Run consolidation pass on existing files
    ...
```

WHY THIS MATTERS:  Phase 1 adds new memories (increasing file count). Phase 2
periodically merges and prunes (reducing file count). Without Phase 2, memory
grows monotonically and context pressure increases over time.

GAP in code-shiniyaya:  Each STEP 4 run generates findings that accumulate in
session state. There is no periodic deduplication or consolidation of findings
across runs. Over multiple sessions, similar findings are re-discovered and
re-verified, wasting context.

CONCRETE FIX for high-impact-patterns.md:

```
### 11. Two-Phase Finding Consolidation (from autodream)

Phase 1 (Learn): Collect agent findings in current STEP 4 run.
Phase 2 (Consolidation): Every N=3 finding collection runs, run a dedup pass:
  - Group findings by file:line +/- 5
  - Merge overlapping findings (keep highest severity, most complete root cause)
  - Delete superseded findings
  - Update INDEX.md

Consolidation reduces finding count by 30-50% in typical codebases (same bugs
found by different agents in different sessions).
```

================================================================================
PATTERN 7: Log Rotation with Explicit Entry Cap
================================================================================

Source: auto_dream.py:44, auto_dream.py:1016
```python
AUTO_DREAM_LOG_MAX_ENTRIES = 40
merged_entries = [entry, *existing_entries][:AUTO_DREAM_LOG_MAX_ENTRIES]
```

WHY THIS MATTERS:  Logs grow monotonically. Without a rotation cap, log files
become too large to read into context for debugging. The cap ensures the log
is always readable and always fits in context.

GAP in code-shiniyaya:  Session state files accumulate itemStates without bound.
The pending-{sessionId}.json items array can grow without limit. When restoring
from a long session, reading the full pending file could itself be a context
issue.

CONCRETE FIX for SKILL.md (add to 状态文件 section):

```
### Log Rotation Caps

| Log file | Max entries | Rotation behavior |
|---|---|---|
| .dream-log.md equivalent | 40 entries | Newest-first, drop oldest |
| pending-{id}.json items[] | 100 items | Alert user if exceeded, archive to pending-archive/ |
| session-{id}.json itemStates | 200 entries | Alert user if exceeded |
| ERROR_LOG.md | 50 entries | Newest-first, drop oldest |

Rotation happens at write time. No separate cleanup process needed.
```

================================================================================
PATTERN 8: Threshold-Based Execution Gating
================================================================================

Source: auto_dream.py:686-702
```python
def should_run_auto_dream(last_dream_at, recent_session_count, min_hours, min_sessions):
    if recent_session_count <= 0:
        return False
    if last_dream_at is None:
        return True
    hours_since = (datetime.now(timezone.utc) - last_dream_at).total_seconds() / 3600
    if min_sessions > 0 and recent_session_count >= min_sessions:
        return True
    if min_hours > 0 and hours_since >= min_hours:
        return True
    return False
```

WHY THIS MATTERS:  Execution gating prevents the system from running too
frequently, which (a) prevents redundant work, (b) gives sessions time to
accumulate meaningful content, and (c) prevents context exhaustion from
processing near-empty inputs.

GAP in code-shiniyaya:  STEP 4 runs every time the user pastes Codex feedback,
regardless of how much new content is actually present. If the user pastes
a trivial Codex response ("all looks good"), the full 10-agent verification
still fires.

CONCRETE FIX for SKILL.md STEP 4:

```
### STEP 4 -- Minimum Content Gate

Before launching 10-agent verification, check if the Codex feedback has
meaningful content:

GATE CONDITIONS (ANY one triggers full verification):
- Codex feedback > 200 chars AND contains at least one file:line reference
- Codex explicitly disagrees with CC diagnosis
- Codex proposes alternative fix
- User explicitly requests full verification

SKIP CONDITIONS (reduced verification, 3 agents only):
- Codex feedback < 200 chars
- Codex says "all looks good" / "approved" with no specific evidence
- Codex feedback is purely editorial (spelling, formatting only)

Reduced verification: 3 agents across 3 dimensions (accuracy, code-reuse,
architecture). Other dimensions skipped with notation "SKIPPED: trivial Codex
response." in verification report.
```

================================================================================
PATTERN 9: Overlap Detection for Cross-Reference
================================================================================

Source: auto_dream.py:846-918 (find_orphan_candidates), auto_dream.py:1340-1350
(slug_tokens + score_token_overlap)
```python
def slug_tokens(value):
    return {token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(token) > 1}

def score_token_overlap(current_tokens, sibling_tokens):
    if not current_tokens or not sibling_tokens:
        return 0.0
    return len(current_tokens & sibling_tokens) / max(len(current_tokens), len(sibling_tokens))
```

WHY THIS MATTERS:  Overlap detection finds semantically related content (files,
findings, bugs) by token overlap, without needing embeddings. This is
computationally cheap and works at prompt-assembly time. Autodream uses it to
detect "orphan" memory scopes that may be rename leftovers.

GAP in code-shiniyaya:  STEP 4 has no mechanism to detect if two agent findings
from different dimensions are actually about the same root cause. Without overlap
detection, the same bug reported by 3 agents in 3 dimensions appears as 3
separate findings, consuming 3x the context budget.

CONCRETE FIX for SKILL.md STEP 4:

```
### STEP 4 -- Finding Overlap Detection

Before assembly, run token-overlap analysis on all agent findings:

1. Extract slug tokens from each finding's content (alphanumeric, len>1)
2. Compute pairwise overlap score (intersection / max(len(a), len(b)))
3. Pairs with overlap > 0.6: flag as POTENTIAL DUPLICATE
4. In prompt assembly: group potential duplicates, present once with
   annotation "also reported by agents X, Y in dimensions A, B"
5. Reduce effective finding count by deduplication before capping

This typically reduces finding count by 15-25% before caps are applied.
```

================================================================================
PATTERN 10: Utility Model Pre-Summarization
================================================================================

Source: auto_dream.py:142-149
```python
system_sum = agent.read_prompt("fw.topic_summary.sys.md")
for session in recent_sessions:
    if len(session.transcript) > MAX_SESSION_CHARS:
        msg_sum = agent.read_prompt("fw.topic_summary.msg.md", content=session.transcript)
        summary = await agent.call_utility_model(system=system_sum, message=msg_sum)
        if summary:
            session.transcript = summary.strip()
```

WHY THIS MATTERS:  Before the main LLM call, long content is pre-summarized
by a cheaper/faster utility model. This reduces the input to the main call
while preserving the essential information. The utility model call is made
per-item (not batch), so failure of one summary doesn't block others.

GAP in code-shiniyaya:  Agent findings that exceed MAX_FINDING_CHARS are
truncated (Pattern 2), but truncation loses information. Pre-summarization
would preserve key findings while reducing size.

CONCRETE FIX for anti-hang-v2.md:

```
### Pre-Summarization for Long Agent Outputs

When an agent finding exceeds 2x MAX_FINDING_CHARS (i.e., > 1200 chars),
attempt pre-summarization before truncation:

1. If finding > 1200 chars: send to utility model with prompt:
   "Summarize this agent finding in <= 400 chars. Preserve: file:line
    references, P0/P1/P2 severity, root cause, and fix direction."
2. If utility model succeeds: use summary as the finding content
3. If utility model fails or times out: fall back to head-tail truncation
4. Store both original and summary; reference original by file path

This preserves ~90% of finding information at ~33% of the context cost.
```

================================================================================
## PRIORITY SUMMARY

| Priority | Pattern | Context overflow risk | Implementation complexity |
|---|---|---|---|
| P0 | 1. Explicit MAX_* caps | HIGH -- STEP 4 has zero caps | Low -- add constants + table |
| P0 | 2. Head-tail truncation | HIGH -- no truncation = overflow | Low -- add function spec |
| P0 | 4. Per-source capping order | HIGH -- assembly without bounds | Low -- add ordering rules |
| P1 | 3. Index-content separation | MEDIUM -- structural fix | Medium -- new directory layout |
| P1 | 5. Checksum idempotency | MEDIUM -- wastes context on re-verification | Low -- add hashing logic |
| P1 | 10. Utility pre-summarization | MEDIUM -- lost info from truncation | Medium -- requires model call |
| P2 | 6. Two-phase consolidation | LOW -- accumulation over time | Medium -- new consolidation step |
| P2 | 7. Log rotation caps | LOW -- log file size | Low -- add max entries |
| P2 | 8. Threshold gating | LOW -- redundant verification | Low -- add gate conditions |
| P2 | 9. Overlap detection | LOW -- duplicate findings | Low -- token overlap function |

## INTEGRATION ORDER

If only ONE thing is fixed: Patterns 1+2+4 combined (caps + truncation +
per-source capping) -- these three together form the minimum viable context
overflow defense. They can be added to SKILL.md STEP 4 as a single block
and applied immediately by CC at the next STEP 4 invocation.

Index-content separation (Pattern 3) is the next highest-impact fix because
it structurally prevents the "all findings in one prompt" problem, but
requires a directory layout change and may need user approval.
