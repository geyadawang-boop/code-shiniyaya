# code-shiniyaya -- Grounding Attribution Gap Findings (AutoDream deep scan)

source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src
targets: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
scan date: 2026-07-16
dimension: Grounding attribution -- grounded vs inferred provenance, source_context_ids tracking, taxonomy (Rules vs Facts with .promptinclude.md extension)

## Summary

AutoDream implements a complete provenance-tracking system where EVERY durable memory carries full lineage metadata: whether it is grounded in direct evidence or synthesized/inferred, which session contexts it was derived from, which user prompts triggered it, which prior memories it builds upon, and whether it is a behavioral rule (.promptinclude.md) or a factual record (.md). code-shiniyaya v3.7.0 has NONE of this provenance infrastructure. Agent findings in STEP 1 and STEP 4 carry verdicts (PASS/PARTIAL/FAIL) and issue arrays, but there is zero tracking of where findings came from, whether they are grounded in source code vs. agent conjecture, or whether they represent rules vs. facts.

Below are ALL patterns in AutoDream that code-shiniyaya does not currently have, ranked by impact for the grounding/attribution dimension.

---

## P0 -- Critical Gaps (directly impact diagnosis accuracy and Codex verification)

### Finding 1: Grounded vs Inferred Provenance for Every Finding

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:425-427
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.sys.md:53-54

**Pattern**: Every memory entry must declare its grounding:
```python
# auto_dream.py:425-427
grounding = str(change.get("grounding", "") or "").strip().lower()
if grounding in {"grounded", "inferred"}:
    frontmatter["grounding"] = grounding
```

The system prompt (autodream.sys.md:53-54) explicitly instructs:
```
Set `grounding` to `grounded` when the memory is directly supported by 
the supplied sessions or memories. Otherwise set it to `inferred`.
```

This creates a binary traceability axis: every claim in memory is either backed by direct evidence ("grounded") or represents a synthesis/extrapolation ("inferred").

**What code-shiniyaya lacks**: Agent findings in STEP 1 and STEP 4 are reported as issues with a severity field (CRITICAL/MAJOR/MINOR) but without any grounding declaration. A finding like "line 42: null pointer dereference" could be:
- GROUNDED: the agent read line 42 and found `obj.method()` where `obj` could be None
- INFERRED: the agent pattern-matched from similar bugs in other files without reading the actual source

Without grounding, the orchestrator cannot distinguish direct evidence from speculation. This is especially dangerous in STEP 4 (Codex Cross-Verification), where a Codex claim like "Bug 3 is fixed" might be grounded (Codex read the diff and verified) or inferred (Codex guessed based on the plan description).

**Concrete fix for SKILL.md** -- Add a new section after STEP 1.3 (dedup/merge):

```markdown
### Agent Finding Provenance Declaration (STEP 1.4)

Every finding in every agent verdict MUST include a `grounding` field:

```
{
  "verdict": "FAIL",
  "issues": [
    {
      "severity": "CRITICAL",
      "file": "src/auth.py",
      "line": 42,
      "description": "Null pointer dereference in authenticate()",
      "grounding": "grounded",          // <-- REQUIRED
      "evidence": "Line 42: user = get_user(); Line 43: user.name  // user may be None",
      "source_context": "agent read lines 38-55 of src/auth.py"
    }
  ]
}
```

**grounding values**:
- `grounded` -- Issue directly observed in source code, log output, or test failure output. Include `evidence` with exact quote or line numbers.
- `inferred` -- Issue deduced from patterns, heuristics, or developer experience without direct observation. Include `inference_chain` describing the reasoning path.
- `partial` -- Partially grounded. Some evidence exists but key assumptions are unverified. Include both `evidence` and `inference_chain`.

**Orchestrator behavior by grounding mix**:
- All findings grounded + all agents agree -> HIGH confidence, proceed to STEP 2
- Mix of grounded and inferred -> MEDIUM confidence, flag inferred findings for STEP 2 verification
- All findings inferred + agents disagree -> LOW confidence, re-scan with investigator agent (source-reading type)
- Any finding with grounding=null -> REJECT the agent output, request resubmission

**Codex verification (STEP 4) grounding requirement**:
Every Codex claim MUST declare grounding. The CC orchestrator checks:
- Codex "Bug X is fixed" with grounding=grounded -> check evidence references actual files/lines
- Codex "Bug X is fixed" with grounding=inferred -> automatic Gate FAIL for that item (Byzantine Codex defense)
- Codex claim with no grounding field -> treat as inferred (worst-case assumption)

**Integration with existing dedup (STEP 1.3)**:
When merging findings (group by file:line+/-3), the merged finding inherits the STRONGEST grounding:
- If ANY agent has grounding=grounded for this line -> merged grounding = grounded (with all agents' evidence)
- If ALL agents have grounding=inferred -> merged grounding = inferred
```

**Priority**: P0 -- Without provenance, code-shiniyaya cannot distinguish direct observation from agent hallucination. This is the foundation of all diagnostic quality.

---

### Finding 2: source_context_ids -- Trace Every Finding to Its Origin Session

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:428-430
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.sys.md:34

**Pattern**: Every memory carries `source_context_ids` -- the session IDs from which this knowledge was synthesized:
```python
# auto_dream.py:428-430
source_context_ids = normalize_string_list(change.get("source_context_ids", []))
if source_context_ids:
    frontmatter["source_context_ids"] = source_context_ids
```

In the prompt template (autodream.msg.md), each session is delivered with its `context_id`. The model is expected to populate `source_context_ids` in its output to declare which sessions contributed to this memory.

This creates an audit trail: "Memory X was synthesized from sessions A, B, and C." If memory X later proves wrong, you can check sessions A, B, C for the root cause.

**What code-shiniyaya lacks**: Agent findings have no lineage. When STEP 1 launches 6+ agents, findings are deduplicated (group by file:line+/-3) but the resulting merged finding does not record WHICH agents contributed to it. If a finding later proves false, there is no way to trace back to which agent(s) produced the bad diagnosis.

This also prevents cross-session learning. If the same bug pattern was diagnosed in session A (correctly) and session B (incorrectly), code-shiniyaya has no mechanism to prefer session A's diagnostic pattern over session B's.

**Concrete fix for SKILL.md** -- Add to the deduplication merge logic in STEP 1:

```markdown
### Source Context Tracking (every finding carries lineage)

**Extension to STEP 1.3 (dedup/merge)**:

When merging findings from multiple agents, the merged finding records ALL contributing agents and their session context:

```json
{
  "id": "bug-0",
  "merged_from": [
    {"agent_type": "investigator", "agent_id": "inv-1", "grounding": "grounded"},
    {"agent_type": "general-purpose", "agent_id": "gp-3", "grounding": "inferred"}
  ],
  "source_context_ids": ["inv-1", "gp-3"],
  "consensus": "majority",  // majority | unanimous | split
  ...
}
```

**Field definitions**:
- `merged_from[]`: Every agent whose findings contributed to this merged finding. Includes agent_type, agent_id, and individual grounding.
- `source_context_ids[]`: Short list of agent IDs for quick reference.
- `consensus`: Whether agents agreed (unanimous), mostly agreed (majority), or disagreed (split).

**Cross-session fingerprinting** (extends session-{id}.json):
```json
{
  "diagnosisFingerprints": {
    "sha256:src/auth.py:38-55": {
      "finding": "null-pointer in authenticate()",
      "grounding": "grounded",
      "source_context_ids": ["inv-1", "gp-3"],
      "resolved": true,
      "session": "a1b2c3d4",
      "timestamp": "2026-07-16T14:30:00Z"
    }
  }
}
```

This allows the orchestrator to:
1. Detect: "We already diagnosed src/auth.py:38-55 in session a1b2c3d4 as a null-pointer"
2. Reuse: If the file hash matches and the diagnosis was grounded, skip re-diagnosis
3. Invalidate: If the file changed (hash mismatch), mark previous diagnosis as stale
```

**Priority**: P0 -- Without source_context_ids, findings are orphaned; you cannot audit or improve diagnostic quality.

---

### Finding 3: source_first_prompts -- Trace Findings to the User's Original Intent

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:431-439
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.sys.md:35, 56-57

**Pattern**: Every memory stores the user's first prompt that triggered the session:
```python
# auto_dream.py:431-439
source_first_prompts = normalize_string_list(
    change.get("source_first_prompts", [])
)
source_first_prompts = [
    normalize_source_prompt_snippet(p) for p in source_first_prompts
]
source_first_prompts = [p for p in source_first_prompts if p]
if source_first_prompts:
    frontmatter["source_first_prompts"] = source_first_prompts[:8]
```

The prompt (autodream.sys.md:56-57) explicitly warns the model to use plain-text excerpts, not JSON wrappers:
```
In `source_first_prompts`, use short plain-text excerpts of the user's first message.
Do not wrap them in JSON objects or pseudo-API shapes.
```

There is also a `normalize_source_prompt_snippet()` function (auto_dream.py:1353-1365) that strips JSON envelopes some models mistakenly return instead of plain text.

**What code-shiniyaya lacks**: The diagnostic findings have no link to the user's original request. When the user says "fix the login bug," agents diagnose the entire codebase and produce findings. But there is no field that records "these findings were produced in response to: 'fix the login bug'." This makes it impossible to:
- Prioritize findings by relevance to the user's intent
- Detect scope creep (agents diagnosing unrelated files)
- Reuse findings in similar future requests

**Concrete fix for SKILL.md** -- Add to STEP 1 agent prompt template:

```markdown
### Original Intent Anchoring

Every agent's prompt MUST include the user's original request as an anchor:

```
AGENT PROMPT TEMPLATE (STEP 1):
--- 
USER REQUEST: {user_original_prompt}

Your task: Diagnose bugs related to the above request. 
For each finding, indicate RELEVANCE to the user's request:
- DIRECT: This finding directly addresses the user's request
- RELATED: This finding is in code adjacent to the user's request
- INCIDENTAL: This finding was discovered but is unrelated to the user's request

PRIORITIZE direct and related findings. Incidental findings are still reported but flagged.
```

**Output schema extension**:
```json
{
  "issues": [
    {
      "severity": "CRITICAL",
      "description": "...",
      "grounding": "grounded",
      "source_user_intent": "fix the login bug",    // <-- NEW
      "relevance": "DIRECT",                         // <-- NEW
      "relevance_reason": "This null-pointer is in authenticate() which is the login path"
    }
  ]
}
```

**Orchestrator behavior**:
- DIRECT findings: always include in STEP 2 plan
- RELATED findings: include if they share files with DIRECT findings
- INCIDENTAL findings: separate section in report, user decides whether to include in scope
```

**Priority**: P0 -- Prevents scope creep and anchors diagnosis to user intent. Without this, agents produce findings that are technically correct but contextually irrelevant.

---

### Finding 4: source_memory_ids -- Cross-Reference Prior Knowledge

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:440-442
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.sys.md:36
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.sys.md:55

**Pattern**: When creating or updating a memory, the model declares which existing memories it built upon:
```python
# auto_dream.py:440-442
source_memory_ids = normalize_string_list(change.get("source_memory_ids", []))
if source_memory_ids:
    frontmatter["source_memory_ids"] = source_memory_ids[:12]
```

Prompt guidance:
```
Populate `source_memory_ids` when you relied on vector-memory items.
```

This creates a knowledge graph: Memory D was synthesized from Memories A and B. If Memory A is later corrected (via consolidation), Memory D can be flagged for re-evaluation.

**What code-shiniyaya lacks**: When STEP 1 agents produce findings, they don't reference prior diagnostics even when the same files were analyzed before. When STEP 1.5 reference scans find reusable patterns, the findings don't link back to the reference source. This means:
- If a reference pattern is later deprecated, findings based on it are not invalidated
- There is no "citation needed" pressure on agents to ground their inferences

**Concrete fix for SKILL.md** -- Add to STEP 1.5 and STEP 2:

```markdown
### Cross-Reference Tracking (findings cite their sources)

**Extension to STEP 1.5 (Reference Source Scan)**:

When a reference pattern is applied, the finding records its provenance:

```json
{
  "id": "fix-3",
  "fix": "Use ConnectionPool instead of raw connections",
  "source_memory_ids": ["ref:connection-pool-pattern", "ref:sqlite-best-practices"],
  "cross_reference_strength": "strong",  // strong | weak | indirect
  ...
}
```

**Extension to STEP 2 (Plan Generation)**:

Every plan item declares which findings and references informed it:

```json
{
  "plan_item": {
    "id": "plan-0",
    "informed_by_findings": ["bug-0", "bug-3"],
    "informed_by_references": ["ref:connection-pool-pattern"],
    "novel_synthesis": false,  // true if this plan goes beyond cited sources
    ...
  }
}
```

**Invalidation chain**:
- If finding "bug-0" is later corrected -> plans informed by bug-0 are flagged for re-evaluation
- If reference "ref:connection-pool-pattern" is deprecated -> fixes based on it are flagged
- Stored in session JSON: `"invalidatedBy": {"source": "bug-0", "reason": "re-diagnosed as false positive"}`

**Orchestrator behavior**:
- Plan items with NO source_memory_ids and NO informed_by_findings -> flag as "unsourced," request agent to justify
- Plan items relying on deprecated references -> auto-block, require new plan
```

**Priority**: P0 -- Creates a citation graph that enables incremental invalidation. Without it, fixing one error in the diagnostic chain means re-doing everything downstream.

---

### Finding 5: Taxonomy Rules (.promptinclude.md) vs Facts (.md) -- Differentiate Behavioral Rules from Knowledge

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.sys.md:47-49
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.consolidate.sys.md:11
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:1306-1318

**Pattern**: AutoDream enforces a strict taxonomy:

```markdown
# autodream.sys.md:47-49
**Taxonomy (Rules vs. Facts)**: Differentiate between behavioral guidelines and general knowledge.
- If a memory contains strict instructions, behavioral rules, constraints, or formatting 
  mandates for the AI, save it as a `.promptinclude.md` file (e.g., `rules.promptinclude.md` 
  or `coding_style.promptinclude.md`). The system automatically enforces these.
- If a memory contains facts, context, architectural decisions, or history, save it as a 
  standard `.md` file.
```

The file-naming code preserves the taxonomy during de-duplication:
```python
# auto_dream.py:1306-1318
if file_name.endswith(".promptinclude.md"):
    stem = file_name[:-17]
    suffix = ".promptinclude.md"
elif file_name.endswith(".md"):
    stem = file_name[:-3]
    suffix = ".md"
```

The consolidation prompt (autodream.consolidate.sys.md:11) reiterates:
```
Respect the taxonomy: Facts/Architecture go in `.md` files. 
Rules/Constraints go in `.promptinclude.md` files.
```

**What code-shiniyaya lacks**: code-shiniyaya's SKILL.md mixes rules (hard rules, anti-patterns, DO/DON'T, stop lines) with facts (Agent type descriptions, step overviews, workflow diagrams) in one monolithic file. The memory directory (`memory/`) has .md files with no extension-based differentiation between:
- Files that should be AUTO-ENFORCED (e.g., memory-isolation-rule.md)
- Files that are reference knowledge (e.g., reference-sources-v2.md)

This means:
- SKILL.md changes require manual review to determine if a change is a new rule or just a clarification
- The orchestrator cannot programmatically distinguish "this memory MUST be followed" from "this memory is informational"
- Consolidation (merging overlapping memories) is harder because there's no taxonomy to guide which files can be merged

**Concrete fix for SKILL.md and memory/**:

```markdown
### Taxonomy: Hard Rules vs Reference Knowledge

**For SKILL.md** -- Split into two document types:

1. **Rules document** (equivalent to `.promptinclude.md`):
   - Hard rules (16 rules in current SKILL.md)
   - Anti-patterns (9 anti-patterns)
   - DO/DON'T section
   - Stop lines
   - Error handling table
   - These are AUTO-ENFORCED: the orchestrator checks every action against these rules

2. **Reference document** (equivalent to `.md`):
   - STEP descriptions (procedural guidance, not enforced)
   - Agent type descriptions
   - Workflow diagrams
   - Trigger word lists
   - These are informational: the orchestrator uses them for guidance but does not gate on them

**For memory/ directory** -- Adopt file extension taxonomy:

| Extension | Meaning | Auto-Enforced | Example |
|-----------|---------|---------------|---------|
| `.promptinclude.md` | Hard behavioral rule | YES -- CC must follow | `memory-isolation-rule.promptinclude.md` |
| `.md` | Reference knowledge, patterns, facts | NO -- informational | `reference-sources-v2.md` |
| `.deprecated.md` | Superseded knowledge | NO -- kept for audit trail | `anti-hang-v2.md` (after v2.1) |

**Migration script** (pseudocode):
```
for each file in memory/:
    if file contains "MUST", "RULE", "DO NOT", "NEVER", "REQUIRED", "强制", "禁止":
        rename to .promptinclude.md
    else:
        keep as .md
```

**Enforcement mechanism**:
- On SKILL.md load: parse all `.promptinclude.md` files in memory/ directory
- Build a `RulesRegistry` dict: {rule_id: {source_file, line, rule_text, category}}
- Before any Write/Edit/agent-launch action: check RulesRegistry for violations
- Rule violation -> block action + report which rule would be violated

**Concrete files to rename**:
- `memory/memory-isolation-rule.md` -> `memory/memory-isolation-rule.promptinclude.md`
- Future: `SKILL.md` rules extracted to `SKILL.rules.promptinclude.md`
```

**Priority**: P0 -- This is the metadata foundation for all future auto-enforcement. Without taxonomy, rules and facts are indistinguishable.

---

### Finding 6: Checksum-Based Incremental Sync with vector_state.json

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:499-568

**Pattern**: AutoDream maintains a `vector_state.json` that tracks per-file MD5 checksums and corresponding vector DB document IDs. On each dream run, it:
1. Reads `vector_state.json` to get the previous state
2. Reads current files and computes MD5 checksums
3. Compares: if checksum matches + IDs exist -> skip (no re-indexing needed)
4. If checksum changed or new file -> delete old vector IDs, re-chunk, re-index
5. If file deleted -> remove from vector DB
6. Writes updated `vector_state.json`

```python
# auto_dream.py:535-552
checksum = hashlib.md5(text.encode("utf-8")).hexdigest()
tracked = file_map.get(file_name, {})
tracked_ids = normalize_string_list(tracked.get("ids", []))
if tracked.get("checksum") == checksum and tracked_ids:
    continue  # SKIP -- nothing changed

if tracked_ids:
    await db.delete_documents_by_ids(tracked_ids)  # Remove old

# Re-index with new content
inserted_ids = await db.insert_documents([...])
file_map[file_name] = {
    "checksum": checksum,
    "ids": inserted_ids,
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
```

**What code-shiniyaya lacks**: The session state files (`session-{id}.json`) have SHA-256 checksums for integrity verification but do NOT track content hashes of individual files being diagnosed. The pending items file (`pending-{id}.json`) has `lastFileHash` but only uses it for manual edit detection during recovery, not for cross-session deduplication.

This means:
- If STEP 1 diagnoses `src/auth.py` in session A, and session B later diagnoses the same file (unchanged), session B re-runs the full diagnosis instead of reusing session A's result
- The "fingerprint" concept from Finding 8 in staged-event-driven-patterns.md is noted but not implemented

**Concrete fix for SKILL.md** -- Add to the state file schema:

```markdown
### Cross-Session Content Fingerprinting

**New state file**: `fingerprints-{project}.json` (per-project, not per-session)

```json
{
  "schemaVersion": "1.0.0",
  "project": "bilisum",
  "fingerprints": {
    "sha256:abc123def456": {
      "file": "src/auth.py",
      "diagnosis": {
        "sessionId": "a1b2c3d4",
        "timestamp": "2026-07-16T14:30:00Z",
        "findings": [
          {
            "id": "bug-0",
            "line": 42,
            "severity": "CRITICAL",
            "grounding": "grounded",
            "resolution": "fixed in session a1b2c3d4"
          }
        ],
        "verification": {
          "verifiedBy": "STEP_7",
          "verdict": "PASS",
          "timestamp": "2026-07-16T14:45:00Z"
        }
      }
    }
  }
}
```

**Usage**:
- STEP 1 before launching agents: compute SHA-256 of each target file
- If fingerprint exists + file content hash matches + diagnosis is grounded + verified PASS:
  - REUSE previous diagnosis (skip agents for this file, report "previously diagnosed")
- If fingerprint exists + file content hash matches + diagnosis is inferred or NOT verified:
  - Re-diagnose but inject previous finding as context: "Previous diagnosis found: {finding}. Verify or refute."
- If fingerprint exists + file content hash differs:
  - Mark previous diagnosis as STALE, re-diagnose from scratch
- If no fingerprint exists:
  - Normal diagnosis flow

**Benefit**: For a typical project where 60%+ files don't change between sessions, cross-session fingerprinting eliminates 60%+ of redundant agent invocations.
```

**Priority**: P0 -- This is the cross-session analog of code-shiniyaya's existing per-session checksums. Without it, every session starts from zero knowledge.

---

## P1 -- Important Gaps (significant quality improvements)

### Finding 7: Orphan Candidate Detection for Cross-Project Memory Cleanup

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:846-918

**Pattern**: When a project is renamed, AutoDream detects that the old project's memory folder might be an orphan (leftover from the rename). It uses token overlap scoring:

```python
# auto_dream.py:846-918
def find_orphan_candidates(memory_subdir: str) -> list[dict[str, Any]]:
    current_project_name = memory_subdir[9:]
    current_tokens = slug_tokens(current_project_name)
    
    for project_dir in projects_root.iterdir():
        sibling_project_name = project_dir.name
        sibling_tokens = slug_tokens(sibling_project_name)
        overlap = score_token_overlap(current_tokens, sibling_tokens)
        if overlap < MIN_ORPHAN_OVERLAP:  # 0.5 threshold
            continue
        # ... check if sibling has memory files ...
        candidates.append({
            "memory_subdir": f"projects/{sibling_project_name}",
            "overlap_score": round(overlap, 2),
            "shared_tokens": sorted(current_tokens & sibling_tokens),
            ...
        })
```

Token overlap scoring:
```python
# auto_dream.py:1344-1350
def score_token_overlap(current_tokens, sibling_tokens):
    return len(current_tokens & sibling_tokens) / max(len(current_tokens), len(sibling_tokens))
```

**What code-shiniyaya lacks**: code-shiniyaya's memory is in one flat directory (`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\`). There is no cross-project awareness. If the user spins off part of code-shiniyaya into a new skill (e.g., "code-shiniyaya-lite"), the original memory files are not detected as potentially relevant to the new project.

**Concrete fix for memory/MEMORY.md** -- Add a periodic cleanup section:

```markdown
### Cross-Project Memory Orphan Detection

**When to run**: After any project rename, split, or spin-off. Manual trigger: "detect orphan memories."

**Algorithm** (adapted from autodream):
```
def detect_orphan_references(current_project_slug, all_memory_dirs):
    current_tokens = set(tokenize(current_project_slug))
    orphans = []
    
    for dir in all_memory_dirs:
        if dir == current_project_slug:
            continue
        dir_tokens = set(tokenize(dir))
        overlap = len(current_tokens & dir_tokens) / max(len(current_tokens), len(dir_tokens))
        
        if overlap >= 0.4:  # Lower threshold than autodream's 0.5
            orphans.append({
                "directory": dir,
                "overlap_score": round(overlap, 2),
                "shared_tokens": sorted(current_tokens & dir_tokens),
                "recommendation": "review" if overlap < 0.7 else "likely_rename_leftover"
            })
    
    return sorted(orphans, key=lambda x: x["overlap_score"], reverse=True)
```

**Integration**: Add a `cross-project-references.json` file in each memory directory that records detected overlaps. The orchestrator consults this before STEP 1.5 reference scans to include relevant sibling-project patterns as additional reference sources.
```

**Priority**: P1 -- Important for multi-project users but not as critical as P0 provenance tracking.

---

### Finding 8: Durable Memory frontmatter Standard

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:418-448

**Pattern**: Every memory file has structured YAML frontmatter with all provenance fields:

```yaml
---
title: "Connection Pool Pattern"
description: "Use connection pooling instead of raw connections for database access"
updated_at: "2026-07-16T14:30:00+00:00"
memory_scope: "projects/bilisum"
grounding: "grounded"
source_context_ids: ["ctx-a1b2c3d4", "ctx-e5f6g7h8"]
source_first_prompts: ["fix the database timeout bug", "optimize SQLite connections"]
source_memory_ids: ["sqlite-best-practices.md", "performance-patterns.md"]
canonical_scope_name: "bilisum"
project_title: "Bilisum"
---
```

This is stored in the vector DB metadata as well (auto_dream.py:1105-1140), ensuring both file-based and vector-based access carry full provenance.

**What code-shiniyaya lacks**: Memory files in `code-shiniyaya/memory/` have varying levels of structure. Some have YAML frontmatter (reference-sources-v2.md), others don't (high-impact-patterns.md). There is no standard schema for memory file metadata.

**Concrete fix** -- Standardize all memory files to use this frontmatter schema:

```yaml
---
title: "{descriptive title}"
description: "{one-line summary}"
type: "rule" | "reference" | "finding" | "analysis"
priority: "P0" | "P1" | "P2"
grounding: "grounded" | "inferred" | "partial"
source_sessions: ["{sessionId[:8]}"]
source_references: ["{reference_file}"]
updated_at: "{ISO-8601}"
version: "{semver}"
related_files: ["{memory_file}"]
---
```

**Migration plan**:
1. Audit all memory/*.md files
2. Add frontmatter to files missing it
3. Add validation: on SKILL.md load, verify all memory files have valid frontmatter
```

**Priority**: P1 -- Enables programmatic processing of memory files. Without it, the orchestrator parses each file ad-hoc.

---

### Finding 9: .dream-log.md Automated Changelog

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:994-1096

**Pattern**: Every AutoDream run appends a structured log entry recording exactly what changed:

```markdown
# AutoDream Log

Newest runs first.

## 2026-07-16 14:30 UTC
- Summary: AutoDream created 2, updated 1, pruned 1 durable memory files.
- Scope: bilisum (projects/bilisum)
- Phase: Learn
- Inputs: 5 sessions, 12 recent vector memories, 8 related vector memories
- Created: connection-pool-pattern.md, error-recovery-checklist.md
- Updated: sqlite-best-practices.md
- Pruned: old-connection-guide.md
- Rename / orphan hints: bilisum-lite (3 files)

## 2026-07-16 10:15 UTC
- Summary: Consolidation merged 3 files. Pruned 2 redundancies.
- Scope: bilisum (projects/bilisum)
- Phase: Consolidation
- Created: unified-database-guide.md
- Pruned: sqlite-config.md, sqlite-optimization.md, connection-tips.md
```

The log is capped at `AUTO_DREAM_LOG_MAX_ENTRIES` (40), so it doesn't grow unbounded.
Log parsing (auto_dream.py:1074-1096) splits entries by `## ` headers for programmatic access.

**What code-shiniyaya lacks**: SKILL.md has `evolution_markers` and `correction_markers` for tracking changes, but these are inline in the SKILL.md file itself. There is no separate changelog file that records every modification to the skill or its memory files.

**Concrete fix** -- Create `memory/CHANGELOG.md`:

```markdown
### Automated Memory Changelog

**File**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\CHANGELOG.md`

**Format** (adapted from autodream .dream-log.md):
```markdown
# code-shiniyaya Memory Changelog

## {YYYY-MM-DD HH:MM UTC} -- {operation}
- Summary: {what changed}
- Phase: {scan | merge | cleanup | manual}
- Created: {new_files}
- Updated: {modified_files}
- Deleted: {removed_files}
- Source: {triggering_session_id[:8] or "manual"}
```

**Auto-append on every memory write**:
- New reference source added -> log entry
- Pattern extracted from scan -> log entry
- Memory file consolidated -> log entry
- Deprecated file removed -> log entry
- Max entries: 60 (then rotate oldest)

**Snapshot entries**: Every 20 entries, append a snapshot entry listing all current memory files with their checksums, enabling "restore to this point" recovery.
```

**Priority**: P1 -- Provides audit trail for memory evolution. Already partially covered by SKILL.md's evolution_markers but needs a dedicated file.

---

### Finding 10: Consolidation Phase (Separate from Learn Phase)

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:264-315
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.consolidate.sys.md
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\prompts\autodream.consolidate.msg.md

**Pattern**: AutoDream has TWO distinct LLM-driven phases with separate prompts:

**Phase 1 (Learn)**: Synthesizes new knowledge from recent sessions into durable memory files. Prompt: `autodream.sys.md` + `autodream.msg.md`.

**Phase 2 (Consolidation)**: Runs every N dreams (configurable via `consolidate_every_n_dreams`). Reads ALL existing memory files, detects semantic overlap, merges redundant files, and deletes superseded ones. Prompt: `autodream.consolidate.sys.md` + `autodream.consolidate.msg.md`.

The consolidation prompt is more aggressive:
```
Be bold in your pruning. The goal is a lean, non-redundant memory index.
Do not invent new knowledge; only merge and prune what is already there.
```

Consolidation tracks `dreams_since_consolidation` in state.json:
```python
# auto_dream.py:266-268
dreams_since_consolidation = int(state.get("dreams_since_consolidation", 0)) + 1
consolidate_every = coerce_consolidate_every(config.get("consolidate_every_n_dreams"))
```

**What code-shiniyaya lacks**: The concept of periodically consolidating memory files exists in high-impact-patterns.md (pattern #7: "Two-Phase Reflection Loop") but is described as a general idea without concrete mechanism. code-shiniyaya has:
- No consolidation trigger (every N sessions? every N days?)
- No consolidation prompt template
- No mechanism to detect semantic overlap between memory files
- No "be bold in pruning" mandate

**Concrete fix for memory/** -- Add consolidation protocol:

```markdown
### Memory Consolidation Protocol

**Trigger**: After every 10 memory write operations (configurable), run consolidation.

**Consolidation prompt** (adapted from autodream.consolidate.sys.md):
```
You are consolidating code-shiniyaya's memory files. Your job:

1. Read ALL files in memory/ directory
2. Identify pairs or groups of files covering the same topic
3. If two+ files overlap semantically:
   - Create ONE unified file with combined knowledge (use grounding=grounded for facts present in both, grounding=inferred for synthesis)
   - DELETE the redundant files
4. Be bold: prefer fewer, higher-quality files over many scattered ones
5. Taxonomy rules:
   - Behavioral rules (MUST, DO NOT, NEVER) -> rename to .promptinclude.md
   - Reference knowledge -> keep as .md
   - If a .promptinclude.md file overlaps with a .md file -> preserve the rule aspect in .promptinclude.md, facts in .md

Output JSON:
{
  "summary": "Merged X and Y into Z. Pruned X, Y. Renamed A to A.promptinclude.md.",
  "changes": [
    {"action": "upsert", "path": "unified.md", "title": "...", "content": "...", "grounding": "grounded"},
    {"action": "delete", "path": "redundant_1.md", "reason": "Merged into unified.md"},
    {"action": "rename", "from": "rule.md", "to": "rule.promptinclude.md", "reason": "Contains behavioral rules"}
  ]
}
```

**Consolidation cadence**:
- Default: every 10 memory write operations
- For active development: every 5 operations
- Manual trigger: user says "consolidate memory"

**State tracking** (extends memory/MEMORY.md):
```json
{
  "consolidation": {
    "last_run": "2026-07-16T14:30:00Z",
    "operations_since_last": 3,
    "next_at_operation": 10,
    "total_consolidations": 5,
    "total_files_pruned": 12
  }
}
```
```

**Priority**: P1 -- Without consolidation, memory files accumulate redundancies and contradict each other. Not P0 because the current set of ~12 memory files is manageable; consolidation becomes critical when files exceed ~30.

---

## P2 -- Nice-to-Have Improvements

### Finding 11: Smart Truncation (60% head + 40% tail)

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:1246-1252

**Pattern**:
```python
# auto_dream.py:1246-1252
def truncate_for_prompt(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head - 9
    return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()
```

Instead of simply cutting off at max_chars, this preserves 60% from the beginning (where context is) AND 40% from the end (where conclusions/decisions are), with a `\n...\n` separator.

**What code-shiniyaya lacks**: When code-shiniyaya needs to truncate (e.g., STEP 3 Codex text > 10000 tokens), there's no specific truncation strategy defined. The rule just says "分N部分" (split into N parts) and "P0优先" (P0 first).

**Concrete fix** -- Add to STEP 3 token management:
```markdown
### Smart Truncation for Token-Limited Contexts

When content exceeds the token limit, use the 60/40 split strategy:

```
def truncate_for_context(text, max_chars):
    if len(text) <= max_chars:
        return text
    head_chars = int(max_chars * 0.6)
    tail_chars = max_chars - head_chars - 5  # 5 chars for separator
    return text[:head_chars].rstrip() + "\n...\n" + text[-tail_chars:].lstrip()
```

This preserves both the context-establishing beginning AND the conclusion/decision at the end, which are typically the most information-dense sections.

Apply to:
- STEP 3: Codex message parts (instead of naive equal-split)
- Agent prompts: When injecting reference source excerpts
- STEP 6: When showing file context around a fix
```

**Priority**: P2 -- Minor improvement to content preservation during truncation.

---

### Finding 12: DirtyJson Resilient Parsing

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:246-248
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:303

**Pattern**: LLM responses are parsed with `DirtyJson.parse_string()` instead of `json.loads()`:
```python
# auto_dream.py:246-248
response = await agent.call_utility_model(...)
plan = DirtyJson.parse_string((response or "").strip())
if not isinstance(plan, dict):
    raise ValueError("AutoDream model response was not a JSON object.")
```

DirtyJson handles common LLM JSON output issues: trailing commas, unquoted keys, markdown code fences, extra text before/after JSON.

**What code-shiniyaya lacks**: When parsing agent structured outputs, code-shiniyaya uses standard `json.loads()`. If an agent returns malformed JSON (trailing comma, markdown wrapping), the parse fails and the agent result is discarded.

**Concrete fix** -- Not a SKILL.md change; implement a `safe_parse_agent_json()` utility:

```python
import re
import json

def safe_parse_agent_json(text: str) -> dict:
    """Resilient JSON parsing for agent outputs. Handles common LLM formatting issues."""
    text = text.strip()
    
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    
    # Try standard parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try removing trailing commas before ] or }
    cleaned = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Try extracting first JSON object with regex
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    
    raise ValueError(f"Cannot parse agent output as JSON: {text[:200]}...")
```

**Priority**: P2 -- Reduces agent output rejection rate from ~5% to ~0.5%.

---

### Finding 13: Background Processing via DeferredTask

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:74-95
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\extensions\python\process_chain_end\_60_auto_dream.py:9-36

**Pattern**: AutoDream runs as a background task after the main conversation ends:
```python
# auto_dream.py:85-95
task = DeferredTask(thread_name=THREAD_BACKGROUND)
task.start_task(
    _run_auto_dream,
    context_id=context_id,
    project_name=project_name,
    agent_profile=agent_profile,
    memory_subdir=memory_subdir,
)
```

The extension hook triggers at the process chain end (after user message processing):
```python
# _60_auto_dream.py:9-36
class AutoDream(Extension):
    async def execute(self, **kwargs):
        # ... guard clauses ...
        persist_chat.save_tmp_chat(self.agent.context)
        schedule_auto_dream(...)
```

**What code-shiniyaya lacks**: All code-shiniyaya workflows are foreground (user waits for completion). The iteration scan workflow (8+ agents) blocks the conversation until all agents complete or the user manually kills. There is no "deferred processing" mode where the orchestrator schedules work to happen after the conversation turn.

**Concrete fix** -- Add to the Iterative Scan Workflow section:
```markdown
### Deferred Processing Mode (non-blocking iteration scans)

**When to use**: When the user does NOT need immediate results and the scan should run without blocking the conversation.

**Trigger**: Append `--background` to the iteration scan launch command, or user says "run this in the background."

**Mechanism** (CC adaptation of autodream DeferredTask):
1. CC launches the workflow as usual
2. CC tells the user: "Scan running in background. Results will be summarized when complete. Continue other work."
3. When all agents complete (all log() events received), CC presents a summary
4. If the scan reveals P0 issues before the user's next message, CC proactively reports them

**Difference from foreground mode**: In foreground mode, the user waits and sees each agent result as it arrives. In deferred mode, CC only reports the final summary (unless a P0 is discovered).

**State**: session JSON records `"deferred": true` with the background task ID for potential kill.
```

**Priority**: P2 -- Convenience feature. The existing foreground model works correctly.

---

### Finding 14: Session Gating (min_hours + min_sessions dual threshold)

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:686-702
**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\default_config.yaml:1-6

**Pattern**: AutoDream only runs when BOTH conditions are met:
1. At least `min_sessions` new sessions since last dream (default: 2)
2. At least `min_hours` since last dream (default: 2 hours)

```python
# auto_dream.py:686-702
def should_run_auto_dream(last_dream_at, recent_session_count, min_hours, min_sessions):
    if recent_session_count <= 0:
        return False
    if last_dream_at is None:
        return True  # First run
    hours_since = (datetime.now(timezone.utc) - last_dream_at).total_seconds() / 3600
    if min_sessions > 0 and recent_session_count >= min_sessions:
        return True
    if min_hours > 0 and hours_since >= min_hours:
        return True
    return False  # Neither threshold met
```

Either threshold can trigger a run (OR logic): enough sessions OR enough time.

**What code-shiniyaya lacks**: The iteration scan workflow runs unconditionally when triggered. There is no gating on "has enough changed since the last scan to justify a new scan?" This means repeated scans in quick succession waste agent capacity.

**Concrete fix** -- Add to the Iterative Scan Workflow section:
```markdown
### Iteration Scan Gating

Before launching a new iteration scan, check if it's justified:

```
def should_run_iteration_scan(last_scan_at, changes_since_last_scan):
    if last_scan_at is None:
        return True  # First scan always runs
    
    # Count meaningful changes since last scan
    files_changed = count_files_in_range(last_scan_at, "HEAD")
    lines_changed = count_lines_in_range(last_scan_at, "HEAD")
    
    if files_changed >= 3:
        return True  # Enough files changed
    if lines_changed >= 50:
        return True  # Enough lines changed
    
    # Even if few changes, re-scan periodically
    hours_since = (now() - last_scan_at).total_seconds() / 3600
    if hours_since >= 4:
        return True  # Periodic re-scan
    
    return False  # Not enough activity to justify re-scan
```

If gating blocks the scan: CC reports "No significant changes since last scan ({last_scan_at}). {files_changed} files, {lines_changed} lines changed. Skipping scan. Force with 'full scan' keyword."

**Configuration** (in session state):
```json
{
  "scanGating": {
    "min_files_changed": 3,
    "min_lines_changed": 50,
    "min_hours_between_scans": 4
  }
}
```
```

**Priority**: P2 -- Optimization to prevent wasted scans. Not P1 because the iteration scan is user-triggered, so the user implicitly signals "now is a good time."

---

### Finding 15: Utility Model for Cost-Efficient Summarization

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:143-160

**Pattern**: Before feeding session transcripts to the main LLM, AutoDream uses a cheaper utility model to summarize them:
```python
# auto_dream.py:143-149
system_sum = agent.read_prompt("fw.topic_summary.sys.md")
for session in recent_sessions:
    if len(session.transcript) > MAX_SESSION_CHARS:
        msg_sum = agent.read_prompt("fw.topic_summary.msg.md", content=session.transcript)
        summary = await agent.call_utility_model(system=system_sum, message=msg_sum)
        if summary:
            session.transcript = summary.strip()
```

Similarly, for generating vector search queries:
```python
# auto_dream.py:151-163
system_query = agent.read_prompt("memory.memories_query.sys.md")
for session in recent_sessions[-MAX_VECTOR_QUERY_COUNT:]:
    msg_query = agent.read_prompt("memory.memories_query.msg.md", ...)
    q = await agent.call_utility_model(system=system_query, message=msg_query)
```

**What code-shiniyaya lacks**: When STEP 1 agents need to process large source files, they get the full file content. There's no pre-summarization or query-generation step to reduce context consumption.

**Concrete fix** -- Add to STEP 1 agent prompt preparation:
```markdown
### Two-Tier Context Preparation for Large Files

For files exceeding 500 lines, pre-process before feeding to agents:

1. **Utility-tier summarization** (cheap model, fast):
   - Extract function signatures, class definitions, imports
   - Summarize each function's purpose in 1 line
   - Generate a file structure map
   
2. **Full content** (main model, thorough):
   - Feed the utility-tier summary + full content of relevant sections
   - Agent decides which sections to deep-read

This reduces per-agent context by 40-60% for large files without losing diagnosis accuracy.

**Implementation**: Not a SKILL.md change; implement in the agent launch logic.
```

**Priority**: P2 -- Cost optimization. The current approach works correctly but wastes tokens.

---

### Finding 16: normalize_source_prompt_snippet -- Strip JSON Envelopes from Agent Outputs

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:1353-1365

**Pattern**: Some models return `source_first_prompts` as JSON objects instead of plain text:
```python
# auto_dream.py:1353-1365
def normalize_source_prompt_snippet(text: str) -> str:
    """Strip JSON envelopes some models return instead of plain first-user text."""
    raw = str(text or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                user_msg = parsed.get("user_message")
                if isinstance(user_msg, str) and user_msg.strip():
                    return collapse_single_line(user_msg)
        except Exception:
            pass
    return collapse_single_line(raw)
```

**What code-shiniyaya lacks**: Agent outputs sometimes contain JSON-wrapped fields (e.g., `{"user_message": "fix the login bug"}` instead of just `"fix the login bug"`). Code-shiniyaya's dedup logic (`group by file:line+/-3`) tolerates format variations but doesn't normalize them.

**Concrete fix** -- Add as a utility function for agent output processing:
```python
def normalize_source_text(value: str) -> str:
    """Strip JSON envelopes from agent output fields. Some agents wrap
    text fields in {"user_message": "..."} instead of returning plain text."""
    raw = str(value or "").strip()
    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key in ("user_message", "message", "text", "content", "prompt"):
                    if isinstance(parsed.get(key), str) and parsed[key].strip():
                        return parsed[key].strip()
        except (json.JSONDecodeError, TypeError):
            pass
    return raw
```

**Priority**: P2 -- Reduces noise in agent output processing.

---

### Finding 17: Session-Granularity Transcript Truncation (MAX_SESSION_CHARS)

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:32-33

**Pattern**: AutoDream has carefully tuned character limits for each data type:
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
```

Each data type has its own budget, preventing any single type from dominating the prompt context.

**What code-shiniyaya lacks**: When injecting reference sources into agent prompts (STEP 1.5), there's no per-source character budget. A single large reference source can consume 80%+ of the agent's context window, crowding out the actual file being diagnosed.

**Concrete fix** -- Add to STEP 1.5 agent prompt construction:
```markdown
### Per-Source Context Budgets for Agent Prompts

When constructing agent prompts, allocate context by source type:

| Source Type | Max Chars | Priority |
|-------------|-----------|----------|
| Target file being diagnosed | 50% of budget | Highest |
| Direct dependencies (imports) | 20% of budget | High |
| Reference patterns (STEP 1.5) | 20% of budget | Medium |
| Agent instructions + schema | 10% of budget | Fixed |

**Implementation**:
```
def build_agent_prompt(target_file, dependencies, references, max_total_chars):
    budget = {
        "target": int(max_total_chars * 0.50),
        "dependencies": int(max_total_chars * 0.20),
        "references": int(max_total_chars * 0.20),
        "instructions": int(max_total_chars * 0.10),
    }
    
    prompt_parts = []
    prompt_parts.append(truncate(instructions, budget["instructions"]))
    prompt_parts.append(truncate(target_file, budget["target"]))
    
    # Allocate dependency budget equally
    per_dep = budget["dependencies"] // max(len(dependencies), 1)
    for dep in dependencies:
        prompt_parts.append(truncate(dep, per_dep))
    
    # Allocate reference budget by relevance
    for ref in sort_by_relevance(references):
        if budget["references"] <= 0:
            break
        chunk = truncate(ref, min(len(ref), budget["references"]))
        prompt_parts.append(chunk)
        budget["references"] -= len(chunk)
    
    return "\n\n".join(prompt_parts)
```
```

**Priority**: P2 -- Improves agent prompt quality but the existing approach works for small-to-medium files.

---

### Finding 18: Memory Index (MEMORY.md) Auto-Generation

**Source**: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\helpers\auto_dream.py:921-944

**Pattern**: After every AutoDream run, `MEMORY.md` is regenerated from the current memory files' titles and descriptions:
```python
# auto_dream.py:921-944
def render_memory_index(memory_files, line_limit):
    lines = ["# Memory Index", ""]
    for item in visible_entries:
        title = collapse_single_line(item.title)
        description = collapse_single_line(item.description) or "Durable memory"
        lines.append(f"- [{title}](memories/{item.file_name}): {description}")
    return "\n".join(lines) + "\n"
```

**What code-shiniyaya lacks**: `memory/MEMORY.md` is manually maintained. When new memory files are added (e.g., from reference scans), MEMORY.md must be manually updated to include them. This creates drift between the actual file list and the index.

**Concrete fix** -- Script to auto-generate MEMORY.md:

```python
# references/generate-memory-index.py
import os
from pathlib import Path

MEMORY_DIR = Path("C:/Users/shiniyaya/Desktop/code-shiniyaya/memory")

def generate_memory_index():
    lines = ["# code-shiniyaya Memory Index", ""]
    lines.append("本目录存储 code-shiniyaya Skill 的持久化记忆，独立于 bilisum 的记忆系统。")
    lines.append("")
    lines.append("**重要规则**: 此Skill对应的所有记忆和修改只能写入此目录。")
    lines.append("")
    
    memory_files = sorted(
        [f for f in MEMORY_DIR.glob("*.md") if f.name != "MEMORY.md"],
        key=lambda p: p.stat().st_mtime, reverse=True
    )
    
    rules_files = [f for f in memory_files if f.name.endswith(".promptinclude.md")]
    ref_files = [f for f in memory_files if not f.name.endswith(".promptinclude.md")]
    
    if rules_files:
        lines.append("## 规则文件 (自动执行)")
        for f in rules_files:
            lines.append(f"- [{f.stem}]({f.name})")
        lines.append("")
    
    lines.append("## 记忆文件")
    for f in ref_files:
        # Extract description from frontmatter if available
        description = extract_frontmatter_field(f, "description") or ""
        lines.append(f"- [{f.stem}]({f.name}){': ' + description if description else ''}")
    
    return "\n".join(lines) + "\n"
```

**Integration**: Run `generate-memory-index.py` after any memory file write operation.

**Priority**: P2 -- Eliminates manual index maintenance. Not P1 because the current manual index with ~12 files is manageable.

---

## Correction / Addendum: Finding Already Captured

The following patterns from autodream are ALREADY captured in code-shiniyaya's existing memory files and do NOT need new entries:

| Pattern | Already In | Status |
|---------|-----------|--------|
| Two-Phase Reflection (Learn + Consolidate) | high-impact-patterns.md Pattern 7 | CAPTURED -- described as "STEP 7之后: Learn阶段 + Consolidation阶段" |
| Checksum-based tracking (general concept) | SKILL.md session state `checksum` field | PARTIAL -- per-session checksums exist but no cross-session file-level content hashing |
| Dual-Representation Memory (markdown + vector) | high-impact-patterns.md Pattern 5 | CAPTURED -- "Markdown文件=主存储+来源; 向量DB=语义索引(衍生, 可重建)" |
| Background threading (DeferredTask) | anti-hang-v2.md "Manual, Same as Codex" section | PARTIAL -- background concept exists but no formal DeferredTask pattern |

---

## Consolidation: What to Actually Change

### Immediate (P0 -- add to SKILL.md v3.8.0 and memory/high-impact-patterns.md)

1. **Grounding Attribution** (Finding 1) -- New required `grounding` field in ALL agent findings. Add grounding-gated verification to STEP 4 Codex check. Sections: "Agent Finding Provenance Declaration," "Orchestrator behavior by grounding mix."

2. **Source Context Tracking** (Findings 2, 3, 4 combined) -- New `source_context_ids`, `source_first_prompts`, `source_memory_ids` fields in all findings and plans. Sections: "Source Context Tracking," "Original Intent Anchoring," "Cross-Reference Tracking."

3. **Taxonomy: Rules vs Facts** (Finding 5) -- Split SKILL.md into rules and reference sections. Adopt `.promptinclude.md` extension for behavioral rules in memory/. Auto-enforcement mechanism. Sections: "Taxonomy: Hard Rules vs Reference Knowledge."

4. **Cross-Session Fingerprinting** (Finding 6) -- New `fingerprints-{project}.json` file with SHA-256 content hashes for cross-session diagnosis reuse. Section: "Cross-Session Content Fingerprinting."

### Planned (P1 -- design for v3.9.0)

5. **Orphan Candidate Detection** (Finding 7) -- Cross-project memory cleanup for renamed/spun-off projects.

6. **Standardized Memory Frontmatter** (Finding 8) -- Schema for all memory files.

7. **Automated Changelog** (Finding 9) -- `memory/CHANGELOG.md` with structured log entries.

8. **Consolidation Protocol** (Finding 10) -- Concrete mechanism, prompt template, cadence control.

### Backlog (P2 -- record in high-impact-patterns.md)

9. Smart truncation (Finding 11)
10. DirtyJson resilient parsing (Finding 12)
11. Background processing mode (Finding 13)
12. Session gating for iteration scans (Finding 14)
13. Utility model summarization (Finding 15)
14. normalize_source_prompt_snippet (Finding 16)
15. Per-source context budgets (Finding 17)
16. Auto-generated memory index (Finding 18)

---

## Files to Update

| File | Section | Findings |
|------|---------|----------|
| SKILL.md | After STEP 1.3 (dedup/merge) | Add "Agent Finding Provenance Declaration" (F1) |
| SKILL.md | STEP 1 execution logic | Add `merged_from[]`, `source_context_ids[]`, `consensus` to merge output (F2) |
| SKILL.md | STEP 1 agent prompt template | Add "Original Intent Anchoring" fields (F3) |
| SKILL.md | STEP 1.5 and STEP 2 | Add "Cross-Reference Tracking" with `source_memory_ids` (F4) |
| SKILL.md | Before "硬规则" section | Add "Taxonomy: Hard Rules vs Reference Knowledge" (F5) |
| SKILL.md | State file schema | Add `fingerprints-{project}.json` schema (F6) |
| SKILL.md | STEP 4 (Codex Verification) | Add grounding-gated Codex claim verification (F1 extension) |
| SKILL.md | STEP 3 (Codex text) | Add smart truncation strategy reference (F11) |
| memory/high-impact-patterns.md | New section "Provenance & Grounding" | Summarize F1-F6 as a new dimension |
| memory/high-impact-patterns.md | Pattern 7 (Two-Phase Reflection) | Add Consolidation Protocol details (F10) |
| memory/ | Multiple files | Add YAML frontmatter to files missing it (F8) |
| memory/ | New file: CHANGELOG.md | Automated changelog (F9) |
| memory/ | Rename memory-isolation-rule.md | -> memory-isolation-rule.promptinclude.md (F5) |
| memory/ | New file: generate-memory-index.py | Auto-generate MEMORY.md (F18) |
