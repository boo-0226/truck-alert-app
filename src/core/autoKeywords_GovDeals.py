# src/core/autoKeywords_GovDeals.py

import re
from dataclasses import dataclass
from typing import Optional

try:
    from src.core.config import is_allowed_state, target_state_names
except ImportError:  # pragma: no cover - supports direct script execution with src on sys.path
    from core.config import is_allowed_state, target_state_names


# -------------------------------
# Global alert filters
# -------------------------------
MAX_GAS_MILES = 130_000
MAX_DIESEL_MILES = 150_000
MAX_GAS_BID = 5_000
CLOSE_SOON_MINUTES = 30


# -------------------------------
# Gas targeting vocabulary
# -------------------------------
GAS_MAKES = {
    "Ford": ("ford",),
    "Chevrolet": ("chevrolet", "chevy"),
    "GMC": ("gmc",),
    "Ram": ("ram", "dodge ram", "dodge"),
}

GAS_MODELS = {
    "F-150": ("f-150", "f150", "f 150"),
    "F-250": ("f-250", "f250", "f 250"),
    "F-350": ("f-350", "f350", "f 350"),
    "Silverado 1500": ("silverado 1500", "chevrolet 1500", "chevy 1500"),
    "Sierra 1500": ("sierra 1500", "gmc 1500"),
    "Silverado 2500": ("silverado 2500", "chevrolet 2500", "chevy 2500"),
    "Silverado 3500": ("silverado 3500", "chevrolet 3500", "chevy 3500"),
    "Sierra 2500": ("sierra 2500", "gmc 2500"),
    "Sierra 3500": ("sierra 3500", "gmc 3500"),
    "Ram 1500": ("ram 1500", "dodge ram 1500"),
    "1500": ("1500",),
    "2500": ("2500",),
    "3500": ("3500",),
}

GAS_ENGINES = {
    "5.0 V8": ("5.0", "5.0l", "5.0 liter", "5.0 litre", "coyote"),
    "2.7 EcoBoost": ("2.7 ecoboost", "2.7 eco boost", "2.7l ecoboost"),
    "6.2L gas": ("6.2", "6.2l", "6.2 liter", "6.2 litre"),
    "5.3 V8": ("5.3", "5.3l", "5.3 liter", "5.3 litre"),
    "6.0 gas": ("6.0", "6.0l", "6.0 liter", "6.0 litre"),
    "5.7 HEMI": ("5.7 hemi", "5.7l hemi", "hemi"),
}


# -------------------------------
# Diesel targeting vocabulary
# -------------------------------
DIESEL_MAKES = {
    "Ford": ("ford",),
    "Chevrolet": ("chevrolet", "chevy"),
    "GMC": ("gmc",),
    "Ram": ("ram", "dodge ram", "dodge"),
    "International": ("international",),
    "Freightliner": ("freightliner",),
}

DIESEL_MODELS = {
    "F-250": ("f-250", "f250", "f 250"),
    "F-350": ("f-350", "f350", "f 350"),
    "F-450": ("f-450", "f450", "f 450"),
    "F-550": ("f-550", "f550", "f 550"),
    "F-650": ("f-650", "f650", "f 650"),
    "F-750": ("f-750", "f750", "f 750"),
    "Silverado 2500": ("silverado 2500", "silverado 2500hd", "chevrolet 2500", "chevy 2500"),
    "Silverado 3500": ("silverado 3500", "silverado 3500hd", "chevrolet 3500", "chevy 3500"),
    "Sierra 2500": ("sierra 2500", "sierra 2500hd", "gmc 2500"),
    "Sierra 3500": ("sierra 3500", "sierra 3500hd", "gmc 3500"),
    "Ram 2500": ("ram 2500", "dodge ram 2500"),
    "Ram 3500": ("ram 3500", "dodge ram 3500"),
    "4300": ("international 4300", "model 4300"),
    "M2": ("freightliner m2", "m2", "m2 106"),
}

DIESEL_ENGINES = {
    "6.7 Power Stroke": ("6.7 power stroke", "6.7l power stroke", "6.7 powerstroke", "6.7l powerstroke"),
    "Power Stroke": ("power stroke", "powerstroke"),
    "6.7 Cummins": ("6.7 cummins", "6.7l cummins"),
    "Cummins": ("cummins",),
    "6.6 Duramax": ("6.6 duramax", "6.6l duramax"),
    "Duramax": ("duramax",),
    "6.7": ("6.7", "6.7l", "6.7 liter", "6.7 litre"),
    "6.6": ("6.6", "6.6l", "6.6 liter", "6.6 litre"),
    "DT466": ("dt466", "dt 466"),
    "CAT": ("cat",),
    "Caterpillar": ("caterpillar",),
}

SPECIALTY_TRUCK_KEYWORDS_TOP = (
    "bucket",
    "aerial",
    "altec",
    "versalift",
    "boom",
    "dump",
    "service truck",
    "utility truck",
    "mechanics truck",
    "service body",
    "crane",
    "compressor",
)

SPECIALTY_TRUCK_KEYWORDS_GOOD = (
    "flatbed",
    "stake bed",
    "box truck",
    "rollback",
    "wrecker",
    "tow truck",
    "liftgate",
    "pto",
    "knapheide",
    "reading",
    "stellar",
    "imt",
    "venturo",
    "vanair",
)

SPECIALTY_TRUCK_KEYWORDS = {
    "top": SPECIALTY_TRUCK_KEYWORDS_TOP,
    "good": SPECIALTY_TRUCK_KEYWORDS_GOOD,
}


# -------------------------------
# Hard excludes block alerting immediately.
# Soft warnings are shown in debug/alerts only.
# -------------------------------
HARD_EXCLUDE_KEYWORDS = (
    "no title",
    "salvage",
    "parts only",
    "bad engine",
    "bad transmission",
    "major rust",
)

SOFT_WARNING_KEYWORDS = (
    "passenger",
    "unknown mileage",
    "towed",
    "rust",
    "check engine",
    "does not start",
)

# Backward-compatible name for older imports. This is intentionally hard-only.
EXCLUDE_KEYWORDS = set(HARD_EXCLUDE_KEYWORDS)

HARD_EXCLUDE_PATTERNS = {
    "no title": (
        r"\bno\s+titles?\b",
        r"\btitles?\s+(?:is\s+|are\s+)?(?:missing|absent|unavailable|not\s+available|not\s+included)\b",
        r"\bmissing\s+titles?\b",
        r"\bwithout\s+(?:a\s+)?titles?\b",
        r"\bbill\s+of\s+sale\s+only\b",
    ),
    "salvage": (
        r"\bsalvage(?:d)?\b",
        r"\bsalvage\s+titles?\b",
        r"\brebuilt\s+salvage\b",
    ),
    "parts only": (
        r"\bparts\s+only\b",
        r"\bfor\s+parts\b",
        r"\bparts\s+(?:vehicle|truck|car|unit)\b",
        r"\b(?:vehicle|truck|car|unit)\s+for\s+parts\b",
    ),
    "bad engine": (
        r"\bbad\s+engine\b",
        r"\bengine\s+(?:is\s+)?bad\b",
        r"\bblown\s+engine\b",
        r"\bseized\s+engine\b",
        r"\bengine\s+(?:failure|failed|seized|blown)\b",
        r"\bneeds?\s+(?:a\s+)?(?:new\s+|replacement\s+)?engine\b",
    ),
    "bad transmission": (
        r"\bbad\s+transmission\b",
        r"\btransmission\s+(?:is\s+)?bad\b",
        r"\btransmission\s+(?:failure|failed|slipping|inoperable)\b",
        r"\bneeds?\s+(?:a\s+)?(?:new\s+|replacement\s+)?transmission\b",
    ),
    "major rust": (
        r"\bmajor\s+rust\b",
        r"\bsevere\s+rust\b",
        r"\bheavy\s+rust\b",
        r"\bextensive\s+rust\b",
        r"\brust(?:ed)?\s+(?:through|out)\b",
        r"\bframe\s+rust(?:ed)?\s+(?:through|out)?\b",
    ),
}

SOFT_WARNING_PATTERNS = {
    "passenger": (
        r"\bpassengers?\b",
        r"\bpassenger\s+(?:van|bus|vehicle|seat|seating)\b",
    ),
    "unknown mileage": (
        r"\bunknown\s+(?:mileage|miles|odometer)\b",
        r"\b(?:mileage|miles|odometer)\s+unknown\b",
        r"\bodometer\s+(?:not\s+actual|exempt|unreadable|inoperable)\b",
        r"\bnot\s+actual\s+(?:mileage|miles)\b",
    ),
    "towed": (
        r"\btowed\b",
        r"\btow\s+away\b",
        r"\bmust\s+be\s+towed\b",
        r"\bneeds?\s+(?:to\s+be\s+)?towed\b",
    ),
    "rust": (
        r"\brust\b",
        r"\brusty\b",
        r"\bsurface\s+rust\b",
        r"\brust(?:ed|ing)?\b",
    ),
    "check engine": (
        r"\bcheck\s+engine\b",
        r"\bcheck\s+engine\s+light\b",
        r"\bcel\b",
        r"\bservice\s+engine\s+soon\b",
    ),
    "does not start": (
        r"\bdoes\s+not\s+start\b",
        r"\bdoesn't\s+start\b",
        r"\bwill\s+not\s+start\b",
        r"\bwon't\s+start\b",
        r"\bno\s+start\b",
        r"\bcranks?\s+but\s+(?:does\s+not|doesn't|won't|will\s+not)\s+start\b",
        r"\bdoes\s+not\s+run\b",
        r"\bdoesn't\s+run\b",
        r"\bwill\s+not\s+run\b",
        r"\bwon't\s+run\b",
    ),
}


# -------------------------------
# States allowed for alerting. Centralized in config.py through TARGET_STATES.
# -------------------------------
ALERT_STATES = target_state_names()


@dataclass(frozen=True)
class GasFastFlipRule:
    lane: str
    makes: tuple[str, ...]
    models: tuple[str, ...]
    year_min: int
    year_max: int
    engines: tuple[str, ...]

    @property
    def reason(self) -> str:
        engine_text = " or ".join(self.engines)
        return f"{self.lane}: {self.year_min}-{self.year_max}, engine {engine_text}"


@dataclass(frozen=True)
class DieselTruckRule:
    lane: str
    makes: tuple[str, ...]
    models: tuple[str, ...]
    year_min: int
    year_max: int
    engines: tuple[str, ...]

    @property
    def reason(self) -> str:
        model_text = " or ".join(self.models)
        engine_text = " or ".join(self.engines)
        return f"{self.lane}: {self.year_min}-{self.year_max}, model {model_text}, engine {engine_text}"


GAS_FAST_FLIP_RULES = (
    GasFastFlipRule(
        lane="Ford F-150",
        makes=("Ford",),
        models=("F-150",),
        year_min=2015,
        year_max=2017,
        engines=("5.0 V8", "2.7 EcoBoost"),
    ),
    GasFastFlipRule(
        lane="Ford F-250/F-350 gas",
        makes=("Ford",),
        models=("F-250", "F-350"),
        year_min=2011,
        year_max=2016,
        engines=("6.2L gas",),
    ),
    GasFastFlipRule(
        lane="Silverado/Sierra 1500",
        makes=("Chevrolet", "GMC"),
        models=("Silverado 1500", "Sierra 1500", "1500"),
        year_min=2014,
        year_max=2018,
        engines=("5.3 V8",),
    ),
    GasFastFlipRule(
        lane="Silverado/Sierra 2500/3500 gas",
        makes=("Chevrolet", "GMC"),
        models=("Silverado 2500", "Silverado 3500", "Sierra 2500", "Sierra 3500", "2500", "3500"),
        year_min=2011,
        year_max=2018,
        engines=("6.0 gas",),
    ),
    GasFastFlipRule(
        lane="Ram 1500",
        makes=("Ram",),
        models=("Ram 1500", "1500"),
        year_min=2014,
        year_max=2019,
        engines=("5.7 HEMI",),
    ),
)

GAS_FAST_FLIP_RULE = GAS_FAST_FLIP_RULES

DIESEL_TRUCK_FILTER = (
    DieselTruckRule(
        lane="FORD",
        makes=("Ford",),
        models=("F-250", "F-350", "F-450", "F-550", "F-650", "F-750"),
        year_min=2011,
        year_max=2016,
        engines=("6.7", "6.7 Power Stroke", "Power Stroke"),
    ),
    DieselTruckRule(
        lane="CHEVROLET_GMC",
        makes=("Chevrolet", "GMC"),
        models=("Silverado 2500", "Silverado 3500", "Sierra 2500", "Sierra 3500"),
        year_min=2011,
        year_max=2016,
        engines=("Duramax", "6.6 Duramax", "6.6"),
    ),
    DieselTruckRule(
        lane="RAM",
        makes=("Ram",),
        models=("Ram 2500", "Ram 3500"),
        year_min=2010,
        year_max=2018,
        engines=("Cummins", "6.7 Cummins"),
    ),
    DieselTruckRule(
        lane="INTERNATIONAL",
        makes=("International",),
        models=("4300",),
        year_min=2006,
        year_max=2016,
        engines=("DT466",),
    ),
    DieselTruckRule(
        lane="FREIGHTLINER",
        makes=("Freightliner",),
        models=("M2",),
        year_min=2006,
        year_max=2016,
        engines=("Cummins", "CAT", "Caterpillar"),
    ),
)


_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")

_MAKE_PATTERNS = {
    "Ford": (r"\bford\b",),
    "Chevrolet": (r"\bchevrolet\b", r"\bchevy\b"),
    "GMC": (r"\bgmc\b",),
    "Ram": (r"\bdodge\s+ram\b", r"\bram\b", r"\bdodge\b"),
}

_OTHER_MAKE_PATTERNS = {
    "Toyota": (r"\btoyota\b",),
    "Nissan": (r"\bnissan\b",),
    "Honda": (r"\bhonda\b",),
    "Jeep": (r"\bjeep\b",),
    "Cadillac": (r"\bcadillac\b",),
    "Lincoln": (r"\blincoln\b",),
    "Buick": (r"\bbuick\b",),
    "Chrysler": (r"\bchrysler\b",),
    "Acura": (r"\bacura\b",),
    "Lexus": (r"\blexus\b",),
    "Infiniti": (r"\binfiniti\b",),
    "Mazda": (r"\bmazda\b",),
    "Hyundai": (r"\bhyundai\b",),
    "Kia": (r"\bkia\b",),
    "Subaru": (r"\bsubaru\b",),
    "Mitsubishi": (r"\bmitsubishi\b",),
    "Volkswagen": (r"\bvolkswagen\b", r"\bvw\b"),
    "Audi": (r"\baudi\b",),
    "Mercedes-Benz": (r"\bmercedes(?:-benz)?\b",),
    "BMW": (r"\bbmw\b",),
    "Tesla": (r"\btesla\b",),
    "Freightliner": (r"\bfreightliner\b",),
    "International": (r"\binternational\b",),
    "Isuzu": (r"\bisuzu\b",),
    "Hino": (r"\bhino\b",),
    "Peterbilt": (r"\bpeterbilt\b",),
    "Kenworth": (r"\bkenworth\b",),
    "Mack": (r"\bmack\b",),
    "Volvo": (r"\bvolvo\b",),
}

_MODEL_PATTERNS = {
    "F-150": (r"\bf[\s-]?150\b",),
    "F-250": (r"\bf[\s-]?250\b",),
    "F-350": (r"\bf[\s-]?350\b",),
    "F-450": (r"\bf[\s-]?450\b",),
    "F-550": (r"\bf[\s-]?550\b",),
    "F-650": (r"\bf[\s-]?650\b",),
    "F-750": (r"\bf[\s-]?750\b",),
    "Silverado 1500": (r"\bsilverado\s+1500\b", r"\bchev(?:rolet|y)?\s+1500\b"),
    "Sierra 1500": (r"\bsierra\s+1500\b", r"\bgmc\s+1500\b"),
    "Silverado 2500": (r"\bsilverado\s+2500(?:\s*hd)?\b", r"\bchev(?:rolet|y)?\s+2500(?:\s*hd)?\b"),
    "Silverado 3500": (r"\bsilverado\s+3500(?:\s*hd)?\b", r"\bchev(?:rolet|y)?\s+3500(?:\s*hd)?\b"),
    "Sierra 2500": (r"\bsierra\s+2500(?:\s*hd)?\b", r"\bgmc\s+2500(?:\s*hd)?\b"),
    "Sierra 3500": (r"\bsierra\s+3500(?:\s*hd)?\b", r"\bgmc\s+3500(?:\s*hd)?\b"),
    "Ram 1500": (r"\bram\s+1500\b", r"\bdodge\s+ram\s+1500\b"),
    "Ram 2500": (r"\bram\s+2500\b", r"\bdodge\s+ram\s+2500\b"),
    "Ram 3500": (r"\bram\s+3500\b", r"\bdodge\s+ram\s+3500\b"),
    "4300": (r"\binternational\s+4300\b", r"\bmodel\s*:?\s*4300\b"),
    "M2": (r"\bfreightliner\s+m2\b", r"\bm2\s+106\b", r"\bm2\b"),
    "1500": (r"\b1500\b",),
    "2500": (r"\b2500\b",),
    "3500": (r"\b3500\b",),
}

_OTHER_MODEL_PATTERNS = {
    "Colorado": (r"\bcolorado\b",),
    "Canyon": (r"\bcanyon\b",),
    "Ranger": (r"\branger\b",),
    "Maverick": (r"\bmaverick\b",),
    "Transit": (r"\btransit\b",),
    "E-150": (r"\be[\s-]?150\b",),
    "E-250": (r"\be[\s-]?250\b",),
    "E-350": (r"\be[\s-]?350\b",),
    "Express": (r"\bexpress\b",),
    "Savana": (r"\bsavana\b",),
    "Tahoe": (r"\btahoe\b",),
    "Suburban": (r"\bsuburban\b",),
    "Explorer": (r"\bexplorer\b",),
    "Expedition": (r"\bexpedition\b",),
    "Escape": (r"\bescape\b",),
    "Edge": (r"\bedge\b",),
    "Durango": (r"\bdurango\b",),
    "Charger": (r"\bcharger\b",),
    "Challenger": (r"\bchallenger\b",),
    "Grand Caravan": (r"\bgrand\s+caravan\b",),
    "Tacoma": (r"\btacoma\b",),
    "Tundra": (r"\btundra\b",),
    "Titan": (r"\btitan\b",),
    "Frontier": (r"\bfrontier\b",),
    "Ridgeline": (r"\bridgeline\b",),
    "Gladiator": (r"\bgladiator\b",),
    "Wrangler": (r"\bwrangler\b",),
    "Cherokee": (r"\bcherokee\b",),
    "Sprinter": (r"\bsprinter\b",),
    "M2": (r"\bm2\b", r"\bm2\s+106\b"),
    "NPR": (r"\bnpr\b",),
}

MODEL_DISPLAY_QUALIFIER_PATTERNS = (
    r"\s+police\s+utility\b.*$",
    r"\s+police\s+interceptor\b.*$",
    r"\s+(?:police|utility|awd|4wd|2wd|fwd|rwd)\b.*$",
    r"\s+(?:crew|regular|extended|super|quad|double)\s+cab\b.*$",
    r"\s+(?:supercrew|supercab|megacab)\b.*$",
)

KNOWN_TRUCK_CONTEXT_PATTERNS = (
    r"\bf[\s-]?(?:150|250|350|450|550|650|750)\b",
    r"\bsuper\s+duty\b",
    r"\bsilverado\b",
    r"\bsierra\b",
    r"\bram\b",
    r"\bdodge\s+ram\b",
    r"\b(?:1500|2500|3500)(?:\s*hd)?\b",
    r"\binternational\s+4300\b",
    r"\bfreightliner\s+m2\b",
    r"\bm2\s+106\b",
)

_APPROVED_ENGINE_PATTERNS = {
    "5.0 V8": (
        r"\b5\.0\s*(?:l|liter|litre)?\b(?:.{0,40}\bv8\b)?",
        r"\bcoyote\b",
    ),
    "2.7 EcoBoost": (
        r"\b2\.7\s*(?:l|liter|litre)?\b.{0,50}\beco\s*boost\b",
        r"\beco\s*boost\b.{0,50}\b2\.7\s*(?:l|liter|litre)?\b",
    ),
    "6.2L gas": (
        r"\b6\.2\s*(?:l|liter|litre)?\b",
    ),
    "5.3 V8": (
        r"\b5\.3\s*(?:l|liter|litre)?\b",
    ),
    "6.0 gas": (
        r"\b6\.0\s*(?:l|liter|litre)?\b",
    ),
    "5.7 HEMI": (
        r"\b5\.7\s*(?:l|liter|litre)?\b.{0,50}\bhemi\b",
        r"\bhemi\b",
    ),
}

_KNOWN_BAD_ENGINE_PATTERNS = (
    r"\b3\.5\s*(?:l|liter|litre)?\b.{0,50}\beco\s*boost\b",
    r"\beco\s*boost\b.{0,50}\b3\.5\s*(?:l|liter|litre)?\b",
    r"\b3\.3\s*(?:l|liter|litre)?\b",
    r"\b3\.5\s*(?:l|liter|litre)?\b",
    r"\b3\.7\s*(?:l|liter|litre)?\b",
    r"\b4\.6\s*(?:l|liter|litre)?\b",
    r"\b6\.7\s*(?:l|liter|litre)?\b",
    r"\b6\.6\s*(?:l|liter|litre)?\b",
    r"\b6\.4\s*(?:l|liter|litre)?\b",
    r"\b6\.8\s*(?:l|liter|litre)?\b",
    r"\b7\.3\s*(?:l|liter|litre)?\b",
    r"\b4\.8\s*(?:l|liter|litre)?\b",
    r"\b4\.3\s*(?:l|liter|litre)?\b",
    r"\bdiesel\b",
    r"\bturbo\s+diesel\b",
    r"\bpower\s*stroke\b",
    r"\bpowerstroke\b",
    r"\bduramax\b",
    r"\bcummins\b",
)

_AMBIGUOUS_ENGINE_PATTERNS = (
    r"\bv8\b",
    r"\bv6\b",
    r"\beco\s*boost\b",
    r"\bgas(?:oline)?\b",
)

_GAS_FUEL_PATTERNS = (
    r"\bgas(?:oline)?\b",
)

_DIESEL_FUEL_PATTERNS = (
    r"\bdiesel\b",
    r"\bturbo\s+diesel\b",
    r"\bpower\s*stroke\b",
    r"\bpowerstroke\b",
    r"\bduramax\b",
    r"\bcummins\b",
    r"\bdt\s*466\b",
    r"\bcat\b",
    r"\bcaterpillar\b",
)


# Backward-compatible keyword set for older ad-hoc tests/imports.
TARGET_KEYWORDS = set().union(
    *[set(values) for values in GAS_MAKES.values()],
    *[set(values) for values in GAS_MODELS.values()],
    *[set(values) for values in GAS_ENGINES.values()],
    *[set(values) for values in DIESEL_MAKES.values()],
    *[set(values) for values in DIESEL_MODELS.values()],
    *[set(values) for values in DIESEL_ENGINES.values()],
    set(SPECIALTY_TRUCK_KEYWORDS_TOP),
    set(SPECIALTY_TRUCK_KEYWORDS_GOOD),
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _first_pattern_match(text: str, patterns: tuple[str, ...]) -> Optional[re.Match]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match
    return None


def _keyword_pattern(keyword: str) -> str:
    escaped = re.escape(keyword.lower())
    escaped = escaped.replace(r"\ ", r"\s+").replace(r"\-", r"[-\s]?")
    return rf"(?<!\w){escaped}(?!\w)"


def _find_keyword_matches(text: str, keywords: tuple[str, ...]) -> list[str]:
    clean_text = text or ""
    matches = []
    for keyword in keywords:
        if re.search(_keyword_pattern(keyword), clean_text, re.IGNORECASE):
            matches.append(keyword)
    return matches


def _has_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    clean_text = text or ""
    return any(re.search(pattern, clean_text, re.IGNORECASE) for pattern in patterns)


def _has_gas_fuel_clue(text: str) -> bool:
    return _has_any_pattern(text, _GAS_FUEL_PATTERNS)


def _has_diesel_fuel_clue(text: str) -> bool:
    return _has_any_pattern(text, _DIESEL_FUEL_PATTERNS)


def _gas_lane_control_ok(text: str, engine: dict) -> bool:
    if _has_diesel_fuel_clue(text):
        return False

    return (
        bool(engine.get("known") and engine.get("approved")) or
        _has_gas_fuel_clue(text)
    )


def _diesel_lane_control_ok(text: str, engine: dict) -> bool:
    if _has_gas_fuel_clue(text):
        return False

    return bool(engine.get("known")) or _has_diesel_fuel_clue(text)


def find_specialty_keywords(text: str) -> dict:
    top_matches = _find_keyword_matches(text, SPECIALTY_TRUCK_KEYWORDS_TOP)
    good_matches = _find_keyword_matches(text, SPECIALTY_TRUCK_KEYWORDS_GOOD)

    priority_level = None
    if top_matches:
        priority_level = "top"
    elif good_matches:
        priority_level = "good"

    return {
        "priority_level": priority_level,
        "matched": top_matches + good_matches,
    }


def find_year(text: str) -> Optional[int]:
    match = _YEAR_RE.search(text or "")
    return int(match.group(1)) if match else None


def find_make(text: str) -> Optional[str]:
    for make, patterns in _MAKE_PATTERNS.items():
        if _first_pattern_match(text, patterns):
            return make
    for make, patterns in _OTHER_MAKE_PATTERNS.items():
        if _first_pattern_match(text, patterns):
            return make
    return None


def find_model(text: str) -> Optional[str]:
    matches = []
    for model_patterns in (_MODEL_PATTERNS, _OTHER_MODEL_PATTERNS):
        for model, patterns in model_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    matches.append((match.start(), -len(match.group(0)), model))

    if matches:
        return min(matches)[2]

    return None


def clean_model_display(model: Optional[str]) -> Optional[str]:
    """
    Clean model strings for display only. Evaluation still uses the original
    listing text and find_model() results.
    """
    clean_model = normalize_text(model or "")
    if not clean_model:
        return None

    model_patterns = {}
    model_patterns.update(_MODEL_PATTERNS)
    model_patterns.update(_OTHER_MODEL_PATTERNS)

    ordered_models = sorted(model_patterns, key=len, reverse=True)
    for base_model in ordered_models:
        for pattern in model_patterns[base_model]:
            if re.search(pattern, clean_model, re.IGNORECASE):
                return base_model

    for pattern in MODEL_DISPLAY_QUALIFIER_PATTERNS:
        cleaned = re.sub(pattern, "", clean_model, flags=re.IGNORECASE).strip()
        if cleaned != clean_model:
            return cleaned or clean_model

    return clean_model


def _normalize_structured_make(make: Optional[str]) -> Optional[str]:
    clean_make = normalize_text(make or "")
    if not clean_make:
        return None
    return find_make(clean_make) or clean_make


def _normalize_structured_model(model: Optional[str]) -> Optional[str]:
    return clean_model_display(model)


def find_engine(text: str, make: Optional[str] = None, model: Optional[str] = None) -> dict:
    """
    Return exact approved/disallowed engine details when the listing states enough.
    Ambiguous text like "V8" is kept for debug, but treated as unknown so it
    fails open per the alert rules.
    """
    clean_text = text or ""

    for pattern in _KNOWN_BAD_ENGINE_PATTERNS:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            return {
                "value": match.group(0).strip(),
                "text": match.group(0).strip(),
                "known": True,
                "approved": False,
            }

    for engine, patterns in _APPROVED_ENGINE_PATTERNS.items():
        match = _first_pattern_match(clean_text, patterns)
        if match:
            return {
                "value": engine,
                "text": match.group(0).strip(),
                "known": True,
                "approved": True,
            }

    if make == "Ram" and model == "Ram 1500":
        match = re.search(r"\b5\.7\s*(?:l|liter|litre)?\b", clean_text, re.IGNORECASE)
        if match:
            return {
                "value": "5.7 HEMI",
                "text": match.group(0).strip(),
                "known": True,
                "approved": True,
            }

    match = re.search(r"\b5\.7\s*(?:l|liter|litre)?\b", clean_text, re.IGNORECASE)
    if match:
        return {
            "value": match.group(0).strip(),
            "text": match.group(0).strip(),
            "known": True,
            "approved": False,
        }

    ambiguous = []
    for pattern in _AMBIGUOUS_ENGINE_PATTERNS:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            ambiguous.append(match.group(0).strip())

    return {
        "value": None,
        "text": ", ".join(dict.fromkeys(ambiguous)),
        "known": False,
        "approved": False,
    }


def find_diesel_engine(text: str) -> dict:
    clean_text = text or ""

    for engine, keywords in DIESEL_ENGINES.items():
        for keyword in keywords:
            match = re.search(_keyword_pattern(keyword), clean_text, re.IGNORECASE)
            if match:
                return {
                    "value": engine,
                    "text": match.group(0).strip(),
                    "known": True,
                    "approved": True,
                }

    return {
        "value": None,
        "text": "",
        "known": False,
        "approved": False,
    }


def find_exclude_keywords(text: str) -> list[str]:
    return find_hard_exclude_keywords(text)


def _find_pattern_family_matches(text: str, pattern_families: dict[str, tuple[str, ...]]) -> list[str]:
    clean_text = text or ""
    matches = []
    for label, patterns in pattern_families.items():
        if any(re.search(pattern, clean_text, re.IGNORECASE) for pattern in patterns):
            matches.append(label)
    return matches


def find_hard_exclude_keywords(text: str) -> list[str]:
    return _find_pattern_family_matches(text, HARD_EXCLUDE_PATTERNS)


def find_soft_warning_keywords(text: str) -> list[str]:
    return _find_pattern_family_matches(text, SOFT_WARNING_PATTERNS)


def find_exclude_keyword_groups(text: str) -> dict:
    hard_matches = find_hard_exclude_keywords(text)
    soft_matches = find_soft_warning_keywords(text)
    return {
        "hard_exclude_keywords_matched": hard_matches,
        "hard_exclude_hit": bool(hard_matches),
        "soft_warning_keywords_matched": soft_matches,
    }


def location_matches_alert_state(location: str) -> bool:
    return is_allowed_state(location)


def parse_bid_amount(value: str | None) -> Optional[float]:
    if value is None:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _match_status_for_rule(rule: GasFastFlipRule, year: Optional[int], make: Optional[str], model: Optional[str], engine: dict) -> dict:
    engine_value = engine.get("value")
    engine_known = bool(engine.get("known"))

    return {
        "year_ok": year is None or rule.year_min <= year <= rule.year_max,
        "make_ok": make is None or make in rule.makes,
        "model_ok": model is None or model in rule.models,
        "engine_ok": (not engine_known) or engine_value in rule.engines,
    }


def _debug_status_for_rule(rule: GasFastFlipRule, year: Optional[int], make: Optional[str], model: Optional[str], engine: dict) -> dict:
    engine_value = engine.get("value")
    engine_known = bool(engine.get("known"))

    return {
        "year_ok": year is None or rule.year_min <= year <= rule.year_max,
        "make_ok": make is not None and make in rule.makes,
        "model_ok": model is not None and model in rule.models,
        "engine_ok": (not engine_known) or engine_value in rule.engines,
    }


def _has_known_truck_context(text: str) -> bool:
    clean_text = text or ""
    return any(re.search(pattern, clean_text, re.IGNORECASE) for pattern in KNOWN_TRUCK_CONTEXT_PATTERNS)


def _engine_match_has_vehicle_context(make: Optional[str], model: Optional[str], vehicle_context_text: str) -> bool:
    return make is not None or model is not None or _has_known_truck_context(vehicle_context_text)


def _known_match_score(statuses: dict, year: Optional[int], make: Optional[str], model: Optional[str], engine: dict) -> int:
    score = 0
    weights = {
        "year_ok": 1,
        "make_ok": 3,
        "model_ok": 4,
        "engine_ok": 2,
    }
    known_fields = (
        ("year_ok", year is not None),
        ("make_ok", make is not None),
        ("model_ok", model is not None),
        ("engine_ok", bool(engine.get("known"))),
    )
    for key, is_known in known_fields:
        if not is_known:
            continue
        weight = weights[key]
        score += weight if statuses[key] else -weight
    return score


def evaluate_gas_fast_flip(
    text: str,
    structured_make: Optional[str] = None,
    structured_model: Optional[str] = None,
    allow_make_model_fallback: bool = True,
    vehicle_context_text: Optional[str] = None,
) -> dict:
    """
    Evaluate the gas fast-flip lanes.
    Missing make/model values still fail open for lane matching, but returned
    make_ok/model_ok debug flags are true only when a found value fits the lane.
    """
    clean_text = normalize_text(text)
    year = find_year(clean_text)
    make = _normalize_structured_make(structured_make) if structured_make else (
        find_make(clean_text) if allow_make_model_fallback else None
    )
    model = _normalize_structured_model(structured_model) if structured_model else (
        find_model(clean_text) if allow_make_model_fallback else None
    )
    engine = find_engine(clean_text, make, model)
    gas_control_ok = _gas_lane_control_ok(clean_text, engine)
    vehicle_context_ok = _engine_match_has_vehicle_context(
        make,
        model,
        normalize_text(vehicle_context_text if vehicle_context_text is not None else clean_text),
    )

    lane_results = []
    for rule in GAS_FAST_FLIP_RULES:
        statuses = _match_status_for_rule(rule, year, make, model, engine)
        debug_statuses = _debug_status_for_rule(rule, year, make, model, engine)
        lane_results.append(
            {
                "rule": rule,
                "statuses": statuses,
                "debug_statuses": debug_statuses,
                "matches": all(statuses.values()) and gas_control_ok and vehicle_context_ok,
                "fuel_control_ok": gas_control_ok,
                "vehicle_context_ok": vehicle_context_ok,
                "score": _known_match_score(statuses, year, make, model, engine),
            }
        )

    matched = [result for result in lane_results if result["matches"]]
    selected = matched[0] if matched else max(lane_results, key=lambda result: result["score"])
    selected_rule = selected["rule"]
    selected_statuses = selected["statuses"]
    selected_debug_statuses = selected["debug_statuses"]

    return {
        "gas_rule": bool(matched),
        "gas_match": bool(matched),
        "matched_lane": selected_rule.lane if matched else None,
        "matched_rule_reason": selected_rule.reason if matched else "No gas fast-flip lane matched",
        "year_value": year,
        "make_value": make,
        "model_value": model,
        "engine_value": engine.get("value"),
        "engine_text": engine.get("text") or "",
        "engine_known": bool(engine.get("known")),
        "year_ok": selected_statuses["year_ok"],
        "make_ok": selected_debug_statuses["make_ok"],
        "model_ok": selected_debug_statuses["model_ok"],
        "engine_ok": selected_statuses["engine_ok"],
        "fuel_control_ok": gas_control_ok,
        "vehicle_context_ok": vehicle_context_ok,
        "all_lane_results": lane_results,
    }


def evaluate_diesel_truck_filter(
    text: str,
    structured_make: Optional[str] = None,
    structured_model: Optional[str] = None,
    allow_make_model_fallback: bool = True,
    vehicle_context_text: Optional[str] = None,
) -> dict:
    """
    Evaluate the diesel truck lane.
    Missing make/model values still fail open for lane matching, but returned
    make_ok/model_ok debug flags are true only when a found value fits the lane.
    """
    clean_text = normalize_text(text)
    year = find_year(clean_text)
    make = _normalize_structured_make(structured_make) if structured_make else (
        find_make(clean_text) if allow_make_model_fallback else None
    )
    model = _normalize_structured_model(structured_model) if structured_model else (
        find_model(clean_text) if allow_make_model_fallback else None
    )
    engine = find_diesel_engine(clean_text)
    diesel_control_ok = _diesel_lane_control_ok(clean_text, engine)
    vehicle_context_ok = _engine_match_has_vehicle_context(
        make,
        model,
        normalize_text(vehicle_context_text if vehicle_context_text is not None else clean_text),
    )
    specialty = find_specialty_keywords(clean_text)

    lane_results = []
    for rule in DIESEL_TRUCK_FILTER:
        statuses = _match_status_for_rule(rule, year, make, model, engine)
        debug_statuses = _debug_status_for_rule(rule, year, make, model, engine)
        lane_results.append(
            {
                "rule": rule,
                "statuses": statuses,
                "debug_statuses": debug_statuses,
                "matches": all(statuses.values()) and diesel_control_ok and vehicle_context_ok,
                "fuel_control_ok": diesel_control_ok,
                "vehicle_context_ok": vehicle_context_ok,
                "score": _known_match_score(statuses, year, make, model, engine),
            }
        )

    matched = [result for result in lane_results if result["matches"]]
    selected = matched[0] if matched else max(lane_results, key=lambda result: result["score"])
    selected_rule = selected["rule"]
    selected_statuses = selected["statuses"]
    selected_debug_statuses = selected["debug_statuses"]
    diesel_match = bool(matched)
    priority_level = specialty["priority_level"] or ("standard" if diesel_match else None)

    return {
        "diesel_match": diesel_match,
        "matched_lane": selected_rule.lane if diesel_match else None,
        "matched_rule_reason": selected_rule.reason if diesel_match else "No diesel truck filter matched",
        "diesel_priority_level": priority_level,
        "specialty_keywords_matched": specialty["matched"],
        "year_value": year,
        "make_value": make,
        "model_value": model,
        "engine_value": engine.get("value"),
        "engine_text": engine.get("text") or "",
        "engine_known": bool(engine.get("known")),
        "year_ok": selected_statuses["year_ok"],
        "make_ok": selected_debug_statuses["make_ok"],
        "model_ok": selected_debug_statuses["model_ok"],
        "engine_ok": selected_statuses["engine_ok"],
        "fuel_control_ok": diesel_control_ok,
        "vehicle_context_ok": vehicle_context_ok,
        "all_lane_results": lane_results,
    }
