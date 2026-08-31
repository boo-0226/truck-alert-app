import importlib.util
from pathlib import Path

from src.core import alerts
from src.core.collect import _normalize_row
from src.core.config import TARGET_STATES, is_allowed_state, normalize_state
from src.sites.govdeals import normalize as normalize_govdeals
from src.sites.govdeals_http import GOVDEALS_FILTERED_URL, build_govdeals_search_payload


def _load_public_surplus_module():
    module_path = Path(__file__).with_name("auto_public_surplus.py")
    spec = importlib.util.spec_from_file_location("auto_public_surplus_location_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _strong_govdeals_item(state):
    return {
        "assetId": f"gd-{state or 'unknown'}",
        "assetShortDescription": "2019 Ford F150 Pickup",
        "assetLongDescription": "5.0 V8 Lariat Crew Cab 4x4 38,000 miles gas runs and drives",
        "categoryName": "Pickup Trucks",
        "locationCity": "Austin",
        "locationState": state,
        "currentBid": "$4,000",
        "secondsRemaining": 7200,
    }


def _public_surplus_detail(location):
    return {
        "title": "2019 Ford F150 Pickup",
        "structured_text": "",
        "description_text": "5.0 V8 Lariat Crew Cab 4x4 38,000 miles gas runs and drives",
        "current_bid": 3000.0,
        "minutes_left": 20,
        "mileage_value": 38_000,
        "location": location,
        "condition": "Runs",
        "title_status": "Clean",
    }


def test_normalize_state_handles_names_and_codes():
    assert normalize_state("TX") == "TX"
    assert normalize_state("Texas") == "TX"
    assert normalize_state(" texas ") == "TX"
    assert normalize_state("Oklahoma") == "OK"
    assert normalize_state("") == ""


def test_default_target_states_allows_only_texas():
    assert TARGET_STATES == frozenset({"TX"})
    assert is_allowed_state("TX") is True
    assert is_allowed_state("Texas") is True
    assert is_allowed_state("OK") is False
    assert is_allowed_state("Oklahoma") is False
    assert is_allowed_state("LA") is False
    assert is_allowed_state("") is False


def test_govdeals_search_payload_requests_texas_only():
    payload = build_govdeals_search_payload()
    filters = payload["facetsFilter"]
    state_filters = [value for value in filters if "stateDesc" in value]

    assert state_filters == ['{!tag=stateDesc}stateDesc:"Texas"']
    assert "stateName=Texas" in GOVDEALS_FILTERED_URL
    assert "Oklahoma" not in GOVDEALS_FILTERED_URL


def test_govdeals_texas_row_remains_eligible():
    row = normalize_govdeals([_strong_govdeals_item("TX")], detail_session=None)[0]

    assert row["location_allowed"] is True
    assert row["location_block_reason"] == ""
    assert row["normalized_state"] == "TX"
    assert row["target"] is True
    assert row["blocked"] is False
    assert row["classification"] == "ALERT"


def test_govdeals_non_texas_row_is_blocked_by_location():
    row = normalize_govdeals([_strong_govdeals_item("Oklahoma")], detail_session=None)[0]

    assert row["location_allowed"] is False
    assert row["location_block_reason"] == "outside_target_state"
    assert row["normalized_state"] == "OK"
    assert row["target"] is False
    assert row["blocked"] is True
    assert row["classification"] == "REJECT"
    assert "outside_target_state" in row["block_reasons"]


def test_public_surplus_texas_row_remains_eligible():
    public_surplus = _load_public_surplus_module()
    evaluation = public_surplus.evaluate_truck(
        {"region_text": "TX", "listing_url": "https://example.test/ps"},
        _public_surplus_detail("Austin, Texas"),
    )

    assert evaluation["location_allowed"] is True
    assert evaluation["location_block_reason"] == ""
    assert evaluation["normalized_state"] == "TX"
    assert evaluation["target"] is True
    assert evaluation["blocked"] is False
    assert evaluation["should_alert"] is True


def test_public_surplus_non_texas_row_is_blocked_by_location():
    public_surplus = _load_public_surplus_module()
    evaluation = public_surplus.evaluate_truck(
        {"region_text": "AL", "listing_url": "https://example.test/ps-al"},
        _public_surplus_detail("Birmingham, Alabama"),
    )

    assert evaluation["location_allowed"] is False
    assert evaluation["location_block_reason"] == "outside_target_state"
    assert evaluation["normalized_state"] == "AL"
    assert evaluation["target"] is False
    assert evaluation["blocked"] is True
    assert evaluation["classification"] == "REJECT"
    assert evaluation["should_alert"] is False


def test_unknown_state_is_blocked_by_shared_guard():
    row = _normalize_row({
        "site": "GovDeals",
        "asset_id": "unknown-state",
        "title": "Ford F-550 6.7 Power Stroke service body utility truck",
        "state": "",
        "bid_cents": 400000,
        "secs": 300,
        "target": True,
        "blocked": False,
        "classification": "ALERT",
        "target_strategy": "DIESEL_COMMERCIAL",
    })

    assert row["location_allowed"] is False
    assert row["location_block_reason"] == "location_state_unknown"
    assert row["target"] is False
    assert row["blocked"] is True
    assert row["classification"] == "REJECT"
    assert "location_state_unknown" in row["block_reasons"]


def test_non_texas_diesel_target_cannot_enter_alert_path(monkeypatch):
    monkeypatch.setattr(alerts, "mark_alerted", lambda *args, **kwargs: None)
    monkeypatch.setattr(alerts, "save_cache", lambda *args, **kwargs: None)
    row = _normalize_row({
        "site": "GovDeals",
        "asset_id": "ok-diesel",
        "title": "Ford F-550 6.7 Power Stroke service body utility truck",
        "state": "OK",
        "bid_cents": 400000,
        "secs": 300,
        "target": True,
        "blocked": False,
        "classification": "ALERT",
        "target_strategy": "DIESEL_COMMERCIAL",
    })

    assert row["target"] is False
    assert row["blocked"] is True
    assert alerts.evaluate_and_alert({}, [row], alerts_enabled=True) is None


def test_texas_consumer_gas_can_alert_but_oklahoma_clone_cannot():
    texas = normalize_govdeals([_strong_govdeals_item("Texas")], detail_session=None)[0]
    oklahoma = normalize_govdeals([_strong_govdeals_item("Oklahoma")], detail_session=None)[0]

    assert texas["target_strategy"] == "CONSUMER_GAS_LIQUID"
    assert texas["target"] is True
    assert texas["blocked"] is False
    assert texas["classification"] == "ALERT"
    assert oklahoma["target_strategy"] == "CONSUMER_GAS_LIQUID"
    assert oklahoma["target"] is False
    assert oklahoma["blocked"] is True
    assert oklahoma["classification"] == "REJECT"
    assert oklahoma["location_block_reason"] == "outside_target_state"


def test_texas_diesel_commercial_still_classifies_after_location_guard():
    row = normalize_govdeals(
        [
            {
                "assetId": "tx-diesel",
                "assetShortDescription": "Ford F-550 utility truck",
                "assetLongDescription": "Ford F-550 6.7 Power Stroke service body utility truck",
                "categoryName": "Service Trucks",
                "locationCity": "Austin",
                "locationState": "TX",
                "currentBid": "$4,500",
                "secondsRemaining": 7200,
            }
        ],
        detail_session=None,
    )[0]

    assert row["location_allowed"] is True
    assert row["target_strategy"] == "DIESEL_COMMERCIAL"
    assert row["target"] is True
    assert row["blocked"] is False
