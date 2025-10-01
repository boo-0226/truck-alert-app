# /src/core/healthcheck.py
import json, time
from pathlib import Path
from typing import Optional, Dict

STATE_PATH = Path(".health_state.json")

def _load_state() -> Dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            return {}
    return {}

def _save_state(state: Dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception:
        pass

def should_send(now_ts: Optional[float], interval_minutes: int) -> bool:
    if interval_minutes <= 0:
        return False
    if now_ts is None:
        now_ts = time.time()
    last = _load_state().get("last_healthcheck_ts", 0)
    return (now_ts - last) >= interval_minutes * 60

def mark_sent(now_ts: Optional[float] = None) -> None:
    if now_ts is None:
        now_ts = time.time()
    state = _load_state()
    state["last_healthcheck_ts"] = now_ts
    _save_state(state)
