import importlib.util
from pathlib import Path

import pytest

from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.consumer_gas_liquid import classify_consumer_gas_liquid
from src.core.decision_log import make_listing_key, normalize_decision_record, render_daily_report
from src.core.discovery import DIESEL_COMMERCIAL, GAS_WORK_LOCAL, discover_vehicle_candidates
from src.core.strategies import classify_listing_strategies, strategy_result_to_row_fields


def _row(**overrides):
    row = {
        "source": "GovDeals",
        "site": "GovDeals",
        "url": "https://example.test/lot",
        "title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles",
        "state": "TX",
        "bid_cents": 400000,
        "minutes_left": 10,
        "bid_under_limit": True,
        "mileage_ok": True,
        "close_soon_flag": True,
        "should_alert": False,
    }
    row.update(overrides)
    return normalize_decision_record(row)


def _public_surplus_module():
    pytest.importorskip("selenium")
    path = Path(__file__).with_name("auto_public_surplus.py")
    spec = importlib.util.spec_from_file_location("auto_public_surplus_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_listing_key_by_url_and_report_unique_count():
    first = _row(url="https://example.test/lot/123?utm_source=x", minutes_left=20)
    second = _row(url="https://example.test/lot/123", minutes_left=5)

    assert make_listing_key(first) == make_listing_key(second)

    report = render_daily_report([first, second], "2026-09-13")

    assert "row evaluations scanned: 2" in report
    assert "unique listings scanned: 1" in report
    assert "unique Texas listings: 1" in report


def test_deduped_near_misses_choose_best_scan():
    rows = [
        _row(
            url="https://example.test/watch/1",
            title="2020 Ford Ranger XLT Crew Cab 4x4 45k miles",
            minutes_left=minutes,
            classification="WATCHLIST",
            target_strategy=CONSUMER_GAS_LIQUID,
            strategies_considered=[CONSUMER_GAS_LIQUID],
            broad_discovery_candidate=True,
            consumer_gas_score=55,
            positive_signals=["consumer_gas_opportunistic_model"],
            block_reasons=["consumer_gas_watchlist_score"],
        )
        for minutes in (25, 20, 15, 10, 5)
    ]

    report = render_daily_report(rows, "2026-09-13")
    near_misses = report.split("5. Near Misses", 1)[1].split("6. Missing Data Examples", 1)[0]

    assert near_misses.count("2020 Ford Ranger XLT Crew Cab 4x4") == 1
    assert "minutes=5" in near_misses
    assert "evaluation_count_for_listing=5" in near_misses
    assert "deduped by listing_key" in near_misses


def test_missing_data_examples_are_deduped_by_listing_key():
    rows = [
        _row(
            url="https://example.test/missing/1",
            title="2019 Ford F-150 Lariat SuperCrew 4WD 5.0 gas",
            minutes_left=minutes,
            classification="WATCHLIST",
            target_strategy=CONSUMER_GAS_LIQUID,
            strategies_considered=[CONSUMER_GAS_LIQUID],
            broad_discovery_candidate=True,
            missing_fields=["missing_mileage"],
            missing_data_notes=["missing_mileage mattered because CONSUMER_GAS_LIQUID requires reliable mileage for ALERT."],
            block_reasons=["consumer_gas_missing_mileage"],
        )
        for minutes in (25, 15, 5)
    ]

    report = render_daily_report(rows, "2026-09-13")
    missing = report.split("6. Missing Data Examples", 1)[1]

    assert missing.count("2019 Ford F-150 Lariat SuperCrew") == 1
    assert "evaluation_count_for_listing=3" in missing
    assert "missing=missing_mileage" in missing


def test_public_surplus_outside_tx_early_skip_logs_location_filter(monkeypatch):
    module = _public_surplus_module()
    captured = []
    monkeypatch.setattr(module, "log_decision", lambda row: captured.append(row))
    listing = {
        "auction_id": "ps-az-1",
        "listing_url": "https://www.publicsurplus.com/sms/auction/view?auc=ps-az-1",
        "region_text": "AZ",
    }

    should_skip, reason = module.should_skip_public_surplus_listing_by_region(listing)
    if should_skip:
        module._log_public_surplus_location_reject(listing, reason)

    assert should_skip is True
    assert reason == "outside_target_state"
    assert captured[0]["decision_stage"] == "LOCATION_FILTER"
    assert captured[0]["primary_reject_reason"] == "outside_target_state"
    assert captured[0]["target"] is False
    assert captured[0]["blocked"] is True
    assert captured[0]["should_alert"] is False
    assert "target_strategy" not in captured[0]


def test_public_surplus_tx_region_is_allowed_to_continue():
    module = _public_surplus_module()
    should_skip, reason = module.should_skip_public_surplus_listing_by_region({"region_text": "TX"})

    assert should_skip is False
    assert reason == ""


def test_tahoe_ppv_is_not_sierra_or_consumer_pickup():
    listing = {
        "title": "FULLY EQUIPPED 2019 Chevrolet Tahoe PPV",
        "desc": "5.3L, police SUV",
    }
    result = classify_listing_strategies(listing, current_year=2026)
    fields = strategy_result_to_row_fields(result)
    consumer = result["consumer_gas"]

    assert consumer["make"] == "Chevrolet"
    assert consumer["model"] in {"Tahoe", "Tahoe PPV"}
    assert consumer["model"] != "Sierra 1500"
    assert result["target_strategy"] is None
    assert result["classification"] == "REJECT"
    assert fields["body_not_pickup"] is True


def test_sierra_still_classifies_as_sierra():
    result = classify_consumer_gas_liquid(
        {"title": "2019 GMC Sierra 1500 Crew Cab 4x4 5.3L 48k miles"},
        current_year=2026,
    )

    assert result["make"] == "GMC"
    assert result["model"] == "Sierra 1500"
    assert result["is_consumer_gas_candidate"] is True
    assert result["strategy"] == CONSUMER_GAS_LIQUID


def test_polaris_ranger_is_not_ford_ranger_or_consumer_gas():
    result = classify_listing_strategies({"title": "Polaris Ranger Crew 24161"}, current_year=2026)
    consumer = result["consumer_gas"]

    assert consumer["make"] == "Polaris"
    assert consumer["model"] == "Ranger"
    assert consumer["make"] != "Ford"
    assert result["target_strategy"] is None
    assert CONSUMER_GAS_LIQUID not in result["strategies_considered"]


def test_ford_ranger_still_routes_to_consumer_gas():
    result = classify_listing_strategies(
        {"title": "2020 Ford Ranger XLT Crew Cab 4x4 45k miles"},
        current_year=2026,
    )

    assert result["consumer_gas"]["make"] == "Ford"
    assert result["consumer_gas"]["model"] == "Ranger"
    assert result["target_strategy"] == CONSUMER_GAS_LIQUID
    assert result["classification"] in {"WATCHLIST", "ALERT"}


@pytest.mark.parametrize(
    ("title", "not_strategy"),
    [
        ("Ford F-150 Tailgate", CONSUMER_GAS_LIQUID),
        ("2019 F350 Superduty Dually Bed", GAS_WORK_LOCAL),
        ("Vehicle Jacks (2)", DIESEL_COMMERCIAL),
    ],
)
def test_parts_and_equipment_only_are_not_strategy_candidates(title, not_strategy):
    result = classify_listing_strategies({"title": title}, current_year=2026)
    fields = strategy_result_to_row_fields(result)

    assert result["classification"] == "REJECT"
    assert result["target_strategy"] is None
    assert not_strategy not in result["strategies_considered"]
    assert fields["parts_or_equipment_only"] or fields["non_vehicle_listing"]
    assert result["decision_reasons"][0] in {"parts_or_equipment_only", "non_vehicle_listing"}


def test_vehicle_jacks_do_not_trigger_commercial_discovery():
    discovery = discover_vehicle_candidates({"title": "Vehicle Jacks (2)"})

    assert discovery["discovered"] is False
    assert "discovery_commercial_body" not in discovery["discovery_reasons"]
    assert "discovery_diesel_keyword" not in discovery["discovery_reasons"]
    assert "discovery_cummins_keyword" not in discovery["discovery_reasons"]


def test_tow_only_is_not_tow_truck_discovery():
    discovery = discover_vehicle_candidates({"title": "2012 Chevrolet Impala FFV **TOW ONLY**"})
    result = classify_listing_strategies({"title": "2012 Chevrolet Impala FFV **TOW ONLY**"}, current_year=2026)

    assert discovery["discovered"] is False
    assert "discovery_commercial_body" not in discovery["discovery_reasons"]
    assert result["target_strategy"] is None
    assert result["classification"] == "REJECT"


def test_tow_truck_still_candidate():
    result = classify_listing_strategies(
        {"title": "2015 Ford F-550 Tow Truck", "desc": "6.7 Power Stroke diesel 90k miles"},
        current_year=2026,
    )

    assert result["target_strategy"] == DIESEL_COMMERCIAL
    assert result["classification"] == "ALERT"
    assert result["target"] is True


def test_complete_service_truck_still_candidate():
    result = classify_listing_strategies(
        {"title": "2015 Ford F-550 Service Truck", "desc": "utility body, compressor, 6.7 diesel 90k miles"},
        current_year=2026,
    )

    assert result["target_strategy"] == DIESEL_COMMERCIAL
    assert result["classification"] == "ALERT"
