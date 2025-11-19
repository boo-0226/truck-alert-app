# /src/core/timeparse.py
# Purpose: one robust time parser used by all sites.
# - Treat tz-naive strings as LOCAL time (DST-aware).
# - Handle ns/ms/s numeric epochs.
# - Apply a GovDeals-only 1h correction to direct-seconds and epoch-based times.

from __future__ import annotations
import typing, os
from datetime import datetime, timezone, timedelta
import time as _t

# ---------- Local timezone helper (DST-aware) ----------

def _local_tz():
    """Return the machine's local tz offset as a tzinfo, honoring DST."""
    off = -_t.timezone
    if _t.daylight and _t.localtime().tm_isdst > 0:
        off = -_t.altzone
    return timezone(timedelta(seconds=off))

# ---------- Numeric epoch parsing ----------

def _epoch_from_number(v) -> typing.Optional[int]:
    try:
        x = float(v)
        # ns -> s
        if x > 2_000_000_000_000:
            x /= 1_000_000_000.0
        # ms -> s
        elif x > 10_000_000_000:
            x /= 1000.0
        return int(x)
    except Exception:
        return None

# ---------- String datetime parsing ----------

def _epoch_from_iso(s: str) -> typing.Optional[int]:
    """Parse ISO-ish strings; treat naive as LOCAL."""
    try:
        s2 = s.strip()
        # Normalize trailing 'Z'
        if s2.endswith("Z"):
            s2 = s2[:-1] + "+00:00"
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_local_tz())
        return int(dt.timestamp())
    except Exception:
        return None

def _epoch_from_formats(s: str) -> typing.Optional[int]:
    """Try a few common display formats; treat naive as LOCAL."""
    fmts = (
        "%m/%d/%Y %I:%M %p %Z",
        "%m/%d/%Y %H:%M %Z",
        "%B %d, %Y %I:%M %p %Z",
        "%b %d, %Y %I:%M %p %Z",
        "%Y-%m-%d %H:%M:%S",      # fallback non-ISO, naive
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_local_tz())
            return int(dt.timestamp())
        except Exception:
            continue
    return None

def _best_epoch_from_string(s: str) -> typing.Optional[int]:
    return _epoch_from_iso(s) or _epoch_from_formats(s)

# ---------- Site heuristics ----------

def _looks_like_govdeals(item: dict) -> bool:
    """
    Heuristic: GovDeals search objects usually include one or more of:
      'secondsRemaining','timeLeftInSeconds','assetAuctionEndDateEpoch','auctionEndEpoch'
    and also 'assetId'/'accountId'/'businessId'.
    """
    if not isinstance(item, dict):
        return False
    has_any_time = any(k in item for k in (
        "secondsRemaining", "timeLeftInSeconds", "timeRemaining", "secondsToEnd",
        "assetAuctionEndDateEpoch", "auctionEndEpoch", "endTimeEpochMs",
        "endEpoch", "endDate", "auctionEndDate"
    ))
    if not has_any_time:
        return False
    return any(k in item for k in ("assetId", "accountId", "businessId"))
    # (These keys are present on the maestro.lqdt1.com GovDeals payloads.)

_GD_HOUR_FIX_ENABLED = (os.getenv("GD_HOUR_FIX_ENABLED", "1").strip().lower()
                        in ("1","true","yes","y"))

# ---------- Public API ----------

def seconds_remaining(item: dict) -> typing.Optional[int]:
    """
    Returns seconds remaining (int) or None.

    Priority:
      1) direct seconds fields
      2) epoch fields (ns/ms/s)
      3) string fields (ISO/known formats) — NAIVE strings treated as LOCAL tz
    """
    now_utc_ts = datetime.now(timezone.utc).timestamp()
    is_gd = _GD_HOUR_FIX_ENABLED and _looks_like_govdeals(item)

    # 1) direct seconds counts (authoritative on GovDeals too)
    for k in ("secondsRemaining", "timeLeftInSeconds", "timeRemaining", "secondsToEnd"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v >= 0:
            rem = int(v)
            if is_gd:
                # Observed consistent +1h drift vs site; correct it.
                rem -= 3600
            return rem if rem > 0 else None

    # 2) epoch (ns/ms/s)
    for k in ("assetAuctionEndDateEpoch", "auctionEndEpoch", "endTimeEpochMs",
              "endEpoch", "endDate", "auctionEndDate"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            ep = _epoch_from_number(v)
            if ep is None:
                continue
            rem = int(ep - now_utc_ts)
            if is_gd:
                rem -= 3600
            return rem if rem > 0 else None

    # 3) strings (assume LOCAL if tz-naive)
    candidates = []
    for k in ("assetAuctionEndDate", "endTime", "end_time",
              "endDateStr", "auctionEndDateDisplay"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    for s in candidates:
        ep = _best_epoch_from_string(s)
        if ep is not None:
            rem = int(ep - now_utc_ts)
            # Strings parsed as LOCAL already; no GovDeals adjust here.
            if rem > 0:
                return rem

    return None
