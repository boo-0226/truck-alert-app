# file: src/core/digest.py

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.core.config import (
    ALERT_TO,
    DIGEST_ENABLED,
    DIGEST_LOCAL_HOUR,
    DIGEST_SMS_ENABLED,
    TWILIO_FROM,
    TWILIO_MESSAGING_SID,
    TWILIO_SID,
    TWILIO_TOKEN,
)
from src.core.service_health import compose_daily_check_message

try:
    from twilio.rest import Client
except Exception:
    Client = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = PROJECT_ROOT / ".digest_state.json"
LOCK_PATH = PROJECT_ROOT / ".digest_state.lock"
LOCK_TIMEOUT_SECONDS = 10
LOCK_STALE_SECONDS = 60


@contextmanager
def _daily_check_lock():
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd = None

    while fd is None:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}".encode("utf-8"))
        except FileExistsError:
            try:
                if time.time() - LOCK_PATH.stat().st_mtime > LOCK_STALE_SECONDS:
                    LOCK_PATH.unlink()
                    continue
            except OSError:
                pass

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for daily check lock: {LOCK_PATH}")
            time.sleep(0.1)

    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def _twilio_client():
    if Client is None:
        raise RuntimeError("Twilio client not available. pip install twilio")
    if not (TWILIO_SID and TWILIO_TOKEN):
        raise RuntimeError("Missing TWILIO_SID/TWILIO_TOKEN")
    return Client(TWILIO_SID, TWILIO_TOKEN)


def _send_sms(body: str) -> bool:
    if not DIGEST_SMS_ENABLED:
        print("Digest SMS disabled (DIGEST_SMS_ENABLED=0).")
        return False

    try:
        client = _twilio_client()
        if TWILIO_MESSAGING_SID:
            msg = client.messages.create(
                to=ALERT_TO,
                messaging_service_sid=TWILIO_MESSAGING_SID,
                body=body,
            )
        else:
            msg = client.messages.create(
                to=ALERT_TO,
                from_=TWILIO_FROM,
                body=body,
            )
        print(f"Daily Check SMS sent (SID={msg.sid})")
        return True
    except Exception as exc:
        print(f"Daily Check SMS failed: {exc}")
        return False


def compose_digest(rows: List[Dict]) -> str:
    return compose_daily_check_message()


def should_send_today(local_hour: int) -> bool:
    if not DIGEST_ENABLED or not DIGEST_SMS_ENABLED:
        return False
    now = datetime.now()
    if now.hour < local_hour:
        return False
    state = _load_state()
    last = state.get("last_sent_date")
    today = now.strftime("%Y-%m-%d")
    return last != today


def mark_sent_today() -> None:
    state = _load_state()
    state["last_sent_date"] = datetime.now().strftime("%Y-%m-%d")
    _save_state(state)


def try_send_daily_check(local_hour: int = DIGEST_LOCAL_HOUR) -> bool:
    if not should_send_today(local_hour):
        return False

    with _daily_check_lock():
        if not should_send_today(local_hour):
            return False
        body = compose_daily_check_message()
        _send_sms(body)
        mark_sent_today()
        return True


def try_send_digest(rows: List[Dict], local_hour: int) -> bool:
    return try_send_daily_check(local_hour)
