# file path: /src/core/evaluator.py
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import os

# Defaults (you can wire these to your .env if you like)
MAX_BID_CENTS = int(os.getenv("MAX_BID_CENTS", "600000"))     # $6,000
EARLY_ALERT_SECS = int(os.getenv("EARLY_ALERT_SECS", "18")) * 3600  # 18h before close
FINAL_ALERT_SECS = int(os.getenv("FINAL_ALERT_SECS", "10")) * 60    # 10m before close

def evaluate_item(itm: Dict) -> Tuple[bool, List[str]]:
    """
    Returns (will_alert, reasons[])
    reasons: list of machine-readable strings you can show as badges
    """
    reasons: List[str] = []
    # 1) blocked?
    if itm.get("blocked"):
        reasons.append("blocked_keyword")
    # 2) target?
    if not itm.get("target", False):
        reasons.append("not_target")
    # 3) bid cap
    bid = itm.get("bid_cents")
    if isinstance(bid, int) and bid > MAX_BID_CENTS:
        reasons.append("price_over_cap")
    # 4) time windows
    secs = itm.get("secs")
    if secs is None:
        reasons.append("no_secs")
    else:
        if secs > EARLY_ALERT_SECS:
            reasons.append("too_early")
        if secs < 0:
            reasons.append("already_closed")
        # This example assumes your pings happen at either early window or final window
        in_any_window = (0 <= secs <= FINAL_ALERT_SECS) or (FINAL_ALERT_SECS < secs <= EARLY_ALERT_SECS)
        if not in_any_window:
            reasons.append("outside_alert_window")

    will_alert = True
    for bad in ("blocked_keyword", "not_target", "price_over_cap", "already_closed", "no_secs"):
        if bad in reasons:
            will_alert = False
            break
    # If it passed the structural gates but is "outside_alert_window", that still means "not right now"
    if "outside_alert_window" in reasons:
        will_alert = False

    return will_alert, reasons
