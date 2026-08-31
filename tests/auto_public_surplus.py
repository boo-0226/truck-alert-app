# file: tests/auto_public_surplus.py

import html
import os
import platform
import random
import re
import shutil
import sys
import tempfile
import time
from typing import Any, Optional
from urllib.parse import parse_qs, urljoin, urlparse

# Make sure .../src is on sys.path so "core" becomes importable.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

for import_path in (PROJECT_ROOT, SRC_DIR):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

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
)
from core.decision_log import log_decision
from core.autoTwilio_Alerts import send_alert as send_twilio_alert
from src.core.consumer_gas_liquid import STRATEGY as CONSUMER_GAS_LIQUID
from src.core.discovery import GAS_WORK_LOCAL
from src.core.strategies import classify_listing_strategies, strategy_result_to_row_fields


BASE_URL = "https://www.publicsurplus.com/sms/browse/cataucs?catid=4"
PUBLIC_SURPLUS_ROOT = "https://www.publicsurplus.com"
DETAIL_TITLE_SELECTOR = ".nav-sub-head .text-wrap"
DETAIL_TIME_LEFT_SELECTOR = "[id^='timeLeftValue']"

RUN_ONCE = os.getenv("PUBLIC_SURPLUS_RUN_ONCE", "0").strip().lower() in ("1", "true", "yes", "on")
MAX_TEST_LISTINGS = int(os.getenv("PUBLIC_SURPLUS_MAX_TEST_LISTINGS", "10"))
LOOP_SLEEP_SECONDS = 300
LISTING_REQUEST_SLEEP_MIN_SECONDS = 2.0
LISTING_REQUEST_SLEEP_MAX_SECONDS = 5.0


STATE_CODE_TO_NAME = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}


STRUCTURED_FIELD_KEYS = (
    "year",
    "make",
    "model",
    "mileage",
    "engine",
    "condition",
    "running_condition",
    "transmission",
    "vin",
)


STRUCTURED_FIELD_ALIASES = {
    "year": ("year", "yr"),
    "make": ("make",),
    "model": ("model",),
    "mileage": ("mileage", "miles", "odometer", "odometer reading"),
    "engine": ("engine", "motor"),
    "condition": ("condition",),
    "running_condition": ("running condition", "run condition", "running", "runs"),
    "transmission": ("transmission",),
    "vin": ("vin", "vin number", "vehicle identification number"),
    "body_style": ("body style", "bodystyle", "body type", "vehicle body"),
    "location": ("location", "item location", "state"),
    "title_status": ("title status", "title restriction", "title", "ownership document"),
}


def create_driver():
    system = platform.system().lower()
    options = Options()
    options.binary_location = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    chrome_args = [
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--remote-debugging-port=0",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--metrics-recording-only",
        "--no-first-run",
        "--disable-default-apps",
    ]
    for arg in chrome_args:
        options.add_argument(arg)

    profile_dir = tempfile.mkdtemp(prefix="truck_sniper_chrome_")
    options.add_argument(f"--user-data-dir={profile_dir}")

    timeout = 20 if system == "windows" else 30

    try:
        driver = webdriver.Chrome(options=options)
    except Exception:
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise

    driver._truck_sniper_profile_dir = profile_dir
    wait = WebDriverWait(driver, timeout)
    return driver, wait


def _quit_driver(driver):
    profile_dir = getattr(driver, "_truck_sniper_profile_dir", None)
    try:
        driver.quit()
    finally:
        if profile_dir:
            shutil.rmtree(profile_dir, ignore_errors=True)


def send_alert(message: str):
    send_twilio_alert(message)


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _element_text(element, separator: str = " ") -> str:
    if not element:
        return ""
    return _clean_text(element.get_text(separator, strip=True))


def _element_raw_lines(element) -> list[str]:
    if not element:
        return []
    raw_text = html.unescape(element.get_text("\n", strip=True))
    return [_clean_text(line) for line in raw_text.splitlines() if _clean_text(line)]


def _auction_id_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parse_qs(parsed.query).get("auc") or [""])[0]
    except Exception:
        return ""


def _find_listing_container(link):
    best = link.parent
    current = link.parent

    for _ in range(8):
        if current is None or not getattr(current, "name", None):
            break

        classes = " ".join(current.get("class", [])).lower()
        looks_like_card = (
            current.name in ("article", "li", "tr")
            or any(
                token in classes
                for token in ("auction-item", "auction", "card", "result", "listing", "lot", "item")
            )
        )

        link_count = 0
        try:
            link_count = len(current.select('a[href*="/sms/auction/view?auc="]'))
        except Exception:
            pass

        if looks_like_card and link_count <= 2:
            return current
        if link_count <= 1:
            best = current

        current = current.parent

    return best or link.parent or link


def _extract_region_text(card) -> str:
    if not card:
        return ""

    region = _element_text(card.select_one(".auction-item-state"))
    if region:
        return region

    lines = _element_raw_lines(card)
    for line in lines:
        upper = line.upper()
        if upper in STATE_CODE_TO_NAME:
            return upper

    text = " ".join(lines).upper()
    match = re.search(r"\b([A-Z]{2})\b", text)
    if match and match.group(1) in STATE_CODE_TO_NAME:
        return match.group(1)

    return ""


def parse_time_left_minutes(time_left_text: str | None) -> Optional[float]:
    text = _clean_text(time_left_text).lower()
    if not text:
        return None

    if any(word in text for word in ("closed", "ended", "expired")):
        return 0.0

    if "less than" in text and "minute" in text:
        return 0.0

    text = re.sub(r"time\s*left\s*:?", " ", text, flags=re.IGNORECASE)
    text = _clean_text(text)

    colon_match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)
    if colon_match:
        first = int(colon_match.group(1))
        second = int(colon_match.group(2))
        third = colon_match.group(3)
        if third is not None:
            return first * 60 + second + int(third) / 60
        return first + second / 60

    total_minutes = 0.0
    unit_patterns = (
        (r"(\d+(?:\.\d+)?)\s*(?:days?|d)\b", 1440.0),
        (r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr|h)\b", 60.0),
        (r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|min|m)\b", 1.0),
        (r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|sec|s)\b", 1.0 / 60.0),
    )

    for pattern, multiplier in unit_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            total_minutes += float(match.group(1)) * multiplier

    if total_minutes > 0:
        return total_minutes

    number_match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if number_match:
        return float(number_match.group(1))

    return None


def parse_listing_cards(driver) -> list[dict]:
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/sms/auction/view?auc="]'))
        )
    except TimeoutException:
        print("Public Surplus listing links did not appear before timeout; parsing current HTML anyway.")

    soup = BeautifulSoup(driver.page_source, "html.parser")
    links = soup.select('a[href*="/sms/auction/view?auc="]')
    cards = []
    seen = set()

    for link in links:
        try:
            href = link.get("href") or ""
            listing_url = urljoin(PUBLIC_SURPLUS_ROOT, href)
            auction_id = _auction_id_from_url(listing_url) or listing_url
            if auction_id in seen:
                continue
            seen.add(auction_id)

            card = _find_listing_container(link)

            cards.append(
                {
                    "auction_id": auction_id,
                    "listing_url": listing_url,
                    "region_text": _extract_region_text(card),
                }
            )
        except Exception as exc:
            print(f"Error parsing Public Surplus listing card, skipping: {exc}")

    return cards


def _canonical_field(label: str) -> Optional[str]:
    clean_label = re.sub(r"[^a-z0-9 ]+", " ", (label or "").lower())
    clean_label = re.sub(r"\s+", " ", clean_label).strip()
    collapsed = clean_label.replace(" ", "")

    for key, aliases in STRUCTURED_FIELD_ALIASES.items():
        for alias in aliases:
            clean_alias = alias.lower()
            if clean_label == clean_alias or collapsed == clean_alias.replace(" ", ""):
                return key

    return None


def _store_structured_field(data: dict, label: str, value: str):
    key = _canonical_field(label)
    clean_value = _clean_text(value).strip(":")
    if key and clean_value and data.get(key) in (None, ""):
        data[key] = clean_value


def _normalize_structured_label(label: str) -> str:
    return _clean_text(label).rstrip(":").lower()


def _span_value_after_auctitle(label_span) -> str:
    value_span = label_span.find_next_sibling("span")
    if not value_span:
        return ""
    if "auctitle" in value_span.get("class", []):
        return ""
    return _element_text(value_span)


def extract_structured_data(soup: BeautifulSoup) -> dict:
    data = {key: None for key in STRUCTURED_FIELD_KEYS}

    for label_span in soup.select("span.auctitle"):
        label = _normalize_structured_label(_element_text(label_span))
        value = _span_value_after_auctitle(label_span)
        _store_structured_field(data, label, value)

    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue

        label = _element_text(cells[0]).rstrip(":")
        value = _element_text(cells[1])
        _store_structured_field(data, label, value)

    for tag in soup.find_all(["dt", "strong", "b"]):
        label = _element_text(tag).rstrip(":")
        if not _canonical_field(label):
            continue

        value = ""
        if tag.name == "dt":
            next_dd = tag.find_next_sibling("dd")
            value = _element_text(next_dd)
        else:
            value = _element_text(tag.parent).replace(_element_text(tag), "", 1)

        _store_structured_field(data, label, value)

    if data.get("mileage"):
        data["mileage_value"] = parse_mileage(data["mileage"])

    return data


def _candidate_description_texts(soup: BeautifulSoup) -> list[str]:
    candidates = []
    seen = set()

    def add_candidate(text: str):
        clean = _clean_text(text)
        if len(clean) < 20 or clean in seen:
            return
        seen.add(clean)
        candidates.append(clean)

    for tag in soup.find_all(["div", "section", "td", "p", "span"]):
        attrs = " ".join(
            [
                str(tag.get("id") or ""),
                " ".join(tag.get("class", [])),
                str(tag.get("name") or ""),
            ]
        ).lower()
        if any(token in attrs for token in ("description", "desc", "auctiondetail", "auction-detail", "additional")):
            add_candidate(tag.get_text(" ", strip=True))

    body = soup.body or soup
    add_candidate(body.get_text(" ", strip=True))
    return candidates


def _extract_direct_selector_text(driver, soup: BeautifulSoup, selector: str, timeout: int = 5) -> str:
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        text = _clean_text(element.text or element.get_attribute("textContent"))
        if text:
            return text
    except TimeoutException:
        pass
    except Exception:
        pass

    return _element_text(soup.select_one(selector))


def _parse_current_bid_text(text: str) -> Optional[float]:
    clean_text = _clean_text(text).replace("$", "").replace(",", "")
    if not clean_text:
        return None

    try:
        return float(clean_text)
    except ValueError:
        return None


def _extract_current_bid(driver) -> Optional[float]:
    try:
        bid_elem = driver.find_element(By.CSS_SELECTOR, "strong[id^='val_']")
    except Exception:
        try:
            bid_elem = driver.find_element(By.XPATH, "//strong[starts-with(@id, 'val_')]")
        except Exception:
            return None

    bid_text = bid_elem.text or bid_elem.get_attribute("textContent")
    return _parse_current_bid_text(bid_text)


def _find_first_pattern(text: str, patterns: tuple[tuple[str, str], ...]) -> Optional[str]:
    for value, pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return value
    return None


def parse_mileage(text: str | None) -> Optional[int]:
    clean_text = _clean_text(text)
    if not clean_text:
        return None

    patterns = (
        r"\blast\s+known\s+mileage\s*[-:#]?\s*([\d,]+)",
        r"\blast\s+reported\s+odometer\s+(?:was\s+)?([\d,]+)",
        r"\bodometer(?:\s+(?:reading|miles|mi))?\s*[-:#]?\s*([\d,]+)",
        r"\bmileage\s*[-:#]?\s*([\d,]+)",
        r"\b([\d,]+)\s+(?:actual\s+)?(?:miles|mi)\b",
    )

    for pattern in patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if not match:
            continue

        try:
            miles = int(match.group(1).replace(",", ""))
        except ValueError:
            continue

        if 0 <= miles <= 1_000_000:
            return miles

    loose_number = re.fullmatch(r"\d[\d,]*(?:\.\d+)?", clean_text)
    if loose_number:
        try:
            return int(float(clean_text.replace(",", "")))
        except ValueError:
            return None

    return None


def extract_fallback_text_data(text: str) -> dict:
    clean_text = _clean_text(text)

    year_match = re.search(r"\b((?:19|20)\d{2})\b", clean_text)

    make = _find_first_pattern(
        clean_text,
        (
            ("Ford", r"\bford\b"),
            ("Chevrolet", r"\b(?:chevrolet|chevy)\b"),
            ("GMC", r"\bgmc\b"),
            ("Ram", r"\b(?:ram|dodge\s+ram|dodge)\b"),
            ("International", r"\binternational\b"),
            ("Freightliner", r"\bfreightliner\b"),
        ),
    )

    engine = _find_first_pattern(
        clean_text,
        (
            ("6.7 Power Stroke", r"\b6\.7\s*(?:l|liter|litre)?\b.{0,50}\bpower\s*stroke\b"),
            ("Power Stroke", r"\bpower\s*stroke\b|\bpowerstroke\b"),
            ("6.7 Cummins", r"\b6\.7\s*(?:l|liter|litre)?\b.{0,50}\bcummins\b"),
            ("Cummins", r"\bcummins\b"),
            ("6.6 Duramax", r"\b6\.6\s*(?:l|liter|litre)?\b.{0,50}\bduramax\b"),
            ("Duramax", r"\bduramax\b"),
            ("Diesel", r"\bdiesel\b"),
            ("6.7", r"\b6\.7\s*(?:l|liter|litre)?\b"),
            ("6.6", r"\b6\.6\s*(?:l|liter|litre)?\b"),
        ),
    )

    run_status = []
    negative_run_status = re.search(
        r"\b(?:does\s+not|doesn't|will\s+not|won't|no)\s+(?:run|start|drive)",
        clean_text,
        re.IGNORECASE,
    )
    if not negative_run_status:
        for label, pattern in (
            ("runs", r"\bruns\b|\bruns\s+and\s+drives\b"),
            ("starts", r"\bstarts\b"),
            ("drives", r"\bdrives\b"),
        ):
            if re.search(pattern, clean_text, re.IGNORECASE):
                run_status.append(label)

    return {
        "year": int(year_match.group(1)) if year_match else None,
        "make": make,
        "engine": engine,
        "mileage_value": parse_mileage(clean_text),
        "run_status": run_status,
        "hard_exclude_keywords_matched": find_hard_exclude_keywords(clean_text),
        "soft_warning_keywords_matched": find_soft_warning_keywords(clean_text),
    }


def _structured_text(structured: dict) -> str:
    parts = []
    for key, value in structured.items():
        if key.endswith("_value") or value in (None, ""):
            continue
        label = key.replace("_", " ").title()
        parts.append(f"{label}: {value}")
    return " ".join(parts)


def parse_detail_page(driver, listing: Optional[dict] = None) -> dict:
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    except TimeoutException:
        print("Public Surplus detail body did not appear before timeout; parsing current HTML anyway.")

    soup = BeautifulSoup(driver.page_source, "html.parser")
    listing = listing or {}

    structured = extract_structured_data(soup)
    description_text = " ".join(_candidate_description_texts(soup))
    needs_fallback = (
        any(structured.get(key) in (None, "") for key in ("year", "make", "engine"))
        or structured.get("mileage_value") is None
    )
    fallback = extract_fallback_text_data(description_text) if needs_fallback else {
        "run_status": [],
        "hard_exclude_keywords_matched": [],
        "soft_warning_keywords_matched": [],
    }

    title = _extract_direct_selector_text(driver, soup, DETAIL_TITLE_SELECTOR, timeout=10)
    time_left_text = _extract_direct_selector_text(driver, soup, DETAIL_TIME_LEFT_SELECTOR, timeout=5)
    current_bid = _extract_current_bid(driver)

    mileage_value = structured.get("mileage_value")
    if mileage_value is None:
        mileage_value = fallback.get("mileage_value")

    return {
        "title": title or "Untitled Public Surplus listing",
        "time_left_text": time_left_text,
        "minutes_left": parse_time_left_minutes(time_left_text),
        "current_bid": current_bid,
        "year": structured.get("year") or fallback.get("year"),
        "make": structured.get("make") or fallback.get("make"),
        "model": clean_model_display(structured.get("model")),
        "engine": structured.get("engine") or fallback.get("engine"),
        "condition": structured.get("condition"),
        "running_condition": structured.get("running_condition"),
        "transmission": structured.get("transmission"),
        "vin": structured.get("vin"),
        "body_style": structured.get("body_style"),
        "mileage_value": mileage_value,
        "location": structured.get("location"),
        "title_status": structured.get("title_status"),
        "run_status": fallback.get("run_status", []),
        "description_text": description_text,
        "structured_text": _structured_text(structured),
        "structured_data": structured,
        "fallback_data": fallback,
    }


def _state_name_from_region(region_text: str) -> str:
    clean_region = _clean_text(region_text)
    upper_region = clean_region.upper()

    if upper_region in STATE_CODE_TO_NAME:
        return STATE_CODE_TO_NAME[upper_region]

    for code, state in STATE_CODE_TO_NAME.items():
        if re.search(rf"\b{re.escape(code)}\b", upper_region):
            return state
        if re.search(rf"\b{re.escape(state)}\b", clean_region, re.IGNORECASE):
            return state

    return ""


def _location_for_filter(listing: dict, detail: dict) -> str:
    region_text = listing.get("region_text") or ""
    state_name = _state_name_from_region(region_text)
    return " ".join(
        part for part in (detail.get("location"), region_text, state_name) if part
    )


def _display_minutes(minutes_left: Optional[float]) -> str:
    if minutes_left is None:
        return "Not found"
    if abs(minutes_left - round(minutes_left)) < 0.01:
        return str(int(round(minutes_left)))
    return f"{minutes_left:.1f}"


def _first_display(*values) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return "Not found"


def _display_current_bid(current_bid: Optional[float]) -> str:
    if current_bid is None:
        return "Not found"
    if float(current_bid).is_integer():
        return str(int(current_bid))
    return str(current_bid)


def _selected_debug_eval(gas_eval: dict, diesel_eval: dict) -> dict:
    if gas_eval["gas_match"]:
        return gas_eval
    if diesel_eval["diesel_match"]:
        return diesel_eval
    return gas_eval


def _legacy_gas_work_existing(gas_eval: dict) -> dict:
    lane = (gas_eval.get("matched_lane") or "").lower()
    is_hd_gas_work = any(token in lane for token in ("f-250", "f-350", "2500", "3500"))
    if gas_eval.get("gas_match") and is_hd_gas_work:
        return {"target": True, "label": gas_eval.get("matched_lane") or "GAS WORK LOCAL"}
    return {}


def _strategy_listing_from_public_surplus(listing: dict, detail: dict) -> dict:
    miles_value = detail.get("mileage_value")
    return {
        "title": detail.get("title"),
        "desc": detail.get("description_text"),
        "structured_text": detail.get("structured_text"),
        "category": "Public Surplus vehicle auction",
        "city": detail.get("location"),
        "state": listing.get("region_text"),
        "url": listing.get("listing_url"),
        "current_bid": detail.get("current_bid"),
        "year": detail.get("year"),
        "make": detail.get("make"),
        "model": detail.get("model"),
        "engine": detail.get("engine"),
        "condition": detail.get("condition"),
        "title_status": detail.get("title_status"),
        "body_style": detail.get("body_style"),
        "vin": detail.get("vin"),
        "fuel": detail.get("fuel"),
        "mileage": miles_value,
        "mileage_value": miles_value,
        "mileage_display": f"{miles_value:,}" if isinstance(miles_value, int) else "",
    }


def evaluate_truck(listing: dict, detail: dict) -> dict:
    search_blob = " ".join(
        [
            detail.get("title") or "",
            detail.get("structured_text") or "",
            detail.get("description_text") or "",
        ]
    )

    gas_eval = evaluate_gas_fast_flip(search_blob, vehicle_context_text=detail.get("title"))
    diesel_eval = evaluate_diesel_truck_filter(search_blob, vehicle_context_text=detail.get("title"))

    diesel_match = diesel_eval["diesel_match"]
    strategy_result = classify_listing_strategies(
        _strategy_listing_from_public_surplus(listing, detail),
        diesel_result={
            "strategy": "DIESEL_COMMERCIAL",
            "classification": "ALERT" if diesel_match else "REJECT",
            "target": diesel_match,
            "blocked": not diesel_match,
            "decision_reasons": ["diesel_commercial_existing_match"] if diesel_match else ["diesel_commercial_existing_no_match"],
        },
        gas_work_existing=_legacy_gas_work_existing(gas_eval),
    )
    strategy_fields = strategy_result_to_row_fields(strategy_result)

    gas_work_match = (
        strategy_result.get("target_strategy") == GAS_WORK_LOCAL
        and strategy_result.get("target") is True
    )
    consumer_gas_match = (
        strategy_result.get("target_strategy") == CONSUMER_GAS_LIQUID
        and strategy_result.get("classification") == "ALERT"
    )
    gas_match = gas_work_match or consumer_gas_match
    target_match = gas_match or diesel_match
    debug_eval = _selected_debug_eval(gas_eval, diesel_eval)

    consumer_result = strategy_result.get("consumer_gas") or {}
    miles_value = consumer_result.get("mileage")
    if miles_value is None:
        miles_value = detail.get("mileage_value")
    gas_mileage_ok = miles_value is None or miles_value < MAX_GAS_MILES
    diesel_mileage_ok = miles_value is None or miles_value <= MAX_DIESEL_MILES
    mileage_ok = (
        miles_value is None
        or (gas_match and gas_mileage_ok)
        or (diesel_match and diesel_mileage_ok)
    )

    current_bid = detail.get("current_bid")
    bid_under_limit = current_bid is not None and current_bid < MAX_GAS_BID

    minutes_left = detail.get("minutes_left")

    close_soon_flag = (
        minutes_left is not None
        and 0 <= minutes_left <= CLOSE_SOON_MINUTES
    )

    location_filter_text = _location_for_filter(listing, detail)
    location_valid = location_matches_alert_state(location_filter_text)

    hard_exclude_keywords_matched = find_hard_exclude_keywords(search_blob)
    soft_warning_keywords_matched = find_soft_warning_keywords(search_blob)
    hard_exclude_hit = bool(hard_exclude_keywords_matched)

    should_alert = (
        location_valid is True
        and bid_under_limit is True
        and mileage_ok is True
        and close_soon_flag is True
        and target_match is True
        and not hard_exclude_hit
    )

    year_value = consumer_result.get("year") or debug_eval.get("year_value") or detail.get("year")
    make_value = consumer_result.get("make") or debug_eval.get("make_value") or detail.get("make")
    model_value = consumer_result.get("model") or detail.get("model")
    engine_value = (
        consumer_result.get("engine")
        or debug_eval.get("engine_value")
        or debug_eval.get("engine_text")
        or detail.get("engine")
    )

    alert_debug_lines = [
        "[ALERT DEBUG]",
        f"year: {_first_display(year_value)} | year_ok: {debug_eval['year_ok']}",
        f"make: {_first_display(make_value)} | make_ok: {debug_eval['make_ok']}",
        f"model: {_first_display(model_value)} | model_ok: {debug_eval['model_ok']}",
        f"engine: {_first_display(engine_value)} | engine_ok: {debug_eval['engine_ok']}",
        f"legacy_gas_match: {gas_eval['gas_match']}",
        f"gas_match: {gas_match}",
        f"diesel_match: {diesel_match}",
        f"target_strategy: {strategy_result.get('target_strategy')}",
        f"classification: {strategy_result.get('classification')}",
        f"consumer_gas_score: {strategy_fields.get('consumer_gas_score')}",
        f"decision_reasons: {strategy_result.get('decision_reasons')}",
        f"diesel_priority_level: {diesel_eval['diesel_priority_level'] if diesel_match else None}",
        f"specialty_keywords_matched: {diesel_eval['specialty_keywords_matched']}",
        f"hard_exclude_keywords_matched: {hard_exclude_keywords_matched}",
        f"hard_exclude_hit: {hard_exclude_hit}",
        f"soft_warning_keywords_matched: {soft_warning_keywords_matched}",
        f"location_valid: {location_valid}",
        f"current_bid: {current_bid}",
        f"bid_under_limit: {bid_under_limit}",
        f"mileage_ok: {mileage_ok}",
        f"minutes_left: {_display_minutes(minutes_left)}",
        f"close_soon_flag: {close_soon_flag}",
        f"should_alert: {should_alert}",
    ]

    if strategy_result.get("target_strategy") == CONSUMER_GAS_LIQUID:
        target_label = CONSUMER_GAS_LIQUID
    elif strategy_result.get("target_strategy") == GAS_WORK_LOCAL:
        target_label = "GAS WORK LOCAL"
    elif diesel_match:
        target_label = "DIESEL TARGET"
    else:
        target_label = "NO TARGET"

    return {
        "should_alert": should_alert,
        "target_label": target_label,
        "search_blob": search_blob,
        "gas_eval": gas_eval,
        "diesel_eval": diesel_eval,
        "debug_eval": debug_eval,
        "strategy_result": strategy_result,
        **strategy_fields,
        "gas_match": gas_match,
        "legacy_gas_match": gas_eval["gas_match"],
        "gas_work_match": gas_work_match,
        "consumer_gas_match": consumer_gas_match,
        "diesel_match": diesel_match,
        "diesel_priority_level": diesel_eval["diesel_priority_level"] if diesel_match else None,
        "specialty_keywords_matched": diesel_eval["specialty_keywords_matched"],
        "hard_exclude_keywords_matched": hard_exclude_keywords_matched,
        "hard_exclude_hit": hard_exclude_hit,
        "soft_warning_keywords_matched": soft_warning_keywords_matched,
        "location_valid": location_valid,
        "bid_under_limit": bid_under_limit,
        "mileage_ok": mileage_ok,
        "close_soon_flag": close_soon_flag,
        "minutes_left": minutes_left,
        "current_bid": current_bid,
        "miles_value": miles_value,
        "year_value": year_value,
        "make_value": make_value,
        "model_value": model_value,
        "engine_value": engine_value,
        "alert_debug_lines": alert_debug_lines,
    }


def _build_alert_message(listing: dict, detail: dict, evaluation: dict) -> str:
    location_display = detail.get("location") or listing.get("region_text") or "Not found"
    mileage_display = (
        str(evaluation["miles_value"])
        if evaluation["miles_value"] is not None
        else "Not found"
    )

    alert_lines = [
        "SOURCE: Public Surplus",
        f"ALERT TYPE: {evaluation['target_label']}",
        f"Title: {detail.get('title') or 'Not found'}",
        f"Current Bid: {_display_current_bid(evaluation['current_bid'])}",
        f"Location: {location_display}",
        f"Year: {_first_display(evaluation['year_value'])}",
        f"Make: {_first_display(evaluation['make_value'])}",
        f"Model: {_first_display(evaluation['model_value'])}",
        f"Engine: {_first_display(evaluation['engine_value'])}",
        f"Mileage: {mileage_display}",
        f"Diesel priority level: {evaluation['diesel_priority_level'] or 'None'}",
        f"Hard exclude keywords matched: {', '.join(evaluation['hard_exclude_keywords_matched']) if evaluation['hard_exclude_keywords_matched'] else 'None'}",
        f"Soft warning keywords matched: {', '.join(evaluation['soft_warning_keywords_matched']) if evaluation['soft_warning_keywords_matched'] else 'None'}",
        f"Time remaining: {_display_minutes(evaluation['minutes_left'])} minutes",
        f"URL: {listing.get('listing_url')}",
        "",
        *evaluation["alert_debug_lines"],
    ]
    if evaluation.get("next_action"):
        alert_lines.insert(2, f"Next action: {evaluation['next_action']}")

    return "\n".join(alert_lines)


def _print_alert_debug(evaluation: dict):
    print("\n".join(evaluation["alert_debug_lines"]))


def _log_public_surplus_decision(listing: dict, detail: dict, evaluation: dict):
    debug_eval = evaluation["debug_eval"]
    log_decision({
        "source": "Public Surplus",
        "url": listing.get("listing_url"),
        "title": detail.get("title"),
        "location": detail.get("location") or listing.get("region_text"),
        "current_bid": evaluation["current_bid"],
        "minutes_left": evaluation["minutes_left"],
        "year": evaluation["year_value"],
        "make": evaluation["make_value"],
        "model": clean_model_display(evaluation["model_value"]),
        "engine": evaluation["engine_value"],
        "mileage": evaluation["miles_value"],
        "gas_match": evaluation["gas_match"],
        "legacy_gas_match": evaluation.get("legacy_gas_match"),
        "diesel_match": evaluation["diesel_match"],
        "diesel_priority_level": evaluation["diesel_priority_level"],
        "specialty_keywords_matched": evaluation["specialty_keywords_matched"],
        "hard_exclude_hit": evaluation["hard_exclude_hit"],
        "hard_exclude_keywords_matched": evaluation["hard_exclude_keywords_matched"],
        "soft_warning_keywords_matched": evaluation["soft_warning_keywords_matched"],
        "location_valid": evaluation["location_valid"],
        "bid_under_limit": evaluation["bid_under_limit"],
        "mileage_ok": evaluation["mileage_ok"],
        "close_soon_flag": evaluation["close_soon_flag"],
        "should_alert": evaluation["should_alert"],
        "year_ok": debug_eval["year_ok"],
        "make_ok": debug_eval["make_ok"],
        "model_ok": debug_eval["model_ok"],
        "engine_ok": debug_eval["engine_ok"],
        "target_strategy": evaluation.get("target_strategy"),
        "strategies_considered": evaluation.get("strategies_considered"),
        "discovery_reasons": evaluation.get("discovery_reasons"),
        "decision_reasons": evaluation.get("decision_reasons"),
        "positive_signals": evaluation.get("positive_signals"),
        "negative_signals": evaluation.get("negative_signals"),
        "block_reasons": evaluation.get("block_reasons"),
        "score": evaluation.get("score"),
        "consumer_gas_score": evaluation.get("consumer_gas_score"),
        "consumer_gas_model_key": evaluation.get("consumer_gas_model_key"),
        "next_action": evaluation.get("next_action"),
        "model_year": evaluation.get("model_year"),
        "vehicle_age": evaluation.get("vehicle_age"),
        "parsed_make": evaluation.get("parsed_make"),
        "parsed_model": evaluation.get("parsed_model"),
        "parsed_year": evaluation.get("parsed_year"),
        "parsed_vehicle_age": evaluation.get("parsed_vehicle_age"),
        "parsed_mileage": evaluation.get("parsed_mileage"),
        "parsed_trim": evaluation.get("parsed_trim"),
        "parsed_cab": evaluation.get("parsed_cab"),
        "parsed_drivetrain": evaluation.get("parsed_drivetrain"),
        "parsed_engine": evaluation.get("parsed_engine"),
        "parsed_fuel": evaluation.get("parsed_fuel"),
        "vin": evaluation.get("vin"),
        "trim": evaluation.get("trim"),
        "cab": evaluation.get("cab"),
        "drivetrain": evaluation.get("drivetrain"),
        "fuel": evaluation.get("fuel"),
        "mileage_display": evaluation.get("mileage_display"),
    })


def _sleep_between_listing_requests(index: int):
    if index <= 1:
        return

    delay = random.uniform(
        LISTING_REQUEST_SLEEP_MIN_SECONDS,
        LISTING_REQUEST_SLEEP_MAX_SECONDS,
    )
    print(f"Pausing {delay:.1f}s before next Public Surplus listing request...")
    time.sleep(delay)


def scan_public_surplus_once(max_test_listings: Optional[int] = None) -> int:
    alerts_sent = 0
    driver = None
    seen_this_run = set()

    try:
        driver, wait = create_driver()
        driver.get(BASE_URL)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        listings = parse_listing_cards(driver)
        print(f"Found {len(listings)} unique Public Surplus listing links on this page")

        listing_limit = max_test_listings

        for index, listing in enumerate(listings, start=1):
            if listing_limit is not None and index > listing_limit:
                print(f"Stopping test scan at MAX_TEST_LISTINGS={listing_limit}")
                break

            auction_id = listing.get("auction_id") or listing.get("listing_url")
            if auction_id in seen_this_run:
                continue
            seen_this_run.add(auction_id)

            try:
                print("\n====================")
                print(f"Visiting Public Surplus listing {index}: {listing.get('listing_url')}")
                print(f"Listing region: {listing.get('region_text') or 'Not found'}")

                _sleep_between_listing_requests(index)
                driver.get(listing["listing_url"])
                detail = parse_detail_page(driver, listing)
                detail_minutes_left = detail.get("minutes_left")
                print(f"Detail title: {detail.get('title') or 'Not found'}")
                print(f"Detail time left: {detail.get('time_left_text') or 'Not found'}")
                print(f"Current bid: {_display_current_bid(detail.get('current_bid'))}")

                evaluation = evaluate_truck(listing, detail)
                _log_public_surplus_decision(listing, detail, evaluation)

                if detail_minutes_left is not None and detail_minutes_left > CLOSE_SOON_MINUTES:
                    print(
                        "Stopping scan because detail page countdown is beyond "
                        f"{CLOSE_SOON_MINUTES}-minute window: "
                        f"{detail.get('title') or 'Not found'} "
                        f"({_display_minutes(detail_minutes_left)} minutes)"
                    )
                    break

                _print_alert_debug(evaluation)

                if evaluation["should_alert"]:
                    alert_message = _build_alert_message(listing, detail, evaluation)
                    send_alert(alert_message)
                    alerts_sent += 1
                    print("RESULT: ALERT SENT")
                else:
                    print("RESULT: NO ALERT SENT")

            except Exception as exc:
                print("Error on Public Surplus listing, skipping...")
                print(f"URL: {listing.get('listing_url')}")
                print(f"Error: {exc}")
                continue

    finally:
        if driver is not None:
            _quit_driver(driver)

    return alerts_sent


def main():
    if RUN_ONCE:
        total = scan_public_surplus_once(max_test_listings=MAX_TEST_LISTINGS)
        print(f"Public Surplus scan complete. Alerts sent: {total}")
        return

    while True:
        try:
            total = scan_public_surplus_once(max_test_listings=None)
            print(f"Public Surplus scan complete. Alerts sent: {total}")
        except Exception as exc:
            print(f"Public Surplus scan loop error: {exc}")
        time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
