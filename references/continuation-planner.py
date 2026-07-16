#!/usr/bin/env python3
"""
Continuation planner: reads an existing scan-state-N.json and generates the
minimal re-run plan — only the dimensions that hung or failed, not all 10.

Usage:
  python continuation-planner.py <scan-state-N.json> [--format prompt|json]

  --format prompt: Output agent prompts for the retry dimensions (default)
  --format json:   Output raw JSON with retry dimension specs

The planner answers: "If 7/10 agents returned clean (PASS), only re-run the 3
that failed/timed-out, not all 10."
"""

import json
import sys
import os
import argparse
from typing import Dict, List, Optional


def load_scan_state(state_path: str) -> dict:
    """Load and validate a scan-state file."""
    if not os.path.isfile(state_path):
        print(f"Error: scan state file not found: {state_path}", file=sys.stderr)
        sys.exit(1)

    with open(state_path, "r", encoding="utf-8") as f:
        state = json.load(f)

    required = ["schemaVersion", "iteration", "dimensions", "continuation"]
    missing = [k for k in required if k not in state]
    if missing:
        print(f"Error: invalid scan state, missing fields: {missing}", file=sys.stderr)
        sys.exit(1)

    return state


class ContinuationPlan:
    """Minimal re-run plan derived from a scan state."""

    def __init__(self, state: dict, retry_fail: bool = False):
        self.state = state
        self.retry_fail = retry_fail
        self.completed = self._filter_completed()
        self.to_retry = self._filter_retry()
        self.cumulative = self._cumulative_issues()

    def _filter_completed(self) -> List[dict]:
        """Dimensions that completed and do NOT need re-running."""
        completed = []
        for dim in self.state.get("dimensions", []):
            if dim.get("key") == "__journal_errors__":
                continue
            status = dim.get("status")
            verdict = dim.get("verdict")
            if status == "completed":
                # FAIL verdicts are only "completed" if retry_fail is False
                if verdict == "FAIL" and self.retry_fail:
                    continue  # treat FAIL as needing retry
                completed.append(dim)
        return completed

    def _filter_retry(self) -> List[dict]:
        """Dimensions that need re-running (hung, timed_out, or optionally FAIL verdict)."""
        to_retry = []
        for dim in self.state.get("dimensions", []):
            if dim.get("key") == "__journal_errors__":
                continue
            status = dim.get("status")
            verdict = dim.get("verdict")

            # Always retry timed_out dimensions
            if status in ("timed_out", "pending", "running"):
                to_retry.append(dim)
            # Only retry FAIL verdicts when retry_fail flag is set
            elif self.retry_fail and status == "completed" and verdict == "FAIL":
                to_retry.append(dim)
        return to_retry

    def _cumulative_issues(self) -> List[dict]:
        """All issues from all completed dimensions across iterations."""
        issues = []
        for dim in self.state.get("dimensions", []):
            if dim.get("key") == "__journal_errors__":
                continue
            for iss in dim.get("issues", []):
                iss_copy = dict(iss)
                iss_copy["sourceDimension"] = dim.get("label", dim.get("key", "unknown"))
                iss_copy["sourceKey"] = dim.get("key", "")
                iss_copy["sourceVerdict"] = dim.get("verdict", "UNKNOWN")
                issues.append(iss_copy)
        # Sort by severity
        severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        issues.sort(key=lambda i: severity_rank.get(i.get("severity", "LOW"), 99))
        return issues

    def cost_savings(self) -> dict:
        """Compute how many agents we save by not re-running completed ones."""
        total = len(self.completed) + len(self.to_retry)
        saved = len(self.completed)
        rerun = len(self.to_retry)
        pct = (saved / total * 100) if total > 0 else 0
        return {
            "totalDimensions": total,
            "alreadyCompleted": saved,
            "needRerun": rerun,
            "savingsPercent": round(pct, 1),
        }

    def generate_prompts(self, template_prompt: str = "") -> List[dict]:
        """
        Generate minimal agent prompts for retry dimensions.

        Each prompt should re-test the SAME dimension with the SAME scope
        as the original — the only difference is fewer agents are launched.
        """
        prompts = []
        for dim in self.to_retry:
            label = dim.get("label", dim.get("key", "unknown")[:16])
            original_key = dim.get("key", "")
            reason = self.state.get("continuation", {}).get("retryReason", {}).get(original_key, "TIMED_OUT")

            prompt_spec = {
                "key": original_key,
                "label": label,
                "reason": reason,
                "prompt": template_prompt.format(
                    label=label,
                    key=original_key,
                    reason=reason,
                ) if template_prompt else f"[RETRY {label}] Original agent timed out. Re-run with same scope.",
                "schema": {
                    "type": "object",
                    "required": ["verdict", "issues"],
                    "properties": {
                        "verdict": {"type": "string", "enum": ["PASS", "PARTIAL", "FAIL"]},
                        "issues": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["severity", "description"],
                                "properties": {
                                    "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            }
            prompts.append(prompt_spec)
        return prompts


def print_plan(plan: ContinuationPlan):
    """Human-readable plan summary."""
    costs = plan.cost_savings()
    print("=" * 60)
    print(f"  Continuation Plan for iteration {plan.state['iteration']}")
    print(f"  Workflow: {plan.state['workflowId']}")
    print("-" * 60)
    print(f"  Total dimensions:     {costs['totalDimensions']}")
    print(f"  Already completed:    {costs['alreadyCompleted']}  (<-- SKIP)")
    print(f"  Need re-run:          {costs['needRerun']}  (<-- LAUNCH)")
    print(f"  Cost saved:           {costs['savingsPercent']}%")
    print("-" * 60)

    if plan.completed:
        print(f"\n  Completed dimensions (will NOT re-run):")
        for dim in plan.completed:
            label = dim.get("label", dim["key"][:16])
            print(f"    [OK] {dim['verdict']:8s}  {label}  ({len(dim.get('issues', []))} issues)")

    if plan.to_retry:
        print(f"\n  Dimensions to re-run:")
        for dim in plan.to_retry:
            label = dim.get("label", dim["key"][:16])
            reason = plan.state.get("continuation", {}).get("retryReason", {}).get(dim["key"], "UNKNOWN")
            print(f"    [XX] {dim.get('status', '?'):12s}  {label}  reason: {reason}")

    if plan.cumulative:
        print(f"\n  Cumulative issues across all completed dimensions: {len(plan.cumulative)}")
        by_severity = {}
        for iss in plan.cumulative:
            sev = iss.get("severity", "UNKNOWN")
            by_severity.setdefault(sev, 0)
            by_severity[sev] += 1
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            if sev in by_severity:
                print(f"    {sev}: {by_severity[sev]}")

    print("=" * 60)

    if plan.to_retry:
        next_iter = plan.state["iteration"] + 1
        print(f"\n  Next: launch {len(plan.to_retry)} agents for iteration {next_iter}")
        print(f"  Output will be: scan-state-{next_iter:03d}.json")


def main():
    parser = argparse.ArgumentParser(
        description="Generate minimal re-run plan from scan-state file"
    )
    parser.add_argument("scan_state", help="Path to scan-state-N.json")
    parser.add_argument(
        "--format", choices=["prompt", "json"], default="prompt",
        help="Output format: prompt (agent task specs) or json (raw)",
    )
    parser.add_argument(
        "--include-pass", action="store_true",
        help="Include PASS dimensions in cumulative issues (normally excluded)",
    )
    parser.add_argument(
        "--retry-fail", action="store_true",
        help="Also re-run dimensions with FAIL verdict (default: only timed_out)",
    )
    args = parser.parse_args()

    state = load_scan_state(args.scan_state)
    plan = ContinuationPlan(state, retry_fail=args.retry_fail)

    if args.format == "json":
        output = {
            "plan": plan.cost_savings(),
            "completedDimensions": plan.completed,
            "retryDimensions": plan.to_retry,
            "cumulativeIssues": plan.cumulative,
            "retryPrompts": plan.generate_prompts(),
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print_plan(plan)

        # Also output the prompt spec
        if plan.to_retry:
            print(f"\n  Agent prompt specs for iteration {plan.state['iteration'] + 1}:")
            for p in plan.generate_prompts():
                print(f"\n  --- {p['label']} ---")
                print(f"  Reason: {p['reason']}")
                print(f"  Key: {p['key']}")
                print(f"  Prompt: {p['prompt']}")


if __name__ == "__main__":
    main()
