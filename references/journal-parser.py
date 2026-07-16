#!/usr/bin/env python3
"""
Post-mortem journal parser for killed/stuck multi-agent workflows.

Parses a workflow's journal.jsonl to recover partial results, identify hung
agents, and generate a scan-state file for incremental continuation.

Usage:
  python journal-parser.py <workflow_dir> [--iter N] [--output-dir <dir>]

  workflow_dir: Path to the workflow directory containing journal.jsonl
                (e.g. .../subagents/workflows/wf_d93815ef-cfe/)
  --iter N:     Iteration number for scan-state filename (default: 1)
  --output-dir: Where to write scan-state-{iter}.json (default: same as workflow_dir)

Output:
  - Prints summary to stdout
  - Writes scan-state-{iter}.json to output_dir

Exit codes:
  0 - All agents returned (no hung agents)
  1 - Some agents hung (partial results recovered)
  2 - No results at all (all agents hung or journal empty)
  3 - journal.jsonl not found or unreadable
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from collections import Counter
from typing import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# Data models (match scan-state.schema.json)
# ---------------------------------------------------------------------------

class DimensionState:
    """State for a single scan dimension."""
    def __init__(self, key: str, agent_id: str, label: str = ""):
        self.key = key
        self.agentId = agent_id
        self.label = label
        self.status: str = "pending"  # pending | running | completed | timed_out
        self.verdict: Optional[str] = None  # PASS | PARTIAL | FAIL
        self.issues: List[dict] = []
        self.iterDetected: int = 0  # Which iteration detected this
        self.iterResolved: Optional[int] = None
        self.notes: str = ""

    def to_dict(self) -> dict:
        d = {
            "key": self.key,
            "agentId": self.agentId,
            "label": self.label,
            "status": self.status,
            "verdict": self.verdict,
            "issues": self.issues,
            "iterDetected": self.iterDetected,
            "iterResolved": self.iterResolved,
            "notes": self.notes,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DimensionState":
        ds = cls(d["key"], d["agentId"], d.get("label", ""))
        ds.status = d.get("status", "pending")
        ds.verdict = d.get("verdict")
        ds.issues = d.get("issues", [])
        ds.iterDetected = d.get("iterDetected", 0)
        ds.iterResolved = d.get("iterResolved")
        ds.notes = d.get("notes", "")
        return ds


class ScanState:
    """Complete scan state for one iteration."""
    def __init__(self, iter_num: int, workflow_id: str):
        self.schemaVersion = "1.0.0"
        self.iteration = iter_num
        self.workflowId = workflow_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.summary = {
            "totalAgents": 0,
            "completed": 0,
            "hung": 0,
            "passCount": 0,
            "partialCount": 0,
            "failCount": 0,
            "criticalIssues": 0,
            "highIssues": 0,
            "mediumIssues": 0,
            "lowIssues": 0,
        }
        self.dimensions: List[DimensionState] = []
        self.continuation = {
            "completedKeys": [],
            "retryKeys": [],
            "parentIteration": None,  # iter number this continues from
            "retryReason": {},        # key -> reason string (TIMED_OUT | FAILED | KILLED)
        }

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schemaVersion,
            "iteration": self.iteration,
            "workflowId": self.workflowId,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "continuation": self.continuation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScanState":
        ss = cls(d["iteration"], d["workflowId"])
        ss.schemaVersion = d.get("schemaVersion", "1.0.0")
        ss.timestamp = d.get("timestamp", "")
        ss.summary = d.get("summary", {})
        ss.dimensions = [DimensionState.from_dict(dd) for dd in d.get("dimensions", [])]
        ss.continuation = d.get("continuation", {
            "completedKeys": [],
            "retryKeys": [],
            "parentIteration": None,
            "retryReason": {},
        })
        return ss


# ---------------------------------------------------------------------------
# Journal parsing
# ---------------------------------------------------------------------------

def parse_journal(journal_path: str) -> tuple:
    """
    Parse journal.jsonl and return (entries, errors).

    entries: dict mapping key -> {started, result, agentId}
      - started: bool (True if 'started' line seen)
      - result: dict | None (the 'result' object from a 'result' line)
      - agentId: str | None

    errors: list of (line_no, error_message) for unparseable lines
    """
    entries: Dict[str, dict] = {}
    errors: list = []

    if not os.path.isfile(journal_path):
        return entries, [(0, f"File not found: {journal_path}")]

    with open(journal_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append((line_no, f"JSON parse error: {e}"))
                continue

            entry_type = obj.get("type")
            key = obj.get("key", "")

            if not key:
                errors.append((line_no, f"Missing 'key' field in {entry_type} entry"))
                continue

            if key not in entries:
                entries[key] = {"started": False, "result": None, "agentId": None}

            if entry_type == "started":
                entries[key]["started"] = True
                entries[key]["agentId"] = obj.get("agentId", entries[key]["agentId"])

            elif entry_type == "result":
                entries[key]["result"] = obj.get("result")
                entries[key]["agentId"] = obj.get("agentId", entries[key]["agentId"])
                # Also mark as started (in case started line was missed)
                if not entries[key]["started"]:
                    entries[key]["started"] = True

            else:
                errors.append((line_no, f"Unknown entry type: {entry_type}"))

    return entries, errors


def compute_summary(entries: dict) -> dict:
    """Compute summary statistics from parsed entries."""
    total = len(entries)
    completed = sum(1 for e in entries.values() if e["result"] is not None)
    hung = total - completed

    pass_count = 0
    partial_count = 0
    fail_count = 0
    severity_counter = Counter()

    for e in entries.values():
        result = e.get("result")
        if result is None:
            continue

        verdict = result.get("verdict", "UNKNOWN")
        if verdict == "PASS":
            pass_count += 1
        elif verdict == "PARTIAL":
            partial_count += 1
        elif verdict == "FAIL":
            fail_count += 1

        for issue in result.get("issues", []):
            sev = issue.get("severity", "UNKNOWN").upper()
            severity_counter[sev] += 1

    return {
        "totalAgents": total,
        "completed": completed,
        "hung": hung,
        "passCount": pass_count,
        "partialCount": partial_count,
        "failCount": fail_count,
        "criticalIssues": severity_counter.get("CRITICAL", 0),
        "highIssues": severity_counter.get("HIGH", 0),
        "mediumIssues": severity_counter.get("MEDIUM", 0),
        "lowIssues": severity_counter.get("LOW", 0),
    }


def extract_labels_from_agent_journals(workflow_dir: str, entries: dict) -> dict:
    """
    Attempt to extract agent labels by reading agent-{id}.jsonl files.
    Labels are typically embedded in the first user message's prompt content.

    Returns: dict mapping key -> label string (empty string if not found)
    """
    labels: Dict[str, str] = {}

    for key, entry in entries.items():
        agent_id = entry.get("agentId")
        if not agent_id:
            continue

        agent_file = os.path.join(workflow_dir, f"agent-{agent_id}.jsonl")
        if not os.path.isfile(agent_file):
            continue

        try:
            with open(agent_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Look for label in the user message
                    if obj.get("type") == "user":
                        msg = obj.get("message", {})
                        content = msg.get("content", "")

                        # CC agent launch messages may embed label info
                        # Common patterns: the workflow prompt may include a dimension key
                        # For now, extract from the first line of content if short
                        if isinstance(content, str) and len(content) < 200:
                            # Use first meaningful line as label
                            first_line = content.split("\n")[0].strip()
                            if first_line and len(first_line) < 80:
                                labels[key] = first_line
                            else:
                                labels[key] = f"agent-{agent_id[:8]}"
                        else:
                            labels[key] = f"agent-{agent_id[:8]}"
                        break  # Only read first user message
        except Exception:
            labels[key] = f"agent-{agent_id[:8]}"

    return labels


# ---------------------------------------------------------------------------
# Scan state generation
# ---------------------------------------------------------------------------

def build_scan_state(
    entries: dict,
    errors: list,
    workflow_id: str,
    iteration: int,
    labels: dict,
    parent_state: Optional[ScanState] = None,
) -> ScanState:
    """Build a ScanState from parsed journal entries."""
    state = ScanState(iteration, workflow_id)
    state.summary = compute_summary(entries)

    completed_keys = []
    retry_keys = []

    for key, entry in entries.items():
        agent_id = entry.get("agentId", "unknown")
        label = labels.get(key, f"agent-{agent_id[:8]}" if agent_id else key[:12])

        dim = DimensionState(key, agent_id, label)
        dim.iterDetected = iteration

        result = entry.get("result")
        if result is not None:
            dim.status = "completed"
            dim.verdict = result.get("verdict", "UNKNOWN")
            dim.issues = result.get("issues", [])
            completed_keys.append(key)
        else:
            dim.status = "timed_out"
            retry_keys.append(key)

        state.dimensions.append(dim)

    # Build continuation plan
    state.continuation["completedKeys"] = completed_keys
    state.continuation["retryKeys"] = retry_keys

    if parent_state:
        state.continuation["parentIteration"] = parent_state.iteration

    # Determine reason for each retry
    for key in retry_keys:
        # Default reason: agent had a 'started' line but no 'result'
        state.continuation["retryReason"][key] = "TIMED_OUT"

    # If there are errors, add a special dimension for journal integrity
    if errors:
        err_dim = DimensionState(
            key="__journal_errors__",
            agent_id="__system__",
            label="journal.jsonl parse errors",
        )
        err_dim.status = "completed"
        err_dim.verdict = "FAIL"
        err_dim.issues = [
            {"severity": "HIGH", "description": f"Line {ln}: {msg}"}
            for ln, msg in errors
        ]
        err_dim.iterDetected = iteration
        state.dimensions.append(err_dim)

    return state


def merge_scan_states(parent: ScanState, child: ScanState) -> ScanState:
    """
    Merge a child (continuation) scan state into a parent.

    Rules:
    - Child's completed dimensions override parent's timed_out dimensions for the same key.
    - Parent's completed dimensions are preserved unchanged.
    - Issues accumulate: child issues for the same dimension are appended.
    - Summary is recomputed from the merged dimension set.
    """
    merged = ScanState(child.iteration, child.workflowId)

    # Build dimension map from parent
    dim_map: Dict[str, DimensionState] = {}
    for d in parent.dimensions:
        dim_map[d.key] = d

    # Merge child dimensions
    for d in child.dimensions:
        if d.key in dim_map:
            existing = dim_map[d.key]
            # Only override if child has a real result and parent has timed_out
            if d.status == "completed" and existing.status == "timed_out":
                existing.status = "completed"
                existing.verdict = d.verdict
                existing.agentId = d.agentId  # may be different agent
                # Append child issues (they could be complementary findings)
                existing.issues = existing.issues + d.issues
                existing.iterResolved = d.iterDetected
            elif d.status == "completed" and existing.status == "completed":
                # Both have results — append new issues (different iteration may find different things)
                existing.issues = existing.issues + d.issues
                # Take the worse verdict
                verdict_rank = {"PASS": 0, "PARTIAL": 1, "FAIL": 2, "UNKNOWN": 3}
                if verdict_rank.get(d.verdict, 0) > verdict_rank.get(existing.verdict, 0):
                    existing.verdict = d.verdict
        else:
            dim_map[d.key] = d

    # Rebuild dimensions list, sorted: completed first, then pending/timed_out
    merged.dimensions = sorted(
        dim_map.values(),
        key=lambda d: (0 if d.status == "completed" else 1, d.key),
    )

    # Merge continuation info
    merged.continuation["completedKeys"] = list(
        set(parent.continuation.get("completedKeys", [])
        + child.continuation.get("completedKeys", []))
    )
    merged.continuation["retryKeys"] = child.continuation.get("retryKeys", [])
    merged.continuation["parentIteration"] = parent.iteration
    merged.continuation["retryReason"] = child.continuation.get("retryReason", {})

    # Recompute summary
    merged.summary = recompute_summary_from_dimensions(merged.dimensions)
    merged.timestamp = datetime.now(timezone.utc).isoformat()

    return merged


def recompute_summary_from_dimensions(dimensions: List[DimensionState]) -> dict:
    """Recompute summary from a list of DimensionState objects."""
    total = len([d for d in dimensions if d.key != "__journal_errors__"])
    completed = sum(1 for d in dimensions if d.status == "completed" and d.key != "__journal_errors__")
    hung = total - completed

    pass_count = 0
    partial_count = 0
    fail_count = 0
    severity_counter = Counter()

    for d in dimensions:
        if d.key == "__journal_errors__":
            continue
        if d.status != "completed":
            continue

        verdict = d.verdict or "UNKNOWN"
        if verdict == "PASS":
            pass_count += 1
        elif verdict == "PARTIAL":
            partial_count += 1
        elif verdict == "FAIL":
            fail_count += 1

        for issue in d.issues:
            sev = issue.get("severity", "UNKNOWN").upper()
            severity_counter[sev] += 1

    return {
        "totalAgents": total,
        "completed": completed,
        "hung": hung,
        "passCount": pass_count,
        "partialCount": partial_count,
        "failCount": fail_count,
        "criticalIssues": severity_counter.get("CRITICAL", 0),
        "highIssues": severity_counter.get("HIGH", 0),
        "mediumIssues": severity_counter.get("MEDIUM", 0),
        "lowIssues": severity_counter.get("LOW", 0),
    }


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def format_verdict_row(verdict: Optional[str]) -> str:
    """Color-coded verdict display."""
    if verdict == "PASS":
        return "PASS    "
    elif verdict == "PARTIAL":
        return "PARTIAL "
    elif verdict == "FAIL":
        return "FAIL    "
    return "NO_RESULT"


def print_summary(state: ScanState, errors: list):
    """Print human-readable summary."""
    s = state.summary
    print("=" * 60)
    print(f"  Workflow: {state.workflowId}")
    print(f"  Iteration: {state.iteration}")
    print(f"  Timestamp: {state.timestamp}")
    print("-" * 60)
    print(f"  Agents launched: {s['totalAgents']}")
    print(f"  Completed:       {s['completed']}")
    print(f"  Hung/Killed:     {s['hung']}")
    print("-" * 60)
    print(f"  PASS:    {s['passCount']}")
    print(f"  PARTIAL: {s['partialCount']}")
    print(f"  FAIL:    {s['failCount']}")
    print("-" * 60)
    print(f"  CRITICAL: {s['criticalIssues']}")
    print(f"  HIGH:     {s['highIssues']}")
    print(f"  MEDIUM:   {s['mediumIssues']}")
    print(f"  LOW:      {s['lowIssues']}")
    print("=" * 60)

    if errors:
        print(f"\n[!] {len(errors)} journal parse error(s):")
        for ln, msg in errors[:10]:
            print(f"    Line {ln}: {msg}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    if state.dimensions:
        print(f"\nPer-dimension results:")
        for d in state.dimensions:
            if d.key == "__journal_errors__":
                continue
            status_marker = "[OK]" if d.status == "completed" else "[XX]"
            label = d.label if d.label else d.key[:16]
            issues_n = len(d.issues)
            print(f"  {status_marker} {format_verdict_row(d.verdict)}  {label}  ({issues_n} issue(s))")

    if state.continuation["retryKeys"]:
        print(f"\n[!] {len(state.continuation['retryKeys'])} dimension(s) need retry:")
        for key in state.continuation["retryKeys"]:
            reason = state.continuation["retryReason"].get(key, "UNKNOWN")
            print(f"    {key[:24]}...  reason: {reason}")


def main():
    parser = argparse.ArgumentParser(
        description="Post-mortem journal parser for killed/stuck multi-agent workflows"
    )
    parser.add_argument(
        "workflow_dir",
        help="Path to workflow directory containing journal.jsonl",
    )
    parser.add_argument(
        "--iter", type=int, default=1,
        help="Iteration number for scan-state filename (default: 1)",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to write scan-state-{iter}.json (default: same as workflow_dir)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON to stdout instead of human summary",
    )
    parser.add_argument(
        "--merge-from",
        help="Path to previous scan-state-{N}.json to merge with",
    )
    args = parser.parse_args()

    workflow_dir = os.path.abspath(args.workflow_dir)
    journal_path = os.path.join(workflow_dir, "journal.jsonl")
    output_dir = os.path.abspath(args.output_dir) if args.output_dir else workflow_dir

    # Validate
    if not os.path.isdir(workflow_dir):
        print(f"Error: workflow directory not found: {workflow_dir}", file=sys.stderr)
        sys.exit(3)

    if not os.path.isfile(journal_path):
        print(f"Error: journal.jsonl not found in {workflow_dir}", file=sys.stderr)
        sys.exit(3)

    # Parse
    workflow_id = os.path.basename(workflow_dir)
    entries, errors = parse_journal(journal_path)
    labels = extract_labels_from_agent_journals(workflow_dir, entries)

    # Load parent state for merging
    parent_state = None
    if args.merge_from:
        if os.path.isfile(args.merge_from):
            with open(args.merge_from, "r", encoding="utf-8") as f:
                parent_state = ScanState.from_dict(json.load(f))
        else:
            print(f"Warning: merge-from file not found: {args.merge_from}", file=sys.stderr)

    # Build state
    state = build_scan_state(entries, errors, workflow_id, args.iter, labels, parent_state)

    # Merge if parent exists
    if parent_state:
        state = merge_scan_states(parent_state, state)

    # Write scan-state file
    state_file = os.path.join(output_dir, f"scan-state-{args.iter:03d}.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state.to_dict(), f, indent=2, ensure_ascii=False)

    # Output
    if args.json:
        print(json.dumps(state.to_dict(), indent=2, ensure_ascii=False))
    else:
        print_summary(state, errors)
        print(f"\nScan state written to: {state_file}")

    # Exit code
    s = state.summary
    if s["hung"] == 0 and s["completed"] > 0:
        sys.exit(0)  # All clean
    elif s["completed"] > 0:
        sys.exit(1)  # Partial recovery
    else:
        sys.exit(2)  # Nothing recovered


if __name__ == "__main__":
    main()
