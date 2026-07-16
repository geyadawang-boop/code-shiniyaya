# Continuation Workflow Template for code-shiniyaya Scans

Use this template when resuming a scan from a partial result set. It reads
the scan-state file, identifies which dimensions need re-running, and
launches only those agents.

## Pre-flight: Recover partial results

Before launching a continuation workflow, run the post-mortem parser:

```bash
python references/journal-parser.py \
  "C:\Users\shiniyaya\.claude\projects\...\subagents\workflows\wf_XXXXX" \
  --iter 1
```

This produces `scan-state-001.json` in the workflow directory.

## Option A: CC-Orchestrated Continuation

When resuming within a CC session, read the scan-state file and launch only
retry agents:

```javascript
// 1. Read scan state
var stateFile = 'path/to/scan-state-001.json'
var state = JSON.parse(readFile(stateFile))
var retryKeys = state.continuation.retryKeys
var completedKeys = state.continuation.completedKeys

log('Resuming from iteration ' + state.iteration + ': ' +
    completedKeys.length + ' dimensions complete, ' +
    retryKeys.length + ' need retry')

// 2. Map retry keys back to their original prompts
// (Read the original agent-*.jsonl files or reconstruct from labels)
var retryPrompts = retryKeys.map(function(key) {
  return {
    key: key,
    label: findLabelForDimension(key, state),
    prompt: '[RETRY] Dimension ' + key + ' — re-run with same scope as original.'
  }
})

// 3. Launch only retry agents
var retryResults = await parallel(retryPrompts.map(function(t) {
  return function() {
    log('Retry agent for ' + t.label + ' launched')
    return agent(t.prompt, { label: t.label, schema: F })
  }
}))

// 4. After all retry agents complete:
// Run journal-parser.py again with --iter 2 --merge-from scan-state-001.json
// This produces scan-state-002.json with merged results.

// 5. Build final report from scan-state-002.json
```

## Option B: CLI-Only Continuation

When the original CC session is gone, use the continuation planner:

```bash
# 1. See what needs re-running
python references/continuation-planner.py scan-state-001.json

# 2. Launch a new workflow with ONLY the retry dimensions (not all 10)
# Use the prompt specs output by continuation-planner.py

# 3. After the new workflow completes (or times out):
python references/journal-parser.py \
  "C:\Users\shiniyaya\.claude\projects\...\subagents\workflows\wf_YYYYY" \
  --iter 2 --merge-from scan-state-001.json

# This produces scan-state-002.json with MERGED results from both iterations
```

## Handling FAIL Verdicts

By default, FAIL-verdict dimensions are NOT re-run (they have data). To also
re-run FAIL verdicts:

```bash
python references/continuation-planner.py scan-state-001.json --retry-fail
```

## Full Pipeline Example

```bash
# Initial workflow killed mid-way (7/10 returned)
# Step 1: Parse what we have
python references/journal-parser.py \
  "C:\Users\shiniyaya\.claude\projects\D---claude\SESSION\subagents\workflows\wf_KILLED" \
  --iter 1

# Output: scan-state-001.json
#   -> 7 completed (5 PASS, 2 FAIL)
#   -> 3 hung (need retry)
#   -> Exit code 1 (partial recovery)

# Step 2: Plan continuation
python references/continuation-planner.py scan-state-001.json

# Output: 62.5% cost saved, 3 dimensions need re-run

# Step 3: Launch continuation workflow with only 3 agents
# (New CC session or manual launch)

# Step 4: Parse continuation results and merge
python references/journal-parser.py \
  "C:\Users\shiniyaya\.claude\projects\D---claude\SESSION\subagents\workflows\wf_CONTINUATION" \
  --iter 2 --merge-from scan-state-001.json

# Output: scan-state-002.json
#   -> All 10 dimensions complete (7 from iter 1 + 3 from iter 2)
#   -> Exit code 0 (all clean)

# Step 5: Read final aggregated report
python -c "
import json
with open('scan-state-002.json') as f:
    state = json.load(f)
print(f'All {state[\"summary\"][\"completed\"]}/{state[\"summary\"][\"totalAgents\"]} dimensions verified')
print(f'Issues: {state[\"summary\"][\"criticalIssues\"]} CRITICAL, {state[\"summary\"][\"highIssues\"]} HIGH')
"
```

## Notes

- **scan-state files are idempotent**: re-running the parser on the same journal
  with the same --iter number overwrites the previous scan-state with identical data.
- **Merging preserves history**: `--merge-from` appends new issues without duplicating
  existing ones (keyed by dimension key).
- **Journal files persist**: agent-*.jsonl and journal.jsonl are never deleted, so
  post-mortem analysis works even days after the workflow was killed.
- **Cost model**: a 10-agent scan at $0.02/agent = $0.20. With 62.5% savings, the
  continuation costs $0.075 instead of $0.20, saving $0.125 per iteration.
