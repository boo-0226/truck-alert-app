# /src/sites/govdeals.py
# Purpose: adapter for GovDeals; returns normalized listings
import uuid, random, time, requests
from datetime import timezone, datetime
from typing import List, Dict
from typing import List, Dict, Optional
from src.core.utils import (
    parse_bid_cents, dprint,
    is_specialty_body, has_cummins, is_engine_67,
    annotate_tags, BLOCKED_MODELS
)
from src.core.timeparse import seconds_remaining
from typing import Optional

URL = "https://maestro.lqdt1.com/search/list"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
]

def build_headers():
    return {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://www.govdeals.com",
        "referer": "https://www.govdeals.com/en/trucks",
        "host": "maestro.lqdt1.com",
        "user-agent": random.choice(USER_AGENTS),
        "x-api-key": "af93060f-337e-428c-87b8-c74b5837d6cd",
        "ocp-apim-subscription-key": "cf620d1d8f904b5797507dc5fd1fdb80",
        "x-api-correlation-id": str(uuid.uuid4()),
        "x-ecom-session-id": str(uuid.uuid4()),
        "x-user-id": "-1",
        "x-user-timezone": "America/Chicago",
    }

def build_payload(page=1):
    return {
        "categoryIds": "",
        "businessId": "GD",
        "searchText": "*",
        "isQAL": False,
        "locationId": None,
        "model": "",
        "makebrand": "",
        "auctionTypeId": None,
        "page": page,
        "displayRows": 24,
        "sortField": "auctionclose",
        "sortOrder": "asc",
        "sessionId": str(uuid.uuid4()),
        "requestType": "search",
        "responseStyle": "productsOnly",
        "facets": [
            "categoryName","auctionTypeID","condition","saleEventName","sellerDisplayName",
            "product_pricecents","isReserveMet","hasBuyNowPrice","isReserveNotMet",
            "sellerType","warehouseId","region","currencyTypeCode","categoryName","tierId",
        ],
        "facetsFilter": [
            '{!tag=product_category_external_id}product_category_external_id:"t6"',
            '{!tag=product_category_external_id}product_category_external_id:"94C"',
        ],
        "timeType": "",
        "sellerTypeId": None,
        "accountIds": [],
    }

def fetch_listings(pages=5, page_delay=6.0) -> List[Dict]:
    headers = build_headers()
    all_items = []
    seen = set()
    total_raw = 0
    for page in range(1, pages+1):
        try:
            r = requests.post(URL, headers=headers, json=build_payload(page), timeout=15)
        except requests.exceptions.RequestException as e:
            dprint(f"[GD] net error on page {page}: {e}")
            break

        ct = (r.headers.get("Content-Type") or "").lower()
        dprint(f"[GD] HTTP {r.status_code} | CT={ct} | page={page}")

        if r.status_code != 200 or "application/json" not in ct:
            dprint(f"[GD] bad response (status/ct) on page {page}")
            break

        try:
            data = r.json()
        except Exception as e:
            dprint(f"[GD] json parse failed page {page}: {e}")
            break

        items = data.get("assetSearchResults", []) or []
        dprint(f"[GD] page {page}: {len(items)} items")
        total_raw += len(items)

        for it in items:
            asset_id = str(it.get("assetId") or it.get("id") or "")
            if not asset_id or asset_id in seen:
                continue
            seen.add(asset_id)
            all_items.append(it)

        time.sleep(max(0.0, page_delay + random.uniform(-1.0, 1.5)))

    dprint(f"[GD] total raw items before normalize: {total_raw}; unique kept: {len(all_items)}")
    rows = normalize(all_items)
    dprint(f"[GD] normalized rows: {len(rows)}")
    # Quick count after specialty/diesel filter (blocked flag)
    blocked_ct = sum(1 for r in rows if r.get("blocked"))
    dprint(f"[GD] blocked by specialty/diesel filter: {blocked_ct}; passing: {len(rows) - blocked_ct}")
    return rows


def normalize(items: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for idx, item in enumerate(items, start=1):
        title = (item.get("assetShortDescription") or "").strip()
        desc  = (item.get("assetLongDescription") or "").strip()
        cat   = (item.get("categoryName") or "").strip()
        city  = item.get("locationCity") or "Unknown"
        state = item.get("locationState") or ""

        # ----- price -----
        bid = None
        for k in ("product_pricecents", "currentBidCents", "currentBid"):
            v = item.get(k)
            cents = parse_bid_cents(v)
            if cents is not None:
                bid = cents
                break

        # ----- time -----
        secs = seconds_remaining(item)

        # ----- targeting (LOOSE: specialty only) -----
        text = f"{title} {desc} {cat}".lower()

        # specialty by free-text (dump/bucket/crane/box/emergency/utility/refuse/tanker/mixer…)
        specialty_text = is_specialty_body(text)

        # specialty by GovDeals category name
        cat_l = cat.lower()
        specialty_cat = any(kw in cat_l for kw in (
            "dump", "bucket", "aerial", "boom", "crane", "knuckle",
            "derrick", "box", "straight truck", "van body",
            "ambulance", "rescue", "fire", "wrecker", "tow",
            "utility", "service", "refuse", "garbage",
            "roll off", "roll-off", "vacuum", "sewer",
            "tanker", "mixer"
        ))

        # cummins / 6.7 are always ok
        cummins_or_67 = has_cummins(text) or is_engine_67(text)

        # FINAL: pass if specialty by text OR category OR explicit engine hit
        target = specialty_text or specialty_cat or cummins_or_67

        # still block light-duty gassers (F-150/1500 etc.)
        blocked_ld = any(b in text for b in BLOCKED_MODELS)

        tags = annotate_tags(text)
        asset_id = str(item.get("assetId") or item.get("id") or f"idx-{idx}")
        url_id   = item.get("assetId") or item.get("id")
        url      = f"https://www.govdeals.com/asset/{url_id}" if url_id else None

        row = {
            "site": "GovDeals",
            "asset_id": asset_id,
            "title": title,
            "city": city, "state": state,
            "bid_cents": bid,
            "secs": secs,
            "url": url,
            "engine_67": is_engine_67(text),  # still annotate if true
            "blocked": blocked_ld or (not target),
            "tags": tags,
        }
        out.append(row)
    return out

