from src.core.carvana_gas import classify_carvana_gas


def _codes(result):
    return set(
        result.get("positive_signals", [])
        + result.get("negative_signals", [])
        + result.get("block_reasons", [])
    )


def test_frontier_old_high_mileage_rejects():
    result = classify_carvana_gas({"title": "2016 Nissan Frontier 4.0 V6 120k miles"})

    assert result["classification"] == "REJECT"
    assert result["should_alert"] is False
    codes = _codes(result)
    assert "carvana_low_ceiling_model" in codes
    assert "carvana_mileage_too_high" in codes
    assert "carvana_year_too_old" in codes


def test_silverado_wt_2wd_does_not_alert():
    result = classify_carvana_gas({"title": "2019 Chevrolet Silverado 1500 WT 2WD 67k miles"})

    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False
    codes = _codes(result)
    assert "carvana_base_trim_low_ceiling" in codes
    assert "carvana_configuration_low_ceiling" in codes


def test_silverado_ltz_crew_4wd_alerts():
    result = classify_carvana_gas({
        "title": "2019 Chevrolet Silverado 1500 LTZ Crew Cab 4WD 50k miles 5.3 V8"
    })

    assert result["classification"] == "ALERT"
    assert result["should_alert"] is True
    codes = _codes(result)
    assert "carvana_strong_trim" in codes
    assert "carvana_strong_cab" in codes
    assert "carvana_4wd_bonus" in codes
    assert "carvana_preferred_engine" in codes
    assert "carvana_very_low_mileage" in codes
    assert result["next_action"] == "GET CARVANA QUOTE"


def test_f150_regular_cab_xl_does_not_score_like_supercrew():
    result = classify_carvana_gas({"title": "2019 Ford F-150 Regular Cab XL 51k miles"})

    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False
    codes = _codes(result)
    assert "carvana_base_trim_low_ceiling" in codes
    assert "carvana_configuration_low_ceiling" in codes


def test_f150_king_ranch_supercrew_4wd_alerts():
    result = classify_carvana_gas({"title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles"})

    assert result["classification"] == "ALERT"
    assert result["score"] >= 75
    codes = _codes(result)
    assert "carvana_strong_trim" in codes
    assert "carvana_strong_cab" in codes
    assert "carvana_4wd_bonus" in codes


def test_tundra_crewmax_sr5_alerts():
    result = classify_carvana_gas({"title": "2019 Toyota Tundra CrewMax SR5 5.7 V8 58k miles"})

    assert result["classification"] == "ALERT"
    codes = _codes(result)
    assert "carvana_value_retention_bonus" in codes
    assert "carvana_good_trim" in codes
    assert "carvana_strong_cab" in codes
    assert "carvana_preferred_engine" in codes


def test_2018_tundra_limited_is_not_rejected_for_year():
    result = classify_carvana_gas({"title": "2018 Toyota Tundra CrewMax Limited 5.7 70k miles"})

    assert result["classification"] in {"ALERT", "WATCHLIST"}
    assert "carvana_year_too_old" not in _codes(result)


def test_colorado_wt_low_mileage_is_not_enough():
    result = classify_carvana_gas({"title": "2020 Chevrolet Colorado WT 50k miles"})

    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False
    assert "carvana_base_trim_low_ceiling" in _codes(result)


def test_colorado_zr2_crew_4wd_alerts():
    result = classify_carvana_gas({"title": "2022 Chevrolet Colorado ZR2 Crew Cab 4WD 33k miles"})

    assert result["classification"] == "ALERT"
    codes = _codes(result)
    assert "carvana_strong_trim" in codes
    assert "carvana_strong_cab" in codes
    assert "carvana_4wd_bonus" in codes


def test_ranger_xlt_low_mileage_is_not_automatic():
    result = classify_carvana_gas({"title": "2019 Ford Ranger XLT 50k miles"})

    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False


def test_rust_hard_rejects_otherwise_good_truck():
    result = classify_carvana_gas({
        "title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles frame rust"
    })

    assert result["classification"] == "REJECT"
    assert result["should_alert"] is False
    assert "carvana_rust" in result["block_reasons"]


def test_negated_rust_does_not_hard_reject():
    result = classify_carvana_gas({
        "title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles no rust"
    })

    assert result["classification"] == "ALERT"
    assert "carvana_rust" not in result["block_reasons"]


def test_diesel_fuel_rejects_carvana_lane():
    result = classify_carvana_gas({
        "title": "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles Power Stroke diesel"
    })

    assert result["classification"] == "REJECT"
    assert result["should_alert"] is False
    assert "carvana_wrong_fuel" in result["block_reasons"]


def test_unknown_mileage_does_not_alert():
    result = classify_carvana_gas({
        "title": "2019 Ford F-150 King Ranch SuperCrew 4WD mileage unknown"
    })

    assert result["classification"] in {"WATCHLIST", "REJECT"}
    assert result["should_alert"] is False
    assert "carvana_missing_required_data" in _codes(result)
