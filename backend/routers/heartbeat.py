"""
Router: Heartbeat v2 status and control endpoints.

Provides:
  GET  /api/heartbeat/status       -- Full heartbeat system status (dashboard)
  GET  /api/heartbeat/agents       -- Agent listing only
  GET  /api/heartbeat/workflows    -- Workflow listing only
  GET  /api/heartbeat/alerts       -- Pending alerts only
  POST /api/heartbeat/log          -- Write a heartbeat entry from external agents

Cross-leverage:
  - error_aggregator:  hang alerts flow through record_error() for dashboard visibility
  - chat_logger:        heartbeat journal is JSONL for grep/sed/jq post-hoc analysis
  - oracle:             watchdog confidence scoring uses confirm-gating
  - rate_limiter:       API endpoint is lightweight (no lock contention)
"""

from __future__ import annotations

import time as _time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/heartbeat", tags=["heartbeat"])


def _require_heartbeat():
    """Lazy-import heartbeat_v2 to avoid import-time side effects."""
    from heartbeat_v2 import (
        get_status, log, log_phase_enter, log_phase_exit,
        log_workflow_start, log_workflow_end, log_info,
        start_watchdog, stop_watchdog, watchdog_scan,
        HEARTBEAT_INTERVAL, WATCHDOG_INTERVAL, AGENT_TTL,
    )
    return {
        "get_status": get_status,
        "log": log,
        "log_phase_enter": log_phase_enter,
        "log_phase_exit": log_phase_exit,
        "log_workflow_start": log_workflow_start,
        "log_workflow_end": log_workflow_end,
        "log_info": log_info,
        "start_watchdog": start_watchdog,
        "stop_watchdog": stop_watchdog,
        "watchdog_scan": watchdog_scan,
        "HEARTBEAT_INTERVAL": HEARTBEAT_INTERVAL,
        "WATCHDOG_INTERVAL": WATCHDOG_INTERVAL,
        "AGENT_TTL": AGENT_TTL,
    }


# ---------------------------------------------------------------------------
# GET /api/heartbeat/status
# ---------------------------------------------------------------------------


@router.get("/status")
async def heartbeat_status():
    """Return full heartbeat system status for the monitoring dashboard.

    Response includes:
      - System config (intervals, TTL, cooldown)
      - Per-agent records (state, phase, stall time, missed count)
      - Per-workflow records (status, phases, budget status)
      - Pending alerts (hangs detected in last scan)
    """
    hb = _require_heartbeat()
    return JSONResponse({
        "success": True,
        "data": hb["get_status"](),
    })


# ---------------------------------------------------------------------------
# GET /api/heartbeat/agents
# ---------------------------------------------------------------------------


@router.get("/agents")
async def heartbeat_agents():
    """Return agent records only (lightweight, for polling)."""
    hb = _require_heartbeat()
    status = hb["get_status"]()
    return JSONResponse({
        "success": True,
        "data": {
            "count": len(status["agents"]),
            "agents": status["agents"],
        },
    })


# ---------------------------------------------------------------------------
# GET /api/heartbeat/workflows
# ---------------------------------------------------------------------------


@router.get("/workflows")
async def heartbeat_workflows():
    """Return workflow records only."""
    hb = _require_heartbeat()
    status = hb["get_status"]()
    return JSONResponse({
        "success": True,
        "data": {
            "count": len(status["workflows"]),
            "workflows": status["workflows"],
        },
    })


# ---------------------------------------------------------------------------
# GET /api/heartbeat/alerts
# ---------------------------------------------------------------------------


@router.get("/alerts")
async def heartbeat_alerts():
    """Return pending alerts from the last watchdog scan."""
    hb = _require_heartbeat()
    status = hb["get_status"]()
    # Only include alerts from the last 10 minutes
    now_mono = _time.monotonic()
    recent = [
        a for a in status["pending_alerts"]
        if now_mono - a.get("stall_s", 0) < 600
    ]
    return JSONResponse({
        "success": True,
        "data": {
            "count": len(recent),
            "alerts": recent,
        },
    })


# ---------------------------------------------------------------------------
# POST /api/heartbeat/log -- external agents write heartbeats via HTTP
# ---------------------------------------------------------------------------


@router.post("/log")
async def heartbeat_log(request: Request):
    """Write a heartbeat entry from an external agent.

    Body (JSON):
      {
        "agent_id": "A01",           // required
        "workflow_id": "batch-1",    // optional
        "type": "heartbeat",         // heartbeat | phase_enter | phase_exit | workflow_start | workflow_end | log
        "state": "running",          // for heartbeat type
        "phase": "scan",             // for heartbeat/phase_enter/phase_exit types
        "message": "optional log",   // for log type
        "level": "info",             // for log type
        "budget_s": 120,             // for phase_enter type
        "result": "ok",              // for phase_exit type
        "agents": ["A01","A02"],     // for workflow_start type
        "status": "completed",       // for workflow_end type
        "agents_finished": 5,        // for workflow_end type
      }

    Returns: {"success": true, "written": true}
    """
    hb = _require_heartbeat()

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"success": False, "error": "Invalid JSON body"},
            status_code=400,
        )

    agent_id = (body.get("agent_id") or "").strip()
    entry_type = (body.get("type") or "heartbeat").strip()

    if not agent_id and entry_type not in ("workflow_start", "workflow_end"):
        return JSONResponse(
            {"success": False, "error": "agent_id is required for this entry type"},
            status_code=400,
        )

    workflow_id = (body.get("workflow_id") or "").strip()

    try:
        if entry_type == "heartbeat":
            hb["log"](
                agent_id=agent_id,
                workflow_id=workflow_id,
                state=body.get("state", "running"),
                phase=body.get("phase", ""),
                message=body.get("message", ""),
                level=body.get("level", "info"),
                extra=body.get("extra"),
            )
        elif entry_type == "phase_enter":
            hb["log_phase_enter"](
                agent_id=agent_id,
                workflow_id=workflow_id,
                phase=body.get("phase", "unknown"),
                budget_s=body.get("budget_s", 300.0),
            )
        elif entry_type == "phase_exit":
            hb["log_phase_exit"](
                agent_id=agent_id,
                workflow_id=workflow_id,
                phase=body.get("phase", "unknown"),
                result=body.get("result", "ok"),
            )
        elif entry_type == "workflow_start":
            hb["log_workflow_start"](
                workflow_id=workflow_id or body.get("workflow_id", "unknown"),
                agents=body.get("agents", []),
                phase=body.get("phase", "init"),
            )
        elif entry_type == "workflow_end":
            hb["log_workflow_end"](
                workflow_id=workflow_id or body.get("workflow_id", "unknown"),
                status=body.get("status", "completed"),
                agents_finished=body.get("agents_finished", 0),
            )
        elif entry_type == "log":
            hb["log_info"](
                agent_id=agent_id,
                workflow_id=workflow_id,
                message=body.get("message", ""),
                level=body.get("level", "info"),
                extra=body.get("extra"),
            )
        else:
            return JSONResponse(
                {"success": False, "error": f"Unknown entry type: {entry_type}"},
                status_code=400,
            )
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": f"Write failed: {e}"},
            status_code=500,
        )

    return JSONResponse({"success": True, "written": True})


# ---------------------------------------------------------------------------
# GET /api/heartbeat/config
# ---------------------------------------------------------------------------


@router.get("/config")
async def heartbeat_config():
    """Return current heartbeat configuration (read-only)."""
    hb = _require_heartbeat()
    return JSONResponse({
        "success": True,
        "data": {
            "heartbeat_interval_s": hb["HEARTBEAT_INTERVAL"],
            "watchdog_interval_s": hb["WATCHDOG_INTERVAL"],
            "agent_ttl_s": hb["AGENT_TTL"],
            "api_version": "v2",
        },
    })
