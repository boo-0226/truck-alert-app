# file: src/core/strategies.py
from __future__ import annotations

from typing import Any

from src.core.consumer_gas_liquid import (
    NEXT_ACTION,
    STRATEGY as CONSUMER_GAS_LIQUID,
    classify_consumer_gas_liquid,
    consumer_gas_result_to_row_fields,
    listing_vehicle_guard,
)
from src.core.discovery import DIESEL_COMMERCIAL, GAS_WORK_LOCAL, discover_vehicle_candidates
from src.core.utils import annotate_tags, is_engine_67, is_target_vehicle


def _text_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text_value(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_text_value(item) for item in value.values())
    return str(value)


def _listing_text(listing: dict[str, Any]) -> str:
    return " ".join(
        _text_value(listing.get(field))
        for field in ("title", "desc", "description", "category", "container_text", "structured_text")
    ).strip()


def classify_diesel_commercial_existing(listing: dict[str, Any]) -> dict[str, Any]:
    guard = listing_vehicle_guard(listing)
    if guard.get("blocked"):
        reason = guard.get("reason") or "non_vehicle_listing"
        return {
            "strategy": DIESEL_COMMERCIAL,
            "classification": "REJECT",
            "target": False,
            "blocked": True,
            "engine_67": False,
            "tags": [],
            "decision_reasons": [str(reason)],
            **guard,
        }

    text = _listing_text(listing)
    target = is_target_vehicle(text)
    return {
        "strategy": DIESEL_COMMERCIAL,
        "classification": "ALERT" if target else "REJECT",
        "target": bool(target),
        "blocked": not bool(target),
        "engine_67": is_engine_67(text),
        "tags": annotate_tags(text),
        "decision_reasons": ["diesel_commercial_existing_match"] if target else ["diesel_commercial_existing_no_match"],
    }


def classify_gas_work_local(
    listing: dict[str, Any],
    *,
    existing_match: bool = False,
    existing_label: str | None = None,
) -> dict[str, Any]:
    guard = listing_vehicle_guard(listing)
    if guard.get("blocked"):
        reason = guard.get("reason") or "non_vehicle_listing"
        return {
            "strategy": GAS_WORK_LOCAL,
            "classification": "REJECT",
            "target": False,
            "blocked": True,
            "should_alert": False,
            "matched_label": existing_label,
            "decision_reasons": [str(reason)],
            **guard,
        }

    discovery = discover_vehicle_candidates(listing)
    is_candidate = GAS_WORK_LOCAL in discovery.get("strategy_candidates", [])
    classification = "ALERT" if existing_match else ("WATCHLIST" if is_candidate else "REJECT")
    return {
        "strategy": GAS_WORK_LOCAL,
        "classification": classification,
        "target": bool(existing_match),
        "blocked": False if existing_match or is_candidate else True,
        "should_alert": bool(existing_match),
        "matched_label": existing_label,
        "decision_reasons": ["gas_work_local_existing_match"] if existing_match else ["gas_work_local_not_configured"],
    }


def classify_listing_strategies(
    listing: dict[str, Any],
    *,
    current_year: int | None = None,
    diesel_result: dict[str, Any] | None = None,
    gas_work_existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    discovery = discover_vehicle_candidates(listing)
    guard = listing_vehicle_guard(listing)
    if guard.get("blocked"):
        reason = guard.get("reason") or "non_vehicle_listing"
        consumer = classify_consumer_gas_liquid(listing, current_year=current_year)
        return {
            "discovery": discovery,
            "strategies_considered": [],
            "diesel": {
                "strategy": DIESEL_COMMERCIAL,
                "classification": "REJECT",
                "target": False,
                "blocked": True,
                "decision_reasons": [str(reason)],
            },
            "gas_work": {
                "strategy": GAS_WORK_LOCAL,
                "classification": "REJECT",
                "target": False,
                "blocked": True,
                "decision_reasons": [str(reason)],
            },
            "consumer_gas": consumer,
            "strategy": None,
            "target_strategy": None,
            "classification": "REJECT",
            "target": False,
            "blocked": True,
            "decision_reasons": [str(reason)],
            "next_action": "",
            **guard,
        }

    diesel = diesel_result or classify_diesel_commercial_existing(listing)
    gas_work_existing = gas_work_existing or {}
    gas_work = classify_gas_work_local(
        listing,
        existing_match=bool(gas_work_existing.get("target") or gas_work_existing.get("should_alert")),
        existing_label=gas_work_existing.get("label"),
    )
    consumer = classify_consumer_gas_liquid(listing, current_year=current_year)

    base = {
        "discovery": discovery,
        "strategies_considered": discovery.get("strategy_candidates", []),
        "diesel": diesel,
        "gas_work": gas_work,
        "consumer_gas": consumer,
    }

    if diesel.get("target") and not diesel.get("blocked"):
        return {
            **base,
            "strategy": DIESEL_COMMERCIAL,
            "target_strategy": DIESEL_COMMERCIAL,
            "classification": "ALERT",
            "target": True,
            "blocked": False,
            "decision_reasons": diesel.get("decision_reasons", []),
            "next_action": "",
        }

    if gas_work.get("target") and not gas_work.get("blocked"):
        return {
            **base,
            "strategy": GAS_WORK_LOCAL,
            "target_strategy": GAS_WORK_LOCAL,
            "classification": gas_work.get("classification", "ALERT"),
            "target": True,
            "blocked": False,
            "decision_reasons": gas_work.get("decision_reasons", []),
            "next_action": "",
        }

    if consumer.get("is_consumer_gas_candidate"):
        classification = consumer.get("classification")
        return {
            **base,
            "strategy": CONSUMER_GAS_LIQUID,
            "target_strategy": CONSUMER_GAS_LIQUID,
            "classification": classification,
            "target": classification == "ALERT",
            "blocked": classification == "REJECT",
            "decision_reasons": consumer.get("decision_reasons", []),
            "next_action": NEXT_ACTION if classification == "ALERT" else "",
        }

    return {
        **base,
        "strategy": None,
        "target_strategy": None,
        "classification": "REJECT",
        "target": False,
        "blocked": True,
        "decision_reasons": discovery.get("discovery_reasons", []) or ["no_strategy_candidate"],
        "next_action": "",
    }


def strategy_result_to_row_fields(result: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "target_strategy": result.get("target_strategy"),
        "strategies_considered": result.get("strategies_considered") or [],
        "classification": result.get("classification"),
        "discovery_reasons": (result.get("discovery") or {}).get("discovery_reasons", []),
        "decision_reasons": result.get("decision_reasons") or [],
        "next_action": result.get("next_action") or "",
        "non_vehicle_listing": result.get("non_vehicle_listing") or (result.get("discovery") or {}).get("non_vehicle_listing", False),
        "parts_or_equipment_only": result.get("parts_or_equipment_only") or (result.get("discovery") or {}).get("parts_or_equipment_only", False),
        "body_not_pickup": result.get("body_not_pickup") or (result.get("discovery") or {}).get("body_not_pickup", False),
        "parser_warning": result.get("parser_warning") or (result.get("discovery") or {}).get("parser_warning", ""),
        "parser_correction_reason": result.get("parser_correction_reason") or (result.get("discovery") or {}).get("parser_correction_reason", ""),
    }

    if result.get("target_strategy") == CONSUMER_GAS_LIQUID:
        fields.update(consumer_gas_result_to_row_fields(result.get("consumer_gas") or {}))
    elif result.get("target_strategy") == GAS_WORK_LOCAL:
        fields.update({
            "target_strategy": GAS_WORK_LOCAL,
            "classification": result.get("classification"),
            "decision_reasons": result.get("decision_reasons") or [],
            "next_action": "",
        })
    else:
        consumer_fields = consumer_gas_result_to_row_fields(result.get("consumer_gas") or {})
        for key in (
            "parsed_make",
            "parsed_model",
            "parsed_year",
            "parsed_vehicle_age",
            "parsed_mileage",
            "parsed_trim",
            "parsed_cab",
            "parsed_drivetrain",
            "parsed_engine",
            "parsed_fuel",
            "non_vehicle_listing",
            "parts_or_equipment_only",
            "body_not_pickup",
            "parser_warning",
            "parser_correction_reason",
        ):
            if consumer_fields.get(key) not in (None, "", False):
                fields[key] = consumer_fields[key]

    return fields
