# /src/core/digest.py
import json, time, os
from typing import List, Dict
from datetime import datetime, timezone, timedelta
from src.core.utils import format_dollars
from src.core.config import (
    DIGEST_ENABLED, DIGEST_HOURS, DIGEST_MAX_LINES,
    DIGEST_SMS_ENABLED, ALERT_TO, TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM, TWILIO_MESSAGING_SID,
)

try:
    from twilio.rest import Client
except Exception:
    Client = None

STATE_PATH = ".digest_state.json"

def _load_state():
    if os.path.exists(STATE_PATH):
        try:
            return json.loads(open(STATE_PATH, "r", encoding="utf-8").read())
        except Exception:
            pass
    return {}

def _save_state(state: dict):
    try:
        open(STATE_PATH, "w", encoding="utf-8").write(json.dumps(state, indent=2))
    except Exception:
        pass

def _twilio_client():
    if Client is None:
        raise RuntimeError("Twilio client not available. pip install twilio")
    if not (TWILIO_SID and TWILIO_TOKEN):
        raise RuntimeError("Missing TWILIO_SID/TWILIO_TOKEN")
    return Client(TWILIO_SID, TWILIO_TOKEN)

def _send_sms(body: str):
    if not DIGEST_SMS_ENABLED:
        print("ℹ️  Digest SMS disabled (DIGEST_SMS_ENABLED=0).")
        return False
    try:
        client = _twilio_client()
        if TWILIO_MESSAGING_SID:
            msg = client.messages.create(
                to=ALERT_TO,
                messaging_service_sid=TWILIO_MESSAGING_SID,
                body=body
            )
        else:
            msg = client.messages.create(
                to=ALERT_TO,
                from_=TWILIO_FROM,
                body=body
            )
        print(f"✅ Digest SMS sent (SID={msg.sid})")
        return True
    except Exception as e:
        print(f"❌ Digest SMS failed: {e}")
        return False


def _mmss(secs):
    if isinstance(secs, int):
        h, m = secs // 3600, (secs % 3600) // 60
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"
    return "N/A"

def _is_target(itm: dict) -> bool:
    # Respect site-normalized flags from adapters
    if itm.get("blocked"):
        return False
    if not itm.get("engine_67", False):
        return False
    return True

def compose_digest(rows: List[Dict]) -> str:
    """
    Build one compact SMS for all eligible items ending within DIGEST_HOURS.
    Format per line:
      [Site] Title … City, ST | $X | TL=1h 23m
    """
    if not rows:
        return "Daily check: no listings collected."

    # Filter: target-only, time window, price present
    pick = []
    horizon_secs = DIGEST_HOURS * 3600
    for r in rows:
        if not _is_target(r):          # 6.7L diesel-only + not blocked
            continue
        secs = r.get("secs")
        bid  = r.get("bid_cents")
        if not isinstance(secs, int) or secs < 0:
            continue
        if secs > horizon_secs:
            continue
        # Keep even if price is None — but show N/A; user may watch.
        pick.append(r)

    if not pick:
        return f"Daily check: no target trucks in next {DIGEST_HOURS}h."

    # Sort by soonest end
    pick.sort(key=lambda x: x.get("secs", 1_000_000_000))

    # Build lines (truncate to DIGEST_MAX_LINES and ~1300 chars safety)
    lines = []
    for r in pick[:DIGEST_MAX_LINES]:
        site  = r.get("site") or "?"
        title = (r.get("title") or "Untitled").strip()
        city  = r.get("city") or "?"
        state = r.get("state") or ""
        price = format_dollars(r.get("bid_cents"))
        tl    = _mmss(r.get("secs"))
        lines.append(f"[{site}] {title} | {city}, {state} | {price} | TL={tl}")

    body = "DAILY TRUCK DIGEST\n" + "\n".join(lines)
    # hard cap to keep carriers happy
    return (body[:1300] + "…") if len(body) > 1300 else body

def should_send_today(local_hour: int) -> bool:
    """
    Send at most once per calendar day, AFTER the given local hour.
    """
    if not DIGEST_ENABLED or not DIGEST_SMS_ENABLED:
        return False
    now = datetime.now()
    if now.hour < local_hour:
        return False
    st = _load_state()
    last = st.get("last_sent_date")  # "YYYY-MM-DD"
    today = now.strftime("%Y-%m-%d")
    return last != today

def mark_sent_today():
    st = _load_state()
    st["last_sent_date"] = datetime.now().strftime("%Y-%m-%d")
    _save_state(st)

def try_send_digest(rows: List[Dict], local_hour: int) -> bool:
    """
    Compose + send once per day (after local_hour). Returns True if sent.
    """
    if not should_send_today(local_hour):
        return False
    body = compose_digest(rows)
    _send_sms(body)
    mark_sent_today()
    return True
