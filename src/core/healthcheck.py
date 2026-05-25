# file: src/core/healthcheck.py

from __future__ import annotations

from typing import Optional


def should_send(now_ts: Optional[float], interval_minutes: int) -> bool:
    return False


def mark_sent(now_ts: Optional[float] = None) -> None:
    return None
