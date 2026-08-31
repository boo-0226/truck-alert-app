from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.discovery import DIESEL_COMMERCIAL, GAS_WORK_LOCAL
from src.core.strategies import classify_listing_strategies, strategy_result_to_row_fields


def test_diesel_commercial_wins_over_other_strategy_results():
    result = classify_listing_strategies(
        {"title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles"},
        current_year=2026,
        diesel_result={
            "strategy": DIESEL_COMMERCIAL,
            "classification": "ALERT",
            "target": True,
            "blocked": False,
            "decision_reasons": ["diesel_commercial_existing_match"],
        },
    )

    assert result["target_strategy"] == DIESEL_COMMERCIAL
    assert result["target"] is True
    assert result["blocked"] is False
    assert result["decision_reasons"] == ["diesel_commercial_existing_match"]


def test_consumer_gas_alert_routes_to_target_row_fields():
    result = classify_listing_strategies(
        {"title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles"},
        current_year=2026,
    )
    fields = strategy_result_to_row_fields(result)

    assert result["target_strategy"] == CONSUMER_GAS_LIQUID
    assert result["classification"] == "ALERT"
    assert result["target"] is True
    assert result["blocked"] is False
    assert fields["target_strategy"] == CONSUMER_GAS_LIQUID
    assert fields["next_action"] == "GET CARVANA QUOTE"
    assert fields["consumer_gas_score"] >= 75


def test_consumer_gas_watchlist_is_non_alerting_and_unblocked_for_reporting():
    result = classify_listing_strategies(
        {"title": "2019 Ford F-150 King Ranch SuperCrew 4WD mileage unknown"},
        current_year=2026,
    )

    assert result["target_strategy"] == CONSUMER_GAS_LIQUID
    assert result["classification"] == "WATCHLIST"
    assert result["target"] is False
    assert result["blocked"] is False
    assert result["next_action"] == ""


def test_gas_work_local_uses_existing_hd_gas_signal_only():
    result = classify_listing_strategies(
        {"title": "2014 Ford F-250 6.2 gas service body 80k miles"},
        current_year=2026,
        diesel_result={
            "strategy": DIESEL_COMMERCIAL,
            "classification": "REJECT",
            "target": False,
            "blocked": True,
            "decision_reasons": ["diesel_commercial_existing_no_match"],
        },
        gas_work_existing={"target": True, "label": "Ford F-250/F-350 gas"},
    )

    assert result["target_strategy"] == GAS_WORK_LOCAL
    assert result["classification"] == "ALERT"
    assert result["target"] is True
    assert result["blocked"] is False
