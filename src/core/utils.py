# /src/core/utils.py
# Purpose: money parsing, logging, and tight specialty-truck targeting helpers
import re
from src.core.config import DEBUG

MONEY_RE = re.compile(r"[\$,]")

# ---------- Specialty bodies (phrases/brands) ----------
# Use body PHRASES (avoid single words like "box" to dodge "toolbox"/"glove box")
DUMP_PHRASES = {
    "dump truck", "dump bed", "dump-body", "single axle dump", "tandem dump"
}
BUCKET_PHRASES = {
    "bucket truck", "boom truck", "aerial lift", "cherry picker", "manlift", "lift truck"
}
BUCKET_BRANDS = {
    "altec", "terex", "hi-ranger", "versalift", "lift-all", "at37", "aa600"
}
CRANE_PHRASES = {
    "crane truck", "truck mounted crane", "service crane", "boom crane",
    "knuckleboom", "digger derrick", "derrick digger",
}
CRANE_BRANDS = {
    "manitex", "stellar", "auto crane", "imt", "elliott", "palfinger", "national crane"
}
BOX_PHRASES = {
    "box truck", "straight truck", "van body", "cargo box", "delivery truck"
}
EMERGENCY_PHRASES = {
    "ambulance", "rescue truck", "fire truck", "pumper", "ems"
}
UTILITY_REFUSE_TANKER_PHRASES = {
    "utility line truck", "line truck",
    "refuse truck", "garbage truck", "roll off", "roll-off",
    "tanker truck", "vacuum truck", "vactor", "sewer truck",
    "cement mixer", "mixer truck"
}

# ---------- Diesel / engine keywords ----------
# For "diesel required" logic. Cummins allowed even without body match (per your request).

# src/core/utils.py

# /src/core/utils.py

# GovDeals specialty keywords (for dump trucks, bucket trucks, etc.)
DUMP_KWS = ["dump truck", "dump body", "dumpbed", "dump-bed", "dump"]
BUCKET_KWS = ["bucket truck", "boom truck", "lift truck", "aerial", "cherry picker"]


SPECIALTY_KWS = {
    "dump": ["dump truck", "dump"],
    "bucket": ["bucket truck", "aerial", "lift"],
    "utility": ["utility", "service body", "mechanic"],
    "flatbed": ["flatbed"],
    "crane": ["crane"],
}

# ---------- Negative keywords to filter false positives ----------
SPECIALTY_NEGATIVE_KWS = {
    # Example: avoid matching "box" in "toolbox" or "glove box"
    "toolbox", "glove box", "gearbox",
    # Add any other phrases you’ve seen pollute your results
}


DIESEL_KWS = {
    "diesel", "power stroke", "duramax", "cummins", "caterpillar", "cat c7", "cat c9",
    "isx", "isl", "isb", "dt466", "maxxforce", "t444e", "om906", "mbe900"
}
CUMMINS_KWS = {
    "cummins", "isx", "isl", "isb", "b5.9", "5.9l", "6.7 cummins", "6.7l cummins"
}

# ---------- Block light-duty models ----------
BLOCKED_MODELS = {
    "f150", "f-150", "f 150", "1500", "silverado 1500", "ram 1500",
    "tacoma", "ranger", "colorado"
}

# ---------- Back-compat: keep your 6.7 helper (used elsewhere) ----------
def is_engine_67(text: str) -> bool:
    """
    Heuristic match for 6.7L diesels (Power Stroke or Cummins).
    """
    t = (text or "").lower()
    if "diesel" not in t and "power stroke" not in t and "cummins" not in t and "6.7" not in t:
        return False
    needles = (
        "6.7l", "6.7 l", "6.7-liter", "6.7 litre",
        "6.7 power stroke", "power stroke 6.7",
        "cummins 6.7", "6.7 cummins"
    )
    return any(n in t for n in needles)

# ---------- Targeting helpers ----------
def _contains_any(t: str, words) -> bool:
    return any(w in t for w in words)

def is_diesel(text: str) -> bool:
    t = (text or "").lower()
    return _contains_any(t, DIESEL_KWS)

def has_cummins(text: str) -> bool:
    t = (text or "").lower()
    return _contains_any(t, CUMMINS_KWS)

def is_specialty_body(text: str) -> bool:
    """
    True if listing looks like one of the specialty bodies we flip:
    dump, bucket/aerial, crane, box/straight, emergency, utility/refuse/tanker/mixer.
    """
    t = (text or "").lower()
    return (
        _contains_any(t, DUMP_PHRASES)
        or _contains_any(t, BUCKET_PHRASES)
        or _contains_any(t, BUCKET_BRANDS)
        or _contains_any(t, CRANE_PHRASES)
        or _contains_any(t, CRANE_BRANDS)
        or _contains_any(t, BOX_PHRASES)
        or _contains_any(t, EMERGENCY_PHRASES)
        or _contains_any(t, UTILITY_REFUSE_TANKER_PHRASES)
    )

def is_target_vehicle(text: str) -> bool:
    """
    Your new rule:
      - (diesel AND specialty body) OR (any Cummins mention)
      - and not a blocked light-duty model
    """
    t = (text or "").lower()
    if any(b in t for b in BLOCKED_MODELS):
        return False
    if has_cummins(t):
        return True
    return is_diesel(t) and is_specialty_body(t)

def annotate_tags(text: str):
    """
    Optional: derive simple tags for UI/logs. Non-exclusive.
    """
    t = (text or "").lower()
    tags = []
    if _contains_any(t, DUMP_PHRASES): tags.append("dump")
    if _contains_any(t, BUCKET_PHRASES) or _contains_any(t, BUCKET_BRANDS): tags.append("bucket")
    if _contains_any(t, CRANE_PHRASES) or _contains_any(t, CRANE_BRANDS): tags.append("crane")
    if _contains_any(t, BOX_PHRASES): tags.append("box")
    if _contains_any(t, EMERGENCY_PHRASES): tags.append("emergency")
    if _contains_any(t, UTILITY_REFUSE_TANKER_PHRASES): tags.append("utility")
    if has_cummins(t): tags.append("cummins")
    return tags

# ---------- Debug log ----------
def dprint(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

# ---------- Money helpers ----------
def parse_bid_cents(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 250_000 else value * 100
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, str):
        s = MONEY_RE.sub("", value).strip()
        if not s:
            return None
        try:
            return int(round(float(s) * 100))
        except ValueError:
            return None
    return None

def format_dollars(cents):
    if cents is None:
        return "N/A"
    return f"${cents/100:,.2f}"
