# file: src/core/decision_log.py

from __future__ import annotations

import csv
import os
import re
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from src.core.config import location_block_reason as configured_location_block_reason
    from src.core.config import normalize_state
except ImportError:  # pragma: no cover - supports direct script execution with src on sys.path
    from core.config import location_block_reason as configured_location_block_reason
    from core.config import normalize_state

try:
    from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
    from src.core.discovery import DIESEL_COMMERCIAL, GAS_WORK_LOCAL, discover_vehicle_candidates
except ImportError:  # pragma: no cover
    from core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
    from core.discovery import DIESEL_COMMERCIAL, GAS_WORK_LOCAL, discover_vehicle_candidates


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 60
RETENTION_DAYS = 14
LEGACY_LOG_PATTERNS = (
    "multi_*.log",
    "proxibid_govdeals_*.log",
    "govdeals_daemon.log.*",
    "public_surplus_daemon.log.*",
)
_last_cleanup_day: str | None = None

PIPELINE_STAGES = (
    "SCRAPED",
    "LOCATION_FILTER",
    "BROAD_DISCOVERY",
    "PARSING",
    "STRATEGY_CLASSIFICATION",
    "BID_TIME_GATE",
    "ALERT_ROUTING",
)

REASON_GROUPS = (
    "LOCATION",
    "TIME",
    "BID",
    "DISCOVERY",
    "PARSING_MISSING_DATA",
    "STRATEGY_LOW_CEILING",
    "STRATEGY_WRONG_MODEL",
    "STRATEGY_WRONG_FUEL",
    "CONDITION_HARD_REJECT",
    "DIESEL_COMMERCIAL_REJECT",
    "CONSUMER_GAS_REJECT",
    "GAS_WORK_LOCAL_REJECT",
    "ALERT_DEDUPED",
    "UNKNOWN",
)

LOCATION_REASONS = {"outside_target_state", "location_state_unknown", "blocked_location"}
TIME_REASONS = {"missing_time", "outside_time_window", "beyond_scan_window", "already_closed"}
BID_REASONS = {"bid_too_high", "blocked_bid", "missing_bid"}
DISCOVERY_REASONS = {"no_broad_discovery_match"}
MISSING_DATA_REASONS = {
    "missing_required_data",
    "missing_time",
    "missing_mileage",
    "missing_engine",
    "missing_trim",
    "missing_cab",
    "missing_drivetrain",
    "missing_vin",
    "unknown_state",
}
LOW_CEILING_REASONS = {
    "strategy_reject_low_ceiling",
    "consumer_gas_low_ceiling",
    "base_trim_low_ceiling",
    "weak_configuration",
    "mileage_too_high",
    "year_too_old",
}
WRONG_MODEL_REASONS = {"not_target_strategy_match", "blocked_make", "blocked_model"}
WRONG_FUEL_REASONS = {"not_gas_or_diesel_target", "blocked_engine", "consumer_gas_wrong_fuel"}
CONDITION_REASONS = {"hard_exclude", "title_problem", "rust", "major_mechanical"}
ALERT_DEDUPED_REASONS = {"alert_deduped", "already_alerted"}

REASON_ALIASES = {
    "blocked_location": "location_state_unknown",
    "no_secs": "missing_time",
    "no_time_parsed": "missing_time",
    "no_time_found": "missing_time",
    "time_missing": "missing_time",
    "time_too_high": "outside_time_window",
    "too_early": "outside_time_window",
    "outside_alert_window": "outside_time_window",
    "blocked_bid": "bid_too_high",
    "price_over_cap": "bid_too_high",
    "over_price_cap": "bid_too_high",
    "no_current_bid": "missing_bid",
    "blocked_mileage": "mileage_too_high",
    "consumer_gas_mileage_too_high": "mileage_too_high",
    "consumer_gas_missing_mileage": "missing_mileage",
    "consumer_gas_missing_required_data": "missing_required_data",
    "consumer_gas_age_too_old": "year_too_old",
    "consumer_gas_year_too_old": "year_too_old",
    "consumer_gas_base_trim_low_ceiling": "base_trim_low_ceiling",
    "consumer_gas_weak_configuration": "weak_configuration",
    "consumer_gas_low_ceiling_model": "consumer_gas_low_ceiling",
    "consumer_gas_score_below_alert": "consumer_gas_low_ceiling",
    "consumer_gas_watchlist_score": "strategy_reject_low_ceiling",
    "consumer_gas_wrong_fuel": "consumer_gas_wrong_fuel",
    "consumer_gas_rust": "rust",
    "consumer_gas_title_problem": "title_problem",
    "consumer_gas_major_mechanical": "major_mechanical",
    "blocked_hard_exclude": "hard_exclude",
    "blocked_keyword": "hard_exclude",
    "hard_exclude_hit": "hard_exclude",
    "no_title": "title_problem",
    "salvage": "title_problem",
    "parts_only": "title_problem",
    "bad_engine": "major_mechanical",
    "bad_transmission": "major_mechanical",
    "major_rust": "rust",
    "diesel_commercial_existing_no_match": "not_target_strategy_match",
    "gas_work_local_not_configured": "not_target_strategy_match",
    "no_strategy_candidate": "not_target_strategy_match",
    "not_target": "not_target_strategy_match",
    "alert_sent": "alert_gate_passed",
}

PRIMARY_REASON_PRIORITY = (
    "outside_target_state",
    "location_state_unknown",
    "missing_time",
    "beyond_scan_window",
    "outside_time_window",
    "bid_too_high",
    "missing_bid",
    "hard_exclude",
    "title_problem",
    "rust",
    "major_mechanical",
    "no_broad_discovery_match",
    "missing_mileage",
    "missing_required_data",
    "consumer_gas_low_ceiling",
    "strategy_reject_low_ceiling",
    "mileage_too_high",
    "year_too_old",
    "base_trim_low_ceiling",
    "weak_configuration",
    "not_target_strategy_match",
    "not_gas_or_diesel_target",
    "consumer_gas_wrong_fuel",
    "alert_deduped",
    "already_alerted",
    "watchlist_no_twilio",
)

MISSING_FIELD_NOTES = {
    "missing_time": "missing_time prevented alert eligibility.",
    "missing_mileage": (
        "missing_mileage mattered because CONSUMER_GAS_LIQUID requires reliable "
        "mileage for ALERT."
    ),
    "missing_engine": "missing_engine did not block discovery but can prevent a higher score.",
    "missing_trim": "missing_trim limits consumer gas configuration scoring.",
    "missing_cab": "missing_cab limits consumer gas configuration scoring.",
    "missing_drivetrain": "missing_drivetrain limits consumer gas configuration scoring.",
    "missing_vin": "missing_vin can slow manual quote lookup but does not block discovery.",
    "unknown_state": "unknown_state blocked the location filter.",
    "missing_required_data": "missing_required_data kept the strategy from reaching alert confidence.",
}

_REQUESTED_CSV_FIELDS = [
    "run_date",
    "scan_timestamp",
    "timestamp",
    "source",
    "site",
    "listing_id",
    "asset_id",
    "url",
    "title",
    "location",
    "city",
    "state",
    "normalized_state",
    "location_allowed",
    "location_valid",
    "location_block_reason",
    "broad_discovery_candidate",
    "decision_stage",
    "strategy_classification",
    "final_classification",
    "classification",
    "target_strategy",
    "strategies_considered",
    "target",
    "blocked",
    "should_alert",
    "alert_gate_passed",
    "primary_reason_group",
    "primary_reject_reason",
    "secondary_reasons",
    "block_reason",
    "block_reasons",
    "discovery_reasons",
    "parsing_reasons",
    "strategy_reasons",
    "gate_reasons",
    "alert_reasons",
    "missing_fields",
    "missing_data_notes",
    "bid_cents",
    "bid_display",
    "current_bid",
    "secs",
    "minutes_left",
    "year",
    "make",
    "model",
    "trim",
    "cab",
    "drivetrain",
    "engine",
    "fuel",
    "mileage",
    "mileage_display",
    "vin",
    "score",
    "consumer_gas_score",
    "next_action",
]

_LEGACY_CSV_FIELDS = [
    "timestamp",
    "source",
    "url",
    "title",
    "location",
    "state",
    "normalized_state",
    "location_allowed",
    "location_block_reason",
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
    "classification",
    "block_reason",
    "target_strategy",
    "strategies_considered",
    "discovery_reasons",
    "decision_reasons",
    "positive_signals",
    "negative_signals",
    "block_reasons",
    "score",
    "consumer_gas_score",
    "consumer_gas_model_key",
    "next_action",
    "model_year",
    "vehicle_age",
    "parsed_make",
    "parsed_model",
    "parsed_year",
    "parsed_vehicle_age",
    "parsed_mileage",
    "parsed_trim",
    "parsed_cab",
    "parsed_drivetrain",
    "parsed_engine",
    "parsed_fuel",
    "carvana_score",
    "carvana_model_key",
    "carvana_positive_signals",
    "carvana_negative_signals",
    "carvana_block_reasons",
    "carvana_next_action",
    "vin",
    "trim",
    "cab",
    "drivetrain",
    "fuel",
    "mileage_display",
]

CSV_FIELDS = list(dict.fromkeys(_REQUESTED_CSV_FIELDS + _LEGACY_CSV_FIELDS))


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


def cleanup_legacy_log_files() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    deleted_count = 0

    for glob_pattern in LEGACY_LOG_PATTERNS:
        for path in LOG_DIR.glob(glob_pattern):
            if path.name.startswith(("decisions_", "daily_report_", "health_")):
                continue

            try:
                path.unlink()
                deleted_count += 1
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"Could not delete legacy log {path}: {exc}")

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


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() not in {"none", "not found", "unknown"}
    return True


def _has_explicit_value(row: dict[str, Any], key: str) -> bool:
    return key in row and _has_value(row.get(key))


def _has_explicit_false(row: dict[str, Any], key: str) -> bool:
    return key in row and row.get(key) not in (None, "") and not _as_bool(row.get(key))


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    numeric = _as_float(value)
    if numeric is None:
        return None
    return int(round(numeric))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _dedupe(values: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text.lower() in {"none", "not found"}:
            continue
        if text not in seen:
            out.append(text)
            seen.add(text)
    return out


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (list, tuple, set)):
        return ";".join(str(item) for item in value)
    return str(value)


def _slug_reason(reason: str) -> str:
    text = str(reason or "").strip().lower()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def _canonical_reason(reason: Any, *, discovered: bool = True) -> str:
    slug = _slug_reason(str(reason))
    if not slug:
        return ""
    canonical = REASON_ALIASES.get(slug, slug)
    if canonical == "not_gas_or_diesel_target" and not discovered:
        return ""
    return canonical


def _parse_current_bid_cents(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value) * 100))
    text = str(value).replace("$", "").replace(",", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return int(round(float(match.group(0)) * 100))
    except ValueError:
        return None


def _format_dollars_from_cents(value: Any) -> str:
    cents = _as_int(value)
    if cents is None:
        return ""
    dollars = cents / 100.0
    if abs(dollars - round(dollars)) < 1e-9:
        return f"${int(round(dollars)):,}"
    return f"${dollars:,.2f}"


def _site_name(row: dict[str, Any]) -> str:
    return str(row.get("site") or row.get("source") or "Unknown").strip() or "Unknown"


def _strategy_classification(row: dict[str, Any]) -> str:
    classification = str(row.get("strategy_classification") or row.get("classification") or "").strip().upper()
    return classification if classification in {"ALERT", "WATCHLIST", "REJECT"} else ""


def _time_seconds(row: dict[str, Any]) -> float | None:
    secs = _as_float(row.get("secs"))
    if secs is not None:
        return secs
    minutes = _as_float(row.get("minutes_left"))
    if minutes is not None:
        return minutes * 60
    return None


def _has_known_time(row: dict[str, Any]) -> bool:
    return _time_seconds(row) is not None


def _time_required(row: dict[str, Any], discovered: bool) -> bool:
    return (
        discovered
        or _has_value(row.get("target_strategy"))
        or _as_bool(row.get("target"))
        or _as_bool(row.get("gas_match"))
        or _as_bool(row.get("diesel_match"))
    )


def _normalize_identity(row: dict[str, Any]) -> None:
    timestamp = str(row.get("scan_timestamp") or row.get("timestamp") or datetime.now().isoformat(timespec="seconds"))
    row["timestamp"] = row.get("timestamp") or timestamp
    row["scan_timestamp"] = row.get("scan_timestamp") or timestamp
    row["run_date"] = row.get("run_date") or timestamp[:10]

    site = _site_name(row)
    row["site"] = row.get("site") or site
    row["source"] = row.get("source") or site

    listing_id = row.get("listing_id") or row.get("asset_id") or row.get("auction_id") or row.get("id")
    if listing_id not in (None, ""):
        row["listing_id"] = str(listing_id)
    if row.get("asset_id") in (None, "") and listing_id not in (None, ""):
        row["asset_id"] = str(listing_id)

    if not row.get("location"):
        city = str(row.get("city") or "").strip()
        state = str(row.get("state") or row.get("normalized_state") or "").strip()
        row["location"] = ", ".join(part for part in (city, state) if part)


def _normalize_money_and_time(row: dict[str, Any]) -> None:
    bid_cents = _as_int(row.get("bid_cents"))
    if bid_cents is None:
        bid_cents = _parse_current_bid_cents(row.get("current_bid"))
    if bid_cents is not None:
        row["bid_cents"] = bid_cents
        row["bid_display"] = row.get("bid_display") or _format_dollars_from_cents(bid_cents)
        if row.get("current_bid") in (None, ""):
            row["current_bid"] = bid_cents / 100.0
    else:
        row["bid_display"] = row.get("bid_display") or ""

    secs = _time_seconds(row)
    if secs is not None:
        row["secs"] = int(round(secs))
        if row.get("minutes_left") in (None, ""):
            minutes = secs / 60
            row["minutes_left"] = int(minutes) if abs(minutes - int(minutes)) < 1e-9 else round(minutes, 1)


def _raw_location_value(row: dict[str, Any]) -> Any:
    for key in ("state", "normalized_state", "locationState", "stateDesc", "region_text", "location"):
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _normalize_location(row: dict[str, Any]) -> None:
    raw_state = _raw_location_value(row)
    normalized = normalize_state(raw_state)
    reason = str(row.get("location_block_reason") or "").strip()
    if not reason:
        reason = configured_location_block_reason(raw_state)

    if not reason and _has_explicit_false(row, "location_allowed"):
        reason = configured_location_block_reason(raw_state) or "location_state_unknown"
    if not reason and _has_explicit_false(row, "location_valid"):
        reason = configured_location_block_reason(raw_state) or "location_state_unknown"

    row["normalized_state"] = row.get("normalized_state") or normalized
    row["location_block_reason"] = reason
    row["location_allowed"] = False if reason else True
    row["location_valid"] = row["location_allowed"]

    if reason:
        row["target"] = False
        row["blocked"] = True


def _discover_for_report(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return discover_vehicle_candidates(row)
    except Exception:
        return {
            "discovered": False,
            "discovery_reasons": [],
            "strategy_candidates": [],
        }


def _normalize_discovery(row: dict[str, Any]) -> None:
    considered = _as_list(row.get("strategies_considered"))
    discovery_reasons = _as_list(row.get("discovery_reasons"))

    should_probe_discovery = (
        not considered
        and not discovery_reasons
        and _as_bool(row.get("location_allowed"))
    )
    if should_probe_discovery:
        discovery = _discover_for_report(row)
        considered = _as_list(discovery.get("strategy_candidates"))
        discovery_reasons = _as_list(discovery.get("discovery_reasons"))

    discovered = bool(considered)
    if not discovered and _as_bool(row.get("location_allowed")):
        discovery_reasons = ["no_broad_discovery_match"]

    row["strategies_considered"] = _dedupe(considered)
    row["discovery_reasons"] = _dedupe(discovery_reasons)
    row["broad_discovery_candidate"] = discovered


def _strategy_reasons_from_row(row: dict[str, Any], *, discovered: bool) -> list[str]:
    fields = (
        "strategy_reasons",
        "block_reasons",
        "block_reason",
        "decision_reasons",
        "negative_signals",
        "carvana_block_reasons",
        "carvana_negative_signals",
    )
    reasons: list[str] = []
    for field in fields:
        for reason in _as_list(row.get(field)):
            canonical = _canonical_reason(reason, discovered=discovered)
            if not canonical:
                continue
            if canonical in LOCATION_REASONS or canonical in TIME_REASONS or canonical in BID_REASONS:
                continue
            if canonical == "alert_gate_passed":
                continue
            reasons.append(canonical)

    for keyword in _as_list(row.get("hard_exclude_keywords_matched")):
        canonical = _canonical_reason(keyword, discovered=discovered) or "hard_exclude"
        reasons.append(canonical if canonical in CONDITION_REASONS else "hard_exclude")

    if discovered and _has_explicit_false(row, "mileage_ok"):
        reasons.append("mileage_too_high")

    if discovered and _has_explicit_false(row, "year_ok") and _has_explicit_value(row, "year"):
        reasons.append("year_too_old")

    if discovered and _has_explicit_false(row, "make_ok") and _has_explicit_value(row, "make"):
        reasons.append("blocked_make")

    if discovered and _has_explicit_false(row, "model_ok") and _has_explicit_value(row, "model"):
        reasons.append("blocked_model")

    if discovered and _has_explicit_false(row, "engine_ok") and _has_explicit_value(row, "engine"):
        reasons.append("blocked_engine")

    if _as_bool(row.get("hard_exclude_hit")):
        reasons.append("hard_exclude")

    strategy_classification = _strategy_classification(row)
    if discovered and strategy_classification == "REJECT" and not reasons:
        reasons.append("not_target_strategy_match")

    return _dedupe(reasons)


def _is_consumer_gas_candidate(row: dict[str, Any]) -> bool:
    considered = set(_as_list(row.get("strategies_considered")))
    return (
        row.get("target_strategy") == CONSUMER_GAS_LIQUID
        or CONSUMER_GAS_LIQUID in considered
        or _has_value(row.get("consumer_gas_score"))
        or _has_value(row.get("consumer_gas_model_key"))
    )


def _missing_fields_from_row(row: dict[str, Any], *, discovered: bool) -> list[str]:
    missing: list[str] = []
    if row.get("location_block_reason") == "location_state_unknown":
        missing.append("unknown_state")

    if _time_required(row, discovered) and not _has_known_time(row):
        missing.append("missing_time")

    if not discovered and not _has_value(row.get("target_strategy")):
        return _dedupe(missing)

    if _is_consumer_gas_candidate(row):
        if not _has_value(row.get("mileage")) and not _has_value(row.get("parsed_mileage")):
            missing.append("missing_mileage")
        if not _has_value(row.get("engine")) and not _has_value(row.get("parsed_engine")):
            missing.append("missing_engine")
        if not _has_value(row.get("trim")) and not _has_value(row.get("parsed_trim")):
            missing.append("missing_trim")
        if not _has_value(row.get("cab")) and not _has_value(row.get("parsed_cab")):
            missing.append("missing_cab")
        if not _has_value(row.get("drivetrain")) and not _has_value(row.get("parsed_drivetrain")):
            missing.append("missing_drivetrain")
        if not _has_value(row.get("vin")):
            missing.append("missing_vin")
    elif discovered:
        if not _has_value(row.get("engine")) and not _has_value(row.get("parsed_engine")):
            missing.append("missing_engine")

    return _dedupe(missing)


def _gate_reasons_from_row(row: dict[str, Any], *, discovered: bool) -> list[str]:
    if row.get("location_block_reason"):
        return []

    gate_reasons: list[str] = []
    candidate_for_gates = _time_required(row, discovered)

    if candidate_for_gates and _has_explicit_false(row, "bid_under_limit"):
        if _has_value(row.get("bid_cents")) or _has_value(row.get("current_bid")):
            gate_reasons.append("bid_too_high")
        else:
            gate_reasons.append("missing_bid")

    if candidate_for_gates and _has_explicit_false(row, "close_soon_flag"):
        if _has_known_time(row):
            gate_reasons.append("outside_time_window")
        else:
            gate_reasons.append("missing_time")
    elif candidate_for_gates and not _has_known_time(row) and _has_explicit_false(row, "should_alert"):
        gate_reasons.append("missing_time")

    if candidate_for_gates and _has_explicit_false(row, "target"):
        gate_reasons.append("target_false")
    if candidate_for_gates and _as_bool(row.get("blocked")):
        gate_reasons.append("blocked")

    for reason in _as_list(row.get("gate_reasons")):
        canonical = _canonical_reason(reason, discovered=discovered)
        if canonical:
            gate_reasons.append(canonical)

    return _dedupe(gate_reasons)


def _legacy_watchlist_near_miss(row: dict[str, Any], *, discovered: bool) -> bool:
    return (
        discovered
        and not _as_bool(row.get("should_alert"))
        and (_as_bool(row.get("gas_match")) or _as_bool(row.get("diesel_match")))
        and 1 <= _failed_final_filter_count(row) <= 2
    )


def _final_classification(row: dict[str, Any], *, discovered: bool) -> str:
    if _as_bool(row.get("should_alert")):
        return "ALERT"

    strategy_classification = _strategy_classification(row)
    if strategy_classification == "WATCHLIST":
        return "WATCHLIST"

    if not strategy_classification and _legacy_watchlist_near_miss(row, discovered=discovered):
        return "WATCHLIST"

    return "REJECT"


def _alert_reasons_from_row(
    row: dict[str, Any],
    *,
    final_classification: str,
    gate_reasons: list[str],
) -> list[str]:
    reasons: list[str] = []
    for reason in _as_list(row.get("alert_reasons")):
        canonical = _canonical_reason(reason, discovered=True)
        reasons.append(canonical or reason)

    if final_classification == "ALERT":
        reasons.append("alert_gate_passed")
    elif final_classification == "WATCHLIST":
        reasons.append("watchlist_no_twilio")
    elif gate_reasons:
        reasons.append("alert_gate_failed")

    return _dedupe(reasons)


def _primary_reason(
    *,
    final_classification: str,
    location_reason: str,
    discovered: bool,
    parsing_reasons: list[str],
    strategy_reasons: list[str],
    gate_reasons: list[str],
    alert_reasons: list[str],
) -> str:
    if final_classification == "ALERT":
        return ""

    candidates: list[str] = []
    if location_reason:
        candidates.append(location_reason)

    candidates.extend(gate_reasons)

    if any(reason in CONDITION_REASONS for reason in strategy_reasons):
        candidates.extend(reason for reason in strategy_reasons if reason in CONDITION_REASONS)

    if not discovered and not location_reason:
        candidates.append("no_broad_discovery_match")

    candidates.extend(parsing_reasons)
    candidates.extend(strategy_reasons)
    candidates.extend(alert_reasons)

    deduped = _dedupe(candidates)
    for preferred in PRIMARY_REASON_PRIORITY:
        if preferred in deduped:
            return preferred

    return deduped[0] if deduped else "unknown_reject_reason"


def _stage_for_reason(reason: str, final_classification: str) -> str:
    if final_classification == "ALERT":
        return "ALERT_ROUTING"
    if reason in LOCATION_REASONS:
        return "LOCATION_FILTER"
    if reason in DISCOVERY_REASONS:
        return "BROAD_DISCOVERY"
    if reason in {
        "missing_mileage",
        "missing_required_data",
        "missing_engine",
        "missing_trim",
        "missing_cab",
        "missing_drivetrain",
        "missing_vin",
        "unknown_state",
    }:
        return "PARSING"
    if reason in TIME_REASONS or reason in BID_REASONS:
        return "BID_TIME_GATE"
    if reason in ALERT_DEDUPED_REASONS or reason == "watchlist_no_twilio":
        return "ALERT_ROUTING"
    if reason:
        return "STRATEGY_CLASSIFICATION"
    return "SCRAPED"


def primary_reason_group(reason: str, row: dict[str, Any] | None = None) -> str:
    if not reason:
        return ""

    if reason in LOCATION_REASONS:
        return "LOCATION"
    if reason in TIME_REASONS:
        return "TIME"
    if reason in BID_REASONS:
        return "BID"
    if reason in DISCOVERY_REASONS:
        return "DISCOVERY"
    if reason in MISSING_DATA_REASONS:
        return "PARSING_MISSING_DATA"
    if reason in LOW_CEILING_REASONS:
        return "STRATEGY_LOW_CEILING"
    if reason in WRONG_FUEL_REASONS:
        return "STRATEGY_WRONG_FUEL"
    if reason in CONDITION_REASONS:
        return "CONDITION_HARD_REJECT"
    if reason in ALERT_DEDUPED_REASONS:
        return "ALERT_DEDUPED"

    row = row or {}
    considered = set(_as_list(row.get("strategies_considered")))
    target_strategy = row.get("target_strategy")
    if reason in WRONG_MODEL_REASONS:
        if target_strategy == CONSUMER_GAS_LIQUID or CONSUMER_GAS_LIQUID in considered:
            return "CONSUMER_GAS_REJECT"
        if target_strategy == DIESEL_COMMERCIAL or DIESEL_COMMERCIAL in considered:
            return "DIESEL_COMMERCIAL_REJECT"
        if target_strategy == GAS_WORK_LOCAL or GAS_WORK_LOCAL in considered:
            return "GAS_WORK_LOCAL_REJECT"
        return "STRATEGY_WRONG_MODEL"

    if str(reason).startswith("consumer_gas_") or target_strategy == CONSUMER_GAS_LIQUID:
        return "CONSUMER_GAS_REJECT"
    if str(reason).startswith("diesel_") or target_strategy == DIESEL_COMMERCIAL:
        return "DIESEL_COMMERCIAL_REJECT"
    if str(reason).startswith("gas_work_") or target_strategy == GAS_WORK_LOCAL:
        return "GAS_WORK_LOCAL_REJECT"
    return "UNKNOWN"


def _missing_data_notes(missing_fields: list[str]) -> list[str]:
    return [MISSING_FIELD_NOTES[field] for field in missing_fields if field in MISSING_FIELD_NOTES]


def _build_trace(row: dict[str, Any]) -> dict[str, Any]:
    discovered = bool(_as_bool(row.get("broad_discovery_candidate")) or _as_list(row.get("strategies_considered")))
    location_reason = str(row.get("location_block_reason") or "").strip()
    strategy_reasons = _strategy_reasons_from_row(row, discovered=discovered)
    parsing_reasons = _missing_fields_from_row(row, discovered=discovered)
    gate_reasons = _gate_reasons_from_row(row, discovered=discovered)
    final_classification = _final_classification(row, discovered=discovered)
    alert_reasons = _alert_reasons_from_row(
        row,
        final_classification=final_classification,
        gate_reasons=gate_reasons,
    )

    primary = _primary_reason(
        final_classification=final_classification,
        location_reason=location_reason,
        discovered=discovered,
        parsing_reasons=parsing_reasons,
        strategy_reasons=strategy_reasons,
        gate_reasons=gate_reasons,
        alert_reasons=alert_reasons,
    )
    stage = _stage_for_reason(primary, final_classification)

    if location_reason:
        secondary: list[str] = []
    elif primary == "no_broad_discovery_match":
        secondary = []
    elif final_classification == "ALERT":
        secondary = []
    else:
        secondary = [
            reason
            for reason in _dedupe(parsing_reasons + strategy_reasons + gate_reasons + alert_reasons)
            if reason != primary and reason not in {"alert_gate_failed", "watchlist_no_twilio"}
        ]

    block_reasons = _dedupe(([primary] if primary else []) + secondary)
    alert_gate_passed = final_classification == "ALERT" and _as_bool(row.get("should_alert"))

    return {
        "decision_stage": stage,
        "final_classification": final_classification,
        "primary_reason_group": primary_reason_group(primary, row),
        "primary_reject_reason": primary,
        "secondary_reasons": secondary,
        "block_reasons": block_reasons,
        "block_reason": ";".join(block_reasons),
        "parsing_reasons": parsing_reasons,
        "strategy_reasons": strategy_reasons,
        "gate_reasons": gate_reasons,
        "alert_reasons": alert_reasons,
        "alert_gate_passed": alert_gate_passed,
        "missing_fields": parsing_reasons,
        "missing_data_notes": _missing_data_notes(parsing_reasons),
    }


def normalize_decision_record(record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record or {})
    _normalize_identity(row)
    _normalize_money_and_time(row)
    _normalize_location(row)
    _normalize_discovery(row)
    if not row.get("strategy_classification"):
        row["strategy_classification"] = _strategy_classification(row)

    trace = _build_trace(row)
    row.update(trace)

    # The old column now mirrors final reporting classification; the raw strategy
    # decision is still represented by target_strategy and strategy_reasons.
    row["classification"] = row["final_classification"]
    return row


def compute_block_reasons(record: dict[str, Any]) -> list[str]:
    return _as_list(normalize_decision_record(record).get("block_reasons"))


def _normalized_row(record: dict[str, Any]) -> dict[str, str]:
    row = normalize_decision_record(record)
    return {field: _format_value(row.get(field)) for field in CSV_FIELDS}


def _ensure_csv_schema(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames == CSV_FIELDS:
            return
        existing_rows = list(reader)

    tmp_path = path.with_suffix(".schema.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for existing_row in existing_rows:
            writer.writerow(_normalized_row(existing_row))

    tmp_path.replace(path)


def log_decision(record: dict[str, Any]) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        cleanup_old_decision_logs_once_per_day()
        row = _normalized_row(record)
        day_key = row["timestamp"][:10] if row.get("timestamp") else _today_key()

        with _daily_log_lock(day_key):
            path = _csv_path(day_key)
            if path.exists():
                _ensure_csv_schema(path)
            file_has_rows = path.exists() and path.stat().st_size > 0

            for attempt in range(3):
                try:
                    with path.open("a", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
                        if not file_has_rows:
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
    return _as_list(row.get("block_reasons") or row.get("block_reason"))


def _row_classification(row: dict[str, Any]) -> str:
    classification = str(row.get("final_classification") or "").strip().upper()
    if classification in {"ALERT", "WATCHLIST", "REJECT"}:
        return classification
    return _final_classification(row, discovered=_is_broad_discovery_candidate(row))


def classify_decision(record: dict[str, Any]) -> str:
    return _row_classification(normalize_decision_record(record))


def _failed_final_filter_count(row: dict[str, Any]) -> int:
    failed = 0
    if _has_explicit_false(row, "location_valid") or _has_explicit_false(row, "location_allowed"):
        failed += 1
    if _has_explicit_false(row, "bid_under_limit"):
        failed += 1
    if _has_explicit_false(row, "mileage_ok"):
        failed += 1
    if _has_explicit_false(row, "close_soon_flag"):
        failed += 1
    if _as_bool(row.get("hard_exclude_hit")):
        failed += 1
    return failed


def _is_broad_discovery_candidate(row: dict[str, Any]) -> bool:
    return bool(_as_bool(row.get("broad_discovery_candidate")) or _as_list(row.get("strategies_considered")))


def _is_inside_target_state(row: dict[str, Any]) -> bool:
    return _as_bool(row.get("location_allowed")) and not row.get("location_block_reason")


def _candidate_strategies(row: dict[str, Any]) -> list[str]:
    considered = _as_list(row.get("strategies_considered"))
    return considered or ["NONE"]


def _near_miss_sort_key(row: dict[str, Any]) -> tuple[int, float, float, str]:
    classification_rank = {"WATCHLIST": 0, "REJECT": 1, "ALERT": 2}
    minutes = _as_float(row.get("minutes_left"))
    score = _as_float(row.get("consumer_gas_score") or row.get("score") or row.get("carvana_score"))
    return (
        classification_rank.get(_row_classification(row), 9),
        -(score if score is not None else -999999.0),
        minutes if minutes is not None else 999999.0,
        row.get("title") or "",
    )


def _money_display(row: dict[str, Any]) -> str:
    return str(row.get("bid_display") or row.get("current_bid") or "Not found")


def _location_display(row: dict[str, Any]) -> str:
    location = row.get("location")
    if location:
        return str(location)
    return ", ".join(str(row.get(key) or "") for key in ("city", "state") if row.get(key)) or "Not found"


def _vehicle_detail_parts(row: dict[str, Any]) -> list[str]:
    parts = []
    for key in ("year", "make", "model", "trim", "cab", "drivetrain", "engine"):
        value = row.get(key) or row.get(f"parsed_{key}")
        if value not in (None, ""):
            parts.append(f"{key}={value}")
    mileage = row.get("mileage_display") or row.get("mileage") or row.get("parsed_mileage")
    if mileage not in (None, ""):
        parts.append(f"mileage={mileage}")
    return parts


def _listing_line(row: dict[str, Any]) -> str:
    classification = _row_classification(row)
    title = row.get("title") or "Untitled"
    site = _site_name(row)
    strategy = row.get("target_strategy") or ",".join(_as_list(row.get("strategies_considered"))) or "NONE"
    score = row.get("consumer_gas_score") or row.get("score") or row.get("carvana_score") or ""
    bid = _money_display(row)
    minutes = row.get("minutes_left") or "Not found"
    location = _location_display(row)
    primary = row.get("primary_reject_reason") or "None"
    secondary_values = _as_list(row.get("secondary_reasons"))
    secondary = ";".join(secondary_values) if secondary_values else "None"
    details = "; ".join(_vehicle_detail_parts(row))
    url = row.get("url") or ""
    score_part = f" | score={score}" if score else ""
    detail_part = f" | parsed={details}" if details else ""
    return (
        f"- [{classification}] [{site}] {title} | bid={bid} | minutes={minutes} | "
        f"location={location} | strategy={strategy}{score_part} | primary={primary} | "
        f"secondary={secondary}{detail_part} | {url}"
    )


def _reason_counts(rows: list[dict[str, Any]], field: str) -> Counter:
    reason_counts = Counter()
    for row in rows:
        if field in {"primary_reject_reason", "primary_reason_group"}:
            reason = row.get(field)
            if reason:
                reason_counts[str(reason)] += 1
        else:
            reason_counts.update(_as_list(row.get(field)))
    return reason_counts


def _counter_lines(counter: Counter, *, empty_label: str = "none", limit: int | None = None) -> list[str]:
    if not counter:
        return [f"- {empty_label}: 0"]
    items = counter.most_common(limit)
    return [f"- {key}: {count}" for key, count in items]


def _alerts_sent_count(rows: list[dict[str, Any]]) -> int:
    explicit_sent = 0
    for row in rows:
        alert_reasons = set(_as_list(row.get("alert_reasons")))
        block_reasons = set(_block_reasons(row))
        if alert_reasons.intersection({"sent_sms", "sent_voice"}) or "alert_sent" in block_reasons:
            explicit_sent += 1
    if explicit_sent:
        return explicit_sent
    return sum(1 for row in rows if _row_classification(row) == "ALERT")


def _summary_body(rows: list[dict[str, Any]]) -> list[str]:
    classification_counts = Counter(_row_classification(row) for row in rows)
    in_state_rows = [row for row in rows if _is_inside_target_state(row)]
    outside_state_count = sum(1 for row in rows if row.get("location_block_reason") == "outside_target_state")
    unknown_state_count = sum(1 for row in rows if row.get("location_block_reason") == "location_state_unknown")
    broad_rows = [row for row in in_state_rows if _is_broad_discovery_candidate(row)]
    strategy_counts = Counter()
    for row in in_state_rows:
        strategies = _candidate_strategies(row)
        if strategies == ["NONE"]:
            strategy_counts["NONE"] += 1
        else:
            for strategy in strategies:
                strategy_counts[strategy] += 1

    primary_group_counts = _reason_counts(rows, "primary_reason_group")
    primary_reason_counts = _reason_counts(rows, "primary_reject_reason")
    secondary_reason_counts = _reason_counts(rows, "secondary_reasons")
    missing_field_counts = Counter()
    for row in broad_rows:
        missing_field_counts.update(_as_list(row.get("missing_fields")))

    lines = [
        f"total listings scanned: {len(rows)}",
        f"rows outside target state: {outside_state_count}",
        f"rows with unknown state: {unknown_state_count}",
        f"rows inside target state: {len(in_state_rows)}",
        f"broad discovery candidates: {len(broad_rows)}",
        "candidates by strategy:",
        f"- {DIESEL_COMMERCIAL}: {strategy_counts[DIESEL_COMMERCIAL]}",
        f"- {CONSUMER_GAS_LIQUID}: {strategy_counts[CONSUMER_GAS_LIQUID]}",
        f"- {GAS_WORK_LOCAL}: {strategy_counts[GAS_WORK_LOCAL]}",
        f"- NONE: {strategy_counts['NONE']}",
        "count by final_classification:",
        f"- ALERT: {classification_counts['ALERT']}",
        f"- WATCHLIST: {classification_counts['WATCHLIST']}",
        f"- REJECT: {classification_counts['REJECT']}",
        f"alert eligible after gates: {sum(1 for row in rows if _as_bool(row.get('alert_gate_passed')))}",
        f"alerts actually sent/reported: {_alerts_sent_count(rows)}",
        "count by primary_reason_group:",
    ]
    lines.extend(_counter_lines(primary_group_counts))
    lines.append("count by primary_reject_reason:")
    lines.extend(_counter_lines(primary_reason_counts))
    lines.append("count by secondary_reasons:")
    lines.extend(_counter_lines(secondary_reason_counts))
    lines.append("top missing data fields among discovered candidates:")
    lines.extend(_counter_lines(missing_field_counts, limit=10))
    lines.append("sample rejects by primary reason:")
    lines.extend(_sample_reject_lines(rows))
    return lines


def _sample_reject_lines(rows: list[dict[str, Any]], *, max_reasons: int = 5, per_reason: int = 2) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if _row_classification(row) == "ALERT":
            continue
        primary = row.get("primary_reject_reason") or "unknown_reject_reason"
        grouped[str(primary)].append(row)

    if not grouped:
        return ["- none"]

    lines: list[str] = []
    ordered_reasons = Counter({reason: len(items) for reason, items in grouped.items()}).most_common(max_reasons)
    for reason, _count in ordered_reasons:
        lines.append(f"- {reason}:")
        for row in sorted(grouped[reason], key=_near_miss_sort_key)[:per_reason]:
            lines.append(f"  {_listing_line(row)}")
    return lines


def _has_positive_strategy_signal(row: dict[str, Any]) -> bool:
    if _as_list(row.get("positive_signals")) or _as_list(row.get("carvana_positive_signals")):
        return True
    score = _as_float(row.get("consumer_gas_score") or row.get("score") or row.get("carvana_score"))
    if score is not None and score > 0:
        return True
    return bool(row.get("target_strategy") or _as_bool(row.get("gas_match")) or _as_bool(row.get("diesel_match")))


def _is_hard_rejected(row: dict[str, Any]) -> bool:
    reasons = set(_block_reasons(row) + _as_list(row.get("strategy_reasons")))
    return bool(reasons.intersection(CONDITION_REASONS))


def _is_near_miss(record: dict[str, Any]) -> bool:
    return (
        _row_classification(record) != "ALERT"
        and _is_inside_target_state(record)
        and _is_broad_discovery_candidate(record)
        and not _is_hard_rejected(record)
        and _has_positive_strategy_signal(record)
    )


def _near_miss_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted([row for row in rows if _is_near_miss(row)], key=_near_miss_sort_key)[:20]


def _is_relevant_missing_data_row(row: dict[str, Any]) -> bool:
    if not _as_list(row.get("missing_fields")):
        return False
    if _is_broad_discovery_candidate(row) or _has_value(row.get("target_strategy")):
        return True
    return _is_inside_target_state(row) and (
        _as_bool(row.get("gas_match"))
        or _as_bool(row.get("diesel_match"))
        or _has_positive_strategy_signal(row)
    )


def _missing_data_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    examples = [row for row in rows if _is_relevant_missing_data_row(row)]
    return sorted(examples, key=_near_miss_sort_key)[:10]


def _missing_data_line(row: dict[str, Any]) -> str:
    missing_fields = _as_list(row.get("missing_fields"))
    notes = _as_list(row.get("missing_data_notes"))
    missing = ";".join(missing_fields) if missing_fields else "None"
    why = " ".join(notes) if notes else "No missing-data impact recorded."
    return f"{_listing_line(row)} | missing={missing} | why={why}"


def render_daily_report(rows: list[dict[str, Any]], day_key: str | None = None) -> str:
    day_key = day_key or _today_key()
    normalized_rows = [dict(row) for row in rows]

    alerts = [row for row in normalized_rows if _row_classification(row) == "ALERT"]
    near_misses = _near_miss_rows(normalized_rows)
    govdeals_rows = [row for row in normalized_rows if _site_name(row) == "GovDeals"]
    public_surplus_rows = [row for row in normalized_rows if _site_name(row) == "Public Surplus"]

    lines = [
        f"Daily Decision Report - {day_key}",
        "",
        "Pipeline stages: SCRAPED -> LOCATION_FILTER -> BROAD_DISCOVERY -> PARSING -> "
        "STRATEGY_CLASSIFICATION -> BID_TIME_GATE -> ALERT_ROUTING",
        "",
        "1. Combined Summary",
    ]

    lines.extend(_summary_body(normalized_rows))
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
    lines.append("top 20 discovered candidate near misses:")
    if near_misses:
        lines.extend(_listing_line(row) for row in near_misses)
    else:
        lines.append("- none")

    lines.extend(["", "6. Missing Data Examples"])
    missing_data = _missing_data_rows(normalized_rows)
    if missing_data:
        lines.extend(_missing_data_line(row) for row in missing_data)
    else:
        lines.append("- none")

    return os.linesep.join(lines) + os.linesep


def update_daily_report(day_key: str | None = None) -> None:
    day_key = day_key or _today_key()
    rows = _read_rows(day_key)
    report_path = _report_path(day_key)
    tmp_path = report_path.with_suffix(".tmp")
    tmp_path.write_text(render_daily_report(rows, day_key), encoding="utf-8")
    tmp_path.replace(report_path)
