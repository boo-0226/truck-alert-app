# /src/core/utils.py
# --- Truck targeting + parsing helpers (with backward-compat shims) ---

from __future__ import annotations
import os
import re
from typing import Optional, Tuple, List

# ========== Debug / formatting ==========

def _debug_enabled() -> bool:
    v = (os.getenv("DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "on")

def dprint(*args, **kwargs):
    """Print only when DEBUG is enabled in the environment."""
    if _debug_enabled():
        print("[DEBUG]", *args, **kwargs, flush=True)

def format_dollars(value_cents):
    """Format cents to dollars string. Returns '—' if None."""
    if value_cents is None:
        return "—"
    try:
        cents = int(value_cents)
    except (TypeError, ValueError):
        return "—"
    dollars = cents / 100.0
    if abs(dollars - round(dollars)) < 1e-9:
        return f"${int(round(dollars)):,}"
    return f"${dollars:,.2f}"

format_money = format_dollars




# ========== Small text helpers ==========

def _contains_any(text: str, keywords: set[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in keywords)

def normalize_ws(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

# ========== Money / time parsing ==========

def parse_bid_cents(text) -> Optional[int]:
    """
    Extract numeric dollar amount from a string or number like:
      "$4,500", "Current bid: $3,250", 3250.50, 4500
    Return cents (int) or None.
    """
    if text is None:
        return None

    # Normalize type
    if isinstance(text, (int, float)):
        return int(round(float(text) * 100))

    # Defensive: convert to string
    s = str(text).strip()
    if not s:
        return None

    s = s.replace(",", "")
    m = re.search(r"(\d+(?:\.\d{1,2})?)", s)
    if not m:
        return None
    try:
        return int(round(float(m.group(1)) * 100))
    except ValueError:
        return None


# Back-compat aliases some adapters may import
parse_price_cents = parse_bid_cents
money_to_cents = parse_bid_cents

_TIME_TOKEN = re.compile(
    r"(?:(?P<days>\d+)\s*d)?\s*"
    r"(?:(?P<hours>\d+)\s*h)?\s*"
    r"(?:(?P<mins>\d+)\s*m)?\s*"
    r"(?:(?P<secs>\d+)\s*s)?",
    re.I,
)

def parse_time_remaining_to_secs(text: Optional[str]) -> Optional[int]:
    """
    Parse common 'time remaining' strings:
      - '1d 2h 3m', '3h 5m', '12m', '45s'
      - '00:12:30' (HH:MM:SS) or '12:30' (MM:SS)
    Return seconds (int) or None if not recognized.
    """
    t = normalize_ws(text).lower()
    if not t:
        return None

    # HH:MM:SS or MM:SS
    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", t):
        hh, mm, ss = [int(x) for x in t.split(":")]
        return hh * 3600 + mm * 60 + ss
    if re.match(r"^\d{1,2}:\d{2}$", t):
        mm, ss = [int(x) for x in t.split(":")]
        return mm * 60 + ss

    # Token form (d h m s)
    m = _TIME_TOKEN.search(t)
    if m and m.group(0).strip():
        days = int(m.group("days") or 0)
        hours = int(m.group("hours") or 0)
        mins = int(m.group("mins") or 0)
        secs = int(m.group("secs") or 0)
        total = days * 86400 + hours * 3600 + mins * 60 + secs
        return total if total > 0 else None

    return None

# Back-compat alias
parse_secs = parse_time_remaining_to_secs

def parse_city_state(s: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse 'City, ST' → ('City','ST'). Otherwise (None,None).
    """
    t = normalize_ws(s)
    m = re.search(r"^(.+?),\s*([A-Za-z]{2})$", t)
    if m:
        return m.group(1), m.group(2).upper()
    return None, None

# ========== Targeting keyword sets ==========

# Specialty body / upfit cues
DUMP_PHRASES = {
    "dump truck","dump bed","dump-body","single axle dump","tandem dump"
}
BUCKET_PHRASES = {
    "bucket truck","boom truck","aerial lift","cherry picker","manlift",
    "lift truck","platform lift"
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

# Heavy-duty chassis / model cues
HEAVY_DUTY_MODELS = {
    "f450","f-450","f550","f-550","f650","f-650","f750","f-750","super duty",
    "ram 4500","ram 5500",
    "topkick","kodiak","c4500","c5500","c6500","gmc 6500","chevy 4500","chevy 5500",
    "international 4300","4300","4700","4900","durastar","workstar",
    "freightliner m2","m2 106","m2-106","sterling",
    "isuzu npr","isuzu nqr","hino","peterbilt","kenworth"
}

# Diesel / engine keywords
DIESEL_KWS = {
    "diesel","turbo diesel","power stroke","powerstroke","duramax","cummins",
    "caterpillar","cat c7","cat c9",
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

# ========== Matchers ==========

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

def is_engine_67(text: str) -> bool:
    """
    Detect common ways listings mention a 6.7L (Cummins or Power Stroke).
    """
    t = (text or "").lower()
    if ("6.7" in t) and ("cummins" in t or "power stroke" in t or "powerstroke" in t):
        return True
    if re.search(r"\b6\.7\s*(l|liter)\b", t):
        return True
    return False

# ========== Targeting Rule ==========

def is_target_vehicle(text: str) -> bool:
    """
    Rule:
      (diesel AND (specialty body OR heavy-duty chassis)) OR any Cummins mention
    and not a blocked light-duty model
    """
    t = (text or "").lower()
    if _contains_any(t, BLOCKED_MODELS):
        return False
    if has_cummins(t):
        return True
    return is_diesel(t) and (is_specialty_body(t) or is_heavy_duty_model(t))

# ========== Tagging for digests ==========
def annotate_tags(text: str) -> List[str]:
    t = (text or "").lower()
    tags: List[str] = []
    if _contains_any(t, DUMP_PHRASES): tags.append("dump")
    if _contains_any(t, BUCKET_PHRASES) or _contains_any(t, BUCKET_BRANDS): tags.append("bucket")
    if _contains_any(t, CRANE_PHRASES) or _contains_any(t, CRANE_BRANDS): tags.append("crane")
    if _contains_any(t, BOX_PHRASES): tags.append("box")
    if _contains_any(t, EMERGENCY_PHRASES): tags.append("emergency")
    if _contains_any(t, UTILITY_REFUSE_TANKER_PHRASES): tags.append("service")
    if is_heavy_duty_model(t): tags.append("hd-chassis")
    if is_diesel(t): tags.append("diesel")
    if has_cummins(t): tags.append("cummins")
    if is_engine_67(t): tags.append("6.7L")
    return tags
