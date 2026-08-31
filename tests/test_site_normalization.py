import importlib.util
from pathlib import Path

from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.discovery import GAS_WORK_LOCAL
from src.core.strategies import classify_listing_strategies
from src.sites.govdeals import normalize
from src.sites.proxibid import _parse_fragment
from src.sites.renebates import _extract_lot_rows


def _load_public_surplus_module():
    module_path = Path(__file__).with_name("auto_public_surplus.py")
    spec = importlib.util.spec_from_file_location("auto_public_surplus_for_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_govdeals_generic_title_uses_description_for_consumer_gas_fields():
    item = {
        "assetId": "gas-1",
        "assetShortDescription": "2019 Ford F150 Pickup",
        "assetLongDescription": "5.0 V8 Lariat Crew Cab 4x4 38,000 miles runs and drives gas",
        "categoryName": "Pickup Trucks",
        "locationCity": "Austin",
        "locationState": "TX",
        "currentBid": "$4,000",
        "secondsRemaining": 7200,
    }

    row = normalize([item], detail_session=None)[0]

    assert row["target_strategy"] == CONSUMER_GAS_LIQUID
    assert row["classification"] == "ALERT"
    assert row["target"] is True
    assert row["blocked"] is False
    assert row["trim"] == "Lariat"
    assert row["cab"] == "Crew Cab"
    assert row["drivetrain"] == "4WD"
    assert "discovery_make_model_alias" in row["discovery_reasons"]


def test_proxibid_parser_uses_container_text_for_consumer_gas_classification():
    html = """
    <div class="gallery-card">
      <a href="/asp/LotDetail.asp?lid=123"><span class="lotTitle">2019 Ford F150 Pickup</span></a>
      <div class="lotDesc">5.0 V8 Lariat SuperCrew 4x4 38,000 miles runs and drives gas</div>
      <div class="currentPrice">$4,000</div>
      <div class="countdownTimer">
        <span class="auctionTimeEntity">0</span>
        <span class="auctionTimeEntity">5</span>
      </div>
    </div>
    """

    row = _parse_fragment(html)[0]

    assert row["target_strategy"] == CONSUMER_GAS_LIQUID
    assert row["classification"] == "ALERT"
    assert row["target"] is True
    assert row["blocked"] is False
    assert row["cab"] == "SuperCrew"
    assert row["mileage"] == 38_000


def test_renebates_lot_container_text_survives_for_strategy_classification():
    html = """
    <table>
      <tr>
        <td><a href="a_lot_1.php?id=10&lot=22">2019 Ford F150 Pickup</a></td>
        <td>5.0 V8 Lariat SuperCrew 4x4 38,000 miles runs and drives gas</td>
        <td>$4,000</td>
      </tr>
    </table>
    """

    lot = _extract_lot_rows(html)[0]
    result = classify_listing_strategies(
        {
            "title": lot["title"],
            "desc": lot["container_text"],
            "event_title": "City Of Van Alstyne, Texas",
        },
        current_year=2026,
    )

    assert "5.0 V8 Lariat SuperCrew" in lot["container_text"]
    assert result["target_strategy"] == CONSUMER_GAS_LIQUID
    assert result["classification"] == "ALERT"


def test_public_surplus_consumer_gas_routes_through_strategy_classifier():
    public_surplus = _load_public_surplus_module()
    listing = {"region_text": "TX", "listing_url": "https://example.test/ps"}
    detail = {
        "title": "2019 Ford F150 Pickup",
        "structured_text": "",
        "description_text": "5.0 V8 Lariat Crew Cab 4x4 38,000 miles gas runs and drives",
        "current_bid": 3000.0,
        "minutes_left": 20,
        "mileage_value": 38_000,
        "location": "Austin, Texas",
        "condition": "Runs",
        "title_status": "Clean",
        "vin": "1FTFW1E50KFA00000",
    }

    evaluation = public_surplus.evaluate_truck(listing, detail)

    assert evaluation["target_strategy"] == CONSUMER_GAS_LIQUID
    assert evaluation["classification"] == "ALERT"
    assert evaluation["consumer_gas_match"] is True
    assert evaluation["diesel_match"] is False
    assert evaluation["should_alert"] is True
    assert evaluation["next_action"] == "GET CARVANA QUOTE"


def test_public_surplus_preserves_existing_hd_gas_work_match():
    public_surplus = _load_public_surplus_module()
    listing = {"region_text": "TX", "listing_url": "https://example.test/ps-hd"}
    detail = {
        "title": "2014 Ford F-250 Pickup",
        "structured_text": "",
        "description_text": "6.2 gas service body 80,000 miles runs and drives",
        "current_bid": 3000.0,
        "minutes_left": 20,
        "mileage_value": 80_000,
        "location": "Austin, Texas",
        "condition": "Runs",
        "title_status": "Clean",
    }

    evaluation = public_surplus.evaluate_truck(listing, detail)

    assert evaluation["target_strategy"] == GAS_WORK_LOCAL
    assert evaluation["gas_work_match"] is True
    assert evaluation["legacy_gas_match"] is True
    assert evaluation["should_alert"] is True
