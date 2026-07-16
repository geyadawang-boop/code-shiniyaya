"""
Router: /api/errors/* -- Frontend error telemetry + aggregated error dashboard
"""
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/errors", tags=["errors"])
logger = logging.getLogger("bilisum.errors")


@router.post("/report")
async def api_error_report(request: Request):
    """Receive batched frontend error reports for centralized logging."""
    try:
        body = await request.json()
        errors = body.get("errors", [])
        client_trace_id = body.get("clientTraceId", "unknown")

        for err in errors:
            logger.error(
                f"FRONTEND_ERROR [client={client_trace_id}] "
                f"[{err.get('type', 'unknown')}] "
                f"{err.get('message', '')[:200]} "
                f"at {err.get('filename', '')}:{err.get('lineno', 0)} "
                f"| bvid={err.get('currentBvid', '')} "
                f"| page={err.get('pageUrl', '')}",
                extra={
                    "traceId": client_trace_id,
                    "frontend_error": err
                }
            )

        return JSONResponse({
            "success": True,
            "received": len(errors)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/summary")
async def api_error_summary():
    """Get aggregated error summary for dashboard."""
    try:
        from error_aggregator import error_buffer
        return JSONResponse({
            "success": True,
            "data": error_buffer.get_summary()
        })
    except ImportError:
        return JSONResponse({
            "success": True,
            "data": {
                "total_errors_window": 0,
                "window_minutes": 60,
                "unique_error_types": 0,
                "burst_detected": False,
                "top_errors": [],
                "message": "Error aggregator not loaded"
            }
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/alerts")
async def api_error_alerts():
    """Get current active alerts."""
    try:
        from error_aggregator import error_buffer
        alerts = error_buffer.check_alerts()
        return JSONResponse({
            "success": True,
            "data": {
                "alerts": alerts,
                "count": len(alerts),
                "has_critical": any(a["level"] == "critical" for a in alerts)
            }
        })
    except ImportError:
        return JSONResponse({"success": True, "data": {"alerts": [], "count": 0, "has_critical": False}})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.get("/recent")
async def api_error_recent(limit: int = 50):
    """Get most recent N individual errors."""
    try:
        from error_aggregator import error_buffer
        return JSONResponse({
            "success": True,
            "data": {
                "count": min(limit, len(error_buffer.errors)),
                "errors": error_buffer.errors[-limit:]
            }
        })
    except ImportError:
        return JSONResponse({"success": True, "data": {"count": 0, "errors": []}})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
