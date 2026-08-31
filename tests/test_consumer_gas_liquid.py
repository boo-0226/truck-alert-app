from src.core.consumer_gas_liquid import (
    STRATEGY,
    calculate_max_hammer_for_offer,
    classify_consumer_gas_liquid,
)


def _codes(result):
    return set(
        result.get("positive_signals", [])
        + result.get("negative_signals", [])
        + result.get("block_reasons", [])
    )


def test_weak_f150_does_not_alert():
    result = classify_consumer_gas_liquid(
        {"title": "2019 Ford F-150 XL Regular Cab 2WD 95k miles"},
        current_year=2026,
    )

    assert result["strategy"] == STRATEGY
    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False
    codes = _codes(result)
    assert "consumer_gas_base_trim_low_ceiling" in codes
    assert "consumer_gas_weak_configuration" in codes
    assert "consumer_gas_mileage_too_high" in codes


def test_strong_f150_alerts():
    result = classify_consumer_gas_liquid(
        {"title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles"},
        current_year=2026,
    )

    assert result["classification"] == "ALERT"
    assert result["should_alert"] is True
    assert result["score"] >= 75
    codes = _codes(result)
    assert "consumer_gas_strong_trim" in codes
    assert "consumer_gas_strong_cab" in codes
    assert "consumer_gas_4wd" in codes
    assert "consumer_gas_prime_mileage" in codes
    assert result["next_action"] == "GET CARVANA QUOTE"


def test_strong_tundra_older_not_killed_by_universal_age_cutoff():
    result = classify_consumer_gas_liquid(
        {"title": "2018 Toyota Tundra CrewMax Limited 5.7 4WD 65k miles"},
        current_year=2026,
    )

    assert result["classification"] in {"ALERT", "WATCHLIST"}
    assert result["should_alert"] is True
    assert "consumer_gas_age_too_old" not in _codes(result)
    assert "consumer_gas_year_too_old" not in _codes(result)


def test_frontier_old_high_mileage_rejects():
    result = classify_consumer_gas_liquid(
        {"title": "2016 Nissan Frontier 4.0 V6 120k miles"},
        current_year=2026,
    )

    assert result["classification"] == "REJECT"
    assert result["should_alert"] is False
    codes = _codes(result)
    assert "consumer_gas_low_ceiling_model" in codes
    assert "consumer_gas_mileage_too_high" in codes
    assert "consumer_gas_year_too_old" in codes


def test_colorado_zr2_opportunity_alerts():
    result = classify_consumer_gas_liquid(
        {"title": "2022 Chevrolet Colorado ZR2 Crew Cab 4WD 31k miles"},
        current_year=2026,
    )

    assert result["classification"] == "ALERT"
    codes = _codes(result)
    assert "consumer_gas_opportunistic_model" in codes
    assert "consumer_gas_strong_trim" in codes
    assert "consumer_gas_strong_cab" in codes
    assert "consumer_gas_4wd" in codes


def test_colorado_wt_2wd_highish_miles_does_not_alert():
    result = classify_consumer_gas_liquid(
        {"title": "2018 Chevrolet Colorado WT 2WD 76k miles"},
        current_year=2026,
    )

    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False
    codes = _codes(result)
    assert "consumer_gas_low_ceiling_model" in codes
    assert "consumer_gas_base_trim_low_ceiling" in codes
    assert "consumer_gas_weak_configuration" in codes


def test_rust_hard_rejects_otherwise_good_truck():
    result = classify_consumer_gas_liquid(
        {
            "title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles",
            "desc": "Frame rust visible underneath.",
        },
        current_year=2026,
    )

    assert result["classification"] == "REJECT"
    assert result["should_alert"] is False
    assert "consumer_gas_rust" in result["block_reasons"]


def test_negated_rust_does_not_hard_reject():
    result = classify_consumer_gas_liquid(
        {
            "title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles",
            "desc": "No rust noted.",
        },
        current_year=2026,
    )

    assert result["classification"] == "ALERT"
    assert "consumer_gas_rust" not in result["block_reasons"]


def test_diesel_fuel_rejects_consumer_gas_lane():
    result = classify_consumer_gas_liquid(
        {"title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles Power Stroke diesel"},
        current_year=2026,
    )

    assert result["classification"] == "REJECT"
    assert result["should_alert"] is False
    assert "consumer_gas_wrong_fuel" in result["block_reasons"]


def test_make_model_alone_and_low_mileage_alone_do_not_alert():
    model_only = classify_consumer_gas_liquid(
        {"title": "2019 Ford F-150 pickup"},
        current_year=2026,
    )
    low_mileage_only = classify_consumer_gas_liquid(
        {"title": "2022 Chevrolet Colorado 31k miles"},
        current_year=2026,
    )

    assert model_only["classification"] != "ALERT"
    assert "consumer_gas_missing_required_data" in _codes(model_only)
    assert low_mileage_only["classification"] != "ALERT"
    assert "consumer_gas_low_ceiling_model" in _codes(low_mileage_only)


def test_future_model_year_watchlists_missing_configuration():
    result = classify_consumer_gas_liquid(
        {"title": "2027 Ford F-150", "desc": "valid mileage, gas pickup"},
        current_year=2026,
    )

    assert result["classification"] == "WATCHLIST"
    assert "consumer_gas_future_model_watchlist" in _codes(result)
    assert "consumer_gas_year_too_old" not in _codes(result)


def test_max_hammer_helper_uses_supplied_offer_only():
    assert calculate_max_hammer_for_offer(
        25_000,
        shipping=750,
        repairs=1_000,
        fixed_costs=500,
        buffer=750,
        premium_rate=0.12,
    ) == (25_000 - 3_500 - 750 - 1_000 - 500 - 750) / 1.12
