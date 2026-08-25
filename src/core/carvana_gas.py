# file: src/core/carvana_gas.py
from __future__ import annotations

import re
from typing import Any

from src.core.config import (
    CARVANA_DEFAULT_BUYER_PREMIUM_RATE,
    CARVANA_DEFAULT_FIXED_COSTS,
    CARVANA_DEFAULT_REPAIR_RESERVE,
    CARVANA_DEFAULT_SAFETY_BUFFER,
    CARVANA_DEFAULT_SHIPPING,
    CARVANA_GAS_MIN_ALERT_SCORE,
    CARVANA_GAS_MIN_WATCHLIST_SCORE,
    MIN_CARVANA_NET_PROFIT,
)


STRATEGY = "CARVANA_GAS"
NEXT_ACTION = "GET CARVANA QUOTE"

_YEAR_RE = re.compile(r"\b(20[0-3]\d|19[8-9]\d)\b")
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)
_MILEAGE_VALUE_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,6}|\d{1,3}(?:\.\d+)?)\s*(k|mi|miles|mile)?\b", re.IGNORECASE)
_MILEAGE_CONTEXT_RE = re.compile(
    r"\b(?:odometer|mileage|miles|mi)\b\s*(?:reading|reads|shows|is|was|actual|listed as|[:#-])?\s*"
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
    r"\bdt466\b",
    r"\bmaxxforce\b",
    r"\bt444e\b",
    r"\b6\.7\s*(?:l|liter)?\s*(?:diesel|power\s*stroke|powerstroke|cummins)?\b",
    r"\b6\.4\s*(?:l|liter)?\s*diesel\b",
    r"\b6\.0\s*(?:l|liter)?\s*diesel\b",
)

HARD_REJECT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "carvana_rust",
        (
            r"\bvisible\s+rust\b",
            r"\bframe\s+rust\b",
            r"\bframe\s+rot\b",
            r"\brust\b",
            r"\bcorrosion\s+damage\b",
        ),
    ),
    (
        "carvana_title_problem",
        (
            r"\bsalvage\s+title\b",
            r"\brebuilt\s+title\b",
            r"\bparts\s+only\b",
            r"\bno\s+title\b",
            r"\bmissing\s+title\b",
            r"\btitle\s+absent\b",
        ),
    ),
    (
        "carvana_major_mechanical",
        (
            r"\bstructural\s+damage\b",
            r"\bflood\b",
            r"\bfire\s+damage\b",
            r"\bmajor\s+collision\s+damage\b",
            r"\bdeployed\s+airbags?\b",
            r"\bseized\s+engine\b",
            r"\bengine\s+knock\b",
            r"\bblown\s+engine\b",
            r"\bneeds\s+(?:an\s+)?engine\b",
            r"\bengine\s+needs\s+repairs?\b",
            r"\bbad\s+transmission\b",
            r"\bneeds\s+(?:a\s+)?transmission\b",
            r"\btransmission\s+needs\s+repairs?\b",
            r"\btransmission\s+failure\b",
            r"\boverheating\b",
            r"\bmajor\s+drivetrain\s+failure\b",
            r"\bdoes\s+not\s+run\b",
            r"\bdoes\s+not\s+run\s+and\s+drive\b",
            r"\bnon[-\s]?running\b",
            r"\bnot\s+running\b",
            r"\binoperable\b",
        ),
    ),
)

UNKNOWN_MILEAGE_PATTERNS = (
    r"\bunknown\s+mileage\b",
    r"\bmileage\s+unknown\b",
    r"\bodometer\s+unknown\b",
    r"\bnot\s+actual\s+miles\b",
    r"\bnot\s+actual\s+mileage\b",
    r"\btmu\b",
    r"\btrue\s+mileage\s+unknown\b",
    r"\bexempt\s+mileage\b",
)

MODEL_ALIASES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("tundra", "Toyota", "Tundra", (r"\btundra\b",)),
    ("tacoma", "Toyota", "Tacoma", (r"\btacoma\b",)),
    ("f150", "Ford", "F-150", (r"\bf[-\s]?150\b",)),
    ("silverado_1500", "Chevrolet", "Silverado 1500", (r"\bsilverado\s*1500\b", r"\bsilverado\b")),
    ("sierra_1500", "GMC", "Sierra 1500", (r"\bsierra\s*1500\b", r"\bsierra\b")),
    ("ram_1500", "Ram", "1500", (r"\bram\s*1500\b",)),
    ("colorado", "Chevrolet", "Colorado", (r"\bcolorado\b",)),
    ("canyon", "GMC", "Canyon", (r"\bcanyon\b",)),
    ("ranger", "Ford", "Ranger", (r"\branger\b",)),
    ("frontier", "Nissan", "Frontier", (r"\bfrontier\b",)),
)

HD_MODEL_PATTERNS = (
    r"\b2500(?:hd)?\b",
    r"\b3500(?:hd)?\b",
    r"\bf[-\s]?250\b",
    r"\bf[-\s]?350\b",
    r"\bram\s*2500\b",
    r"\bram\s*3500\b",
)

TRIM_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TRD Pro", (r"\btrd\s+pro\b",)),
    ("TRD Off-Road", (r"\btrd\s+off[-\s]?road\b",)),
    ("TRD Sport", (r"\btrd\s+sport\b",)),
    ("1794 Edition", (r"\b1794\b",)),
    ("High Country", (r"\bhigh\s+country\b",)),
    ("King Ranch", (r"\bking\s+ranch\b",)),
    ("Trail Boss", (r"\btrail\s+boss\b",)),
    ("PRO-4X", (r"\bpro[-\s]?4x\b",)),
    ("Big Horn", (r"\bbig\s+horn\b",)),
    ("Lone Star", (r"\blone\s+star\b",)),
    ("Work Truck", (r"\bwork\s+truck\b",)),
    ("Tradesman", (r"\btradesman\b",)),
    ("Platinum", (r"\bplatinum\b",)),
    ("Limited", (r"\blimited\b",)),
    ("Laramie", (r"\blaramie\b",)),
    ("Denali", (r"\bdenali\b",)),
    ("Lariat", (r"\blariat\b",)),
    ("Rebel", (r"\brebel\b",)),
    ("Classic", (r"\bclassic\b",)),
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
    ("LT", (r"\blt\b",)),
    ("WT", (r"\bwt\b",)),
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
    ("Extended Cab", (r"\bextended\s+cab\b", r"\bext\s+cab\b")),
    ("Regular Cab", (r"\bregular\s+cab\b", r"\breg\s+cab\b", r"\bsingle\s+cab\b")),
)

ENGINE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("6.2L V8", (r"\b6\.2\s*(?:l|liter)?\b",)),
    ("5.7L HEMI", (r"\b5\.7\s*(?:l|liter)?\s*(?:hemi)?\b", r"\bhemi\b")),
    ("5.7L V8", (r"\b5\.7\s*(?:l|liter)?\b",)),
    ("5.3L V8", (r"\b5\.3\s*(?:l|liter)?\b",)),
    ("5.0L V8", (r"\b5\.0\s*(?:l|liter)?\b",)),
    ("4.0L V6", (r"\b4\.0\s*(?:l|liter)?\b",)),
    ("3.8L V6", (r"\b3\.8\s*(?:l|liter)?\b",)),
    ("3.6L V6", (r"\b3\.6\s*(?:l|liter)?\b",)),
    ("3.5L V6", (r"\b3\.5\s*(?:l|liter)?\b",)),
    ("2.7L I4", (r"\b2\.7\s*(?:l|liter)?\b",)),
)

MODEL_TIERS = {
    "tundra": 1,
    "tacoma": 1,
    "f150": 2,
    "silverado_1500": 2,
    "sierra_1500": 2,
    "ram_1500": 2,
    "colorado": 3,
    "canyon": 3,
    "ranger": 3,
    "frontier": 3,
}

PREFERRED_ENGINES = {
    "tundra": ("5.7L",),
    "tacoma": ("3.5L",),
    "f150": ("5.0L",),
    "silverado_1500": ("5.3L", "6.2L"),
    "sierra_1500": ("5.3L", "6.2L"),
    "ram_1500": ("5.7L", "HEMI"),
    "colorado": ("3.6L",),
    "canyon": ("3.6L",),
    "frontier": ("3.8L",),
}

STRONG_TRIMS = {
    "tundra": {"Limited", "Platinum", "1794 Edition", "TRD Pro"},
    "tacoma": {"TRD Off-Road", "TRD Sport", "TRD Pro"},
    "f150": {"Lariat", "King Ranch", "Platinum"},
    "silverado_1500": {"LTZ", "High Country", "RST", "Trail Boss"},
    "sierra_1500": {"SLT", "AT4", "Denali"},
    "ram_1500": {"Laramie", "Rebel", "Limited"},
    "colorado": {"ZR2", "Z71"},
    "canyon": {"Denali", "AT4"},
    "ranger": {"Lariat"},
    "frontier": {"PRO-4X"},
}

MID_TRIMS = {
    "tundra": {"SR5"},
    "tacoma": {"SR5"},
    "f150": {"XLT"},
    "silverado_1500": {"LT"},
    "sierra_1500": {"SLE"},
    "ram_1500": {"Big Horn", "Lone Star"},
    "ranger": {"XLT"},
    "frontier": {"SV"},
}

BASE_TRIMS = {
    "tacoma": {"SR"},
    "f150": {"XL"},
    "silverado_1500": {"WT", "Work Truck"},
    "sierra_1500": set(),
    "ram_1500": {"Tradesman"},
    "colorado": {"WT"},
    "frontier": {"S"},
}


def _text_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text_value(v) for v in value)
    if isinstance(value, dict):
        return " ".join(_text_value(v) for v in value.values())
    return str(value)


def _listing_text(listing: dict[str, Any]) -> str:
    fields = (
        "title",
        "desc",
        "description",
        "category",
        "cat",
        "make",
        "model",
        "trim",
        "cab",
        "drivetrain",
        "engine",
        "fuel",
        "condition",
        "body_style",
        "bodyStyle",
        "vin",
        "mileage_display",
    )
    return " ".join(_text_value(listing.get(field)) for field in fields).strip()


def _clean_text(text: Any) -> str:
    return re.sub(r"\s+", " ", _text_value(text)).strip()


def _contains_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _parse_year(listing: dict[str, Any], text: str) -> int | None:
    for key in ("year", "modelYear", "assetYear"):
        value = listing.get(key)
        if value in (None, ""):
            continue
        try:
            year = int(float(str(value).strip()))
        except (TypeError, ValueError):
            continue
        if 1980 <= year <= 2035:
            return year

    match = _YEAR_RE.search(text)
    return int(match.group(1)) if match else None


def _parse_make_model(listing: dict[str, Any], text: str) -> tuple[str | None, str | None, str | None]:
    make_hint = _clean_text(listing.get("make") or listing.get("makebrand")).lower()
    model_hint = _clean_text(listing.get("model")).lower()
    hint_text = f"{make_hint} {model_hint} {text}".lower()

    for key, make, model, patterns in MODEL_ALIASES:
        if key in {"silverado_1500", "sierra_1500", "ram_1500"} and _contains_pattern(hint_text, HD_MODEL_PATTERNS):
            continue
        if any(re.search(pattern, hint_text, re.IGNORECASE) for pattern in patterns):
            return key, make, model

    return None, None, None


def _parse_trim(listing: dict[str, Any], text: str) -> str | None:
    explicit = _clean_text(listing.get("trim"))
    if explicit:
        for trim, patterns in TRIM_PATTERNS:
            if any(re.search(pattern, explicit, re.IGNORECASE) for pattern in patterns):
                return trim
        return explicit

    for trim, patterns in TRIM_PATTERNS:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
            return trim
    return None


def _parse_cab(listing: dict[str, Any], text: str) -> str | None:
    explicit = _clean_text(listing.get("cab") or listing.get("body_style") or listing.get("bodyStyle"))
    combined = f"{explicit} {text}".strip()
    for cab, patterns in CAB_PATTERNS:
        if any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns):
            return cab
    return explicit or None


def _parse_drivetrain(listing: dict[str, Any], text: str) -> str | None:
    explicit = _clean_text(listing.get("drivetrain") or listing.get("drive") or listing.get("driveType"))
    combined = f"{explicit} {text}".lower()
    if re.search(r"\b(4wd|4x4|four\s+wheel\s+drive|awd)\b", combined):
        return "4WD"
    if re.search(r"\b(2wd|4x2|rwd|rear\s+wheel\s+drive)\b", combined):
        return "2WD"
    return explicit or None


def _parse_engine(listing: dict[str, Any], text: str) -> str | None:
    explicit = _clean_text(listing.get("engine") or listing.get("engine_type") or listing.get("engineType"))
    combined = f"{explicit} {text}".strip()
    for engine, patterns in ENGINE_PATTERNS:
        if any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns):
            return engine
    return explicit or None


def _parse_fuel(listing: dict[str, Any], text: str) -> str | None:
    explicit = _clean_text(listing.get("fuel") or listing.get("fuel_type") or listing.get("fuelType"))
    combined = f"{explicit} {text}".lower()
    if _contains_pattern(combined, DIESEL_PATTERNS):
        return "Diesel"
    if re.search(r"\b(gas|gasoline|petrol|unleaded)\b", combined):
        return "Gas"
    return explicit or None


def _parse_vin(listing: dict[str, Any], text: str) -> str | None:
    explicit = _clean_text(listing.get("vin") or listing.get("vinserial") or listing.get("vin_serial"))
    if explicit:
        match = _VIN_RE.search(explicit)
        return match.group(0).upper() if match else explicit
    match = _VIN_RE.search(text)
    return match.group(0).upper() if match else None


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


def _parse_mileage(listing: dict[str, Any], text: str) -> tuple[int | None, str]:
    for key in ("mileage", "odometer", "meterCount", "miles"):
        miles = _parse_mileage_value(listing.get(key))
        if miles is not None:
            return miles, f"{miles:,}"

    if _contains_pattern(text.lower(), UNKNOWN_MILEAGE_PATTERNS):
        return None, "UNKNOWN"

    context_match = _MILEAGE_CONTEXT_RE.search(text)
    if context_match:
        miles = _parse_mileage_value(context_match.group(1))
        if miles is not None:
            return miles, f"{miles:,}"

    for match in _MILEAGE_VALUE_RE.finditer(text):
        value_text = match.group(0)
        suffix = (match.group(2) or "").lower()
        if suffix not in {"k", "mi", "miles", "mile"}:
            continue
        miles = _parse_mileage_value(value_text)
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
        if pattern in {r"\bno\s+title\b"}:
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


def _score_year(model_key: str, year: int | None, add_positive, add_negative, block_reasons: list[str]) -> None:
    if year is None:
        add_negative(-8, "carvana_missing_required_data")
        block_reasons.append("carvana_missing_required_data")
        return

    if model_key in {"tundra"}:
        if 2017 <= year <= 2021:
            add_positive(20, "carvana_strong_year")
        elif year >= 2022:
            add_positive(10, "carvana_newer_but_model_cycle")
        else:
            add_negative(-16, "carvana_year_too_old")
            block_reasons.append("carvana_year_too_old")
    elif model_key == "tacoma":
        if 2018 <= year <= 2022:
            add_positive(20, "carvana_strong_year")
        elif year >= 2023:
            add_positive(14, "carvana_newer_model_year")
        else:
            add_negative(-16, "carvana_year_too_old")
            block_reasons.append("carvana_year_too_old")
    elif model_key in {"f150", "silverado_1500", "sierra_1500", "ram_1500"}:
        if 2019 <= year <= 2022:
            add_positive(20, "carvana_strong_year")
        elif year >= 2023:
            add_positive(14, "carvana_newer_model_year")
        else:
            add_negative(-14, "carvana_year_too_old")
            block_reasons.append("carvana_year_too_old")
    elif model_key in {"colorado", "canyon"}:
        if year >= 2021:
            add_positive(16, "carvana_strong_year")
        elif 2019 <= year <= 2020:
            add_positive(8, "carvana_selective_year")
        else:
            add_negative(-14, "carvana_year_too_old")
            block_reasons.append("carvana_year_too_old")
    elif model_key == "ranger":
        if year >= 2020:
            add_positive(14, "carvana_strong_year")
        elif year == 2019:
            add_positive(6, "carvana_selective_year")
        else:
            add_negative(-14, "carvana_year_too_old")
            block_reasons.append("carvana_year_too_old")
    elif model_key == "frontier":
        if year >= 2022:
            add_positive(18, "carvana_strong_year")
        else:
            add_negative(-18, "carvana_year_too_old")
            block_reasons.append("carvana_year_too_old")
            block_reasons.append("carvana_low_ceiling_model")


def _score_mileage(mileage: int | None, add_positive, add_negative, block_reasons: list[str]) -> None:
    if mileage is None:
        add_negative(-18, "carvana_missing_required_data")
        block_reasons.append("carvana_missing_required_data")
        return

    if mileage <= 30_000:
        add_positive(28, "carvana_huge_low_mileage")
    elif mileage <= 50_000:
        add_positive(24, "carvana_very_low_mileage")
    elif mileage <= 75_000:
        add_positive(14, "carvana_good_mileage")
    elif mileage <= 100_000:
        add_negative(-8, "carvana_mileage_penalty")
        block_reasons.append("carvana_mileage_too_high")
    elif mileage <= 120_000:
        add_negative(-24, "carvana_mileage_too_high")
        block_reasons.append("carvana_mileage_too_high")
    else:
        add_negative(-40, "carvana_mileage_too_high")
        block_reasons.append("carvana_mileage_too_high")


def _score_trim(model_key: str, trim: str | None, add_positive, add_negative, block_reasons: list[str]) -> None:
    if not trim:
        add_negative(-4, "carvana_missing_required_data")
        return

    strong = STRONG_TRIMS.get(model_key, set())
    mid = MID_TRIMS.get(model_key, set())
    base = BASE_TRIMS.get(model_key, set())

    if trim in strong:
        bonus = 18 if trim in {"King Ranch", "Platinum", "High Country", "Denali", "TRD Pro", "PRO-4X"} else 14
        add_positive(bonus, "carvana_strong_trim")
    elif trim in mid:
        add_positive(8, "carvana_good_trim")
    elif trim in base:
        add_negative(-20, "carvana_base_trim_low_ceiling")
        block_reasons.append("carvana_base_trim_low_ceiling")
    elif trim == "Classic" and model_key == "ram_1500":
        add_negative(-18, "carvana_configuration_low_ceiling")
        block_reasons.append("carvana_configuration_low_ceiling")


def _score_cab(cab: str | None, add_positive, add_negative, block_reasons: list[str]) -> None:
    if not cab:
        add_negative(-4, "carvana_missing_required_data")
        return

    if cab in {"CrewMax", "SuperCrew", "Crew Cab"}:
        add_positive(12, "carvana_strong_cab")
    elif cab == "Double Cab":
        add_positive(9, "carvana_strong_cab")
    elif cab in {"Quad Cab", "Access Cab", "Extended Cab"}:
        add_negative(-6, "carvana_configuration_low_ceiling")
        block_reasons.append("carvana_configuration_low_ceiling")
    elif cab == "Regular Cab":
        add_negative(-22, "carvana_configuration_low_ceiling")
        block_reasons.append("carvana_configuration_low_ceiling")


def _score_drivetrain(drivetrain: str | None, add_positive, add_negative, block_reasons: list[str]) -> None:
    if not drivetrain:
        add_negative(-3, "carvana_missing_required_data")
        return

    if drivetrain == "4WD":
        add_positive(12, "carvana_4wd_bonus")
    elif drivetrain == "2WD":
        add_negative(-12, "carvana_configuration_low_ceiling")
        block_reasons.append("carvana_configuration_low_ceiling")


def _score_engine(model_key: str, engine: str | None, add_positive, add_negative, block_reasons: list[str]) -> None:
    if not engine:
        return

    preferred = PREFERRED_ENGINES.get(model_key, ())
    if any(token.lower() in engine.lower() for token in preferred):
        add_positive(10, "carvana_preferred_engine")
    elif model_key == "tacoma" and "2.7" in engine:
        add_negative(-14, "carvana_configuration_low_ceiling")
        block_reasons.append("carvana_configuration_low_ceiling")
    elif model_key == "frontier" and "4.0" in engine:
        add_negative(-8, "carvana_low_ceiling_model")
        block_reasons.append("carvana_low_ceiling_model")


def _is_strong_cab(cab: str | None) -> bool:
    return cab in {"CrewMax", "SuperCrew", "Crew Cab", "Double Cab"}


def _has_strong_trim(model_key: str, trim: str | None) -> bool:
    return bool(trim and trim in STRONG_TRIMS.get(model_key, set()))


def _has_base_trim(model_key: str, trim: str | None) -> bool:
    return bool(trim and trim in BASE_TRIMS.get(model_key, set()))


def _classification(
    *,
    score: int,
    model_key: str | None,
    year: int | None,
    mileage: int | None,
    trim: str | None,
    cab: str | None,
    drivetrain: str | None,
    engine: str | None,
    hard_rejects: list[str],
    block_reasons: list[str],
) -> str:
    if hard_rejects:
        return "REJECT"
    if not model_key:
        return "REJECT"
    if mileage is not None and mileage > 120_000:
        return "REJECT"

    config_count = sum(1 for value in (trim, cab, drivetrain, engine) if value)
    required_data_ok = year is not None and mileage is not None and config_count >= 2
    base_trim = _has_base_trim(model_key, trim)
    regular_cab = cab == "Regular Cab"

    tier = MODEL_TIERS.get(model_key)
    tier3_alert_ok = True
    if tier == 3:
        tier3_alert_ok = (
            _has_strong_trim(model_key, trim)
            and drivetrain == "4WD"
            and _is_strong_cab(cab)
            and mileage is not None
            and mileage <= 50_000
        )
        if not tier3_alert_ok:
            block_reasons.append("carvana_low_ceiling_model")

    if mileage is not None and mileage > 100_000:
        block_reasons.append("carvana_mileage_too_high")
        return "REJECT" if score < CARVANA_GAS_MIN_WATCHLIST_SCORE + 10 else "WATCHLIST"

    if (
        required_data_ok
        and not base_trim
        and not regular_cab
        and tier3_alert_ok
        and score >= CARVANA_GAS_MIN_ALERT_SCORE
    ):
        return "ALERT"

    if not required_data_ok:
        block_reasons.append("carvana_missing_required_data")
    if base_trim:
        block_reasons.append("carvana_base_trim_low_ceiling")
    if regular_cab:
        block_reasons.append("carvana_configuration_low_ceiling")

    if score >= CARVANA_GAS_MIN_WATCHLIST_SCORE:
        block_reasons.append("carvana_watchlist_score")
        return "WATCHLIST"

    block_reasons.append("carvana_score_below_alert")
    return "REJECT"


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def classify_carvana_gas(listing: dict[str, Any]) -> dict[str, Any]:
    text = _listing_text(listing)
    text_l = text.lower()

    year = _parse_year(listing, text)
    model_key, make, model = _parse_make_model(listing, text_l)
    trim = _parse_trim(listing, text_l)
    cab = _parse_cab(listing, text_l)
    drivetrain = _parse_drivetrain(listing, text_l)
    engine = _parse_engine(listing, text)
    fuel = _parse_fuel(listing, text)
    mileage, mileage_display = _parse_mileage(listing, text)
    vin = _parse_vin(listing, text)

    positive_signals: list[str] = []
    negative_signals: list[str] = []
    block_reasons: list[str] = []
    score = 0

    def add_positive(delta: int, code: str) -> None:
        nonlocal score
        score += delta
        positive_signals.append(code)

    def add_negative(delta: int, code: str) -> None:
        nonlocal score
        score += delta
        negative_signals.append(code)

    hard_rejects = _condition_rejects(text_l)

    if fuel == "Diesel":
        hard_rejects.append("carvana_wrong_fuel")

    if _contains_pattern(text_l, UNKNOWN_MILEAGE_PATTERNS):
        block_reasons.append("carvana_missing_required_data")
        negative_signals.append("carvana_missing_required_data")

    if not model_key:
        block_reasons.append("carvana_low_ceiling_model")
    else:
        tier = MODEL_TIERS.get(model_key)
        if tier == 1:
            add_positive(32, "carvana_good_model")
        elif tier == 2:
            add_positive(24, "carvana_good_model")
        elif tier == 3:
            add_positive(10, "carvana_good_model")

        if model_key == "tundra":
            add_positive(8, "carvana_value_retention_bonus")
        elif model_key == "tacoma":
            add_positive(6, "carvana_value_retention_bonus")
        elif model_key == "frontier" and year is not None and year < 2022:
            add_negative(-8, "carvana_low_ceiling_model")
            block_reasons.append("carvana_low_ceiling_model")

        _score_year(model_key, year, add_positive, add_negative, block_reasons)
        _score_mileage(mileage, add_positive, add_negative, block_reasons)
        _score_trim(model_key, trim, add_positive, add_negative, block_reasons)
        _score_cab(cab, add_positive, add_negative, block_reasons)
        _score_drivetrain(drivetrain, add_positive, add_negative, block_reasons)
        _score_engine(model_key, engine, add_positive, add_negative, block_reasons)

    block_reasons.extend(hard_rejects)
    classification = _classification(
        score=score,
        model_key=model_key,
        year=year,
        mileage=mileage,
        trim=trim,
        cab=cab,
        drivetrain=drivetrain,
        engine=engine,
        hard_rejects=hard_rejects,
        block_reasons=block_reasons,
    )

    if classification == "ALERT":
        positive_signals.append("carvana_get_quote")
        block_reasons = []

    block_reasons = _dedupe(block_reasons)
    positive_signals = _dedupe(positive_signals)
    negative_signals = _dedupe(negative_signals)

    return {
        "strategy": STRATEGY,
        "classification": classification,
        "is_carvana_candidate": bool(model_key),
        "should_alert": classification == "ALERT",
        "score": score,
        "model_key": model_key,
        "year": year,
        "make": make,
        "model": model,
        "trim": trim,
        "cab": cab,
        "drivetrain": drivetrain,
        "engine": engine,
        "fuel": fuel or "Gas",
        "mileage": mileage,
        "mileage_display": mileage_display,
        "vin": vin,
        "positive_signals": positive_signals,
        "negative_signals": negative_signals,
        "block_reasons": block_reasons,
        "next_action": NEXT_ACTION if classification == "ALERT" else "",
    }


def carvana_result_to_row_fields(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_strategy": result.get("strategy"),
        "classification": result.get("classification"),
        "carvana_score": result.get("score"),
        "carvana_model_key": result.get("model_key"),
        "carvana_positive_signals": result.get("positive_signals") or [],
        "carvana_negative_signals": result.get("negative_signals") or [],
        "carvana_block_reasons": result.get("block_reasons") or [],
        "carvana_next_action": result.get("next_action") or "",
        "vin": result.get("vin"),
        "year": result.get("year"),
        "make": result.get("make"),
        "model": result.get("model"),
        "trim": result.get("trim"),
        "cab": result.get("cab"),
        "drivetrain": result.get("drivetrain"),
        "engine": result.get("engine"),
        "fuel": result.get("fuel"),
        "mileage": result.get("mileage"),
        "mileage_display": result.get("mileage_display"),
    }


def calculate_max_hammer_for_carvana_offer(
    offer: float,
    *,
    min_profit: float = MIN_CARVANA_NET_PROFIT,
    shipping: float = CARVANA_DEFAULT_SHIPPING,
    repairs: float = CARVANA_DEFAULT_REPAIR_RESERVE,
    fixed_costs: float = CARVANA_DEFAULT_FIXED_COSTS,
    buffer: float = CARVANA_DEFAULT_SAFETY_BUFFER,
    premium_rate: float = CARVANA_DEFAULT_BUYER_PREMIUM_RATE,
) -> float:
    return (offer - min_profit - shipping - repairs - fixed_costs - buffer) / (1 + premium_rate)
