# file: tests/autoGovDealsMoney.py

import os
import sys
import platform
import time
import re
import html
from datetime import datetime

# Make sure .../src is on sys.path so "core" becomes importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))          # ...\truck-alert-app\tests
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)                       # ...\truck-alert-app
SRC_DIR = os.path.join(PROJECT_ROOT, "src")                       # ...\truck-alert-app\src

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException

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



# This function is for if keywords appear in the check then mark as true. 
def contains_any(text: str, keywords: set) -> bool:
    """Return True if any keyword appears in the text (case-insensitive)."""
    t = text.lower()
    return any(kw in t for kw in keywords)

# Create a Chrome driver + wait object.
def create_driver():
    system = platform.system().lower()

    if system == "windows":
        options = Options()
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # options.add_argument("--headless=new")  # optional
        timeout = 20

    else:
        # Linux server
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        timeout = 30

    driver = webdriver.Chrome(options=options)

    wait = WebDriverWait(driver, timeout)
    return driver, wait


# Run one full scan of GovDeals and send Twilio alerts. Returns: number of alerts sent in this pass.
def scan_govdeals_once() -> int:

    alerts_sent = 0
    driver, wait = create_driver()

    try:
        #----- Links. Go into gov deals site it is transportaion and closing soon so it is in order from closing soon to closing later
        driver.get("https://www.govdeals.com/en/transportation/filters?so=asc&sf=auctionclose") 

        #Links. This finds all the links/href first and throw it into an array. 
        link_elems = wait.until(EC.presence_of_all_elements_located((By.XPATH, "(//a[@name='lnkAssetDetails'])"))) # Pulls in the wait for 15 and then it is saying to use the xpath and i give the exmaple which is the tag with name lnkAssetDetails
        hrefs = [a.get_attribute("href") for a in link_elems] # Need this the get the actually href/link

        #Links. Remove duplicates but keep order
        seen = set()
        unique_hrefs = []
        for url in hrefs:
            if url not in seen:
                seen.add(url)
                unique_hrefs.append(url)

        hrefs = unique_hrefs

        print(f"Found {len(hrefs)} unique listing links on this page")# print out the href/link count

        #-----Loop. For loop to loop through the links
        for href in hrefs:
            try:
                print("\n====================")
                print("Visiting: ", href)

                driver.get(href)  

                print("\n====================")
                print("Visiting: ", href)
                driver.get(href) # instead of clicking just naviagate to go around the cookie block. So think of this as the clinking the link that we found. 

                
                #-----Title. Wait until page has a non-empty title
                wait.until(lambda d: d.title and d.title.strip()) # So lamdba is just a function like def conditon () it allows it to be just one line. 
                title = driver.title.strip()
                print("Title:", title)
                

                if "item not available" in title.lower():
                    print("Unavailable GovDeals page. Skipping listing.")
                    print(f"Skipped URL: {href}")
                    continue

                #------Current Bid. Ran into an issue with some vehicles not having been bid on so had to try except to move on if it doesn't have a bid. 
                time.sleep(2)
                try:
                    bid_elem = driver.find_element(By.ID, "currentBid")
                    current_bid = bid_elem.get_attribute("title")  # e.g. "3000"
                    print("Current bid (raw):", current_bid)
                except NoSuchElementException:
                    current_bid = None
                    print("Current bid: None (no bids yet or no currentBid element)")

                #-----Location.
                try:
                    location_elem = driver.find_element(By.XPATH, "//span[@id='lnkAssetDetailLocation']")
                    location = (location_elem.get_attribute("title") or "").strip()
                except NoSuchElementException:
                    location = ""
                    print("Location element not found.")

                print("Location:", location)
                # Check only full state names from ALERT_STATES; abbreviations like TX should not match.
                location_valid = location_matches_alert_state(location)

                #-----Table Description. Prepare holders for specs text + miles
                specs_text_parts = []
                specs_table_found = False
                specs_make_value = None
                specs_model_value = None
                miles_value = None

                try:
                    # GovDeals details/additional info tables
                    rows = driver.find_elements(
                        By.CSS_SELECTOR,
                        "div.tab-content table.table tbody tr"
                    )

                    if rows:
                        specs_table_found = True
                        print("\nDescription specs:")
                        for row in rows:
                            cols = row.find_elements(By.TAG_NAME, "td")
                            if len(cols) >= 2:
                                label = cols[0].text.strip()
                                value = cols[1].text.strip()
                                print(f"{label}: {value}")

                                # Save for keyword blob later
                                specs_text_parts.append(f"{label}: {value}")

                                # Try to extract numeric miles from Odometer or Miles rows
                                label_lower = label.lower()
                                label_key = re.sub(r"[^a-z0-9]+", " ", label_lower).strip()

                                if label_key in ("manufacturer", "make") and value:
                                    specs_make_value = value
                                elif label_key == "model" and value:
                                    specs_model_value = value

                                if label_lower.startswith("odometer") or label_lower.startswith("miles"):
                                    mileage_match = re.search(r"([\d,]+(?:\.\d+)?)", value)
                                    if mileage_match:
                                        try:
                                            miles_value = int(float(mileage_match.group(1).replace(",", "")))
                                            print(f"Parsed mileage from specs table: {miles_value}")
                                        except ValueError:
                                            miles_value = None
                    else:
                        print("\nDescription specs: none found")

                except Exception as e:
                    print("\nDescription specs: error while reading ->", e)

                #------Short Description. Now grab the contents from description under truck
                meta_tag = wait.until(EC.presence_of_element_located((By.XPATH, "//meta[@name='description']"))) # and repeat basically this is a different tag since the description is would im goin gafter with is in the meta tag
                raw_short_desc = meta_tag.get_attribute("content") # Need this to get the contents of the description 
                short_desc = html.unescape(re.sub(r"<[^>]+>", " ", raw_short_desc)).strip() # I was getting tags in the text so this cleans thos tags out.  
                print("\nShort description:\n", short_desc)


                time.sleep(2)

                #------Long Description. Needed to put this in a try catch because some have long descritpions and some does not. 
                try:
                    # p.long-description matches: <p class="long-description py-3">...</p>
                    long_desc_elem = driver.find_element(By.CSS_SELECTOR, "p.long-description")

                    # .text will flatten the <br> tags into newlines/spaces
                    long_desc = long_desc_elem.text.strip()

                    print("\nLong Description:\n", long_desc)

                except NoSuchElementException:
                    long_desc = ""
                    print("\nLong Description: None found")

                # Fallback mileage parse from short/long description if specs table had no mileage
                if miles_value is None:
                    mileage_text = " ".join([
                        short_desc or "",
                        long_desc or "",
                    ])

                    mileage_patterns = [
                        r"\blast\s+known\s+mileage\s*[-:]\s*([\d,]+)",
                        r"\blast\s+reported\s+odometer\s+(?:was\s+)?([\d,]+)",
                        r"\bodometer\s*[:\-]?\s*([\d,]+)",
                        r"\bmileage\s*[:\-]?\s*([\d,]+)",
                        r"\b([\d,]+)\s+miles\b",
                    ]

                    for pattern in mileage_patterns:
                        mileage_match = re.search(pattern, mileage_text, re.IGNORECASE)
                        if mileage_match:
                            try:
                                miles_value = int(mileage_match.group(1).replace(",", ""))
                                print(f"Mileage fallback hit: {miles_value}")
                                break
                            except ValueError:
                                miles_value = None

                #----- Closing Time. Ex.) timer text: "5h48m (Nov 08, 2025 06:16 AM CST)" 
                try:
                    timer_elem = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//p[contains(@class,'timerAttribute')]"))
                    )
                    timer_text = timer_elem.text.strip()
                except Exception:
                    timer_text = ""
                    print("Timer not found.")

                # Split into countdown and actual close datetime
                if "(" in timer_text:
                    countdown_part, close_part = timer_text.split("(", 1)
                    countdown = countdown_part.strip()                # ex.) "9h 20m"
                    close_time = close_part.rstrip(")").strip()       # ex.) "Nov 08, 2025 09:33 AM CST"
                else:
                    countdown = timer_text
                    close_time = ""

                print("Countdown:", countdown)
                print("Closes at:", close_time)

                # always defined for this listing
                minutes_left = None
                stop_after_debug = False

                if close_time:
                    try:
                        close_time_clean = " ".join(close_time.split()[:-1])   # strip timezone (e.g. "CST")

                        # Convert/Parse to datetime
                        close_dt = datetime.strptime(close_time_clean, "%b %d, %Y %I:%M %p")
                        now = datetime.now()  # Current local time
                        minutes_left = (close_dt - now).total_seconds() / 60  # Compute time difference in minutes

                        # Just print info here; "closing soon" will be decided later
                        if minutes_left <= CLOSE_SOON_MINUTES:
                            print(f"Less than {CLOSE_SOON_MINUTES} minutes left!")
                        else:
                            print(f"{minutes_left:.1f} minutes remaining.")

                        # Long-time check and ends loop after debug output
                        if minutes_left > 35:
                            stop_after_debug = True
                    except Exception as e:
                        print("Close time parse error:", e)
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

                # Closing time filter: now based only on minutes_left
                close_soon_flag = (
                    minutes_left is not None and
                    0 <= minutes_left <= CLOSE_SOON_MINUTES
                )

                # Bid filter: current bid < 5000
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
                    matched_rule_reason = gas_eval["matched_rule_reason"]
                    debug_eval = gas_eval
                elif diesel_match:
                    target_label = "DIESEL TARGET"
                    matched_lane = diesel_eval["matched_lane"]
                    matched_rule_reason = diesel_eval["matched_rule_reason"]
                    debug_eval = diesel_eval
                else:
                    target_label = "NO TARGET"
                    matched_lane = None
                    matched_rule_reason = "No gas or diesel target matched"
                    debug_eval = gas_eval

                alert_message = None
                if should_alert:
                    miles_text = miles_value if miles_value is not None else "Not found"
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
                debug_miles = miles_value if miles_value is not None else "Not found"
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
                    alerts_sent += 1

                if stop_after_debug:
                    print("Stopping scan because listing is beyond 35-minute window")

                print("RESULT: ALERT SENT" if should_alert else "RESULT: NO ALERT SENT")

                if stop_after_debug:
                    break
            except Exception as e:
                print("❌ Error on listing, skipping...")
                print(f"URL: {href}")
                print(f"Error: {e}")
                continue

    finally:

        driver.quit() # Need this to quit or it will stay running
    

    return alerts_sent

if __name__ == "__main__":
    # Manual/local run:
    total = scan_govdeals_once()
    print(f"Scan complete. Alerts sent: {total}")
