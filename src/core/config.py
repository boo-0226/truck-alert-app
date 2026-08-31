# /src/core/config.py
# Purpose: load env + global thresholds/channels in one place
import os
import re
from dotenv import load_dotenv

load_dotenv()

def _int_env(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    try:
        return int(v) if v else default
    except ValueError:
        return default

def _float_env(name: str, default: float) -> float:
    v = os.getenv(name, "").strip()
    try:
        return float(v) if v else default
    except ValueError:
        return default

def _dollars_to_cents_env(name: str, default_dollars: int) -> int:
    v = os.getenv(name, "").strip().replace("$","").replace(",","")
    try:
        return int(round(float(v) * 100)) if v else default_dollars * 100
    except ValueError:
        return default_dollars * 100


STATE_CODE_TO_NAME = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
STATE_NAME_TO_CODE = {
    re.sub(r"[^A-Z]+", " ", name.upper()).strip(): code
    for code, name in STATE_CODE_TO_NAME.items()
}


def normalize_state(value: str | None) -> str:
    if value in (None, ""):
        return ""

    clean = re.sub(r"[^A-Za-z]+", " ", str(value)).strip().upper()
    if not clean:
        return ""

    compact = clean.replace(" ", "")
    if compact in STATE_CODE_TO_NAME:
        return compact
    if clean in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[clean]

    tokens = clean.split()
    for token in tokens:
        if token in STATE_CODE_TO_NAME:
            return token

    for state_name, code in STATE_NAME_TO_CODE.items():
        if re.search(rf"\b{re.escape(state_name)}\b", clean):
            return code

    return ""


def _target_states_env() -> frozenset[str]:
    raw = os.getenv("TARGET_STATES", "TX")
    states = {normalize_state(part) for part in raw.split(",")}
    states.discard("")
    return frozenset(states or {"TX"})


TARGET_STATES = _target_states_env()


def target_state_names() -> list[str]:
    return [STATE_CODE_TO_NAME[code] for code in sorted(TARGET_STATES) if code in STATE_CODE_TO_NAME]


def is_allowed_state(value: str | None) -> bool:
    return normalize_state(value) in TARGET_STATES


def location_block_reason(value: str | None) -> str:
    state = normalize_state(value)
    if not state:
        return "location_state_unknown"
    if state not in TARGET_STATES:
        return "outside_target_state"
    return ""


def _reason_list(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item not in (None, "")]
    return [part.strip() for part in re.split(r"[;,]", str(value)) if part.strip()]


def _append_reason(row: dict, field: str, reason: str) -> None:
    reasons = _reason_list(row.get(field))
    if reason and reason not in reasons:
        reasons.append(reason)
    row[field] = reasons


def apply_location_guard(row: dict, state_value: str | None = None) -> dict:
    raw_state = state_value
    if raw_state in (None, ""):
        for key in ("state", "locationState", "stateDesc", "region_text", "location"):
            raw_state = row.get(key)
            if raw_state not in (None, ""):
                break

    normalized_state = normalize_state(raw_state)
    reason = location_block_reason(raw_state)
    row["normalized_state"] = normalized_state
    row["location_allowed"] = reason == ""
    row["location_block_reason"] = reason

    if reason:
        row["target"] = False
        row["blocked"] = True
        row["classification"] = "REJECT"
        _append_reason(row, "block_reasons", reason)
        _append_reason(row, "decision_reasons", reason)

    return row

DEBUG               = os.getenv("DEBUG", "0").lower() in ("1","true","yes","y")
SEND_SMS            = os.getenv("SEND_SMS", "1").lower() in ("1","true","yes","y")
SEND_VOICE          = os.getenv("SEND_VOICE", "1").lower() in ("1","true","yes","y")
ALERT_PRICE_CENTS   = _dollars_to_cents_env("ALERT_PRICE_DOLLARS", 5000)
ALERT_TIME_SECS     = _int_env("ALERT_TIME_SECS", 600)     # 10 min default per your latest
EARLY_TIME_SECS     = _int_env("EARLY_TIME_SECS", 0)
BASE_SLEEP          = _int_env("BASE_SLEEP", 600)
FAST_SLEEP          = _int_env("FAST_SLEEP", 120)
SNIPE_SLEEP         = _int_env("SNIPE_SLEEP", 45)

TWILIO_SID          = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN        = os.getenv("TWILIO_TOKEN", "")
TWILIO_FROM         = os.getenv("TWILIO_FROM", "")
ALERT_TO            = os.getenv("ALERT_TO", "")

# Daily Check (single SMS health summary for both scrapers)
DIGEST_ENABLED      = os.getenv("DIGEST_ENABLED", "1").lower() in ("1","true","yes","y")
DIGEST_LOCAL_HOUR   = _int_env("DIGEST_LOCAL_HOUR", 9)  # send after this local hour
DIGEST_HOURS        = _int_env("DIGEST_HOURS", 48)      # list items ending within next N hours
DIGEST_MAX_LINES    = _int_env("DIGEST_MAX_LINES", 10)  # limit lines in SMS


# Prefer Messaging Service for SMS (handles carrier rules/A2P better)
TWILIO_MESSAGING_SID = os.getenv("TWILIO_MESSAGING_SID", "")


# Legacy heartbeat disabled.
# The daily digest/Daily Check flow is the single daily health notification.
HEALTHCHECK_ENABLED = False
HEALTHCHECK_MINUTES = 0

# Separate SMS controls (so digest can send while per-item alerts are muted)
ALERTS_SMS_ENABLED  = os.getenv("ALERTS_SMS_ENABLED", "0").lower() in ("1","true","yes","y")  # per-vehicle SMS
DIGEST_SMS_ENABLED  = os.getenv("DIGEST_SMS_ENABLED", "1").lower() in ("1","true","yes","y")  # daily list SMS


# Consumer gas strategy knobs. These do not scrape Carvana or invent offers;
# they are defaults for candidate scoring and future manual deal math.
CONSUMER_GAS_ALERT_SCORE = _int_env("CONSUMER_GAS_ALERT_SCORE", 75)
CONSUMER_GAS_WATCHLIST_SCORE = _int_env("CONSUMER_GAS_WATCHLIST_SCORE", 50)
CONSUMER_GAS_MAX_ALERT_MILES_DEFAULT = _int_env("CONSUMER_GAS_MAX_ALERT_MILES_DEFAULT", 100000)
MIN_CONSUMER_GAS_NET_PROFIT = _float_env("MIN_CONSUMER_GAS_NET_PROFIT", 3500.0)
DEFAULT_SHIPPING_RESERVE = _float_env("DEFAULT_SHIPPING_RESERVE", 700.0)
DEFAULT_REPAIR_RESERVE = _float_env("DEFAULT_REPAIR_RESERVE", 1000.0)
DEFAULT_FIXED_COSTS = _float_env("DEFAULT_FIXED_COSTS", 500.0)
DEFAULT_SAFETY_BUFFER = _float_env("DEFAULT_SAFETY_BUFFER", 1000.0)
DEFAULT_BUYER_PREMIUM_RATE = _float_env("DEFAULT_BUYER_PREMIUM_RATE", 0.125)

# Backward-compatible names for older local scripts/tests. They point at the
# same consumer-gas strategy and should not be used as a separate lane.
MIN_CARVANA_NET_PROFIT = MIN_CONSUMER_GAS_NET_PROFIT
CARVANA_DEFAULT_SHIPPING = DEFAULT_SHIPPING_RESERVE
CARVANA_DEFAULT_REPAIR_RESERVE = DEFAULT_REPAIR_RESERVE
CARVANA_DEFAULT_FIXED_COSTS = DEFAULT_FIXED_COSTS
CARVANA_DEFAULT_SAFETY_BUFFER = DEFAULT_SAFETY_BUFFER
CARVANA_DEFAULT_BUYER_PREMIUM_RATE = DEFAULT_BUYER_PREMIUM_RATE
CARVANA_GAS_MIN_ALERT_SCORE = CONSUMER_GAS_ALERT_SCORE
CARVANA_GAS_MIN_WATCHLIST_SCORE = CONSUMER_GAS_WATCHLIST_SCORE


