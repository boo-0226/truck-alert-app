# file: src/core/carvana_gas.py
from __future__ import annotations

from typing import Any

from src.core.consumer_gas_liquid import (
    calculate_max_hammer_for_offer,
    classify_consumer_gas_liquid,
    consumer_gas_result_to_row_fields,
)


def classify_carvana_gas(listing: dict[str, Any]) -> dict[str, Any]:
    return classify_consumer_gas_liquid(listing)


def carvana_result_to_row_fields(result: dict[str, Any]) -> dict[str, Any]:
    return consumer_gas_result_to_row_fields(result)


def calculate_max_hammer_for_carvana_offer(offer: float, **kwargs) -> float:
    return calculate_max_hammer_for_offer(offer, **kwargs)
