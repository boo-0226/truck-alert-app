from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.discovery import DIESEL_COMMERCIAL, discover_vehicle_candidates
from src.core.strategies import classify_listing_strategies


def test_generic_f150_title_discovers_and_classifier_uses_description():
    listing = {
        "title": "2019 Ford F150 Pickup",
        "desc": "5.0 V8 Lariat Crew Cab 4x4 38,000 miles runs and drives",
    }

    discovery = discover_vehicle_candidates(listing)
    result = classify_listing_strategies(listing, current_year=2026)

    assert discovery["discovered"] is True
    assert CONSUMER_GAS_LIQUID in discovery["strategy_candidates"]
    assert "discovery_make_model_alias" in discovery["discovery_reasons"]
    assert result["target_strategy"] == CONSUMER_GAS_LIQUID
    assert result["classification"] == "ALERT"
    assert result["target"] is True


def test_generic_diesel_title_detail_split_uses_existing_diesel_classifier():
    listing = {
        "title": "2007 International Dump Truck",
        "desc": "DT466 diesel automatic 88,000 miles",
    }

    discovery = discover_vehicle_candidates(listing)
    result = classify_listing_strategies(listing, current_year=2026)

    assert discovery["discovered"] is True
    assert DIESEL_COMMERCIAL in discovery["strategy_candidates"]
    assert result["target_strategy"] == DIESEL_COMMERCIAL
    assert result["classification"] == "ALERT"
    assert result["target"] is True


def test_discovery_candidate_does_not_create_alert_without_classifier_match():
    listing = {
        "title": "2007 International Dump Truck",
        "desc": "DT466 diesel automatic 88,000 miles",
    }

    discovery = discover_vehicle_candidates(listing)
    result = classify_listing_strategies(
        listing,
        current_year=2026,
        diesel_result={
            "strategy": DIESEL_COMMERCIAL,
            "classification": "REJECT",
            "target": False,
            "blocked": True,
            "decision_reasons": ["diesel_commercial_existing_no_match"],
        },
    )

    assert discovery["discovered"] is True
    assert "target" not in discovery
    assert result["target"] is False
    assert result["target_strategy"] is None


def test_future_f150_watchlists_missing_detail_instead_of_fixed_year_reject():
    listing = {
        "title": "2027 Ford F-150",
        "desc": "valid mileage, gas pickup",
    }

    discovery = discover_vehicle_candidates(listing)
    result = classify_listing_strategies(listing, current_year=2026)

    assert discovery["discovered"] is True
    assert CONSUMER_GAS_LIQUID in discovery["strategy_candidates"]
    assert result["target_strategy"] == CONSUMER_GAS_LIQUID
    assert result["classification"] == "WATCHLIST"
    assert "consumer_gas_future_model_watchlist" in result["decision_reasons"]
    assert "consumer_gas_year_too_old" not in result["decision_reasons"]
