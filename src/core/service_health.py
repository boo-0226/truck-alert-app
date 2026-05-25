# file: src/core/service_health.py

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
GOVDEALS_HEALTH_FILE = LOG_DIR / "health_govdeals.json"
PUBLIC_SURPLUS_HEALTH_FILE = LOG_DIR / "health_public_surplus.json"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _same_utc_day(timestamp: str | None, day_key: str) -> bool:
    return bool(timestamp and timestamp[:10] == day_key)


def write_service_health(
    *,
    path: Path,
    source: str,
    service_name: str,
    scan_started: str,
    scan_completed: str,
    success: bool,
    alerts_this_run: int,
    error_message: str | None = None,
) -> dict[str, Any]:
    previous = _read_json(path)
    day_key = scan_completed[:10]
    previous_alerts_today = previous.get("alerts_today", 0)

    try:
        previous_alerts_today = int(previous_alerts_today)
    except (TypeError, ValueError):
        previous_alerts_today = 0

    if not _same_utc_day(previous.get("last_scan_completed"), day_key):
        previous_alerts_today = 0

    if success:
        alerts_today = previous_alerts_today + int(alerts_this_run or 0)
        status = "healthy"
        last_successful_scan = scan_completed
        last_error = None
        consecutive_errors = 0
    else:
        alerts_today = previous_alerts_today
        status = "error"
        last_successful_scan = previous.get("last_successful_scan")
        last_error = error_message or "Unknown error"
        try:
            consecutive_errors = int(previous.get("consecutive_errors", 0)) + 1
        except (TypeError, ValueError):
            consecutive_errors = 1

    payload = {
        "source": source,
        "status": status,
        "last_scan_started": scan_started,
        "last_scan_completed": scan_completed,
        "last_successful_scan": last_successful_scan,
        "alerts_today": alerts_today,
        "last_error": last_error,
        "consecutive_errors": consecutive_errors,
        "service_name": service_name,
    }
    _write_json(path, payload)
    return payload


def read_service_health(path: Path, source: str, service_name: str) -> dict[str, Any]:
    payload = _read_json(path)
    status = payload.get("status") or "unknown"
    if status == "ok":
        status = "healthy"
    if status not in ("healthy", "error", "unknown"):
        status = "unknown"

    last_successful_scan = payload.get("last_successful_scan")
    if not last_successful_scan and status == "healthy":
        last_successful_scan = payload.get("last_run_utc")

    return {
        "source": payload.get("source") or source,
        "status": status,
        "last_scan_started": payload.get("last_scan_started"),
        "last_scan_completed": payload.get("last_scan_completed"),
        "last_successful_scan": last_successful_scan,
        "alerts_today": payload.get("alerts_today", 0),
        "last_error": payload.get("last_error"),
        "consecutive_errors": payload.get("consecutive_errors", 0),
        "service_name": payload.get("service_name") or service_name,
    }


def _display_value(value: Any) -> str:
    if value in (None, ""):
        return "Not yet"
    return str(value)


def compose_daily_check_message() -> str:
    health_rows = [
        read_service_health(GOVDEALS_HEALTH_FILE, "GovDeals", "GovDealsSniper"),
        read_service_health(PUBLIC_SURPLUS_HEALTH_FILE, "Public Surplus", "PublicSurplusSniper"),
    ]

    lines = ["Daily Check:"]
    active_errors = []

    for row in health_rows:
        source = row["source"]
        status = row["status"]
        last_success = _display_value(row.get("last_successful_scan"))
        alerts_today = row.get("alerts_today", 0)
        consecutive_errors = row.get("consecutive_errors", 0)
        lines.append(
            f"{source}: {status} | last successful scan: {last_success} | "
            f"alerts today: {alerts_today} | consecutive errors: {consecutive_errors}"
        )
        if status != "healthy" and row.get("last_error"):
            active_errors.append(f"{source}: {row['last_error']}")

    if active_errors:
        lines.append("Active errors:")
        lines.extend(f"- {error}" for error in active_errors)
    else:
        lines.append("Active errors: none")

    return "\n".join(lines)
