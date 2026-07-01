# file: tests/autoGovDealsMoney.py

import html
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import requests

# Make sure .../src is on sys.path so "core" becomes importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))          # ...\truck-alert-app\tests
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)                       # ...\truck-alert-app
SRC_DIR = os.path.join(PROJECT_ROOT, "src")                       # ...\truck-alert-app\src

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# now we can import from src/core
from core.autoKeywords_GovDeals import (
    CLOSE_SOON_MINUTES,
    MAX_DIESEL_MILES,
    MAX_GAS_BID,
    MAX_GAS_MILES,
    clean_model_display,
    evaluate_diesel_truck_filter,
    evaluate_gas_fast_flip,
    find_hard_exclude_keywords,
    find_soft_warning_keywords,
    location_matches_alert_state,
    parse_bid_amount,
)
from core.decision_log import log_decision
from core.autoTwilio_Alerts import send_alert


GOVDEALS_SEARCH_URL = "https://maestro.lqdt1.com/search/list"
GOVDEALS_DETAIL_URL_TEMPLATE = "https://maestro.lqdt1.com/assets/{asset_id}/{account_id}/false"

GOVDEALS_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.govdeals.com",
    "Referer": "https://www.govdeals.com/",
    "User-Agent": "Mozilla/5.0",
}

GOVDEALS_SEARCH_PAYLOAD = {
    "categoryIds": "",
    "businessId": "GD",
    "searchText": "*",
    "isQAL": False,
    "locationId": None,
    "model": "",
    "makebrand": "",
    "auctionTypeId": None,
    "page": 1,
    "displayRows": 120,
    "sortField": "auctionclose",
    "sortOrder": "asc",
    "sessionId": "truck-sniper-session",
    "requestType": "search",
    "responseStyle": "fullResponse",
    "facets": [
        "categoryName",
        "auctionTypeID",
        "condition",
        "saleEventName",
        "sellerDisplayName",
        "product_pricecents",
        "isReserveMet",
        "hasBuyNowPrice",
        "isReserveNotMet",
        "sellerType",
        "warehouseId",
        "region",
        "currencyTypeCode",
        "countryDesc",
        "stateDesc",
        "city",
        "tierId",
    ],
    "facetsFilter": [
        '{!tag=product_category_external_id}product_category_external_id:"t6"',
        '{!tag=region}region:"Americas"',
        '{!tag=countryDesc}countryDesc:"United\\ States\\ of\\ America"',
        '{!tag=stateDesc}stateDesc:"Texas"',
        '{!tag=stateDesc}stateDesc:"Louisiana"',
        '{!tag=stateDesc}stateDesc:"Alabama"',
        '{!tag=stateDesc}stateDesc:"Tennessee"',
        '{!tag=stateDesc}stateDesc:"Arkansas"',
        '{!tag=stateDesc}stateDesc:"Mississippi"',
        '{!tag=stateDesc}stateDesc:"Missouri"',
        '{!tag=stateDesc}stateDesc:"Oklahoma"',
    ],
    "timeType": "",
    "sellerTypeId": None,
    "accountIds": [],
}

GOVDEALS_DETAIL_PAYLOAD = {
    "businessId": "GD",
    "siteId": 1,
}

STATE_ABBREVIATIONS = {
    "AL": "Alabama",
    "AR": "Arkansas",
    "FL": "Florida",
    "GA": "Georgia",
    "LA": "Louisiana",
    "MO": "Missouri",
    "MS": "Mississippi",
    "OK": "Oklahoma",
    "TN": "Tennessee",
    "TX": "Texas",
}

MILEAGE_NUMBER_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")
MILEAGE_DESC_PATTERNS = [
    re.compile(r"\blast\s+known\s+mileage\s*[-:#]?\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\blast\s+reported\s+odometer\s+(?:was\s+)?(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE),
    re.compile(
        r"\bodometer(?:\s+(?:reading|miles|mi))?\s*"
        r"(?:is|was|reads|shows|showing|listed\s+as|[-:#])?\s*"
        r"(\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmileage\s*"
        r"(?:is|was|reads|shows|showing|listed\s+as|[-:#])?\s*"
        r"(\d[\d,]*(?:\.\d+)?)",
        re.IGNORECASE,
    ),
]


def contains_any(text: str, keywords: set) -> bool:
    """Return True if any keyword appears in the text (case-insensitive)."""
    t = text.lower()
    return any(kw in t for kw in keywords)


def _first(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _clean_api_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _post_json(url: str, payload: dict) -> dict:
    response = requests.post(
        url,
        headers=GOVDEALS_HEADERS,
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _search_govdeals() -> list[dict]:
    data = _post_json(GOVDEALS_SEARCH_URL, GOVDEALS_SEARCH_PAYLOAD)
    results = data.get("assetSearchResults")
    if isinstance(results, list):
        return results

    for key in ("data", "payload", "searchResults"):
        nested = data.get(key)
        if isinstance(nested, dict) and isinstance(nested.get("assetSearchResults"), list):
            return nested["assetSearchResults"]

    return []


def _fetch_detail(asset_id: Any, account_id: Any) -> dict:
    url = GOVDEALS_DETAIL_URL_TEMPLATE.format(asset_id=asset_id, account_id=account_id)
    data = _post_json(url, GOVDEALS_DETAIL_PAYLOAD)
    if not isinstance(data, dict):
        return {}

    for key in ("asset", "assetDetail", "assetDetails", "data", "payload"):
        nested = data.get(key)
        if isinstance(nested, dict):
            return nested

    return data


def _build_listing_url(asset_id: Any, account_id: Any) -> str:
    return f"https://www.govdeals.com/en/asset/{asset_id}/{account_id}"


def _state_display(value: Any) -> str:
    state = str(value or "").strip()
    return STATE_ABBREVIATIONS.get(state.upper(), state)


def _location_from_api(listing: dict, detail: dict) -> str:
    city = _clean_api_text(_first(detail.get("city"), listing.get("locationCity"), listing.get("city")))
    state = _state_display(_first(detail.get("state"), listing.get("locationState"), listing.get("stateDesc")))
    parts = [part for part in (city, state) if part]
    return ", ".join(parts)


def _parse_utc_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def _minutes_left_from_listing(listing: dict) -> float | None:
    close_dt = _parse_utc_datetime(listing.get("assetAuctionEndDateUtc"))
    if close_dt is not None:
        return (close_dt - datetime.now(timezone.utc)).total_seconds() / 60

    remaining = listing.get("timeRemaining")
    if isinstance(remaining, (int, float)):
        return float(remaining) / 60

    if isinstance(remaining, str):
        match = re.search(r"\d[\d,]*(?:\.\d+)?", remaining)
        if match:
            try:
                return float(match.group(0).replace(",", "")) / 60
            except ValueError:
                return None

    return None


def _format_bid_value(value: Any, is_cents: bool = False) -> str | None:
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        amount = float(value)
        if is_cents or amount > 250_000:
            amount = amount / 100
        return str(amount)

    return str(value)


def _current_bid_from_api(listing: dict, detail: dict) -> str | None:
    bid_value = _first(listing.get("currentBid"), detail.get("currentBid"))
    bid_text = _format_bid_value(bid_value)
    if bid_text is not None:
        return bid_text

    cents_value = _first(listing.get("product_pricecents"), detail.get("product_pricecents"))
    return _format_bid_value(cents_value, is_cents=True)


def _iter_attribute_values(obj: Any):
    if isinstance(obj, list):
        for item in obj:
            yield from _iter_attribute_values(item)
        return

    if not isinstance(obj, dict):
        return

    label = _first(
        obj.get("label"),
        obj.get("name"),
        obj.get("displayName"),
        obj.get("attributeName"),
        obj.get("assetAttributeName"),
    )
    value = _first(
        obj.get("value"),
        obj.get("displayValue"),
        obj.get("attributeValue"),
        obj.get("assetAttributeValue"),
    )
    if label is not None:
        yield _clean_api_text(label), _clean_api_text(value)

    for key in (
        "attributes",
        "assetAttributes",
        "attributeValues",
        "values",
        "items",
        "children",
        "assetAttributeGroupValues",
    ):
        if key in obj:
            yield from _iter_attribute_values(obj.get(key))


def _normalized_label(label: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(label or "").lower()).strip()


def _parse_mileage_number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        if value < 0:
            return None
        return int(float(value))

    match = MILEAGE_NUMBER_RE.search(str(value).strip())
    if not match:
        return None

    try:
        return int(float(match.group(1).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _parse_mileage_from_asset_long_desc(text: Any) -> int | None:
    clean_text = _clean_api_text(text)
    if not clean_text:
        return None

    for pattern in MILEAGE_DESC_PATTERNS:
        match = pattern.search(clean_text)
        if match:
            return _parse_mileage_number(match.group(1))

    return None


def _extract_mileage(listing: dict, detail: dict, attributes: list[tuple[str, str]]) -> tuple[int | None, str]:
    mileage = _parse_mileage_number(_first(detail.get("meterCount"), listing.get("meterCount")))

    if mileage is None:
        for label, value in attributes:
            if _normalized_label(label) in ("odometer", "odometer reading", "odometer miles"):
                mileage = _parse_mileage_number(value)
                if mileage is not None:
                    break

    if mileage is None:
        mileage = _parse_mileage_from_asset_long_desc(detail.get("assetLongDesc"))

    mileage_display = str(mileage) if mileage is not None else "Not found"
    return mileage, mileage_display


def _specs_from_api(listing: dict, detail: dict, attributes: list[tuple[str, str]]) -> tuple[list[str], str | None, str | None]:
    specs_text_parts = []

    def add_spec(label: str, value: Any):
        clean_value = _clean_api_text(value)
        if clean_value:
            specs_text_parts.append(f"{label}: {clean_value}")

    make_value = _clean_api_text(_first(detail.get("makebrand"), listing.get("makebrand"))) or None
    model_value = _clean_api_text(_first(detail.get("model"), listing.get("model"))) or None

    add_spec("Year", _first(detail.get("modelYear"), listing.get("modelYear")))
    add_spec("Make", make_value)
    add_spec("Model", model_value)
    add_spec("VIN", detail.get("vinserial"))
    add_spec("Category", _first(detail.get("catDesc"), listing.get("categoryDescription")))
    add_spec("Parent Category", detail.get("parentCatDesc"))

    for label, value in attributes:
        if not label or not value:
            continue
        add_spec(label, value)
        label_key = _normalized_label(label)
        if label_key in ("manufacturer", "make") and not make_value:
            make_value = value
        elif label_key == "model" and not model_value:
            model_value = value

    return specs_text_parts, make_value, model_value


def _process_listing(listing: dict, detail: dict, href: str, minutes_left: float | None) -> bool:
    title = _clean_api_text(
        _first(
            detail.get("assetShortDesc"),
            detail.get("assetShortDescription"),
            listing.get("assetShortDescription"),
            listing.get("shortDescription"),
        )
    ) or "Untitled"
    print("Title:", title)

    if "item not available" in title.lower():
        print("Unavailable GovDeals page. Skipping listing.")
        print(f"Skipped URL: {href}")
        return False

    current_bid = _current_bid_from_api(listing, detail)
    print("Current bid (raw):", current_bid if current_bid is not None else "None")

    location = _location_from_api(listing, detail)
    print("Location:", location)
    location_valid = location_matches_alert_state(location)

    attributes = list(_iter_attribute_values(detail.get("assetAttributeGroups") or []))
    specs_text_parts, specs_make_value, specs_model_value = _specs_from_api(listing, detail, attributes)
    specs_table_found = bool(specs_make_value or specs_model_value)
    miles_value, mileage_display = _extract_mileage(listing, detail, attributes)

    if specs_text_parts:
        print("\nDescription specs:")
        for spec in specs_text_parts:
            print(spec)
    else:
        print("\nDescription specs: none found")

    short_desc = _clean_api_text(
        _first(listing.get("categoryDescription"), detail.get("catDesc"), detail.get("parentCatDesc"))
    )
    print("\nShort description:\n", short_desc)

    long_desc = _clean_api_text(detail.get("assetLongDesc"))
    if long_desc:
        print("\nLong Description:\n", long_desc)
    else:
        print("\nLong Description: None found")

    print("Countdown:", f"{minutes_left:.1f} minutes" if minutes_left is not None else "Not found")
    print("Closes at:", listing.get("assetAuctionEndDateUtc") or "Not found")

    if minutes_left is not None:
        if minutes_left <= CLOSE_SOON_MINUTES:
            print(f"Less than {CLOSE_SOON_MINUTES} minutes left!")
        else:
            print(f"{minutes_left:.1f} minutes remaining.")
    else:
        print("No close time found; cannot compute minutes remaining.")

    # -----Target truck/mileage checks and Twilio alert. Build one big text blob: title + short + long + specs.
    search_blob = " ".join([
        title or "",
        short_desc or "",
        long_desc or "",
        " ".join(specs_text_parts),
    ])

    allow_make_model_fallback = not specs_table_found
    gas_eval = evaluate_gas_fast_flip(
        search_blob,
        structured_make=specs_make_value,
        structured_model=specs_model_value,
        allow_make_model_fallback=allow_make_model_fallback,
        vehicle_context_text=title,
    )
    diesel_eval = evaluate_diesel_truck_filter(
        search_blob,
        structured_make=specs_make_value,
        structured_model=specs_model_value,
        allow_make_model_fallback=allow_make_model_fallback,
        vehicle_context_text=title,
    )
    gas_match = gas_eval["gas_match"]
    diesel_match = diesel_eval["diesel_match"]
    target_match = gas_match or diesel_match
    diesel_priority_level = diesel_eval["diesel_priority_level"] if diesel_match else None
    specialty_keywords_matched = diesel_eval["specialty_keywords_matched"]
    hard_exclude_keywords_matched = find_hard_exclude_keywords(search_blob)
    soft_warning_keywords_matched = find_soft_warning_keywords(search_blob)
    hard_exclude_hit = bool(hard_exclude_keywords_matched)

    # Missing miles fail open. Gas and diesel lanes keep their own mileage caps.
    gas_mileage_ok = miles_value is None or miles_value < MAX_GAS_MILES
    diesel_mileage_ok = miles_value is None or miles_value <= MAX_DIESEL_MILES
    mileage_ok = (
        miles_value is None or
        (gas_match and gas_mileage_ok) or
        (diesel_match and diesel_mileage_ok)
    )

    close_soon_flag = (
        minutes_left is not None and
        0 <= minutes_left <= CLOSE_SOON_MINUTES
    )

    numeric_bid = parse_bid_amount(current_bid)
    bid_under_limit = (
        numeric_bid is not None and
        numeric_bid < MAX_GAS_BID
    )

    should_alert = (
        location_valid is True and
        bid_under_limit is True and
        mileage_ok is True and
        close_soon_flag is True and
        target_match is True and
        not hard_exclude_hit
    )

    if gas_match:
        target_label = "GAS FAST FLIP"
        matched_lane = gas_eval["matched_lane"]
        debug_eval = gas_eval
    elif diesel_match:
        target_label = "DIESEL TARGET"
        matched_lane = diesel_eval["matched_lane"]
        debug_eval = diesel_eval
    else:
        target_label = "NO TARGET"
        matched_lane = None
        debug_eval = gas_eval

    alert_message = None
    if should_alert:
        miles_text = miles_value if miles_value is not None else mileage_display
        bid_text = numeric_bid if numeric_bid is not None else "Not found"
        year_text = debug_eval["year_value"] if debug_eval["year_value"] is not None else "Not found"
        make_text = debug_eval["make_value"] if debug_eval["make_value"] else "Not found"
        model_text = clean_model_display(debug_eval["model_value"]) or "Not found"
        engine_text = debug_eval["engine_value"] or debug_eval["engine_text"] or "Not found"
        title_restriction = "Not found"
        for spec in specs_text_parts:
            label, _, value = spec.partition(":")
            label_lower = label.lower()
            if "title" in label_lower and ("restriction" in label_lower or "status" in label_lower):
                title_restriction = value.strip() or "Not found"
                break

        diesel_priority_text = diesel_priority_level if diesel_priority_level else "None"
        specialty_text = ", ".join(specialty_keywords_matched) if specialty_keywords_matched else "None"
        hard_exclude_text = ", ".join(hard_exclude_keywords_matched) if hard_exclude_keywords_matched else "None"
        soft_warning_text = ", ".join(soft_warning_keywords_matched) if soft_warning_keywords_matched else "None"

        # SMS body stays compact: no full descriptions or raw specs table.
        alert_lines = [
            f"ALERT TYPE: {target_label}",
            f"Title: {title}",
            f"Location: {location if location else 'Not found'}",
            f"Bid: {bid_text}",
            f"Odometer/Miles: {miles_text}",
            f"Year: {year_text}",
            f"Make: {make_text}",
            f"Model: {model_text}",
            f"Engine: {engine_text}",
            f"Title Restriction: {title_restriction}",
            f"Gas match boolean: {gas_match}",
            f"Diesel match boolean: {diesel_match}",
            f"Diesel priority level: {diesel_priority_text}",
            f"Specialty keywords matched: {specialty_text}",
            f"Hard exclude keywords matched: {hard_exclude_text}",
            f"Soft warning keywords matched: {soft_warning_text}",
            f"Link: {href}",
        ]
        alert_message = "\n".join(alert_lines)

    debug_lane_results = debug_eval.get("all_lane_results", [])
    debug_selected_result = None
    if matched_lane:
        debug_selected_result = next(
            (result for result in debug_lane_results if result["rule"].lane == matched_lane),
            None,
        )
    if debug_selected_result is None and debug_lane_results:
        debug_selected_result = max(debug_lane_results, key=lambda result: result["score"])

    debug_rule = debug_selected_result["rule"] if debug_selected_result else None
    allowed_years = f"{debug_rule.year_min}-{debug_rule.year_max}" if debug_rule else "Unknown"
    debug_year = debug_eval["year_value"] if debug_eval["year_value"] is not None else "Not found"
    debug_make = debug_eval["make_value"] if debug_eval["make_value"] else "Not found"
    debug_model = clean_model_display(debug_eval["model_value"]) or "Not found"
    debug_engine = debug_eval["engine_value"] or debug_eval["engine_text"] or "Not found"
    debug_location = location if location else "Not found"
    debug_bid = numeric_bid if numeric_bid is not None else current_bid
    debug_miles = miles_value if miles_value is not None else mileage_display
    debug_minutes = f"{minutes_left:.1f}" if minutes_left is not None else "Not found"
    gas_matched_lane = gas_eval["matched_lane"] if gas_eval["matched_lane"] else "None"
    diesel_matched_lane = diesel_eval["matched_lane"] if diesel_eval["matched_lane"] else "None"

    log_decision({
        "source": "GovDeals",
        "url": href,
        "title": title,
        "location": location,
        "current_bid": numeric_bid,
        "minutes_left": minutes_left,
        "year": debug_eval["year_value"],
        "make": debug_eval["make_value"],
        "model": clean_model_display(debug_eval["model_value"]),
        "engine": debug_eval["engine_value"] or debug_eval["engine_text"],
        "mileage": miles_value,
        "gas_match": gas_match,
        "diesel_match": diesel_match,
        "diesel_priority_level": diesel_priority_level,
        "specialty_keywords_matched": specialty_keywords_matched,
        "hard_exclude_hit": hard_exclude_hit,
        "hard_exclude_keywords_matched": hard_exclude_keywords_matched,
        "soft_warning_keywords_matched": soft_warning_keywords_matched,
        "location_valid": location_valid,
        "bid_under_limit": bid_under_limit,
        "mileage_ok": mileage_ok,
        "close_soon_flag": close_soon_flag,
        "should_alert": should_alert,
        "year_ok": debug_eval["year_ok"],
        "make_ok": debug_eval["make_ok"],
        "model_ok": debug_eval["model_ok"],
        "engine_ok": debug_eval["engine_ok"],
    })

    print("\n[ALERT DEBUG]")
    print(f"  location_valid: {location_valid} | location={debug_location}")
    print(f"  bid_under_limit: {bid_under_limit} | bid={debug_bid if debug_bid is not None else 'Not found'} | cap={MAX_GAS_BID}")
    print(f"  mileage_ok: {mileage_ok} | miles={debug_miles} | cap={MAX_GAS_MILES} gas / {MAX_DIESEL_MILES} diesel")
    print(f"  year_ok: {debug_eval['year_ok']} | year={debug_year} | allowed={allowed_years}")
    print(f"  make_ok: {debug_eval['make_ok']} | make={debug_make}")
    print(f"  model_ok: {debug_eval['model_ok']} | model={debug_model}")
    print(f"  engine_ok: {debug_eval['engine_ok']} | engine={debug_engine}")
    print(f"  gas_match: {gas_match} | matched_lane={gas_matched_lane}")
    print(f"  diesel_match: {diesel_match} | matched_lane={diesel_matched_lane}")
    print(f"  hard_exclude_hit: {hard_exclude_hit} | matched={hard_exclude_keywords_matched}")
    print(f"  soft_warning_keywords_matched: {soft_warning_keywords_matched}")
    print(f"  close_soon_flag: {close_soon_flag} | minutes_left={debug_minutes} | cap={CLOSE_SOON_MINUTES}")
    print(f"  should_alert: {should_alert}")

    if should_alert:
        send_alert(alert_message)

    print("RESULT: ALERT SENT" if should_alert else "RESULT: NO ALERT SENT")
    return should_alert


# Run one full scan of GovDeals and send Twilio alerts. Returns: number of alerts sent in this pass.
def scan_govdeals_once() -> int:
    alerts_sent = 0

    try:
        listings = _search_govdeals()
    except Exception as exc:
        print("GovDeals API search error. Returning 0 alerts for this scan.")
        print(f"Error: {exc}")
        return 0

    if not listings:
        print("GovDeals API returned no results. Returning 0 alerts for this scan.")
        return 0

    print(f"GovDeals API listing count: {len(listings)}")

    for index, listing in enumerate(listings, start=1):
        asset_id = _first(listing.get("assetId"), listing.get("id"))
        account_id = _first(
            listing.get("accountId"),
            listing.get("sellerAccountId"),
            listing.get("clientAccountId"),
        )

        if not asset_id or not account_id:
            print("Skipping GovDeals listing because assetId/accountId is missing.")
            print(f"Raw listing title: {listing.get('assetShortDescription') or 'Not found'}")
            continue

        href = _build_listing_url(asset_id, account_id)
        minutes_left = _minutes_left_from_listing(listing)

        if minutes_left is not None and minutes_left > CLOSE_SOON_MINUTES:
            print(
                "Stopping scan because listing is beyond "
                f"{CLOSE_SOON_MINUTES}-minute window: "
                f"{listing.get('assetShortDescription') or 'Untitled'} "
                f"({minutes_left:.1f} minutes)"
            )
            break

        try:
            print("\n====================")
            print(f"Visiting GovDeals API listing {index}: {href}")

            detail = _fetch_detail(asset_id, account_id)
            if _process_listing(listing, detail, href, minutes_left):
                alerts_sent += 1

        except Exception as exc:
            print("Error on GovDeals API listing, skipping...")
            print(f"URL: {href}")
            print(f"Error: {exc}")
            continue

    return alerts_sent


if __name__ == "__main__":
    # Manual/local run:
    total = scan_govdeals_once()
    print(f"Scan complete. Alerts sent: {total}")
