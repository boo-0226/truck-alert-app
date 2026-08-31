# /src/sites/proxibid.py
# Purpose: Fast, headless Proxibid adapter using lotItems HTML endpoints (no Playwright).
# It fetches paginated fragments, parses titles/price/time, and applies your centralized targeting.

import time, random, requests, re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from src.core.config import apply_location_guard
from src.core.utils import (
    dprint, parse_bid_cents,
    is_engine_67, BLOCKED_MODELS,
    is_target_vehicle, annotate_tags,
)
from src.core.strategies import classify_listing_strategies, strategy_result_to_row_fields
from src.core.timeparse import seconds_remaining

# ---- Config (env-overridable via .env if you want) ----
# Category 3817 is common for trucks; you can swap later if needed.
PROXIBID_CATEGORY_ID = "3817"

# Two HTML styles we see from Proxibid; we’ll try both per page:
#  1) /core/category/lotItems/category/{id}/html?...&pageNumber=N
#  2) /core/category/lotItems/category/{id}/auctionHouseId/0/auctionId/0/metadata/html?auctionType=timed
LOTITEMS_URL = (
    "https://www.proxibid.com/core/category/lotItems/category/"
    "{cat}/html?sortBy=endingsoonest&auctionType=timed&inventoryType=all&"
    "auctionHouseId=0&auctionId=0&featured=false&metaDataFilters=&galleryView=true&"
    "pageNumber={page}"
)
METADATA_URL = (
    "https://www.proxibid.com/core/category/lotItems/category/"
    "{cat}/auctionHouseId/0/auctionId/0/metadata/html?auctionType=timed"
)

# URL pattern to link the lot in SMS
LOT_URL = "https://www.proxibid.com/asp/LotDetail.asp?lid={lid}"

# Basic headers; Proxibid expects "XMLHttpRequest" style requests for these endpoints.
def _headers():
    return {
        "accept": "*/*",
        "user-agent": "Mozilla/5.0",
        "referer": "https://www.proxibid.com/",
        "x-requested-with": "XMLHttpRequest",
    }

LID_RE    = re.compile(r"lid=(\d+)")
MONEY_RE  = re.compile(r"(?<!\w)\$?\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)")
CITY_ST_RE = re.compile(r"^\(([^)]+)\)\s*(.*)$")

def _secs_from_hm(hours_text: Optional[str], minutes_text: Optional[str]) -> Optional[int]:
    hrs = mins = 0
    if hours_text:
        try: hrs = int(hours_text)
        except: pass
    if minutes_text:
        try: mins = int(minutes_text)
        except: pass
    total = hrs * 3600 + mins * 60
    return total if total > 0 else None

def _parse_fragment(html: str) -> List[Dict]:
    """
    Parse a Proxibid lotItems/metadata HTML fragment into normalized rows.
    Tries to locate lot anchor with lid, title, location, price, and time-left.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    out: List[Dict] = []
    seen = set()

    # anchors to LotDetail.asp?lid=###
    links = soup.find_all("a", href=re.compile(r"LotDetail\.asp\?lid=\d+"))
    for a in links:
        href = a.get("href", "")
        m = LID_RE.search(href)
        if not m:
            continue
        lid = m.group(1)
        if lid in seen:
            continue
        seen.add(lid)

        url = href if href.startswith("http") else LOT_URL.format(lid=lid)

        # climb to container
        container = a.find_parent(class_=re.compile(r"(gallery-card|lotContainer|lotInfo)", re.I)) or a.parent

        # title
        title = ""
        if container:
            tnode = container.select_one(".lotTitle") or container.select_one(".lot-title")
            if tnode:
                title = tnode.get_text(strip=True)
        if not title:
            title = a.get_text(strip=True) or "Untitled"

        # location & city/state often appear in text near title; keep Unknown defaults
        city, state = "Unknown", ""
        location_match = CITY_ST_RE.match(title)
        if location_match:
            location_text = location_match.group(1)
            title = (location_match.group(2) or "").strip() or title
            if "," in location_text:
                city_part, state_part = location_text.rsplit(",", 1)
                city = city_part.strip() or city
                state = state_part.strip()[:2]
            else:
                city = location_text.strip() or city

        # price
        price_text = ""
        if container:
            pnode = container.select_one(".currentPrice .price_dollar_val") or container.select_one(".currentPrice")
            if pnode:
                price_text = pnode.get_text(" ", strip=True)
        if not price_text and container:
            price_text = container.get_text(" ", strip=True)
        bid_cents = None
        if price_text:
            m2 = MONEY_RE.search(price_text)
            if m2:
                bid_cents = parse_bid_cents(m2.group(1))

        # time left (look for cascading numbers in a .countdownTimer)
        hours_text = minutes_text = None
        if container:
            timer = container.select_one(".countdownTimer")
            if timer:
                nums = [x.get_text(strip=True) for x in timer.select(".auctionTimeEntity")]
                if len(nums) >= 1: hours_text = nums[0]
                if len(nums) >= 2: minutes_text = nums[1]
        secs = _secs_from_hm(hours_text, minutes_text)

        container_text = container.get_text(" ", strip=True) if container else title

        # Build text blob for filters
        text = f"{title} {container_text}".lower()
        engine67 = is_engine_67(text)
        blocked  = any(b in text for b in BLOCKED_MODELS)
        target   = is_target_vehicle(text)
        tags     = annotate_tags(text)
        diesel_target = target
        diesel_blocked = blocked

        row = {
            "site": "Proxibid",
            "asset_id": lid,
            "title": title,
            "desc": container_text,
            "city": city, "state": state,
            "bid_cents": bid_cents,
            "secs": secs,
            "engine_67": engine67,
            "blocked": diesel_blocked,
            "target": diesel_target,
            "tags": tags,
            "url": url,
        }

        strategy_result = classify_listing_strategies({
            "title": title,
            "desc": container_text,
            "container_text": container_text,
            "bid_cents": bid_cents,
            "secs": secs,
            "url": url,
        }, diesel_result={
            "strategy": "DIESEL_COMMERCIAL",
            "classification": "ALERT" if row["target"] and not row["blocked"] else "REJECT",
            "target": row["target"] and not row["blocked"],
            "blocked": row["blocked"],
            "engine_67": engine67,
            "tags": tags,
            "decision_reasons": ["diesel_commercial_existing_match"] if row["target"] and not row["blocked"] else ["diesel_commercial_existing_no_match"],
        })

        row.update(strategy_result_to_row_fields(strategy_result))
        if strategy_result.get("target_strategy"):
            row["target"] = strategy_result["target"]
            row["blocked"] = strategy_result["blocked"]

        apply_location_guard(row, state)

        out.append(row)
    return out

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=_headers(), timeout=30)
        if r.status_code != 200:
            dprint(f"[Proxibid] HTTP {r.status_code} for {url}")
            return None
        return r.text
    except requests.RequestException as e:
        dprint(f"[Proxibid] net error for {url}: {e}")
        return None

def fetch_listings(pages: int = 3, page_delay: float = 4.0) -> List[Dict]:
    """
    Pull a few pages of lotItems HTML + a metadata variant, parse, and return normalized rows.
    """
    cat = PROXIBID_CATEGORY_ID
    all_rows: List[Dict] = []
    seen = set()

    for p in range(0, max(0, pages)):
        # lotItems paginated
        u1 = LOTITEMS_URL.format(cat=cat, page=p)
        html1 = _fetch_html(u1)
        if html1:
            rows1 = _parse_fragment(html1)
            for r in rows1:
                if r["asset_id"] not in seen:
                    seen.add(r["asset_id"]); all_rows.append(r)

        # metadata variant (sometimes returns extra)
        u2 = METADATA_URL.format(cat=cat)
        html2 = _fetch_html(u2)
        if html2:
            rows2 = _parse_fragment(html2)
            for r in rows2:
                if r["asset_id"] not in seen:
                    seen.add(r["asset_id"]); all_rows.append(r)

        time.sleep(max(0.0, page_delay + random.uniform(-0.5, 1.0)))

    # OPTIONAL: run through time parser if any extra fields show up later
    # (We already compute secs from H/M above; seconds_remaining is here if you
    #  later add epoch/iso fields from another capture.)
    # for r in all_rows:
    #     if r.get("secs") is None:
    #         r["secs"] = seconds_remaining({...})

    dprint(f"[Proxibid] parsed {len(all_rows)} rows across {pages} page(s)")
    return all_rows
