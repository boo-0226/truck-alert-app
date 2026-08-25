from src.core import alerts
from src.core.carvana_gas import classify_carvana_gas, carvana_result_to_row_fields


def _base_row():
    return {
        "site": "GovDeals",
        "asset_id": "route-1",
        "title": "Test truck",
        "city": "Austin",
        "state": "TX",
        "bid_cents": 400000,
        "secs": 300,
        "url": "https://example.test/lot",
    }


def test_carvana_alert_row_uses_existing_target_gate(monkeypatch):
    monkeypatch.setattr(alerts, "mark_alerted", lambda *args, **kwargs: None)
    monkeypatch.setattr(alerts, "save_cache", lambda *args, **kwargs: None)
    result = classify_carvana_gas({
        "title": "2019 Chevrolet Silverado 1500 LTZ Crew Cab 4WD 50k miles 5.3 V8"
    })
    row = _base_row()
    row.update(carvana_result_to_row_fields(result))
    row["target"] = True
    row["blocked"] = False

    assert row["target"] is True
    assert row["blocked"] is False
    assert row["classification"] == "ALERT"
    assert row["target_strategy"] == "CARVANA_GAS"
    assert alerts.evaluate_and_alert({}, [row], alerts_enabled=False) == 300


def test_carvana_watchlist_does_not_enter_twilio_path(monkeypatch):
    monkeypatch.setattr(alerts, "mark_alerted", lambda *args, **kwargs: None)
    monkeypatch.setattr(alerts, "save_cache", lambda *args, **kwargs: None)
    result = classify_carvana_gas({"title": "2019 Chevrolet Silverado 1500 WT 2WD 67k miles"})
    row = _base_row()
    row["asset_id"] = "route-watch"
    row.update(carvana_result_to_row_fields(result))
    row["target"] = False
    row["blocked"] = False

    def fail_twilio_client():
        raise AssertionError("watchlist should not request Twilio")

    monkeypatch.setattr(alerts, "twilio_client", fail_twilio_client)

    assert row["classification"] in {"WATCHLIST", "REJECT"}
    assert alerts.evaluate_and_alert({}, [row], alerts_enabled=True) is None


def test_diesel_alert_row_still_uses_same_gate(monkeypatch):
    monkeypatch.setattr(alerts, "mark_alerted", lambda *args, **kwargs: None)
    monkeypatch.setattr(alerts, "save_cache", lambda *args, **kwargs: None)
    row = _base_row()
    row["asset_id"] = "route-diesel"
    row["title"] = "Ford F-550 6.7 Power Stroke service body utility truck"
    row["target"] = True
    row["blocked"] = False
    row["target_strategy"] = "DIESEL_COMMERCIAL"

    assert alerts.evaluate_and_alert({}, [row], alerts_enabled=False) == 300
