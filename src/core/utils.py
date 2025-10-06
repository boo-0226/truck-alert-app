# /src/core/utils.py
# Purpose: money parsing, logging, and tight specialty-truck targeting helpers
import re
from src.core.config import DEBUG

MONEY_RE = re.compile(r"[\$,]")

# /src/core/utils.py
# --- Truck targeting helpers for auction scraper ---

# ---------- Keyword sets ----------

# Specialty body / upfit cues
DUMP_PHRASES = {
    "dump truck","dump bed","dump-body","single axle dump","tandem dump"
}
BUCKET_PHRASES = {
    "bucket truck","boom truck","aerial lift","cherry picker","manlift","lift truck","platform lift"
}
BUCKET_BRANDS = {
    "altec","terex","hi-ranger","versalift","dur-a-lift","lift-all",
    "at37","at37g","at-37","at200","at235","tm","tl"
}
CRANE_PHRASES = {
    "crane truck","truck mounted crane","service crane","boom crane",
    "knuckleboom","digger derrick","derrick digger"
}
CRANE_BRANDS = {
    "manitex","stellar","auto crane","imt","elliott","palfinger","national crane"
}
BOX_PHRASES = {
    "box truck","straight truck","van body","cargo box","delivery truck"
}
EMERGENCY_PHRASES = {
    "ambulance","rescue truck","fire truck","pumper","ems"
}
UTILITY_REFUSE_TANKER_PHRASES = {
    "utility line truck","line truck","service body","utility body","mechanic body",
    "refuse truck","garbage truck","roll off","roll-off",
    "tanker truck","vacuum truck","vactor","sewer truck",
    "cement mixer","mixer truck","liftgate","tommy gate",
    "knapheide","reading body","cab & chassis","chassis cab"
}

# Heavy-duty chassis/model cues
HEAVY_DUTY_MODELS = {
    "f450","f-450","f550","f-550","f650","f-650","f750","f-750","super duty",
    "ram 4500","ram 5500",
    "topkick","kodiak","c4500","c5500","c6500","gmc 6500","chevy 4500","chevy 5500",
    "international 4300","4300","4700","4900","durastar","workstar",
    "freightliner m2","m2 106","m2-106","sterling","isuzu npr","isuzu nqr",
    "hino","peterbilt","kenworth"
}

# Diesel/engine keywords
DIESEL_KWS = {
    "diesel","turbo diesel","power stroke","duramax","cummins","caterpillar","cat c7","cat c9",
    "isx","isl","isc","isb","dt466","maxxforce","t444e","om906","mbe900",
    "6.7l","6.4l","6.0l","7.3l","5.9l","8.3l"
}
CUMMINS_KWS = {
    "cummins","isx","isl","isc","isb","b5.9","5.9l","6.7 cummins","6.7l cummins"
}

# Light-duty blocklist
BLOCKED_MODELS = {
    "f150","f-150","f 150","1500","silverado 1500","sierra 1500","ram 1500",
    "tundra","titan","tacoma","ranger","colorado"
}

# ---------- Helpers ----------

# debug + formatting helpers required by alerts.py
import os

def _debug_enabled() -> bool:
    v = (os.getenv("DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "on")

def dprint(*args, **kwargs):
    """Print only when DEBUG is enabled in the environment."""
    if _debug_enabled():
        print("[DEBUG]", *args, **kwargs, flush=True)

def format_dollars(value_cents):
    """
    Safe money formatter. Accepts cents (int) or None.
    Returns e.g. '$4,500' or '$4,500.25'. Returns '—' if None.
    """
    if value_cents is None:
        return "—"
    try:
        cents = int(value_cents)
    except (TypeError, ValueError):
        return "—"
    dollars = cents / 100.0
    # no decimals if it's an even dollar amount
    if abs(dollars - round(dollars)) < 1e-9:
        return f"${int(round(dollars)):,}"
    return f"${dollars:,.2f}"


def _contains_any(text: str, keywords: set[str]) -> bool:
    """Returns True if any keyword is found in text."""
    t = (text or "").lower()
    return any(k in t for k in keywords)

def has_cummins(text: str) -> bool:
    return _contains_any(text, CUMMINS_KWS)

def is_diesel(text: str) -> bool:
    return _contains_any(text, DIESEL_KWS)

def is_specialty_body(text: str) -> bool:
    """True if listing contains any specialty-body or upfit keyword."""
    return (
        _contains_any(text, DUMP_PHRASES)
        or _contains_any(text, BUCKET_PHRASES)
        or _contains_any(text, BUCKET_BRANDS)
        or _contains_any(text, CRANE_PHRASES)
        or _contains_any(text, CRANE_BRANDS)
        or _contains_any(text, BOX_PHRASES)
        or _contains_any(text, EMERGENCY_PHRASES)
        or _contains_any(text, UTILITY_REFUSE_TANKER_PHRASES)
    )

def is_heavy_duty_model(text: str) -> bool:
    return _contains_any(text, HEAVY_DUTY_MODELS)

# ---------- Targeting Rule ----------

def is_target_vehicle(text: str) -> bool:
    """
    (diesel AND (specialty body OR heavy-duty chassis)) OR any Cummins mention
    and not a blocked light-duty model
    """
    t = (text or "").lower()
    if _contains_any(t, BLOCKED_MODELS):
        return False
    if has_cummins(t):
        return True
    return is_diesel(t) and (is_specialty_body(t) or is_heavy_duty_model(t))

# ---------- Tagging for SMS Digest ----------

def annotate_tags(text: str):
    t = (text or "").lower()
    tags = []
    if _contains_any(t, DUMP_PHRASES): tags.append("dump")
    if _contains_any(t, BUCKET_PHRASES) or _contains_any(t, BUCKET_BRANDS): tags.append("bucket")
    if _contains_any(t, CRANE_PHRASES) or _contains_any(t, CRANE_BRANDS): tags.append("crane")
    if _contains_any(t, BOX_PHRASES): tags.append("box")
    if _contains_any(t, EMERGENCY_PHRASES): tags.append("emergency")
    if _contains_any(t, UTILITY_REFUSE_TANKER_PHRASES): tags.append("service")
    if is_heavy_duty_model(t): tags.append("hd-chassis")
    if is_diesel(t): tags.append("diesel")
    if has_cummins(t): tags.append("cummins")
    return tags
