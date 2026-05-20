# file: src/core/decision_log.py

from __future__ import annotations

import csv
import os
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 60
RETENTION_DAYS = 14
_last_cleanup_day: str | None = None

CSV_FIELDS = [
    "timestamp",
    "source",
    "url",
    "title",
    "location",
    "current_bid",
    "minutes_left",
    "year",
    "make",
    "model",
    "engine",
    "mileage",
    "gas_match",
    "diesel_match",
    "diesel_priority_level",
    "specialty_keywords_matched",
    "hard_exclude_hit",
    "hard_exclude_keywords_matched",
    "soft_warning_keywords_matched",
    "location_valid",
    "bid_under_limit",
    "mileage_ok",
    "close_soon_flag",
    "should_alert",
    "block_reason",
]


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _csv_path(day_key: str | None = None) -> Path:
    day_key = day_key or _today_key()
    return LOG_DIR / f"decisions_{day_key}.csv"


def _report_path(day_key: str | None = None) -> Path:
    day_key = day_key or _today_key()
    return LOG_DIR / f"daily_report_{day_key}.txt"


def _lock_path(day_key: str) -> Path:
    return LOG_DIR / f".decisions_{day_key}.lock"


def _date_from_log_name(path: Path, prefix: str, suffix: str) -> date | None:
    name = path.name
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None

    date_text = name[len(prefix):-len(suffix)]
    try:
        return datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return None


def cleanup_old_decision_logs(retention_days: int = RETENTION_DAYS) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    retention_days = max(1, retention_days)
    today = datetime.now().date()
    cutoff = today - timedelta(days=retention_days - 1)
    deleted_count = 0

    targets = (
        ("decisions_*.csv", "decisions_", ".csv"),
        ("daily_report_*.txt", "daily_report_", ".txt"),
    )

    for glob_pattern, prefix, suffix in targets:
        for path in LOG_DIR.glob(glob_pattern):
            file_date = _date_from_log_name(path, prefix, suffix)
            if file_date is None or file_date >= cutoff or file_date == today:
                continue

            try:
                path.unlink()
                deleted_count += 1
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"Could not delete old decision log {path}: {exc}")

    return deleted_count


def cleanup_old_decision_logs_once_per_day() -> int:
    global _last_cleanup_day

    day_key = _today_key()
    if _last_cleanup_day == day_key:
        return 0

    deleted_count = cleanup_old_decision_logs()
    _last_cleanup_day = day_key
    return deleted_count


@contextmanager
def _daily_log_lock(day_key: str):
    path = _lock_path(day_key)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd = None

    while fd is None:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}".encode("utf-8"))
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > LOCK_STALE_SECONDS:
                    path.unlink()
                    continue
            except OSError:
                pass

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for decision log lock: {path}")
            time.sleep(0.1)

    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (list, tuple, set)):
        return ";".join(str(item) for item in value)
    return str(value)


def compute_block_reasons(record: dict[str, Any]) -> list[str]:
    if _as_bool(record.get("should_alert")):
        return ["alert_sent"]

    reasons = []

    if not _as_bool(record.get("location_valid")):
        reasons.append("blocked_location")
    if not _as_bool(record.get("bid_under_limit")):
        reasons.append("blocked_bid")
    if not _as_bool(record.get("mileage_ok")):
        reasons.append("blocked_mileage")

    year_value = record.get("year")
    if year_value not in (None, "") and not _as_bool(record.get("year_ok", True)):
        reasons.append("blocked_year")

    make_value = record.get("make")
    if make_value not in (None, "") and not _as_bool(record.get("make_ok", True)):
        reasons.append("blocked_make")

    model_value = record.get("model")
    if model_value not in (None, "") and not _as_bool(record.get("model_ok", True)):
        reasons.append("blocked_model")

    engine_value = record.get("engine")
    if engine_value not in (None, "") and not _as_bool(record.get("engine_ok", True)):
        reasons.append("blocked_engine")

    if _as_bool(record.get("hard_exclude_hit")):
        reasons.append("blocked_hard_exclude")

    if not (_as_bool(record.get("gas_match")) or _as_bool(record.get("diesel_match"))):
        reasons.append("not_gas_or_diesel_target")

    if not _as_bool(record.get("close_soon_flag")):
        reasons.append("missing_time")

    return reasons or ["not_gas_or_diesel_target"]


def _normalized_row(record: dict[str, Any]) -> dict[str, str]:
    row = dict(record)
    row.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    row["block_reason"] = ";".join(compute_block_reasons(row))
    return {field: _format_value(row.get(field)) for field in CSV_FIELDS}


def log_decision(record: dict[str, Any]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cleanup_old_decision_logs_once_per_day()
        row = _normalized_row(record)
        day_key = row["timestamp"][:10] if row.get("timestamp") else _today_key()

        with _daily_log_lock(day_key):
            path = _csv_path(day_key)
            file_exists = path.exists()

            for attempt in range(3):
                try:
                    with path.open("a", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
                        if not file_exists:
                            writer.writeheader()
                        writer.writerow(row)
                    break
                except OSError:
                    if attempt == 2:
                        raise
                    time.sleep(0.2)

            update_daily_report(day_key)
    except Exception as exc:
        print(f"Decision logging failed: {exc}")


def _read_rows(day_key: str) -> list[dict[str, str]]:
    path = _csv_path(day_key)
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _block_reasons(row: dict[str, str]) -> list[str]:
    return _as_list(row.get("block_reason"))


def _failed_final_filter_count(row: dict[str, str]) -> int:
    failed = 0
    if not _as_bool(row.get("location_valid")):
        failed += 1
    if not _as_bool(row.get("bid_under_limit")):
        failed += 1
    if not _as_bool(row.get("mileage_ok")):
        failed += 1
    if not _as_bool(row.get("close_soon_flag")):
        failed += 1
    if _as_bool(row.get("hard_exclude_hit")):
        failed += 1
    return failed


def _near_miss_sort_key(row: dict[str, str]) -> tuple[float, float, str]:
    minutes = _as_float(row.get("minutes_left"))
    bid = _as_float(row.get("current_bid"))
    return (
        minutes if minutes is not None else 999999.0,
        bid if bid is not None else 999999999.0,
        row.get("title") or "",
    )


def _listing_line(row: dict[str, str]) -> str:
    title = row.get("title") or "Untitled"
    source = row.get("source") or "Unknown"
    bid = row.get("current_bid") or "Not found"
    minutes = row.get("minutes_left") or "Not found"
    location = row.get("location") or "Not found"
    reasons = row.get("block_reason") or "None"
    url = row.get("url") or ""
    return f"- [{source}] {title} | bid={bid} | minutes={minutes} | location={location} | reasons={reasons} | {url}"


def _reason_counts(rows: list[dict[str, str]]) -> Counter:
    reason_counts = Counter()
    for row in rows:
        reason_counts.update(_block_reasons(row))
    return reason_counts


def _summary_body(rows: list[dict[str, str]]) -> list[str]:
    alerts = [row for row in rows if _as_bool(row.get("should_alert"))]
    reason_counts = _reason_counts(rows)

    lines = [
        f"total listings scanned: {len(rows)}",
        f"total alerts sent: {len(alerts)}",
        "count by block_reason:",
    ]

    if reason_counts:
        for reason, count in sorted(reason_counts.items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- none: 0")

    return lines


def update_daily_report(day_key: str | None = None) -> None:
    day_key = day_key or _today_key()
    rows = _read_rows(day_key)

    alerts = [row for row in rows if _as_bool(row.get("should_alert"))]
    near_misses = [
        row
        for row in rows
        if not _as_bool(row.get("should_alert"))
        and (_as_bool(row.get("gas_match")) or _as_bool(row.get("diesel_match")))
        and 1 <= _failed_final_filter_count(row) <= 2
    ]
    near_misses = sorted(near_misses, key=_near_miss_sort_key)[:20]
    govdeals_rows = [row for row in rows if row.get("source") == "GovDeals"]
    public_surplus_rows = [row for row in rows if row.get("source") == "Public Surplus"]

    lines = [
        f"Daily Decision Report - {day_key}",
        "",
        "1. Combined Summary",
    ]

    lines.extend(_summary_body(rows))
    lines.extend(["", "2. GovDeals Summary"])
    lines.extend(_summary_body(govdeals_rows))
    lines.extend(["", "3. Public Surplus Summary"])
    lines.extend(_summary_body(public_surplus_rows))

    lines.extend(["", "4. Alerts Sent"])
    if alerts:
        lines.extend(_listing_line(row) for row in alerts)
    else:
        lines.append("- none")

    lines.extend(["", "5. Near Misses"])
    lines.append("top 20 near misses:")
    if near_misses:
        lines.extend(_listing_line(row) for row in near_misses)
    else:
        lines.append("- none")

    report_path = _report_path(day_key)
    tmp_path = report_path.with_suffix(".tmp")
    tmp_path.write_text(os.linesep.join(lines) + os.linesep, encoding="utf-8")
    tmp_path.replace(report_path)
