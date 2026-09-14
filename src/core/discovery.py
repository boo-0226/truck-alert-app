# file: src/core/discovery.py
from __future__ import annotations

import re
from typing import Any

from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.consumer_gas_liquid import identify_consumer_model, listing_text, listing_vehicle_guard
from src.core.utils import (
    BOX_PHRASES,
    BUCKET_BRANDS,
    BUCKET_PHRASES,
    CRANE_BRANDS,
    CRANE_PHRASES,
    CUMMINS_KWS,
    DIESEL_KWS,
    DUMP_PHRASES,
    EMERGENCY_PHRASES,
    HEAVY_DUTY_MODELS,
    UTILITY_REFUSE_TANKER_PHRASES,
)


DIESEL_COMMERCIAL = "DIESEL_COMMERCIAL"
GAS_WORK_LOCAL = "GAS_WORK_LOCAL"

_GAS_WORK_PATTERNS = (
    r"\bford\s+f[-\s]?(?:250|350)\b",
    r"\bf[-\s]?(?:250|350)\b",
    r"\b(?:chevrolet|chevy|gmc)\s+(?:silverado\s+|sierra\s+)?(?:2500|3500)(?:hd)?\b",
    r"\b(?:silverado|sierra)\s+(?:2500|3500)(?:hd)?\b",
    r"\b(?:ram|dodge\s+ram)\s+(?:2500|3500)\b",
)
_GAS_CONTEXT_PATTERNS = (
    r"\bgas\b",
    r"\bgasoline\b",
    r"\bunleaded\b",
    r"\b5\.0\b",
    r"\b5\.3\b",
    r"\b5\.7\b",
    r"\b6\.0\b",
    r"\b6\.2\b",
    r"\bhemi\b",
)
_DETAIL_FIELDS = (
    "desc",
    "description",
    "container_text",
    "structured_text",
    "mileage",
    "parsed_mileage",
    "mileage_value",
    "trim",
    "cab",
    "drivetrain",
    "engine",
    "vin",
)

_COMMERCIAL_BODY_WITHOUT_STANDALONE_LIFTGATE = (
    DUMP_PHRASES
    | BUCKET_PHRASES
    | BUCKET_BRANDS
    | CRANE_PHRASES
    | CRANE_BRANDS
    | BOX_PHRASES
    | EMERGENCY_PHRASES
    | (UTILITY_REFUSE_TANKER_PHRASES - {"liftgate", "tommy gate"})
)

_LIFTGATE_VEHICLE_CONTEXT_PATTERNS = (
    r"\bbox\s+truck\b.{0,50}\blift\s*gate\b",
    r"\bbox\s+truck\b.{0,50}\bliftgate\b",
    r"\btruck\b.{0,50}\blift\s*gate\b",
    r"\btruck\b.{0,50}\bliftgate\b",
)


def _text_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text_value(item) for item in value.values())
    return str(value)


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _matches_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _has_detail_fields(listing_or_text: dict[str, Any] | str) -> bool:
    if isinstance(listing_or_text, str):
        return False
    return any(_text_value(listing_or_text.get(field)).strip() for field in _DETAIL_FIELDS)


def _diesel_discovery(text: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(text, HEAVY_DUTY_MODELS):
        reasons.append("discovery_hd_model")
    if _contains_any(
        text,
        _COMMERCIAL_BODY_WITHOUT_STANDALONE_LIFTGATE,
    ):
        reasons.append("discovery_commercial_body")
    elif _matches_any_pattern(text, _LIFTGATE_VEHICLE_CONTEXT_PATTERNS):
        reasons.append("discovery_commercial_body")
    if _contains_any(text, DIESEL_KWS):
        reasons.append("discovery_diesel_keyword")
    if _contains_any(text, CUMMINS_KWS):
        reasons.append("discovery_cummins_keyword")
    return reasons


def _gas_work_discovery(text: str) -> list[str]:
    if not any(re.search(pattern, text, re.IGNORECASE) for pattern in _GAS_WORK_PATTERNS):
        return []
    reasons = ["discovery_gas_work_hd_model"]
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in _GAS_CONTEXT_PATTERNS):
        reasons.append("discovery_gas_work_gas_context")
    return reasons


def discover_vehicle_candidates(listing_or_text: dict[str, Any] | str) -> dict[str, Any]:
    text = listing_text(listing_or_text).lower()
    reasons: list[str] = []
    strategy_candidates: list[str] = []
    discovered_model_key = None
    discovered_make_model = None
    guard = listing_vehicle_guard(listing_or_text)
    if guard.get("blocked"):
        reason = guard.get("reason") or "non_vehicle_listing"
        return {
            "discovered": False,
            "discovery_reasons": [str(reason)],
            "strategy_candidates": [],
            "discovered_make_model": None,
            "discovered_model_key": None,
            "discovery_confidence": 0,
            "needs_detail": False,
            "non_vehicle_listing": guard.get("non_vehicle_listing", False),
            "parts_or_equipment_only": guard.get("parts_or_equipment_only", False),
            "body_not_pickup": guard.get("body_not_pickup", False),
            "parser_warning": guard.get("parser_warning", ""),
            "parser_correction_reason": guard.get("parser_correction_reason", ""),
        }

    diesel_reasons = _diesel_discovery(text)
    if diesel_reasons:
        strategy_candidates.append(DIESEL_COMMERCIAL)
        reasons.extend(diesel_reasons)

    model_key, rule = identify_consumer_model(listing_or_text)
    if rule:
        discovered_model_key = model_key
        discovered_make_model = f"{rule.make} {rule.model}"
        strategy_candidates.append(CONSUMER_GAS_LIQUID)
        reasons.append("discovery_make_model_alias")
        if rule.group == "core":
            reasons.append("discovery_consumer_core_model")
        else:
            reasons.append("discovery_consumer_opportunistic_model")

    gas_work_reasons = _gas_work_discovery(text)
    if gas_work_reasons:
        strategy_candidates.append(GAS_WORK_LOCAL)
        reasons.extend(gas_work_reasons)

    strategy_candidates = list(dict.fromkeys(strategy_candidates))
    reasons = list(dict.fromkeys(reasons))
    discovered = bool(strategy_candidates)
    confidence = min(100, 35 + (20 * len(strategy_candidates)) + (10 * len(reasons))) if discovered else 0

    return {
        "discovered": discovered,
        "discovery_reasons": reasons,
        "strategy_candidates": strategy_candidates,
        "discovered_make_model": discovered_make_model,
        "discovered_model_key": discovered_model_key,
        "discovery_confidence": confidence,
        "needs_detail": discovered and not _has_detail_fields(listing_or_text),
    }
