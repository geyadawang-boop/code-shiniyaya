"""
BiliSum Error Aggregator + Alerting
Deduplicates errors, tracks frequency, triggers alerts on thresholds.
Integrates with error_handlers.py via the record() function.
"""
import logging
import re
import time as _time
from collections import defaultdict
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("bilisum.error_aggregator")


# ============================================================
# Error Fingerprint (for deduplication)
# ============================================================

@dataclass
class ErrorFingerprint:
    """Unique identifier for an error class, used for aggregation."""
    error_code: str      # e.g., "BILI_API_ERROR"
    endpoint: str         # e.g., "GET /api/bili/info"
    message_pattern: str  # e.g., "video <bvid> not found" (with params stripped)


def fingerprint_error(error_code: str, endpoint: str, message: str) -> ErrorFingerprint:
    """Create a de-duplicable fingerprint from an error."""
    # Strip dynamic values (BV number, IDs, timestamps) from message
    pattern = message
    pattern = re.sub(r'BV[a-zA-Z0-9]+', '<bvid>', pattern)
    pattern = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}', '<uuid>', pattern)
    pattern = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<timestamp>', pattern)
    pattern = re.sub(r'\d+', '<num>', pattern)
    return ErrorFingerprint(
        error_code=error_code,
        endpoint=endpoint,
        message_pattern=pattern[:200]
    )


# ============================================================
# Error Ring Buffer
# ============================================================

class ErrorRingBuffer:
    """Rolling window error tracker with automatic aggregation."""

    def __init__(self, window_minutes: int = 60, max_errors: int = 10000):
        self.window = timedelta(minutes=window_minutes)
        self.max_errors = max_errors
        self.errors: List[dict] = []
        self.fingerprints: Dict[str, dict] = {}  # fingerprint_key -> aggregate
        self._burst_cooldown: Dict[str, float] = {}  # alert key -> last alarm time

    def record(self, error_code: str, endpoint: str, message: str,
               trace_id: str = "", details: dict = None):
        """Record an error occurrence."""
        fp = fingerprint_error(error_code, endpoint, message)
        fp_key = f"{fp.error_code}|{fp.endpoint}|{fp.message_pattern}"
        now = datetime.now()

        # Update aggregate
        if fp_key not in self.fingerprints:
            self.fingerprints[fp_key] = {
                "first_seen": now.isoformat(),
                "last_seen": now.isoformat(),
                "count": 0,
                "error_code": fp.error_code,
                "endpoint": fp.endpoint,
                "message_pattern": fp.message_pattern,
                "recent_trace_ids": []
            }

        agg = self.fingerprints[fp_key]
        agg["last_seen"] = now.isoformat()
        agg["count"] += 1
        if trace_id and len(agg["recent_trace_ids"]) < 5:
            agg["recent_trace_ids"].append(trace_id)

        # Store individual error
        self.errors.append({
            "timestamp": now.isoformat(),
            "error_code": error_code,
            "endpoint": endpoint,
            "message": message[:500],
            "trace_id": trace_id,
            "details": details or {}
        })

        # Trim old errors outside the window
        cutoff = now - self.window
        self.errors = [e for e in self.errors
                       if datetime.fromisoformat(e["timestamp"]) > cutoff]

        # Cap total errors
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]

        # Check alerts after recording
        self._check_and_fire_alerts()

    def get_summary(self) -> dict:
        """Get aggregated error summary for dashboard."""
        now = datetime.now()
        total = len(self.errors)

        # Sort aggregates by count (most frequent first)
        sorted_fps = sorted(
            self.fingerprints.values(),
            key=lambda x: x["count"],
            reverse=True
        )

        # Check for recent burst (>10 errors in 5 minutes)
        five_min_ago = now - timedelta(minutes=5)
        recent_count = sum(
            1 for e in self.errors
            if datetime.fromisoformat(e["timestamp"]) > five_min_ago
        )
        burst = recent_count > 10

        # Compute error rates
        fifteen_min_ago = now - timedelta(minutes=15)
        count_15m = sum(
            1 for e in self.errors
            if datetime.fromisoformat(e["timestamp"]) > fifteen_min_ago
        )
        error_rate_per_min = round(count_15m / 15, 1) if count_15m > 0 else 0

        return {
            "total_errors_window": total,
            "window_minutes": self.window.total_seconds() // 60,
            "unique_error_types": len(self.fingerprints),
            "burst_detected": burst,
            "burst_count_5min": recent_count,
            "error_rate_per_min": error_rate_per_min,
            "top_errors": [
                {
                    "error_code": fp["error_code"],
                    "endpoint": fp["endpoint"],
                    "count": fp["count"],
                    "pattern": fp["message_pattern"][:150],
                    "first_seen": fp["first_seen"],
                    "last_seen": fp["last_seen"],
                    "recent_traces": fp["recent_trace_ids"][-3:]
                }
                for fp in sorted_fps[:10]
            ]
        }

    def check_alerts(self) -> List[dict]:
        """Check if any alert thresholds are exceeded (non-side-effecting)."""
        alerts = []
        now = datetime.now()

        # Threshold 1: More than 50 errors in current window
        if len(self.errors) > 50:
            alerts.append({
                "level": "warning",
                "rule": "high_error_rate",
                "message": f"Over 50 errors in {self.window.total_seconds()//60} minutes",
                "current_count": len(self.errors),
                "timestamp": now.isoformat()
            })

        # Threshold 2: Single error type > 20 occurrences
        for fp_key, agg in self.fingerprints.items():
            if agg["count"] > 20:
                alerts.append({
                    "level": "warning",
                    "rule": "single_error_type_spike",
                    "message": f"Error '{agg['error_code']}' occurred {agg['count']} times",
                    "endpoint": agg["endpoint"],
                    "pattern": agg["message_pattern"][:150],
                    "timestamp": now.isoformat()
                })

        # Threshold 3: Burst (>10 errors in 5 minutes)
        five_min_ago = now - timedelta(minutes=5)
        recent = [e for e in self.errors
                   if datetime.fromisoformat(e["timestamp"]) > five_min_ago]
        if len(recent) > 10:
            alerts.append({
                "level": "critical",
                "rule": "error_burst",
                "message": f"Error burst: {len(recent)} errors in last 5 minutes",
                "errors_per_second": round(len(recent) / 300, 2),
                "timestamp": now.isoformat()
            })

        # Threshold 4: Database errors (P0)
        db_errors = [e for e in self.errors if "DATABASE" in e.get("error_code", "")]
        if len(db_errors) > 0:
            alerts.append({
                "level": "critical",
                "rule": "database_error_detected",
                "message": f"{len(db_errors)} database errors in current window",
                "recent_traces": [e.get("trace_id") for e in db_errors[-3:]],
                "timestamp": now.isoformat()
            })

        # Threshold 5: AI service errors (>5 in window = P1)
        ai_errors = [e for e in self.errors if "AI_API" in e.get("error_code", "")]
        if len(ai_errors) > 5:
            alerts.append({
                "level": "warning",
                "rule": "ai_service_degraded",
                "message": f"{len(ai_errors)} AI API errors in current window",
                "recent_traces": [e.get("trace_id") for e in ai_errors[-3:]],
                "timestamp": now.isoformat()
            })

        return alerts

    def _check_and_fire_alerts(self):
        """Check alerts and log them with cooldown."""
        alerts = self.check_alerts()
        now = _time.time()
        for alert in alerts:
            key = f"{alert['rule']}|{alert.get('endpoint', '')}|{alert.get('pattern', '')[:50]}"
            last_fire = self._burst_cooldown.get(key, 0)
            if now - last_fire > 120:  # 2-minute cooldown per alert type
                self._burst_cooldown[key] = now
                log_level = logging.CRITICAL if alert["level"] == "critical" else logging.WARNING
                logger.log(log_level, f"ALERT [{alert['rule']}]: {alert['message']}")


# ============================================================
# Global Instance
# ============================================================

error_buffer = ErrorRingBuffer(window_minutes=60)


# ============================================================
# Integration hook: called from error_handlers.py
# ============================================================

def record_error(error_code: str, endpoint: str, message: str,
                  trace_id: str = "", details: dict = None):
    """Hook called by exception handlers to record each error in the ring buffer."""
    try:
        error_buffer.record(error_code, endpoint, message, trace_id, details)
    except Exception:
        logger.debug("Error recording failed in aggregator", exc_info=True)
