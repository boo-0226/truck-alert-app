# /src/core/timeparse.py
# Purpose: one robust time parser used by all sites
import typing
from datetime import datetime, timezone

def seconds_remaining(item: dict) -> typing.Optional[int]:
    # 1) direct seconds fields
    for k in ("secondsRemaining","timeLeftInSeconds","timeRemaining","secondsToEnd"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v >= 0:
            return int(v)

    # 2) epoch (ms/s)
    now = datetime.now(timezone.utc).timestamp()
    for k in ("assetAuctionEndDateEpoch","auctionEndEpoch","endTimeEpochMs","endEpoch","endDate","auctionEndDate"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            if v > 10_000_000_000:  # ms → s
                v = v / 1000.0
            rem = int(v - now)            # or int(dt.timestamp() - now)
            return rem if rem > 0 else None


    # 3) strings (assume UTC if naive)
    candidates = []
    for k in ("assetAuctionEndDate","endTime","end_time","endDateStr","auctionEndDateDisplay"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    fmts = (
        "%m/%d/%Y %I:%M %p %Z",
        "%m/%d/%Y %H:%M %Z",
        "%B %d, %Y %I:%M %p %Z",
        "%b %d, %Y %I:%M %p %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",   # naive ISO → assume UTC
    )
    for s in candidates:
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            rem = int(v - now)            # or int(dt.timestamp() - now)
            return rem if rem > 0 else None

        except Exception:
            pass
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                rem = int(v - now)            # or int(dt.timestamp() - now)
                return rem if rem > 0 else None

            except Exception:
                continue
    return None
