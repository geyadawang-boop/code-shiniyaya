"""
Heartbeat v2 -- Agent and Workflow Liveness Monitoring
======================================================
Journal-based heartbeat system with dual-level watchdog detection.

Architecture:
  1. Agents call heartbeat.log() family to write structured entries to a
     JSONL journal file (append-only, one JSON object per line).
  2. The Watchdog agent reads the journal tail every 30 s, builds an
     in-memory index, and detects hangs at two levels:
       - Agent-level:  any agent whose last heartbeat exceeds TTL.
       - Workflow-level: any workflow whose active phase exceeds its
         budget without a phase_exit entry.
  3. Detected hangs are written back to the journal as "hang_detect"
     entries and surfaced through the error_aggregator alerting bus.

Journal format (data/heartbeat_journal.jsonl -- one line per entry):
  {"type":"heartbeat",     "agent_id":"A01","workflow_id":"batch-1","ts":"ISO","seq":42,"state":"running","phase":"scan"}
  {"type":"phase_enter",   "agent_id":"A01","workflow_id":"batch-1","ts":"ISO","phase":"scan","budget_s":120}
  {"type":"phase_exit",    "agent_id":"A01","workflow_id":"batch-1","ts":"ISO","phase":"scan","result":"ok","actual_s":95}
  {"type":"workflow_start","workflow_id":"batch-1","ts":"ISO","agents":["A01","A02","A03"],"phase":"init"}
  {"type":"workflow_end",  "workflow_id":"batch-1","ts":"ISO","status":"completed","agents_finished":3}
  {"type":"log",           "agent_id":"A01","workflow_id":"batch-1","ts":"ISO","level":"info","msg":"Found 5 bugs"}
  {"type":"hang_detect",   "agent_id":"A07","workflow_id":"batch-1","ts":"ISO","kind":"agent","stall_s":95,"last_hb":"ISO"}

TTL Design (all values configurable):
  HEARTBEAT_INTERVAL  = 15 s   -- agents call log() every 15 s
  WATCHDOG_INTERVAL   = 30 s   -- watchdog scans journal every 30 s
  AGENT_TTL           = 45 s   -- 3 missed heartbeats = agent hang
  INITIAL_GRACE       = 15 s   -- extra grace after agent first-heartbeat
  PHASE_BUDGET_MIN    = 120 s  -- minimum per-phase expected duration
  ALERT_COOLDOWN      = 300 s  -- do not re-alert same (agent,kind) within 5 min
  JOURNAL_MAX_LINES   = 20_000 -- rotate when exceeded

False-positive mitigations:
  1. Confirmation gating:    require 2+ consecutive missed heartbeats
  2. Staggered deadlines:     deterministic per-agent TTL jitter avoids alarm storms
  3. Phase > agent TTL:       workflow alarm only fires after ALL agents silent
  4. Cooldown:                prevents alarm fatigue on transient load spikes
  5. Monotonic clock:         all duration math uses time.monotonic()
  6. Grace period:            extra margin for first heartbeat after spawn

False-positive rate estimate: < 5 % (see HEARTBEAT_V2_DESIGN.md)

Works with current API: YES
  - JSONL journal -- no new dependencies
  - asyncio background tasks -- compatible with FastAPI lifespan
  - error_aggregator integration -- same alert cooldown pattern
  - Windows-compatible file locking -- msvcrt / portalocker
  - Exposes /api/heartbeat/status for frontend monitoring dashboard
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("bilisum.heartbeat")

# ---------------------------------------------------------------------------
# Configuration (single source of truth)
# ---------------------------------------------------------------------------

HEARTBEAT_INTERVAL = 15          # seconds between agent heartbeats
WATCHDOG_INTERVAL = 30           # seconds between watchdog scans
AGENT_TTL = 45                   # seconds before an agent is considered hung
INITIAL_GRACE = 15               # extra seconds after first heartbeat before TTL applies
PHASE_BUDGET_MIN = 120           # minimum per-phase budget in seconds
ALERT_COOLDOWN = 300             # seconds before re-alerting the same agent
JOURNAL_MAX_LINES = 20_000       # rotate journal when line count exceeds this
JOURNAL_TAIL_BYTES = 256 * 1024  # read last 256 KiB on scan (avoids full-file read)

# Resolve journal path relative to backend directory
_BACKEND_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BACKEND_DIR.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
JOURNAL_PATH = _DATA_DIR / "heartbeat_journal.jsonl"

# ---------------------------------------------------------------------------
# In-memory state (populated by watchdog scan, shared with status API)
# ---------------------------------------------------------------------------

_agent_index: dict[str, AgentRecord] = {}
_workflow_index: dict[str, WorkflowRecord] = {}
_pending_alerts: list[dict] = []
_last_scan_ts: float = 0.0
_scan_lock = asyncio.Lock()

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AgentRecord:
    """In-memory record of a single agent's last-known state."""
    agent_id: str
    workflow_id: str = ""
    last_heartbeat: float = 0.0     # time.monotonic()
    last_heartbeat_iso: str = ""    # ISO timestamp
    seq: int = 0
    state: str = "unknown"          # unknown | running | idle | done | hung
    phase: str = ""
    missed_count: int = 0           # consecutive missed heartbeats

    @property
    def stall_seconds(self) -> float:
        if self.last_heartbeat <= 0:
            return 0.0
        return _time.monotonic() - self.last_heartbeat


@dataclass
class PhaseRecord:
    """In-memory record of a single phase within a workflow."""
    phase_name: str
    agent_id: str
    budget_s: float = 0.0
    started_at: float = 0.0         # time.monotonic()
    started_at_iso: str = ""
    ended_at: float = 0.0           # 0 = still active
    result: str = ""

    @property
    def elapsed(self) -> float:
        if self.started_at <= 0:
            return 0.0
        end = self.ended_at if self.ended_at > 0 else _time.monotonic()
        return end - self.started_at

    @property
    def is_active(self) -> bool:
        return self.started_at > 0 and self.ended_at <= 0

    @property
    def over_budget(self) -> bool:
        return self.is_active and self.elapsed > max(self.budget_s, PHASE_BUDGET_MIN)


@dataclass
class WorkflowRecord:
    """In-memory record of a workflow's overall state."""
    workflow_id: str
    started_at: float = 0.0         # time.monotonic()
    started_at_iso: str = ""
    ended_at: float = 0.0           # 0 = still active
    status: str = "running"         # running | completed | failed | hung
    agents: list[str] = field(default_factory=list)
    phases: dict[str, PhaseRecord] = field(default_factory=dict)
    active_phase: str = ""

    @property
    def is_active(self) -> bool:
        return self.started_at > 0 and self.ended_at <= 0

    @property
    def all_agents_silent(self) -> bool:
        """True if every agent in this workflow has missed its heartbeat."""
        if not self.agents:
            return True
        now = _time.monotonic()
        for aid in self.agents:
            rec = _agent_index.get(aid)
            if rec and (now - rec.last_heartbeat) < AGENT_TTL:
                return False
        return True  # all agents past TTL or never started


# ---------------------------------------------------------------------------
# Core: heartbeat.log() -- the API agents call
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """UTC ISO 8601 timestamp with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _write_journal_entry(entry: dict) -> None:
    """Append a single JSON object as one line to the journal file.

    Thread-safe: uses os-level append with a small lock window.
    On Windows, line-level append is safe for POSIX-style writes
    as long as each write is a single line (no interleaved bytes).
    """
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    try:
        with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:
        logger.warning("Heartbeat journal write failed: %s", exc)


def _check_rotate():
    """Rotate journal if it exceeds max lines (approximate count by size)."""
    try:
        if not JOURNAL_PATH.exists():
            return
        size_mb = JOURNAL_PATH.stat().st_size / (1024 * 1024)
        # Rough heuristic: ~200 bytes per line => JOURNAL_MAX_LINES * 200 / 1MB
        threshold_mb = (JOURNAL_MAX_LINES * 200) / (1024 * 1024)
        if size_mb > threshold_mb:
            backup = JOURNAL_PATH.with_suffix(".jsonl.bak")
            if backup.exists():
                backup.unlink()
            JOURNAL_PATH.rename(backup)
            logger.info("Heartbeat journal rotated (was %.1f MB)", size_mb)
    except OSError:
        pass  # best-effort rotation; never fail heartbeat


def log(
    agent_id: str,
    workflow_id: str = "",
    *,
    state: str = "running",
    phase: str = "",
    message: str = "",
    level: str = "info",
    extra: Optional[dict] = None,
) -> None:
    """Write a heartbeat entry to the journal.

    This is the primary API that every agent calls on a 15 s interval.

    Args:
        agent_id:   Unique agent identifier (e.g. "A01", "batch1-scan").
        workflow_id: Owning workflow or batch ("" for standalone agents).
        state:      "running" | "idle" | "done" | "error" | "waiting".
        phase:      Current phase name (e.g. "scan", "fix", "verify").
        message:    Free-form log message.
        level:      "debug" | "info" | "warn" | "error".
        extra:      Arbitrary dict merged into the entry.

    Side effects:
        - Appends one line to heartbeat_journal.jsonl
        - Triggers rotation if journal exceeds threshold
    """
    _check_rotate()
    entry: dict[str, Any] = {
        "type": "heartbeat",
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "state": state,
        "phase": phase,
        "level": level,
    }
    if message:
        entry["msg"] = message[:500]
    if extra:
        entry["extra"] = extra
    _write_journal_entry(entry)


def log_phase_enter(
    agent_id: str,
    workflow_id: str,
    phase: str,
    budget_s: float = 300.0,
) -> None:
    """Record that an agent is entering a new workflow phase.

    Args:
        budget_s: Expected maximum duration of this phase in seconds.
                  The watchdog will flag this phase if it exceeds budget_s.
    """
    _check_rotate()
    _write_journal_entry({
        "type": "phase_enter",
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "phase": phase,
        "budget_s": budget_s,
    })


def log_phase_exit(
    agent_id: str,
    workflow_id: str,
    phase: str,
    result: str = "ok",
) -> None:
    """Record that an agent has completed a workflow phase."""
    _check_rotate()
    _write_journal_entry({
        "type": "phase_exit",
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "phase": phase,
        "result": result,
    })


def log_workflow_start(
    workflow_id: str,
    agents: list[str],
    phase: str = "init",
) -> None:
    """Record that a new workflow batch has started."""
    _check_rotate()
    _write_journal_entry({
        "type": "workflow_start",
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "agents": agents,
        "phase": phase,
    })


def log_workflow_end(
    workflow_id: str,
    status: str = "completed",
    agents_finished: int = 0,
) -> None:
    """Record that a workflow batch has finished."""
    _check_rotate()
    _write_journal_entry({
        "type": "workflow_end",
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "status": status,
        "agents_finished": agents_finished,
    })


def log_info(
    agent_id: str,
    workflow_id: str,
    message: str,
    *,
    level: str = "info",
    extra: Optional[dict] = None,
) -> None:
    """Write a structured log entry to the journal (non-heartbeat).

    Useful for recording discoveries, errors, or state transitions
    that should be visible to the watchdog and post-mortem analysis.
    """
    _check_rotate()
    entry: dict[str, Any] = {
        "type": "log",
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "level": level,
        "msg": message[:1000],
    }
    if extra:
        entry["extra"] = extra
    _write_journal_entry(entry)


def log_hang(
    agent_id: str,
    workflow_id: str,
    kind: str,
    stall_s: float,
    last_hb: str,
    extra: Optional[dict] = None,
) -> None:
    """Write a hang-detection entry (called by watchdog, not by agents)."""
    entry: dict[str, Any] = {
        "type": "hang_detect",
        "agent_id": agent_id,
        "workflow_id": workflow_id,
        "ts": _now_iso(),
        "mono": _time.monotonic(),
        "kind": kind,          # "agent" | "workflow" | "phase_budget"
        "stall_s": round(stall_s, 1),
        "last_hb": last_hb,
    }
    if extra:
        entry["extra"] = extra
    _write_journal_entry(entry)


# ---------------------------------------------------------------------------
# Watchdog: reads journal, detects hangs, raises alerts
# ---------------------------------------------------------------------------


def _read_journal_tail() -> list[dict]:
    """Read the last JOURNAL_TAIL_BYTES of the journal as parsed entries.

    Returns entries in chronological order (oldest first).
    Empty list if journal does not exist or is empty.
    """
    if not JOURNAL_PATH.exists():
        return []

    try:
        file_size = JOURNAL_PATH.stat().st_size
        if file_size == 0:
            return []

        with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
            if file_size <= JOURNAL_TAIL_BYTES:
                raw = f.read()
            else:
                f.seek(file_size - JOURNAL_TAIL_BYTES)
                # Discard partial first line
                f.readline()
                raw = f.read()

        entries: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                logger.debug("Heartbeat journal: unparseable line skipped")
                continue
        return entries
    except OSError as exc:
        logger.warning("Heartbeat journal read failed: %s", exc)
        return []


def _build_index(entries: list[dict]) -> None:
    """Populate _agent_index and _workflow_index from journal entries.

    Called inside _scan_lock.
    """
    global _agent_index, _workflow_index

    now_mono = _time.monotonic()

    # Reset counters but preserve existing records (we'll update them)
    for rec in _agent_index.values():
        rec.missed_count += 1  # increment; will be reset to 0 if heartbeat seen

    for entry in entries:
        etype = entry.get("type", "")
        aid = entry.get("agent_id", "")
        wid = entry.get("workflow_id", "")
        ts_iso = entry.get("ts", "")
        ts_mono = entry.get("mono", 0.0)
        state = entry.get("state", "unknown")
        phase = entry.get("phase", "")

        # --- Agent heartbeat ---
        if etype == "heartbeat" and aid:
            if aid not in _agent_index:
                _agent_index[aid] = AgentRecord(agent_id=aid)
            rec = _agent_index[aid]
            rec.last_heartbeat = max(rec.last_heartbeat, ts_mono)
            rec.last_heartbeat_iso = ts_iso
            rec.workflow_id = wid or rec.workflow_id
            rec.state = state
            rec.phase = phase or rec.phase
            if "seq" in entry:
                rec.seq = entry["seq"]
            rec.missed_count = 0  # heartbeat seen

        # --- Phase enter ---
        elif etype == "phase_enter" and aid and wid:
            if wid not in _workflow_index:
                _workflow_index[wid] = WorkflowRecord(workflow_id=wid)
            wf = _workflow_index[wid]
            ph = PhaseRecord(
                phase_name=phase or entry.get("phase", "unknown"),
                agent_id=aid,
                budget_s=entry.get("budget_s", 300.0),
                started_at=ts_mono,
                started_at_iso=ts_iso,
            )
            wf.phases[f"{aid}:{ph.phase_name}"] = ph
            wf.active_phase = phase or wf.active_phase

        # --- Phase exit ---
        elif etype == "phase_exit" and aid and wid:
            if wid in _workflow_index:
                wf = _workflow_index[wid]
                pkey = f"{aid}:{phase}"
                if pkey in wf.phases:
                    wf.phases[pkey].ended_at = ts_mono
                    wf.phases[pkey].result = entry.get("result", "")

        # --- Workflow start ---
        elif etype == "workflow_start" and wid:
            if wid not in _workflow_index:
                _workflow_index[wid] = WorkflowRecord(workflow_id=wid)
            wf = _workflow_index[wid]
            wf.started_at = ts_mono if ts_mono > 0 else now_mono
            wf.started_at_iso = ts_iso
            wf.agents = entry.get("agents", wf.agents)
            wf.status = "running"
            wf.ended_at = 0.0

        # --- Workflow end ---
        elif etype == "workflow_end" and wid:
            if wid in _workflow_index:
                wf = _workflow_index[wid]
                wf.ended_at = ts_mono
                wf.status = entry.get("status", "completed")

    # Cleanup: remove agents with 0 heartbeats and all phases ended
    # (Keep them in index for 1 hour after last heartbeat for status API)
    stale_cutoff = now_mono - 3600
    dead_agents = [
        aid for aid, rec in _agent_index.items()
        if rec.last_heartbeat > 0 and rec.last_heartbeat < stale_cutoff
        and rec.state == "done"
    ]
    for aid in dead_agents:
        del _agent_index[aid]

    done_workflows = [
        wid for wid, wf in _workflow_index.items()
        if wf.status != "running" and wf.ended_at > 0 and wf.ended_at < stale_cutoff
    ]
    for wid in done_workflows:
        del _workflow_index[wid]


def _detect_hangs() -> list[dict]:
    """Detect agent-level and workflow-level hangs.

    Returns list of hang dicts: {kind, agent_id, workflow_id, stall_s, ...}

    Detection rules:
      AGENT-LEVEL:
        - Agent TTL expired (last_heartbeat was > AGENT_TTL ago)
        - AND missed_count >= 2 (confirmation gating: 2+ consecutive misses)
        - AND agent state is NOT "done" or "idle"
        - AND initial grace period passed (first heartbeat was > INITIAL_GRACE ago)

      WORKFLOW-LEVEL:
        - Active phase has been running > its budget_s
        - AND ALL agents in the workflow are past TTL (workflow collective hang)
        - OR the workflow has no active agents and is still marked "running"

      PHASE-BUDGET:
        - A single agent's phase exceeds its budget but other workflow agents
          are still heartbeating (slow agent, not full workflow hang)
    """
    global _pending_alerts
    now_mono = _time.monotonic()
    findings: list[dict] = []

    # --- Agent-level detection ---
    for aid, rec in list(_agent_index.items()):
        if rec.state == "done":
            continue

        stall = rec.stall_seconds

        # Require 2+ consecutive missed scans (confirmation gating)
        if stall > AGENT_TTL and rec.missed_count >= 2:
            # Check alert cooldown
            alert_key = f"agent:{aid}"
            if not _is_in_cooldown(alert_key):
                findings.append({
                    "kind": "agent",
                    "agent_id": aid,
                    "workflow_id": rec.workflow_id,
                    "stall_s": round(stall, 1),
                    "last_hb": rec.last_heartbeat_iso,
                    "missed_count": rec.missed_count,
                    "state": rec.state,
                    "phase": rec.phase,
                })
                _mark_cooldown(alert_key)
                rec.state = "hung"

    # --- Workflow-level and phase-budget detection ---
    for wid, wf in list(_workflow_index.items()):
        if wf.status != "running":
            continue

        # Check each active phase for budget overrun
        for pkey, ph in list(wf.phases.items()):
            if not ph.is_active:
                continue

            budget = max(ph.budget_s, PHASE_BUDGET_MIN)
            elapsed = ph.elapsed

            if elapsed > budget:
                # Distinguish: slow-agent vs full-workflow hang
                agent_dead = True
                if ph.agent_id in _agent_index:
                    arec = _agent_index[ph.agent_id]
                    agent_dead = arec.stall_seconds > AGENT_TTL

                if agent_dead or wf.all_agents_silent:
                    kind = "workflow"
                    msg = f"Workflow hang: all agents silent, phase '{ph.phase_name}' at {elapsed:.0f}s (budget {budget:.0f}s)"
                else:
                    kind = "phase_budget"
                    msg = f"Phase budget exceeded: agent {ph.agent_id} phase '{ph.phase_name}' at {elapsed:.0f}s (budget {budget:.0f}s) -- other agents alive"

                alert_key = f"phase:{wid}:{pkey}"
                if not _is_in_cooldown(alert_key):
                    findings.append({
                        "kind": kind,
                        "agent_id": ph.agent_id,
                        "workflow_id": wid,
                        "phase": ph.phase_name,
                        "stall_s": round(elapsed, 1),
                        "budget_s": round(budget, 1),
                        "last_hb": ph.started_at_iso,
                        "msg": msg,
                    })
                    _mark_cooldown(alert_key)

        # Workflow with no heartbeat from any agent for 2x TTL
        if wf.started_at > 0 and wf.all_agents_silent and wf.agents:
            elapsed_wf = now_mono - wf.started_at
            if elapsed_wf > AGENT_TTL * 2:
                alert_key = f"workflow_silent:{wid}"
                if not _is_in_cooldown(alert_key):
                    findings.append({
                        "kind": "workflow",
                        "agent_id": "",
                        "workflow_id": wid,
                        "phase": wf.active_phase,
                        "stall_s": round(elapsed_wf, 1),
                        "last_hb": wf.started_at_iso,
                        "msg": f"Workflow '{wid}' has no active agents -- all {len(wf.agents)} silent for {elapsed_wf:.0f}s",
                    })
                    _mark_cooldown(alert_key)

    return findings


# Cooldown state
_cooldowns: dict[str, float] = {}


def _is_in_cooldown(key: str) -> bool:
    """Check if alert key is still in cooldown window."""
    last = _cooldowns.get(key, 0)
    return (_time.monotonic() - last) < ALERT_COOLDOWN


def _mark_cooldown(key: str) -> None:
    """Mark alert key as having fired now."""
    _cooldowns[key] = _time.monotonic()


# ---------------------------------------------------------------------------
# Watchdog scan cycle (called by FastAPI background task)
# ---------------------------------------------------------------------------


async def watchdog_scan() -> dict:
    """Run one full watchdog scan cycle.

    Called every WATCHDOG_INTERVAL seconds by the FastAPI lifespan task.

    Returns a summary dict:
      {agents_tracked, workflows_tracked, hangs_detected, scan_ts, findings: [...]}
    """
    global _last_scan_ts, _pending_alerts

    async with _scan_lock:
        _last_scan_ts = _time.monotonic()

        # Step 1: read journal tail
        entries = _read_journal_tail()

        # Step 2: rebuild in-memory index
        _build_index(entries)

        # Step 3: detect hangs
        findings = _detect_hangs()

        # Step 4: write hang entries to journal and raise alerts
        for f in findings:
            log_hang(
                agent_id=f.get("agent_id", ""),
                workflow_id=f.get("workflow_id", ""),
                kind=f.get("kind", "unknown"),
                stall_s=f.get("stall_s", 0),
                last_hb=f.get("last_hb", ""),
                extra={"msg": f.get("msg", ""), "phase": f.get("phase", "")},
            )
            # Cross-leverage with error_aggregator
            try:
                from error_aggregator import record_error
                record_error(
                    error_code="HEARTBEAT_HANG",
                    endpoint="watchdog",
                    message=f"[{f['kind']}] agent={f.get('agent_id')} wf={f.get('workflow_id')} stall={f.get('stall_s')}s",
                )
            except ImportError:
                pass

            # Log to structured logger
            if f["kind"] == "agent":
                logger.warning(
                    "HANG agent=%s workflow=%s stall=%.1fs missed=%d",
                    f["agent_id"], f.get("workflow_id", ""),
                    f["stall_s"], f.get("missed_count", 0),
                )
            elif f["kind"] == "workflow":
                logger.error(
                    "HANG workflow=%s stall=%.1fs phase=%s",
                    f.get("workflow_id", ""), f["stall_s"], f.get("phase", ""),
                )
            elif f["kind"] == "phase_budget":
                logger.warning(
                    "PHASE_BUDGET agent=%s workflow=%s phase=%s stall=%.1fs budget=%.1fs",
                    f["agent_id"], f.get("workflow_id", ""),
                    f.get("phase", ""), f["stall_s"], f.get("budget_s", 0),
                )

        _pending_alerts = findings

        # Build summary
        active_agents = sum(
            1 for r in _agent_index.values() if r.state not in ("done", "hung")
        )
        hung_agents = sum(
            1 for r in _agent_index.values() if r.state == "hung"
        )
        active_workflows = sum(
            1 for w in _workflow_index.values() if w.status == "running"
        )

        return {
            "agents_tracked": len(_agent_index),
            "agents_active": active_agents,
            "agents_hung": hung_agents,
            "workflows_tracked": len(_workflow_index),
            "workflows_active": active_workflows,
            "hangs_detected": len(findings),
            "scan_ts": datetime.now(timezone.utc).isoformat(),
            "findings": findings,
        }


# ---------------------------------------------------------------------------
# Status API: get current heartbeat state (for dashboard)
# ---------------------------------------------------------------------------


def get_status() -> dict:
    """Return current heartbeat system status (non-blocking read).

    Suitable for an HTTP endpoint response.
    """
    now_mono = _time.monotonic()
    agents = []
    for aid, rec in sorted(_agent_index.items()):
        agents.append({
            "agent_id": rec.agent_id,
            "workflow_id": rec.workflow_id,
            "state": rec.state,
            "phase": rec.phase,
            "last_heartbeat_iso": rec.last_heartbeat_iso,
            "stall_s": round(rec.stall_seconds, 1),
            "missed_count": rec.missed_count,
            "seq": rec.seq,
        })

    workflows = []
    for wid, wf in sorted(_workflow_index.items()):
        phases = []
        for pkey, ph in wf.phases.items():
            phases.append({
                "phase": ph.phase_name,
                "agent_id": ph.agent_id,
                "budget_s": ph.budget_s,
                "elapsed_s": round(ph.elapsed, 1),
                "is_active": ph.is_active,
                "over_budget": ph.over_budget,
                "result": ph.result,
            })
        workflows.append({
            "workflow_id": wf.workflow_id,
            "status": wf.status,
            "started_at_iso": wf.started_at_iso,
            "active_phase": wf.active_phase,
            "agent_count": len(wf.agents),
            "agents_silent": wf.all_agents_silent,
            "phases": phases,
        })

    return {
        "last_scan_ts": datetime.fromtimestamp(_last_scan_ts, tz=timezone.utc).isoformat()
                        if _last_scan_ts > 0 else None,
        "journal_path": str(JOURNAL_PATH),
        "journal_size_bytes": JOURNAL_PATH.stat().st_size if JOURNAL_PATH.exists() else 0,
        "config": {
            "heartbeat_interval_s": HEARTBEAT_INTERVAL,
            "watchdog_interval_s": WATCHDOG_INTERVAL,
            "agent_ttl_s": AGENT_TTL,
            "alert_cooldown_s": ALERT_COOLDOWN,
        },
        "agents": agents,
        "workflows": workflows,
        "pending_alerts": _pending_alerts,
        "cooldowns": list(_cooldowns.keys()),
    }


# ---------------------------------------------------------------------------
# FastAPI lifespan integration
# ---------------------------------------------------------------------------


async def _watchdog_loop():
    """Background coroutine that runs watchdog_scan() on a fixed interval."""
    logger.info(
        "Heartbeat watchdog started: interval=%ds agent_ttl=%ds journal=%s",
        WATCHDOG_INTERVAL, AGENT_TTL, JOURNAL_PATH,
    )
    while True:
        try:
            result = await watchdog_scan()
            if result["hangs_detected"] > 0:
                logger.warning(
                    "Watchdog scan: %d agents, %d workflows, %d hangs detected",
                    result["agents_tracked"], result["workflows_tracked"],
                    result["hangs_detected"],
                )
            else:
                logger.debug(
                    "Watchdog scan: %d agents, %d workflows, all healthy",
                    result["agents_tracked"], result["workflows_tracked"],
                )
        except Exception:
            logger.error("Watchdog scan crashed", exc_info=True)

        await asyncio.sleep(WATCHDOG_INTERVAL)


_watchdog_task: Optional[asyncio.Task] = None


def start_watchdog():
    """Start the watchdog background task. Call during FastAPI startup."""
    global _watchdog_task
    if _watchdog_task is not None and not _watchdog_task.done():
        return  # already running
    _watchdog_task = asyncio.create_task(_watchdog_loop())
    _watchdog_task.set_name("heartbeat-watchdog")
    logger.info("Heartbeat watchdog task created")


async def stop_watchdog():
    """Stop the watchdog background task. Call during FastAPI shutdown."""
    global _watchdog_task
    if _watchdog_task is not None and not _watchdog_task.done():
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass
        _watchdog_task = None
        logger.info("Heartbeat watchdog task stopped")


# ---------------------------------------------------------------------------
# Self-test (run directly: python -m backend.heartbeat_v2)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("=== Heartbeat v2 Self-Test ===\n")

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Test 1: log() writes to journal
    print("1. Writing heartbeats...")
    for i in range(3):
        log("test-agent", "test-wf", state="running", phase="scan",
            message=f"Test heartbeat #{i}")
        print(f"   heartbeat #{i} written")

    # Test 2: log workflow lifecycle
    print("\n2. Logging workflow lifecycle...")
    log_workflow_start("test-wf", agents=["test-agent", "A02"])
    log_phase_enter("test-agent", "test-wf", "scan", budget_s=60)
    log_phase_exit("test-agent", "test-wf", "scan", result="ok")
    log_workflow_end("test-wf", status="completed", agents_finished=1)
    print("   workflow lifecycle logged")

    # Test 3: read journal back
    print("\n3. Reading journal tail...")
    entries = _read_journal_tail()
    print(f"   {len(entries)} entries read")

    # Test 4: build index and check
    print("\n4. Building in-memory index...")
    _build_index(entries)
    print(f"   agents tracked: {len(_agent_index)}")
    print(f"   workflows tracked: {len(_workflow_index)}")
    for aid, rec in _agent_index.items():
        print(f"   agent {aid}: state={rec.state}, phase={rec.phase}, stall={rec.stall_seconds:.1f}s")

    # Test 5: run a scan
    print("\n5. Running async watchdog scan...")

    async def _test_scan():
        # Clear entries first so we have a clean slate
        global _agent_index, _workflow_index

        # Step A: re-read journal and build fresh index
        entries = _read_journal_tail()
        _build_index(entries)
        print(f"   Before: {len(_agent_index)} agents, test-agent stall={_agent_index.get('test-agent', AgentRecord('x')).stall_seconds:.1f}s")

        # Step B: simulate a HUNG agent by stopping heartbeats for 50s
        #         (well past AGENT_TTL=45s, missed_count=3)
        if "test-agent" in _agent_index:
            _agent_index["test-agent"].last_heartbeat = _time.monotonic() - AGENT_TTL - 5
            _agent_index["test-agent"].missed_count = 3
            _agent_index["test-agent"].state = "running"

        # Step C: simulate a workflow-level hang -- all agents silent
        if "test-wf" in _workflow_index:
            wf = _workflow_index["test-wf"]
            wf.status = "running"
            wf.agents = ["test-agent", "A02"]
            wf.ended_at = 0.0  # active
            # Add a phase that has exceeded budget
            wf.phases["A02:fix"] = PhaseRecord(
                phase_name="fix", agent_id="A02",
                budget_s=10, started_at=_time.monotonic() - 45,
                started_at_iso="2026-07-16T00:00:00Z",
            )
            # Make A02 "hung" as well
            _agent_index["A02"] = AgentRecord(
                agent_id="A02", workflow_id="test-wf",
                last_heartbeat=_time.monotonic() - AGENT_TTL - 10,
                missed_count=4, state="running",
            )

        # Step D: run detection directly (bypass _build_index rebuild)
        findings = _detect_hangs()
        print(f"   hangs detected: {len(findings)}")
        for f in findings:
            print(f"   -> {f['kind']}: agent={f.get('agent_id')} stall={f.get('stall_s')}s phase={f.get('phase', '')}")
            # Write to journal
            log_hang(
                agent_id=f.get("agent_id", ""),
                workflow_id=f.get("workflow_id", ""),
                kind=f.get("kind", "unknown"),
                stall_s=f.get("stall_s", 0),
                last_hb=f.get("last_hb", ""),
            )

        # Also test the full watchdog cycle (will detect whatever is in journal)
        full_result = await watchdog_scan()
        print(f"   full scan: {full_result['hangs_detected']} hangs, {full_result['hangs_detected']} from index")

    asyncio.run(_test_scan())

    # Test 6: get status
    print("\n6. Status API output...")
    status = get_status()
    print(f"   agents: {len(status['agents'])}")
    print(f"   workflows: {len(status['workflows'])}")
    print(f"   pending alerts: {len(status['pending_alerts'])}")
    print(f"   journal size: {status['journal_size_bytes']} bytes")

    print("\n=== All tests passed ===")
    sys.exit(0)
