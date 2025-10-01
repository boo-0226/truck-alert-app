# /src/sites/renebates.py
import os, re, time, random, requests
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

from src.core.utils import (
    dprint, parse_bid_cents, format_dollars,
    is_target_vehicle, annotate_tags,  # use unified targeting from utils.py
)
# seconds_remaining not used here; RB gives event-level close only
# from src.core.timeparse import seconds_remaining

DEBUG = os.getenv("DEBUG", "0").lower() in ("1","true","yes","y")

INDEX_URL = os.getenv(
    "RENEBATES_INDEX_URL",
    "https://renebates.com/a_main.php"   # master event list
)

HEADERS = {
    "user-agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "accept-language": "en-US,en;q=0.9",
}

# ----------------- regex/consts -----------------

EVENT_LINK_RE = re.compile(r"a_main_2\.php\?id=\d+", re.I)
CURRENCY_RE   = re.compile(r"\$(\d[\d,]*(?:\.\d{2})?)")

# e.g. "City Of Van Alstyne, Texas"
CITY_STATE_RE = re.compile(r"City\s+of\s+([^,]+),\s*([A-Za-z]{2,})", re.I)
STATE_ABBR = {
    "ALABAMA":"AL","ALASKA":"AK","ARIZONA":"AZ","ARKANSAS":"AR","CALIFORNIA":"CA","COLORADO":"CO",
    "CONNECTICUT":"CT","DELAWARE":"DE","FLORIDA":"FL","GEORGIA":"GA","HAWAII":"HI","IDAHO":"ID",
    "ILLINOIS":"IL","INDIANA":"IN","IOWA":"IA","KANSAS":"KS","KENTUCKY":"KY","LOUISIANA":"LA",
    "MAINE":"ME","MARYLAND":"MD","MASSACHUSETTS":"MA","MICHIGAN":"MI","MINNESOTA":"MN","MISSISSIPPI":"MS",
    "MISSOURI":"MO","MONTANA":"MT","NEBRASKA":"NE","NEVADA":"NV","NEW HAMPSHIRE":"NH","NEW JERSEY":"NJ",
    "NEW MEXICO":"NM","NEW YORK":"NY","NORTH CAROLINA":"NC","NORTH DAKOTA":"ND","OHIO":"OH","OKLAHOMA":"OK",
    "OREGON":"OR","PENNSYLVANIA":"PA","RHODE ISLAND":"RI","SOUTH CAROLINA":"SC","SOUTH DAKOTA":"SD",
    "TENNESSEE":"TN","TEXAS":"TX","UTAH":"UT","VERMONT":"VT","VIRGINIA":"VA","WASHINGTON":"WA",
    "WEST VIRGINIA":"WV","WISCONSIN":"WI","WYOMING":"WY","DISTRICT OF COLUMBIA":"DC","WASHINGTON DC":"DC"
}

# Example on RB pages:
# "Closes: Tuesday, September 23, 2025 Beginning at 1:00 PM CDT"
CLOSES_RE = re.compile(
    r"Closes:\s*(?:[A-Za-z]+,\s*)?([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*Beginning at\s*([0-9]{1,2}:[0-9]{2}\s*[AP]M)\s*([A-Z]{2,4})",
    re.I
)
TZ_OFFSETS = {"CST": -6, "CDT": -5, "MST": -7, "MDT": -6, "PST": -8, "PDT": -7, "EST": -5, "EDT": -4}

# Lot URL patterns
LOT_HREF_RE = re.compile(r"a_lot_\d+\.php\?id=\d+&lot=\d+", re.I)
LOT_ID_RE   = re.compile(r"[?&]lot=(\d+)")

# ----------------- helpers -----------------

def _get(url, params=None, timeout=20):
    r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
    r.raise_for_status()
    return r

def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")

def _city_state_from_title(text: str):
    """
    From 'City Of Van Alstyne, Texas' -> ('Van Alstyne','TX')
    Falls back to ('Unknown','').
    """
    t = (text or "").strip()
    if not t:
        return "Unknown", ""
    m = CITY_STATE_RE.search(t)
    if not m:
        return "Unknown", ""
    city = m.group(1).strip()
    raw_state = m.group(2).strip()
    if len(raw_state) == 2 and raw_state.isalpha():
        return city, raw_state.upper()
    abbr = STATE_ABBR.get(raw_state.upper(), "")
    return city, abbr

def _parse_event_close_secs(event_html: str) -> Optional[int]:
    """
    Parse 'Closes: [Weekday, ]Month DD, YYYY Beginning at HH:MM AM TZ'
    Convert local TZ to UTC seconds remaining.
    """
    m = CLOSES_RE.search(event_html)
    if not m:
        return None
    date_s = m.group(1).strip()
    time_s = m.group(2).upper().replace("  "," ")
    tz_s   = m.group(3).upper()

    try:
        dt_local_naive = datetime.strptime(f"{date_s} {time_s}", "%B %d, %Y %I:%M %p")
        # Convert to UTC using the fixed offset map above
        offset_hours = TZ_OFFSETS.get(tz_s)
        if offset_hours is None:
            # Fallback: assume Central if RB omits/odd TZ
            offset_hours = -5 if tz_s.endswith("DT") else -6
        # Local -> UTC: add the absolute UTC offset
        dt_utc = dt_local_naive + timedelta(hours=(0 - offset_hours))
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0, int((dt_utc - now).total_seconds()))
    except Exception:
        return None

def _abs_url(href: str) -> Optional[str]:
    if not href:
        return None
    if href.startswith("http"):
        return href
    return requests.compat.urljoin(INDEX_URL, href)

def _pick_category_links(ev_soup: BeautifulSoup) -> List[str]:
    """
    Prefer category links in the 'Categories' block that likely contain trucks.
    If none, fall back to 'All Items' link.
    Return absolute URLs.
    """
    links = []

    # 1) Categories block (fix deprecation: use string=)
    cat_block = None
    for label in ev_soup.find_all(string=re.compile(r"\bCategories\b", re.I)):
        try:
            cat_block = label.parent if hasattr(label, "parent") else None
            if cat_block:
                break
        except Exception:
            pass

    if cat_block:
        for a in cat_block.find_all("a", href=True):
            txt = a.get_text(" ", strip=True).lower()
            if any(kw in txt for kw in ("truck", "tractor", "fire", "utility", "heavy duty", "diesel", "crane", "bucket", "dump", "box")):
                u = _abs_url(a["href"])
                if u: links.append(u)

    # 2) Fallback: All Items
    if not links:
        for a in ev_soup.find_all("a", href=True):
            if "all items" in a.get_text(" ", strip=True).lower():
                u = _abs_url(a["href"])
                if u: links.append(u)
                break

    # Dedup
    out, seen = [], set()
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def _extract_lot_rows(list_html: str) -> List[Dict]:
    """
    Harvest only true lot links a_lot_*.php?id=NNN&lot=MMM.
    Pull a nearby price if present.
    """
    soup = _soup(list_html)
    out: List[Dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not LOT_HREF_RE.search(href):
            continue
        title = a.get_text(" ", strip=True) or "Untitled"
        url   = _abs_url(href)
        lot_id = None
        m = LOT_ID_RE.search(href)
        if m:
            lot_id = m.group(1)

        # Try to grab a nearby price
        container = a.find_parent(["tr", "div", "li", "p"]) or a.parent
        price = None
        if container:
            m2 = CURRENCY_RE.search(container.get_text(" ", strip=True))
            if m2:
                price = parse_bid_cents(m2.group(1))

        out.append({
            "title": title,
            "url": url,
            "bid_cents": price,
            "asset_id": lot_id or f"lot-{hash(url) & 0xffffffff:x}",
        })
    return out

# ----------------- public API -----------------
def fetch_listings(pages: int = 1, page_delay: float = 3.5, start_offset: int = 0) -> List[Dict]:
    """
    Scrape the index, then N events, then 1 category (or All Items) per event.
    pages = how many events to traverse (top-to-bottom).
    start_offset = index offset to begin from (for round-robin across cycles).
    """
    try:
        r = _get(INDEX_URL)
    except Exception as e:
        dprint(f"[Renebates] index fetch error: {e}")
        return []

    index_soup = _soup(r.text)
    events = []
    for a in index_soup.find_all("a", href=True):
        if EVENT_LINK_RE.search(a["href"]):
            url = requests.compat.urljoin(INDEX_URL, a["href"])
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            events.append({"url": url, "title": title})

    total_events = len(events)
    if DEBUG: dprint(f"[Renebates] found {total_events} events on index")

    # round-robin slice
    pages = max(1, pages)
    start = max(0, start_offset) % max(1, total_events)
    end = start + pages
    if end <= total_events:
        ev_slice = events[start:end]
    else:
        # wrap around
        ev_slice = events[start:] + events[:(end % total_events)]

    rows: List[Dict] = []
    for ev in ev_slice:
        time.sleep(page_delay + random.uniform(-0.5, 1.2))

        time.sleep(max(0.0, page_delay + random.uniform(-0.5, 1.2)))
        try:
            ev_res = _get(ev["url"])
        except Exception as e:
            dprint(f"[Renebates] event fetch error (skip): {e}")
            continue

        ev_html = ev_res.text
        ev_soup = _soup(ev_html)

        city, state = _city_state_from_title(ev.get("title") or ev_html[:140])
        secs_event  = _parse_event_close_secs(ev_html)  # seconds till "Beginning at …"
        if DEBUG:
            dprint(f"[Renebates] event: {ev['title']} secs={secs_event}")

        cat_urls = _pick_category_links(ev_soup)
        if not cat_urls:
            # No categories; keep the event row so digest shows activity
            rows.append({
                "site": "ReneBates",
                "asset_id": f"event-{hash(ev['url']) & 0xffffffff}",
                "title": ev["title"],
                "city": city, "state": state,
                "bid_cents": None,
                "secs": secs_event,
                "url": ev["url"],
                "tags": ["event"],
                "engine_67": False,
                "blocked": False,
            })
            continue

        list_url = cat_urls[0]
        try:
            list_res = _get(list_url)
        except Exception as e:
            dprint(f"[Renebates] category fetch error: {e}")
            continue

        lots = _extract_lot_rows(list_res.text)
        if DEBUG:
            dprint(f"[Renebates] {ev['title']} -> {len(lots)} lots via {list_url}")

        for lot in lots:
            title = lot["title"]
            url   = lot["url"]
            bid   = lot.get("bid_cents")
            asset_id = lot.get("asset_id") or f"{(hash(url) & 0xffffffff):x}"

            text = (title or "").lower()
            tags = annotate_tags(text)
            blocked = not is_target_vehicle(text)  # true target = diesel+specialty OR cummins

            rows.append({
                "site": "ReneBates",
                "asset_id": str(asset_id),
                "title": title,
                "city": city, "state": state,
                "bid_cents": bid,
                "secs": secs_event,   # RB rarely gives per-lot times; use event close
                "url": url,
                "tags": tags,
                "engine_67": ("6.7" in text) or ("power stroke" in text) or ("cummins" in text),
                "blocked": blocked,
            })

    return rows

if __name__ == "__main__":
    pages = int(os.getenv("RENEBATES_PAGES", "3"))
    rows = fetch_listings(pages=pages, page_delay=2.0)
    print(f"Fetched {len(rows)} listings from {pages} events")
    for r in rows[:10]:   # show first 10 for sanity
        print(f"[{r['site']}] {r['title']} | {r['city']}, {r['state']} | "
              f"{format_dollars(r['bid_cents'])} | secs={r['secs']} | {r['url']}")

