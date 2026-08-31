# file: src/core/consumer_gas_liquid.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.config import (
    CONSUMER_GAS_ALERT_SCORE,
    CONSUMER_GAS_MAX_ALERT_MILES_DEFAULT,
    CONSUMER_GAS_WATCHLIST_SCORE,
    DEFAULT_BUYER_PREMIUM_RATE,
    DEFAULT_FIXED_COSTS,
    DEFAULT_REPAIR_RESERVE,
    DEFAULT_SAFETY_BUFFER,
    DEFAULT_SHIPPING_RESERVE,
    MIN_CONSUMER_GAS_NET_PROFIT,
)


STRATEGY = "CONSUMER_GAS_LIQUID"
NEXT_ACTION = "GET CARVANA QUOTE"

CORE = "core"
OPPORTUNISTIC = "opportunistic"

_YEAR_RE = re.compile(r"\b(20[0-4]\d|19[8-9]\d)\b")
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)
_MILEAGE_VALUE_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{1,3}(?:\.\d+)?)\s*(k|mi|miles|mile)?\b",
    re.IGNORECASE,
)
_MILEAGE_CONTEXT_RE = re.compile(
    r"\b(?:odometer|mileage|miles|mi)\b\s*"
    r"(?:reading|reads|shows|is|was|actual|listed as|[:#-])?\s*"
    r"(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{1,3}(?:\.\d+)?\s*k)\b",
    re.IGNORECASE,
)

DIESEL_PATTERNS = (
    r"\bdiesel\b",
    r"\bturbo\s*diesel\b",
    r"\bpower\s*stroke\b",
    r"\bpowerstroke\b",
    r"\bduramax\b",
    r"\bcummins\b",
    r"\bdt\s*466\b",
    r"\bmaxxforce\b",
    r"\bt444e\b",
    r"\b6\.7\s*(?:l|liter|litre)?\s*(?:diesel|power\s*stroke|powerstroke|cummins)\b",
    r"\b6\.4\s*(?:l|liter|litre)?\s*diesel\b",
    r"\b6\.0\s*(?:l|liter|litre)?\s*diesel\b",
)

GAS_FUEL_PATTERNS = (
    r"\bgas\b",
    r"\bgasoline\b",
    r"\bunleaded\b",
    r"\bflex\s*fuel\b",
    r"\bffv\b",
)

UNKNOWN_MILEAGE_PATTERNS = (
    r"\bunknown\s+(?:mileage|miles|odometer)\b",
    r"\b(?:mileage|miles|odometer)\s+unknown\b",
    r"\bnot\s+actual\s+(?:mileage|miles)\b",
    r"\btrue\s+mileage\s+unknown\b",
    r"\btmu\b",
    r"\bexempt\s+mileage\b",
)

HARD_REJECT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "consumer_gas_rust",
        (
            r"\bmeaningful\s+rust\b",
            r"\bvisible\s+rust\b",
            r"\bframe\s+rust\b",
            r"\bframe\s+rot\b",
            r"\bsevere\s+corrosion\b",
            r"\bcorrosion\s+damage\b",
            r"\bmajor\s+rust\b",
            r"\bsevere\s+rust\b",
        ),
    ),
    (
        "consumer_gas_title_problem",
        (
            r"\bsalvage(?:\s+title)?\b",
            r"\brebuilt\s+title\b",
            r"\bparts\s+only\b",
            r"\bfor\s+parts\b",
            r"\bno\s+titles?\b",
            r"\bmissing\s+titles?\b",
            r"\bbill\s+of\s+sale\s+only\b",
        ),
    ),
    (
        "consumer_gas_major_mechanical",
        (
            r"\bframe\s+damage\b",
            r"\bstructural\s+damage\b",
            r"\bflood\b",
            r"\bfire\s+damage\b",
            r"\bmajor\s+collision\b",
            r"\bdeployed\s+airbags?\b",
            r"\bengine\s+knock\b",
            r"\bblown\s+engine\b",
            r"\bseized\s+engine\b",
            r"\bneeds\s+(?:an?\s+)?engine\b",
            r"\bengine\s+needs\s+repairs?\b",
            r"\bbad\s+transmission\b",
            r"\btransmission\s+(?:failure|failed)\b",
            r"\btransmission\s+needs\s+repairs?\b",
            r"\bsevere\s+overheating\b",
            r"\bdoes\s+not\s+run\b",
            r"\bdoesn['’]?t\s+run\b",
            r"\bwill\s+not\s+run\b",
            r"\bnon[-\s]?running\b",
            r"\binoperable\b",
        ),
    ),
)


@dataclass(frozen=True)
class ConsumerGasRule:
    model_key: str
    make: str
    model: str
    aliases: tuple[str, ...]
    group: str
    base_score: int
    max_normal_age: int
    possible_exceptional_age: int
    preferred_engines: tuple[str, ...]
    acceptable_gas_engines: tuple[str, ...]
    strong_trims: tuple[str, ...]
    good_trims: tuple[str, ...]
    weak_trims: tuple[str, ...]
    value_retention_bonus: int = 0
    alert_threshold: int = CONSUMER_GAS_ALERT_SCORE
    watchlist_threshold: int = CONSUMER_GAS_WATCHLIST_SCORE
    max_alert_miles: int = CONSUMER_GAS_MAX_ALERT_MILES_DEFAULT


CONSUMER_GAS_RULES: dict[str, ConsumerGasRule] = {
    "toyota_tundra": ConsumerGasRule(
        model_key="toyota_tundra",
        make="Toyota",
        model="Tundra",
        aliases=(r"\btoyota\s+tundra\b", r"\btundra\b"),
        group=CORE,
        base_score=34,
        max_normal_age=9,
        possible_exceptional_age=12,
        preferred_engines=("5.7L",),
        acceptable_gas_engines=("5.7L",),
        strong_trims=("Limited", "Platinum", "1794 Edition", "TRD Pro"),
        good_trims=("SR5",),
        weak_trims=("SR",),
        value_retention_bonus=10,
    ),
    "toyota_tacoma": ConsumerGasRule(
        model_key="toyota_tacoma",
        make="Toyota",
        model="Tacoma",
        aliases=(r"\btoyota\s+tacoma\b", r"\btacoma\b"),
        group=CORE,
        base_score=32,
        max_normal_age=8,
        possible_exceptional_age=10,
        preferred_engines=("3.5L",),
        acceptable_gas_engines=("3.5L", "2.7L"),
        strong_trims=("TRD Pro", "TRD Off-Road", "TRD Sport"),
        good_trims=("SR5",),
        weak_trims=("SR",),
        value_retention_bonus=8,
    ),
    "ford_f150": ConsumerGasRule(
        model_key="ford_f150",
        make="Ford",
        model="F-150",
        aliases=(r"\bford\s+f[-\s]?150\b", r"\bf[-\s]?150\b"),
        group=CORE,
        base_score=25,
        max_normal_age=7,
        possible_exceptional_age=9,
        preferred_engines=("5.0L",),
        acceptable_gas_engines=("5.0L", "2.7L EcoBoost"),
        strong_trims=("Lariat", "King Ranch", "Platinum", "Limited"),
        good_trims=("XLT",),
        weak_trims=("XL",),
    ),
    "chevrolet_silverado_1500": ConsumerGasRule(
        model_key="chevrolet_silverado_1500",
        make="Chevrolet",
        model="Silverado 1500",
        aliases=(r"\bchevrolet\s+silverado\b", r"\bchevy\s+silverado\b", r"\bsilverado\s*1500\b", r"\bsilverado\b"),
        group=CORE,
        base_score=24,
        max_normal_age=7,
        possible_exceptional_age=9,
        preferred_engines=("5.3L", "6.2L"),
        acceptable_gas_engines=("5.3L", "6.2L", "2.7L"),
        strong_trims=("LTZ", "High Country", "RST", "Trail Boss"),
        good_trims=("LT",),
        weak_trims=("WT", "Work Truck"),
    ),
    "gmc_sierra_1500": ConsumerGasRule(
        model_key="gmc_sierra_1500",
        make="GMC",
        model="Sierra 1500",
        aliases=(r"\bgmc\s+sierra\b", r"\bsierra\s*1500\b", r"\bsierra\b"),
        group=CORE,
        base_score=24,
        max_normal_age=7,
        possible_exceptional_age=9,
        preferred_engines=("5.3L", "6.2L"),
        acceptable_gas_engines=("5.3L", "6.2L", "2.7L"),
        strong_trims=("SLT", "AT4", "Denali"),
        good_trims=("SLE",),
        weak_trims=(),
    ),
    "ram_1500": ConsumerGasRule(
        model_key="ram_1500",
        make="Ram",
        model="1500",
        aliases=(r"\bram\s*1500\b", r"\bdodge\s+ram\s*1500\b", r"\bram\s+pickup\b"),
        group=CORE,
        base_score=24,
        max_normal_age=7,
        possible_exceptional_age=9,
        preferred_engines=("5.7L HEMI", "5.7L"),
        acceptable_gas_engines=("5.7L HEMI", "5.7L", "3.6L"),
        strong_trims=("Laramie", "Rebel", "Limited"),
        good_trims=("Big Horn", "Lone Star"),
        weak_trims=("Tradesman", "Classic"),
    ),
    "chevrolet_colorado": ConsumerGasRule(
        model_key="chevrolet_colorado",
        make="Chevrolet",
        model="Colorado",
        aliases=(r"\bchevrolet\s+colorado\b", r"\bchevy\s+colorado\b", r"\bcolorado\b"),
        group=OPPORTUNISTIC,
        base_score=12,
        max_normal_age=5,
        possible_exceptional_age=7,
        preferred_engines=("3.6L",),
        acceptable_gas_engines=("3.6L", "2.7L"),
        strong_trims=("ZR2", "Z71"),
        good_trims=("LT",),
        weak_trims=("WT",),
        max_alert_miles=60_000,
    ),
    "gmc_canyon": ConsumerGasRule(
        model_key="gmc_canyon",
        make="GMC",
        model="Canyon",
        aliases=(r"\bgmc\s+canyon\b", r"\bcanyon\b"),
        group=OPPORTUNISTIC,
        base_score=12,
        max_normal_age=5,
        possible_exceptional_age=7,
        preferred_engines=("3.6L",),
        acceptable_gas_engines=("3.6L", "2.7L"),
        strong_trims=("Denali", "AT4"),
        good_trims=("SLE",),
        weak_trims=(),
        max_alert_miles=60_000,
    ),
    "ford_ranger": ConsumerGasRule(
        model_key="ford_ranger",
        make="Ford",
        model="Ranger",
        aliases=(r"\bford\s+ranger\b", r"\branger\b"),
        group=OPPORTUNISTIC,
        base_score=10,
        max_normal_age=5,
        possible_exceptional_age=7,
        preferred_engines=("2.3L EcoBoost",),
        acceptable_gas_engines=("2.3L EcoBoost",),
        strong_trims=("Lariat",),
        good_trims=("XLT",),
        weak_trims=("XL",),
        max_alert_miles=55_000,
    ),
    "nissan_frontier": ConsumerGasRule(
        model_key="nissan_frontier",
        make="Nissan",
        model="Frontier",
        aliases=(r"\bnissan\s+frontier\b", r"\bfrontier\b"),
        group=OPPORTUNISTIC,
        base_score=8,
        max_normal_age=4,
        possible_exceptional_age=6,
        preferred_engines=("3.8L",),
        acceptable_gas_engines=("3.8L", "4.0L"),
        strong_trims=("PRO-4X",),
        good_trims=("SV",),
        weak_trims=("S",),
        max_alert_miles=45_000,
    ),
}

TRIM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TRD Off-Road", (r"\btrd\s+off[-\s]?road\b",)),
    ("TRD Sport", (r"\btrd\s+sport\b",)),
    ("TRD Pro", (r"\btrd\s+pro\b",)),
    ("1794 Edition", (r"\b1794\b",)),
    ("High Country", (r"\bhigh\s+country\b",)),
    ("King Ranch", (r"\bking\s+ranch\b",)),
    ("Trail Boss", (r"\btrail\s+boss\b",)),
    ("Work Truck", (r"\bwork\s+truck\b",)),
    ("Big Horn", (r"\bbig\s+horn\b",)),
    ("Lone Star", (r"\blone\s+star\b",)),
    ("PRO-4X", (r"\bpro[-\s]?4x\b",)),
    ("Tradesman", (r"\btradesman\b",)),
    ("Platinum", (r"\bplatinum\b",)),
    ("Limited", (r"\blimited\b",)),
    ("Laramie", (r"\blaramie\b",)),
    ("Denali", (r"\bdenali\b",)),
    ("Lariat", (r"\blariat\b",)),
    ("Classic", (r"\bclassic\b",)),
    ("Rebel", (r"\brebel\b",)),
    ("ZR2", (r"\bzr2\b",)),
    ("Z71", (r"\bz71\b",)),
    ("LTZ", (r"\bltz\b",)),
    ("RST", (r"\brst\b",)),
    ("AT4", (r"\bat4\b",)),
    ("SLT", (r"\bslt\b",)),
    ("SLE", (r"\bsle\b",)),
    ("SR5", (r"\bsr5\b",)),
    ("XLT", (r"\bxlt\b",)),
    ("XL", (r"\bxl\b",)),
    ("WT", (r"\bwt\b",)),
    ("LT", (r"\blt\b",)),
    ("SV", (r"\bsv\b",)),
    ("SR", (r"\bsr\b",)),
    ("S", (r"\bs\b",)),
)

CAB_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("CrewMax", (r"\bcrewmax\b",)),
    ("SuperCrew", (r"\bsuper\s*crew\b", r"\bsupercrew\b")),
    ("Crew Cab", (r"\bcrew\s+cab\b",)),
    ("Double Cab", (r"\bdouble\s+cab\b",)),
    ("Quad Cab", (r"\bquad\s+cab\b",)),
    ("Access Cab", (r"\baccess\s+cab\b",)),
    ("Extended Cab", (r"\bextended\s+cab\b", r"\bext\s+cab\b", r"\bsupercab\b")),
    ("Regular Cab", (r"\bregular\s+cab\b", r"\breg\s+cab\b", r"\bsingle\s+cab\b")),
)

ENGINE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("6.2L", (r"\b6\.2\s*(?:l|liter|litre)?\b",)),
    ("5.7L HEMI", (r"\b5\.7\s*(?:l|liter|litre)?\s*hemi\b", r"\bhemi\b")),
    ("5.7L", (r"\b5\.7\s*(?:l|liter|litre)?\b",)),
    ("5.3L", (r"\b5\.3\s*(?:l|liter|litre)?\b",)),
    ("5.0L", (r"\b5\.0\s*(?:l|liter|litre)?\b", r"\bcoyote\b")),
    ("4.0L", (r"\b4\.0\s*(?:l|liter|litre)?\b",)),
    ("3.8L", (r"\b3\.8\s*(?:l|liter|litre)?\b",)),
    ("3.6L", (r"\b3\.6\s*(?:l|liter|litre)?\b",)),
    ("3.5L", (r"\b3\.5\s*(?:l|liter|litre)?\b",)),
    ("2.7L EcoBoost", (r"\b2\.7\s*(?:l|liter|litre)?\s*eco\s*boost\b", r"\beco\s*boost\b.{0,35}\b2\.7\b")),
    ("2.7L", (r"\b2\.7\s*(?:l|liter|litre)?\b",)),
    ("2.3L EcoBoost", (r"\b2\.3\s*(?:l|liter|litre)?\s*eco\s*boost\b",)),
)

HD_CONTEXT_PATTERNS = (
    r"\b2500(?:hd)?\b",
    r"\b3500(?:hd)?\b",
    r"\bf[-\s]?250\b",
    r"\bf[-\s]?350\b",
    r"\bram\s*2500\b",
    r"\bram\s*3500\b",
)


def _text_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text_value(item) for item in value.values())
    return str(value)


def listing_text(listing: dict[str, Any] | str) -> str:
    if isinstance(listing, str):
        return re.sub(r"\s+", " ", listing).strip()

    fields = (
        "title",
        "desc",
        "description",
        "category",
        "cat",
        "event_title",
        "container_text",
        "structured_text",
        "make",
        "parsed_make",
        "model",
        "parsed_model",
        "trim",
        "cab",
        "drivetrain",
        "engine",
        "fuel",
        "condition",
        "body_style",
        "bodyStyle",
        "title_status",
        "vin",
        "mileage_display",
    )
    return re.sub(r"\s+", " ", " ".join(_text_value(listing.get(field)) for field in fields)).strip()


def _contains_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", _text_value(value)).strip()


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            out.append(value)
            seen.add(value)
    return out


def identify_consumer_model(listing: dict[str, Any] | str) -> tuple[str | None, ConsumerGasRule | None]:
    text = listing_text(listing).lower()
    make_hint = ""
    model_hint = ""
    if isinstance(listing, dict):
        make_hint = _clean_text(listing.get("make") or listing.get("parsed_make") or listing.get("makebrand")).lower()
        model_hint = _clean_text(listing.get("model") or listing.get("parsed_model")).lower()
    searchable = f"{make_hint} {model_hint} {text}".strip()

    for key, rule in CONSUMER_GAS_RULES.items():
        if key in {"chevrolet_silverado_1500", "gmc_sierra_1500", "ram_1500"} and _contains_pattern(searchable, HD_CONTEXT_PATTERNS):
            continue
        if any(re.search(pattern, searchable, re.IGNORECASE) for pattern in rule.aliases):
            return key, rule
    return None, None


def parse_year(listing: dict[str, Any] | str, text: str | None = None) -> int | None:
    if isinstance(listing, dict):
        for key in ("model_year", "year", "parsed_year", "modelYear", "assetYear"):
            value = listing.get(key)
            if value in (None, ""):
                continue
            try:
                year = int(float(str(value).strip()))
            except (TypeError, ValueError):
                continue
            if 1980 <= year <= 2049:
                return year

    match = _YEAR_RE.search(text if text is not None else listing_text(listing))
    return int(match.group(1)) if match else None


def parse_trim(listing: dict[str, Any] | str, text: str | None = None) -> str | None:
    explicit = ""
    if isinstance(listing, dict):
        explicit = _clean_text(listing.get("trim") or listing.get("parsed_trim"))
    haystack = f"{explicit} {text if text is not None else listing_text(listing)}".strip()
    for trim, patterns in TRIM_PATTERNS:
        if _contains_pattern(haystack, patterns):
            return trim
    return explicit or None


def parse_cab(listing: dict[str, Any] | str, text: str | None = None) -> str | None:
    explicit = ""
    if isinstance(listing, dict):
        explicit = _clean_text(
            listing.get("cab")
            or listing.get("parsed_cab")
            or listing.get("body_style")
            or listing.get("bodyStyle")
        )
    haystack = f"{explicit} {text if text is not None else listing_text(listing)}".strip()
    for cab, patterns in CAB_PATTERNS:
        if _contains_pattern(haystack, patterns):
            return cab
    return explicit or None


def parse_drivetrain(listing: dict[str, Any] | str, text: str | None = None) -> str | None:
    explicit = ""
    if isinstance(listing, dict):
        explicit = _clean_text(
            listing.get("drivetrain")
            or listing.get("parsed_drivetrain")
            or listing.get("drive")
            or listing.get("driveType")
        )
    haystack = f"{explicit} {text if text is not None else listing_text(listing)}".lower()
    if re.search(r"\b(4wd|4x4|four\s+wheel\s+drive|awd)\b", haystack):
        return "4WD"
    if re.search(r"\b(2wd|4x2|rwd|rear\s+wheel\s+drive)\b", haystack):
        return "2WD"
    return explicit or None


def parse_engine(listing: dict[str, Any] | str, text: str | None = None) -> str | None:
    explicit = ""
    if isinstance(listing, dict):
        explicit = _clean_text(listing.get("engine") or listing.get("parsed_engine") or listing.get("engine_type") or listing.get("engineType"))
    haystack = f"{explicit} {text if text is not None else listing_text(listing)}".strip()
    for engine, patterns in ENGINE_PATTERNS:
        if _contains_pattern(haystack, patterns):
            return engine
    return explicit or None


def parse_fuel(listing: dict[str, Any] | str, text: str | None = None) -> str | None:
    explicit = ""
    if isinstance(listing, dict):
        explicit = _clean_text(listing.get("fuel") or listing.get("parsed_fuel") or listing.get("fuel_type") or listing.get("fuelType"))
    haystack = f"{explicit} {text if text is not None else listing_text(listing)}".lower()
    if _contains_pattern(haystack, DIESEL_PATTERNS):
        return "Diesel"
    if _contains_pattern(haystack, GAS_FUEL_PATTERNS):
        return "Gas"
    return explicit or None


def parse_vin(listing: dict[str, Any] | str, text: str | None = None) -> str | None:
    explicit = ""
    if isinstance(listing, dict):
        explicit = _clean_text(listing.get("vin") or listing.get("vinserial") or listing.get("vin_serial"))
    haystack = explicit or (text if text is not None else listing_text(listing))
    match = _VIN_RE.search(haystack)
    return match.group(0).upper() if match else (explicit or None)


def _parse_mileage_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        miles = int(float(value))
        return miles if miles >= 0 else None

    raw = str(value).strip().lower()
    if not raw or _contains_pattern(raw, UNKNOWN_MILEAGE_PATTERNS):
        return None

    match = _MILEAGE_VALUE_RE.search(raw.replace(",", ""))
    if not match:
        return None

    number_text = match.group(1).replace(",", "").replace(" ", "")
    suffix = (match.group(2) or "").lower()
    try:
        miles = float(number_text.rstrip("k"))
    except ValueError:
        return None
    if number_text.endswith("k") or suffix == "k":
        miles *= 1000
    miles_int = int(round(miles))
    return miles_int if miles_int >= 0 else None


def parse_mileage(listing: dict[str, Any] | str, text: str | None = None) -> tuple[int | None, str]:
    if isinstance(listing, dict):
        for key in ("mileage", "parsed_mileage", "odometer", "meterCount", "mileage_value", "miles"):
            miles = _parse_mileage_value(listing.get(key))
            if miles is not None:
                return miles, f"{miles:,}"

    haystack = text if text is not None else listing_text(listing)
    if _contains_pattern(haystack.lower(), UNKNOWN_MILEAGE_PATTERNS):
        return None, "UNKNOWN"

    context_match = _MILEAGE_CONTEXT_RE.search(haystack)
    if context_match:
        miles = _parse_mileage_value(context_match.group(1))
        if miles is not None:
            return miles, f"{miles:,}"

    for match in _MILEAGE_VALUE_RE.finditer(haystack):
        suffix = (match.group(2) or "").lower()
        if suffix not in {"k", "mi", "miles", "mile"}:
            continue
        miles = _parse_mileage_value(match.group(0))
        if miles is not None and miles > 1000:
            return miles, f"{miles:,}"

    return None, "UNKNOWN"


def _is_negated_context(text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 24):match.start()]
    suffix = text[match.end():match.end() + 16]
    return bool(
        re.search(r"\b(no|not|without|free\s+of)\s+$", prefix, re.IGNORECASE)
        or re.search(r"^\s*free\b", suffix, re.IGNORECASE)
    )


def _has_unnegated_pattern(text: str, pattern: str) -> bool:
    for match in re.finditer(pattern, text, re.IGNORECASE):
        if pattern in {r"\bno\s+titles?\b"}:
            return True
        if _is_negated_context(text, match):
            continue
        return True
    return False


def _condition_rejects(text: str) -> list[str]:
    reasons: list[str] = []
    for code, patterns in HARD_REJECT_PATTERNS:
        if any(_has_unnegated_pattern(text, pattern) for pattern in patterns):
            reasons.append(code)
    return reasons


def _score_mileage(mileage: int | None, positive: list[str], negative: list[str]) -> int:
    if mileage is None:
        negative.append("consumer_gas_missing_mileage")
        negative.append("consumer_gas_missing_required_data")
        return -18
    if mileage <= 30_000:
        positive.append("consumer_gas_exceptional_mileage")
        return 28
    if mileage <= 50_000:
        positive.append("consumer_gas_prime_mileage")
        return 24
    if mileage <= 70_000:
        positive.append("consumer_gas_strong_mileage")
        return 16
    if mileage <= 90_000:
        negative.append("consumer_gas_mileage_possible_only")
        return -6
    if mileage <= 100_000:
        negative.append("consumer_gas_mileage_too_high")
        return -18
    negative.append("consumer_gas_mileage_too_high")
    return -35


def _score_age(rule: ConsumerGasRule, model_year: int | None, current_year: int, positive: list[str], negative: list[str]) -> tuple[int, int | None]:
    if model_year is None:
        negative.append("consumer_gas_missing_required_data")
        return -10, None

    vehicle_age = current_year - model_year
    if vehicle_age < 0:
        positive.append("consumer_gas_future_model_watchlist")
        return 8, vehicle_age
    if vehicle_age <= 3:
        positive.append("consumer_gas_prime_age")
        return 22, vehicle_age
    if vehicle_age <= rule.max_normal_age:
        positive.append("consumer_gas_strong_age")
        return 15, vehicle_age
    if vehicle_age <= rule.possible_exceptional_age:
        negative.append("consumer_gas_age_possible_only")
        return -9, vehicle_age

    negative.append("consumer_gas_age_too_old")
    negative.append("consumer_gas_year_too_old")
    return -25, vehicle_age


def _score_trim(rule: ConsumerGasRule, trim: str | None, positive: list[str], negative: list[str]) -> int:
    if not trim:
        negative.append("consumer_gas_missing_required_data")
        return -4
    if trim in rule.strong_trims:
        positive.append("consumer_gas_strong_trim")
        return 18 if trim in {"King Ranch", "Platinum", "High Country", "Denali", "TRD Pro", "PRO-4X"} else 14
    if trim in rule.good_trims:
        positive.append("consumer_gas_good_trim")
        return 8
    if trim in rule.weak_trims:
        negative.append("consumer_gas_base_trim_low_ceiling")
        return -20
    return 0


def _score_cab(cab: str | None, positive: list[str], negative: list[str]) -> int:
    if not cab:
        negative.append("consumer_gas_missing_required_data")
        return -4
    if cab in {"CrewMax", "SuperCrew", "Crew Cab"}:
        positive.append("consumer_gas_strong_cab")
        return 12
    if cab == "Double Cab":
        positive.append("consumer_gas_strong_cab")
        return 9
    if cab in {"Quad Cab", "Access Cab", "Extended Cab"}:
        negative.append("consumer_gas_weak_configuration")
        return -6
    if cab == "Regular Cab":
        negative.append("consumer_gas_weak_configuration")
        return -22
    return 0


def _score_drivetrain(drivetrain: str | None, positive: list[str], negative: list[str]) -> int:
    if not drivetrain:
        negative.append("consumer_gas_missing_required_data")
        return -3
    if drivetrain == "4WD":
        positive.append("consumer_gas_4wd")
        return 12
    if drivetrain == "2WD":
        negative.append("consumer_gas_weak_configuration")
        return -12
    return 0


def _score_engine(rule: ConsumerGasRule, engine: str | None, positive: list[str], negative: list[str]) -> int:
    if not engine:
        return 0
    if any(token.lower() in engine.lower() for token in rule.preferred_engines):
        positive.append("consumer_gas_preferred_engine")
        return 10
    if any(token.lower() in engine.lower() for token in rule.acceptable_gas_engines):
        positive.append("consumer_gas_acceptable_engine")
        return 4
    if rule.model_key == "toyota_tacoma" and "2.7" in engine:
        negative.append("consumer_gas_weak_configuration")
        return -12
    if rule.model_key == "nissan_frontier" and "4.0" in engine:
        negative.append("consumer_gas_low_ceiling_model")
        return -8
    return 0


def _is_strong_cab(cab: str | None) -> bool:
    return cab in {"CrewMax", "SuperCrew", "Crew Cab", "Double Cab"}


def _classify(
    *,
    rule: ConsumerGasRule | None,
    score: int,
    model_year: int | None,
    vehicle_age: int | None,
    mileage: int | None,
    trim: str | None,
    cab: str | None,
    drivetrain: str | None,
    engine: str | None,
    fuel: str | None,
    hard_rejects: list[str],
    positive: list[str],
    negative: list[str],
    block_reasons: list[str],
) -> str:
    if hard_rejects:
        block_reasons.extend(hard_rejects)
        return "REJECT"
    if not rule:
        block_reasons.append("consumer_gas_low_ceiling_model")
        return "REJECT"
    if fuel == "Diesel":
        block_reasons.append("consumer_gas_wrong_fuel")
        return "REJECT"

    fatal_reasons: list[str] = []
    if mileage is not None and mileage > 100_000:
        if rule.group == OPPORTUNISTIC:
            fatal_reasons.append("consumer_gas_low_ceiling_model")
        fatal_reasons.append("consumer_gas_mileage_too_high")
    if vehicle_age is not None and vehicle_age > rule.possible_exceptional_age:
        if rule.group == OPPORTUNISTIC:
            fatal_reasons.append("consumer_gas_low_ceiling_model")
        fatal_reasons.append("consumer_gas_age_too_old")
    if fatal_reasons:
        block_reasons.extend(fatal_reasons)
        return "REJECT"

    config_count = sum(1 for value in (trim, cab, drivetrain, engine) if value)
    required_data_ok = model_year is not None and mileage is not None and config_count >= 2
    has_base_trim = bool(trim and trim in rule.weak_trims)
    weak_config = has_base_trim or cab == "Regular Cab" or drivetrain == "2WD"
    future_unknown = "consumer_gas_future_model_watchlist" in positive

    opportunistic_ok = True
    if rule.group == OPPORTUNISTIC:
        opportunistic_ok = (
            bool(trim and trim in rule.strong_trims)
            and _is_strong_cab(cab)
            and drivetrain == "4WD"
            and mileage is not None
            and mileage <= rule.max_alert_miles
        )
        if not opportunistic_ok:
            block_reasons.append("consumer_gas_low_ceiling_model")

    if future_unknown and not required_data_ok:
        block_reasons.append("consumer_gas_future_model_watchlist")
        block_reasons.append("consumer_gas_missing_required_data")
        return "WATCHLIST"

    if not required_data_ok:
        block_reasons.append("consumer_gas_missing_required_data")
        if mileage is None:
            block_reasons.append("consumer_gas_missing_mileage")
    if has_base_trim:
        block_reasons.append("consumer_gas_base_trim_low_ceiling")
    if weak_config:
        block_reasons.append("consumer_gas_weak_configuration")
    if mileage is not None and mileage > rule.max_alert_miles:
        block_reasons.append("consumer_gas_mileage_too_high")

    if (
        required_data_ok
        and not weak_config
        and opportunistic_ok
        and mileage is not None
        and mileage <= rule.max_alert_miles
        and score >= rule.alert_threshold
    ):
        return "ALERT"

    if score >= rule.watchlist_threshold:
        block_reasons.append("consumer_gas_watchlist_score")
        return "WATCHLIST"

    block_reasons.append("consumer_gas_score_below_alert")
    return "REJECT"


def classify_consumer_gas_liquid(listing: dict[str, Any], *, current_year: int | None = None) -> dict[str, Any]:
    current_year = current_year or datetime.now().year
    text = listing_text(listing)
    text_l = text.lower()
    model_key, rule = identify_consumer_model(listing)

    model_year = parse_year(listing, text)
    trim = parse_trim(listing, text_l)
    cab = parse_cab(listing, text_l)
    drivetrain = parse_drivetrain(listing, text_l)
    engine = parse_engine(listing, text)
    fuel = parse_fuel(listing, text)
    mileage, mileage_display = parse_mileage(listing, text)
    vin = parse_vin(listing, text)

    positive: list[str] = []
    negative: list[str] = []
    block_reasons: list[str] = []
    score = 0

    hard_rejects = _condition_rejects(text_l)
    if _contains_pattern(text_l, UNKNOWN_MILEAGE_PATTERNS):
        negative.append("consumer_gas_missing_mileage")
        negative.append("consumer_gas_missing_required_data")

    vehicle_age: int | None = None
    if rule:
        if rule.group == CORE:
            positive.append("consumer_gas_core_model")
        else:
            positive.append("consumer_gas_opportunistic_model")
        score += rule.base_score

        if rule.value_retention_bonus:
            positive.append("consumer_gas_value_retention")
            score += rule.value_retention_bonus

        delta, vehicle_age = _score_age(rule, model_year, current_year, positive, negative)
        score += delta
        score += _score_mileage(mileage, positive, negative)
        score += _score_trim(rule, trim, positive, negative)
        score += _score_cab(cab, positive, negative)
        score += _score_drivetrain(drivetrain, positive, negative)
        score += _score_engine(rule, engine, positive, negative)
    else:
        negative.append("consumer_gas_low_ceiling_model")

    if fuel == "Diesel":
        negative.append("consumer_gas_wrong_fuel")

    classification = _classify(
        rule=rule,
        score=score,
        model_year=model_year,
        vehicle_age=vehicle_age,
        mileage=mileage,
        trim=trim,
        cab=cab,
        drivetrain=drivetrain,
        engine=engine,
        fuel=fuel,
        hard_rejects=hard_rejects,
        positive=positive,
        negative=negative,
        block_reasons=block_reasons,
    )

    if classification == "ALERT":
        positive.append("consumer_gas_get_quote")
        block_reasons = []

    decision_reasons = _dedupe(positive + negative + block_reasons)

    return {
        "strategy": STRATEGY,
        "classification": classification,
        "is_consumer_gas_candidate": bool(rule),
        "should_alert": classification == "ALERT",
        "score": score,
        "model_key": model_key,
        "model_year": model_year,
        "vehicle_age": vehicle_age,
        "year": model_year,
        "make": rule.make if rule else None,
        "model": rule.model if rule else None,
        "trim": trim,
        "cab": cab,
        "drivetrain": drivetrain,
        "engine": engine,
        "fuel": fuel or "Gas",
        "mileage": mileage,
        "mileage_display": mileage_display,
        "vin": vin,
        "positive_signals": _dedupe(positive),
        "negative_signals": _dedupe(negative),
        "block_reasons": _dedupe(block_reasons),
        "decision_reasons": decision_reasons,
        "next_action": NEXT_ACTION if classification == "ALERT" else "",
    }


def consumer_gas_result_to_row_fields(result: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "target_strategy": result.get("strategy"),
        "classification": result.get("classification"),
        "decision_reasons": result.get("decision_reasons") or [],
        "positive_signals": result.get("positive_signals") or [],
        "negative_signals": result.get("negative_signals") or [],
        "block_reasons": result.get("block_reasons") or [],
        "score": result.get("score"),
        "consumer_gas_score": result.get("score"),
        "consumer_gas_model_key": result.get("model_key"),
        "next_action": result.get("next_action") or "",
        "vin": result.get("vin"),
        "year": result.get("year"),
        "model_year": result.get("model_year"),
        "vehicle_age": result.get("vehicle_age"),
        "make": result.get("make"),
        "model": result.get("model"),
        "trim": result.get("trim"),
        "cab": result.get("cab"),
        "drivetrain": result.get("drivetrain"),
        "engine": result.get("engine"),
        "fuel": result.get("fuel"),
        "mileage": result.get("mileage"),
        "mileage_display": result.get("mileage_display"),
        "parsed_make": result.get("make"),
        "parsed_model": result.get("model"),
        "parsed_year": result.get("model_year"),
        "parsed_vehicle_age": result.get("vehicle_age"),
        "parsed_mileage": result.get("mileage"),
        "parsed_trim": result.get("trim"),
        "parsed_cab": result.get("cab"),
        "parsed_drivetrain": result.get("drivetrain"),
        "parsed_engine": result.get("engine"),
        "parsed_fuel": result.get("fuel"),
    }
    return fields


def calculate_max_hammer_for_offer(
    offer: float,
    *,
    min_profit: float = MIN_CONSUMER_GAS_NET_PROFIT,
    shipping: float = DEFAULT_SHIPPING_RESERVE,
    repairs: float = DEFAULT_REPAIR_RESERVE,
    fixed_costs: float = DEFAULT_FIXED_COSTS,
    buffer: float = DEFAULT_SAFETY_BUFFER,
    premium_rate: float = DEFAULT_BUYER_PREMIUM_RATE,
) -> float:
    return (offer - min_profit - shipping - repairs - fixed_costs - buffer) / (1 + premium_rate)
