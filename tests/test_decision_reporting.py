from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.decision_log import CSV_FIELDS, normalize_decision_record, render_daily_report
from src.core.discovery import DIESEL_COMMERCIAL
from src.core.strategies import classify_listing_strategies, strategy_result_to_row_fields


def _normalize(raw):
    row = {
        "source": "GovDeals",
        "site": "GovDeals",
        "asset_id": raw.get("asset_id", "test-asset"),
        "url": raw.get("url", "https://example.test/lot"),
        "city": raw.get("city", "Austin"),
        "state": raw.get("state", "TX"),
        "bid_under_limit": raw.get("bid_under_limit", True),
        "mileage_ok": raw.get("mileage_ok", True),
        "close_soon_flag": raw.get("close_soon_flag", True),
        "should_alert": raw.get("should_alert", False),
    }
    row.update(raw)
    return normalize_decision_record(row)


def _strategy_report_row(title, **overrides):
    strategy_listing = {"title": title, "desc": overrides.pop("desc", "")}
    result = classify_listing_strategies(strategy_listing, current_year=2026)
    row = {
        "title": title,
        "target": result.get("target"),
        "blocked": result.get("blocked"),
        "bid_cents": 400000,
        "minutes_left": 10,
        "bid_under_limit": True,
        "mileage_ok": True,
        "close_soon_flag": True,
        "should_alert": False,
    }
    row.update(strategy_result_to_row_fields(result))
    row.update(overrides)
    return _normalize(row)


def test_outside_state_stops_early_without_polluting_later_reasons():
    row = _normalize(
        {
            "title": "Ford F-550 6.7 Power Stroke service body utility truck",
            "state": "OK",
            "target": True,
            "blocked": False,
            "target_strategy": DIESEL_COMMERCIAL,
            "mileage_ok": False,
            "block_reasons": ["blocked_mileage"],
        }
    )

    assert row["decision_stage"] == "LOCATION_FILTER"
    assert row["primary_reject_reason"] == "outside_target_state"
    assert row["primary_reason_group"] == "LOCATION"
    assert row["should_alert"] is False
    assert "mileage" not in row["block_reasons"]


def test_non_truck_random_car_is_broad_discovery_reject():
    row = _normalize(
        {
            "title": "2015 Chevrolet Traverse",
            "state": "TX",
            "secs": 600,
            "close_soon_flag": True,
            "block_reasons": ["not_gas_or_diesel_target", "blocked_mileage"],
        }
    )

    assert row["decision_stage"] == "BROAD_DISCOVERY"
    assert row["primary_reject_reason"] == "no_broad_discovery_match"
    assert row["broad_discovery_candidate"] is False
    assert "not_gas_or_diesel_target" not in row["block_reasons"]
    assert "mileage_too_high" not in row["block_reasons"]


def test_missing_time_is_primary_only_when_candidate_needs_time():
    row = _strategy_report_row(
        "2019 Ford F-150 Lariat SuperCrew 4WD 5.0 gas 48k miles",
        minutes_left=None,
        secs=None,
        close_soon_flag=False,
    )

    assert row["broad_discovery_candidate"] is True
    assert row["primary_reject_reason"] == "missing_time"
    assert row["primary_reason_group"] == "TIME"
    assert "missing_time" in row["missing_fields"]
    assert row["should_alert"] is False


def test_known_time_outside_window_is_not_missing_time():
    row = _strategy_report_row(
        "2019 Ford F-150 Lariat SuperCrew 4WD 5.0 gas 48k miles",
        minutes_left=90,
        close_soon_flag=False,
    )

    assert row["primary_reject_reason"] == "outside_time_window"
    assert row["primary_reason_group"] == "TIME"
    assert "missing_time" not in row["block_reasons"]


def test_missing_mileage_for_consumer_gas_explains_required_data():
    row = _strategy_report_row(
        "2019 Ford F-150 Lariat SuperCrew 4WD 5.0 gas",
        minutes_left=10,
        close_soon_flag=True,
    )

    assert row["broad_discovery_candidate"] is True
    assert CONSUMER_GAS_LIQUID in row["strategies_considered"]
    assert row["target_strategy"] == CONSUMER_GAS_LIQUID
    assert row["final_classification"] in {"WATCHLIST", "REJECT"}
    assert row["primary_reject_reason"] in {"missing_mileage", "missing_required_data"}
    assert "missing_mileage" in row["missing_fields"]
    assert "CONSUMER_GAS_LIQUID requires reliable mileage" in " ".join(row["missing_data_notes"])


def test_weak_consumer_gas_reports_configuration_instead_of_generic_fuel_reject():
    row = _strategy_report_row(
        "2019 Ford F-150 XL Regular Cab 2WD 95k miles",
        minutes_left=10,
        close_soon_flag=True,
    )

    assert row["broad_discovery_candidate"] is True
    assert CONSUMER_GAS_LIQUID in row["strategies_considered"]
    assert row["final_classification"] != "ALERT"
    assert row["primary_reject_reason"] in {
        "consumer_gas_low_ceiling",
        "strategy_reject_low_ceiling",
        "base_trim_low_ceiling",
        "weak_configuration",
        "mileage_too_high",
    }
    assert "not_gas_or_diesel_target" not in row["block_reasons"]


def test_diesel_regression_reporting_does_not_change_target_result():
    row = _strategy_report_row(
        "2013 Ford F-550 6.7 Power Stroke service body utility truck",
        target_strategy=DIESEL_COMMERCIAL,
        target=True,
        blocked=False,
        classification="ALERT",
        should_alert=True,
        secs=300,
        minutes_left=5,
        close_soon_flag=True,
    )

    assert row["target_strategy"] == DIESEL_COMMERCIAL
    assert row["target"] is True
    assert row["blocked"] is False
    assert row["final_classification"] == "ALERT"
    assert row["decision_stage"] == "ALERT_ROUTING"
    assert row["alert_gate_passed"] is True


def test_watchlist_rows_report_no_twilio_routing():
    row = _strategy_report_row(
        "2019 Ford F-150 King Ranch SuperCrew 4WD mileage unknown",
        minutes_left=10,
        close_soon_flag=True,
    )

    assert row["final_classification"] == "WATCHLIST"
    assert row["should_alert"] is False
    assert "watchlist_no_twilio" in row["alert_reasons"]


def test_daily_report_summary_keeps_candidates_separate_from_junk():
    rows = [
        _normalize(
            {
                "source": "GovDeals",
                "site": "GovDeals",
                "title": "Ford F-550 6.7 Power Stroke service body utility truck",
                "state": "OK",
                "target_strategy": DIESEL_COMMERCIAL,
                "target": True,
                "blocked": False,
            }
        ),
        _normalize(
            {
                "source": "GovDeals",
                "site": "GovDeals",
                "title": "2015 Chevrolet Traverse",
                "state": "TX",
                "secs": 600,
            }
        ),
        _strategy_report_row(
            "2019 Ford F-150 Lariat SuperCrew 4WD 5.0 gas 48k miles",
            source="Public Surplus",
            site="Public Surplus",
            asset_id="ps-missing-time",
            minutes_left=None,
            secs=None,
            close_soon_flag=False,
        ),
        _strategy_report_row(
            "2019 Ford F-150 XL Regular Cab 2WD 95k miles",
            source="Public Surplus",
            site="Public Surplus",
            asset_id="ps-weak",
        ),
        _strategy_report_row(
            "2013 Ford F-550 6.7 Power Stroke service body utility truck",
            source="GovDeals",
            site="GovDeals",
            asset_id="gd-alert",
            target_strategy=DIESEL_COMMERCIAL,
            target=True,
            blocked=False,
            classification="ALERT",
            should_alert=True,
            secs=300,
            minutes_left=5,
        ),
    ]

    report = render_daily_report(rows, "2026-09-09")
    near_miss_section = report.split("5. Near Misses", 1)[1].split("6. Missing Data Examples", 1)[0]
    missing_section = report.split("6. Missing Data Examples", 1)[1]

    assert "count by primary_reason_group:" in report
    assert "count by primary_reject_reason:" in report
    assert "count by secondary_reasons:" in report
    assert "2. GovDeals Summary" in report
    assert "3. Public Surplus Summary" in report
    assert "top missing data fields among discovered candidates:" in report
    assert "top 20 discovered candidate near misses:" in report
    assert "2019 Ford F-150 XL Regular Cab 2WD 95k miles" in near_miss_section
    assert "2015 Chevrolet Traverse" not in near_miss_section
    assert "2015 Chevrolet Traverse" not in missing_section
    assert "missing_time prevented alert eligibility" in missing_section
    assert "primary_reject_reason" in CSV_FIELDS
    assert "primary_reason_group" in CSV_FIELDS
