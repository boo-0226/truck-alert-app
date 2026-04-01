# file: tests/autoGovDealsMoney.py

import os
import sys
import platform

# Make sure .../src is on sys.path so "core" becomes importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))          # ...\truck-alert-app\tests
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)                       # ...\truck-alert-app
SRC_DIR = os.path.join(PROJECT_ROOT, "src")                       # ...\truck-alert-app\src

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
from selenium.common.exceptions import NoSuchElementException
from src.core.autoKeywords_GovDeals import ALERT_STATES



import time
import re, html

# now we can import from src/core
from core.autoKeywords_GovDeals import TARGET_KEYWORDS, EXCLUDE_KEYWORDS
from core.autoTwilio_Alerts import send_alert



# This function is for if keywords appear in the check then mark as true. 
def contains_any(text: str, keywords: set) -> bool:
    """Return True if any keyword appears in the text (case-insensitive)."""
    t = text.lower()
    return any(kw in t for kw in keywords)

# Create a Chrome driver + wait object. For now this still uses your local Windows chromedriver path. We'll swap this for a Linux/headless setup on the server later. 
def create_driver():
    import platform
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from webdriver_manager.chrome import ChromeDriverManager

    system = platform.system().lower()

    # Windows Server (GUI)
    if system == "windows":
        options = Options()
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # options.add_argument("--headless=new")  # optional

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        timeout = 20

    else:
        # Linux server
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),
            options=options
        )
        timeout = 30

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
                    print("Location element not found. Skipping listing.")
                    print(f"Skipped URL: {href}")
                    continue

                if not location:
                    print("Location was blank. Skipping listing.")
                    print(f"Skipped URL: {href}")
                    continue

                print("Location:", location)
                # Check if location contains an allowed state
                location_valid = False
                if location:
                    loc_lower = location.lower()
                    for st in ALERT_STATES:
                        if st.lower() in loc_lower:
                            location_valid = True
                            break

                print("Location Allowed:", location_valid)


                #-----Table Description. # Prepare holders for specs text + miles
                specs_text_parts = []   # Prepare holders for specs text + miles used later for keyword search
                miles_value = None      # numeric miles if we can parse it

                try:
                    rows = driver.find_elements(By.CSS_SELECTOR, "div.showmore div.row.description-body")
                    if rows:
                        print("\nDescription specs:")
                        for row in rows:
                            cols = row.find_elements(By.CLASS_NAME, "col-6")
                            if len(cols) >= 2:
                                label = cols[0].text.strip()
                                value = cols[1].text.strip()
                                print(f"{label}: {value}")

                                # Save for keyword blob later
                                specs_text_parts.append(f"{label}: {value}")

                                # Try to extract numeric miles
                                if label.lower().startswith("miles"):
                                    main_part = value.split("(")[0].strip()  # "136,619.00"
                                    main_part = main_part.replace(",", "")
                                    try:
                                        miles_value = int(float(main_part.split()[0]))
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
                    print("Contains 'diesel'? -> False")

                #----- Closing Time. Ex.) timer text: "5h48m (Nov 08, 2025 06:16 AM CST)" 
                try:
                    timer_elem = wait.until(
                        EC.presence_of_element_located((By.XPATH, "//p[contains(@class,'timerAttribute')]"))
                    )
                    timer_text = timer_elem.text.strip()
                except Exception:
                    print("Timer not found. Skipping listing.")
                    print(f"Skipped URL: {href}")
                    continue

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

                if close_time:
                    close_time_clean = " ".join(close_time.split()[:-1])   # strip timezone (e.g. "CST")

                    # Convert/Parse to datetime
                    close_dt = datetime.strptime(close_time_clean, "%b %d, %Y %I:%M %p")
                    now = datetime.now()  # Current local time
                    minutes_left = (close_dt - now).total_seconds() / 60  # Compute time difference in minutes

                    # Just print info here; "closing soon" will be decided later
                    if minutes_left <= 30:
                        print("Less than 30 minutes left!")
                    else:
                        print(f"{minutes_left:.1f} minutes remaining.")

                    # Long-time check and ends loop
                    hours_left = minutes_left / 60
                    if hours_left > .583:
                        print("More than 35min left on this truck, stopping scan.")
                        break
                else:
                    print("No close time found; cannot compute minutes remaining.")


                # -----Target Truck/mileage checks and Twilio alert. Build one big text blob: title + short + long + specs. Also prints the boolean to reference truck targe, low mileage, and should alert hits. 
                search_blob = " ".join([
                    title or "",
                    short_desc or "",
                    long_desc or "",
                    " ".join(specs_text_parts),
                ])

                truck_target = contains_any(search_blob, TARGET_KEYWORDS)
                low_mileage = (miles_value is not None and miles_value <= 200_000)

                # Closing time filter: now based only on minutes_left
                close_soon_flag = (minutes_left is not None and minutes_left <= 30)

                #Keywords. This tells me which keywords made it true since some vehicles i don't know why it was showing up
                matched_keywords = [kw for kw in TARGET_KEYWORDS if kw in search_blob.lower()]

                #Keywords.
                # Override target if excluded terms are present
                matched_excludes = [kw for kw in EXCLUDE_KEYWORDS if kw in search_blob]
                exclude_hit = bool(matched_excludes)

                if exclude_hit:
                    truck_target = False


                # Bid filter: current bid < 6600
                bid_under_limit = False
                if current_bid is not None:
                    try:
                        numeric_bid = float(current_bid)
                        bid_under_limit = numeric_bid < 6600
                    except ValueError:
                        bid_under_limit = False

                should_alert = (
                    truck_target and
                    low_mileage and
                    close_soon_flag and
                    bid_under_limit 
                )

                print("\n[ALERT DEBUG]")
                print(f"  exclude_hit (blocked keywords): {exclude_hit} {matched_excludes}")
                print(f"  truck_target (keywords hit): {truck_target} (matched={matched_keywords})")
                print(f"  low_mileage (<=150,000):     {low_mileage}  (miles_value={miles_value})")
                print(f"  close_soon (<=30 min):       {close_soon_flag}  (minutes_left={minutes_left})")
                print(f"  bid_under_limit (<6600):     {bid_under_limit}  (current_bid={current_bid})")
                print(f"  should_alert (ALL true):     {should_alert}")

                if should_alert:
                    # Build table description text (one line per item)
                    specs_summary = "\n".join(specs_text_parts) if specs_text_parts else "No specs table."

                    # SMS body: title, bid, miles, specs, and direct link
                    alert_message = (
                        f"{title}\n"
                        f"Bid: {current_bid} | Miles: {miles_value}\n"
                        f"{location}\n"
                        f"{specs_summary}\n"
                        f"Matched keywords: {matched_keywords}\n"
                        f"{href}"
                    )

                    print("  -> ALERT TRIGGERED: sending Twilio SMS/voice now.")
                    send_alert(alert_message)
                else:
                    print("  -> No alert sent for this listing.")
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