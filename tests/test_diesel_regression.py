from src.core.utils import (
    annotate_tags,
    has_cummins,
    is_diesel,
    is_engine_67,
    is_heavy_duty_model,
    is_specialty_body,
    is_target_vehicle,
)
from src.core.carvana_gas import classify_carvana_gas
from src.sites.govdeals import normalize


def test_freightliner_bucket_cummins_diesel_still_targets():
    text = "2013 Freightliner M2 106 bucket truck Cummins diesel"

    assert has_cummins(text) is True
    assert is_diesel(text) is True
    assert is_specialty_body(text) is True
    assert is_heavy_duty_model(text) is True
    assert is_target_vehicle(text) is True


def test_f550_powerstroke_service_body_still_targets():
    text = "Ford F-550 6.7 Power Stroke service body utility truck"

    assert is_diesel(text) is True
    assert is_specialty_body(text) is True
    assert is_heavy_duty_model(text) is True
    assert is_engine_67(text) is True
    assert is_target_vehicle(text) is True


def test_international_dt466_dump_still_targets():
    text = "International 4300 DT466 dump truck"

    assert is_diesel(text) is True
    assert is_specialty_body(text) is True
    assert is_heavy_duty_model(text) is True
    assert is_target_vehicle(text) is True


def test_light_duty_f150_stays_blocked_from_diesel_lane():
    text = "2019 Ford F-150 5.0 gas SuperCrew 4WD"

    assert is_target_vehicle(text) is False


def test_light_duty_gas_can_only_alert_through_carvana_lane():
    diesel_text = "2019 Ford F-150 5.0 gas SuperCrew 4WD"
    carvana_text = "2019 Ford F-150 King Ranch SuperCrew 4WD 48k miles 5.0 gas"

    assert is_target_vehicle(diesel_text) is False
    result = classify_carvana_gas({"title": carvana_text})
    assert result["strategy"] == "CARVANA_GAS"
    assert result["classification"] == "ALERT"


def test_ram_1500_diesel_stays_blocked_from_diesel_lane():
    assert is_target_vehicle("Ram 1500 diesel") is False


def test_govdeals_diesel_normalize_preserves_existing_output():
    item = {
        "assetId": "1001",
        "assetShortDescription": "Ford F-550 utility truck",
        "assetLongDescription": "Ford F-550 6.7 Power Stroke service body utility truck",
        "categoryName": "Service Trucks",
        "locationCity": "Austin",
        "locationState": "TX",
        "currentBid": "$4,500",
        "secondsRemaining": 7200,
    }

    row = normalize([item])[0]
    expected_tags = annotate_tags(
        "Ford F-550 utility truck Ford F-550 6.7 Power Stroke service body utility truck Service Trucks"
    )

    assert row["target"] is True
    assert row["blocked"] is False
    assert row["engine_67"] is True
    assert row["tags"] == expected_tags
    assert row["target_strategy"] == "DIESEL_COMMERCIAL"
