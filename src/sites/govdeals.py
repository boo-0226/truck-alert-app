# file path: /src/sites/govdeals.py
# Purpose: adapter for GovDeals; returns normalized listings
import os
import uuid, random, time as _time, requests
from datetime import timezone, datetime, timedelta
from typing import List, Dict, Optional, Any
from urllib.parse import quote_plus

from src.core.utils import (
    parse_bid_cents, dprint,
    is_specialty_body, has_cummins, is_engine_67,
    annotate_tags, BLOCKED_MODELS
)
from src.core.diagnostics import add_error
from src.core.timeparse import seconds_remaining

URL = "https://maestro.lqdt1.com/search/list"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 Edg/141.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
]

# this was my patch fix for the hour time off -----> GD_TIME_OFFSET_SECONDS = -3600  # subtract 60 minutes from GovDeals times

# ---------- headers + payload ----------

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

def build_payload(page=1, use_category=True):
    payload = {
        "categoryIds": "6" if use_category else "",
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
        "facetsFilter": [],
        "timeType": "",
        "sellerTypeId": None,
        "accountIds": [],
    }
    return payload

# ---------- time helpers (tz fix + recursive scan) ----------

def _local_tz():
    secs = -_time.timezone
    if _time.daylight and _time.localtime().tm_isdst > 0:
        secs = -_time.altzone
    return timezone(timedelta(seconds=secs))

CLOSE_HINTS = ("close", "closing", "end", "expires")
ISO_HINTS   = ("T", "Z", "+")

def _epoch_secs_from_any(v: Any) -> Optional[int]:
    try:
        if isinstance(v, (int, float)):
            x = float(v)
            if x > 2_000_000_000_000:  # ns
                x /= 1_000_000_000.0
            elif x > 2_000_000_000:    # ms
                x /= 1000.0
            return int(x)
    except Exception:
        pass
    return None

def _iso_to_epoch(s: str) -> Optional[int]:
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_local_tz())  # treat naive as local (Central)
        return int(dt.timestamp())
    except Exception:
        return None

def _scan_for_close_epoch(obj: Any, trail: str = "") -> Optional[tuple]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            k_low = str(k).lower()
            new_trail = f"{trail}.{k}" if trail else str(k)
            if any(h in k_low for h in CLOSE_HINTS):
                ep = _epoch_secs_from_any(v)
                if ep:
                    return ep, new_trail
                if isinstance(v, str) and any(h in v for h in ISO_HINTS):
                    ep = _iso_to_epoch(v)
                    if ep:
                        return ep, new_trail
            res = _scan_for_close_epoch(v, new_trail)
            if res:
                return res
    elif isinstance(obj, list):
        for i, it in enumerate(obj):
            res = _scan_for_close_epoch(it, f"{trail}[{i}]")
            if res:
                return res
    return None

# ---------- time helpers (tz fix + recursive scan) ----------
# ... keep everything above as-is ...

def _coerce_secs(item: Dict[str, Any]) -> Optional[int]:
    """
    Mirror the site's countdown:
      1) Use any direct 'seconds remaining' fields if present.
      2) If we get a close datetime string (e.g. 'assetAuctionEndDate'),
         treat it as *local wall time* and subtract datetime.now() (also local).
      3) Fallback to the generic seconds_remaining() and deep scan.
    """
    # 1) any direct secs fields
    for k in ("secondsRemaining", "timeLeftInSeconds", "timeRemaining", "secondsToEnd"):
        v = item.get(k)
        if isinstance(v, (int, float)):
            return max(0, int(v))

    # 2) GovDeals close time as local (mirror the UI timer)
    s = item.get("assetAuctionEndDate") or item.get("auctionEndDate") or item.get("auctionEndDateDisplay")
    if isinstance(s, str) and s.strip():
        s2 = s.strip()
        try:
            # Try ISO-ish first (e.g. '2025-10-21T16:30:00')
            dt = datetime.fromisoformat(s2)
        except Exception:
            dt = None
        if dt is not None:
            # If no tz on the string, treat it as local wall-clock
            if dt.tzinfo is None:
                now_local = datetime.now()  # local, naive
                rem = int((dt - now_local).total_seconds())
            else:
                # If tz exists, use it directly vs UTC 'now'
                now_utc = datetime.now(timezone.utc)
                rem = int((dt.astimezone(timezone.utc) - now_utc).total_seconds())
            # Keep zero for just-closed items; otherwise None if past
            return rem if rem > 0 else (0 if rem >= -5 else None)

    # 3) fallback: generic parser + deep scan
    try:
        s_generic = seconds_remaining(item)
        if isinstance(s_generic, int):
            return s_generic
    except Exception:
        pass

    scanned = _scan_for_close_epoch(item)
    if scanned:
        close_epoch, _path = scanned
        now = int(datetime.now(timezone.utc).timestamp())
        rem = close_epoch - now
        return rem if rem > 0 else (0 if rem >= -5 else None)

    return None

# ---------- ID + URL helpers ----------

def _first(*vals):
    for v in vals:
        if v not in (None, ""):
            return v
    return None

def _acct_asset_from_pair(pair: str, known_asset: str = None):
    """
    '12267-33' → ('12267','33') (account, asset).
    If known_asset is provided, use it to disambiguate.
    """
    try:
        left, right = pair.split("-", 1)
        left, right = left.strip(), right.strip()
        if not (left.isdigit() and right.isdigit()):
            return None, None
        if known_asset:
            if str(known_asset) == left:
                return right, left   # (account, asset)
            if str(known_asset) == right:
                return left, right
        return left, right
    except Exception:
        return None, None

def _acct_asset_from_attributes(item: dict, known_asset: str = None):
    """
    Scan the description table for 'Lot#' → '12267-33'
    """
    try:
        attrs = item.get("assetAttributes") or []
        for row in attrs:
            label = (row.get("label") or "").strip().lower()
            if label in ("lot#", "lot", "lot number", "lot number:"):
                pair = (row.get("value") or "").strip()
                if "-" in pair:
                    return _acct_asset_from_pair(pair, known_asset)
    except Exception:
        pass
    return None, None

def _extract_ids(item: dict, known_asset: str = None):
    """
    Return (accountId, assetId) as strings if we can determine them,
    else (None, assetId or None). Uses multiple sources.
    """
    # direct top-level first
    acct = _first(
        item.get("accountId"), item.get("sellerAccountId"), item.get("clientAccountId"),
        item.get("organizationId"), item.get("sellerId"), item.get("siteId"), item.get("organizationNumber"),
    )
    asset = _first(item.get("assetId"), item.get("id"), item.get("lotId"), item.get("lotNumber"), known_asset)
    if acct and asset:
        return str(acct), str(asset)

    # attributes “Lot#”
    a2, s2 = _acct_asset_from_attributes(item, known_asset=asset or known_asset)
    if a2 and s2:
        return str(a2), str(s2)

    # lotNumberDisplay / productId like "12267-33"
    for k in ("lotNumberDisplay", "lotNumber", "productLotNumberDisplay", "lotNo", "lot", "productId"):
        v = item.get(k)
        if isinstance(v, str) and "-" in v:
            a3, s3 = _acct_asset_from_pair(v, known_asset=asset or known_asset)
            if a3 and s3:
                return str(a3), str(s3)

    # last resort
    return (str(acct) if acct else None, str(asset) if asset else None)

def _is_transportation(item: dict) -> bool:
    """
    Detect Transportation categories (vehicles). If true, we'll flip URL order to asset/account.
    """
    # Primary: breadcrumbs include 'transportation' (GovDeals uses this taxonomy)
    try:
        crumbs = item.get("categoryBreadcrumbs") or []
        for c in crumbs:
            t = (c.get("t") or "").strip().lower()
            n = ((c.get("d") or {}).get("n") or "").strip().lower()
            if "transportation" in (t or n):
                return True
    except Exception:
        pass

    # Fallback: category/parent descriptors
    cat = (item.get("categoryName") or item.get("catDesc") or "").strip().lower()
    parent = (item.get("parentCatDesc") or "").strip().lower()
    if any(x in cat for x in ("truck", "vehicle", "bus", "automobile", "car", "van", "pickup", "tractor")):
        return True
    if "transportation" in parent:
        return True

    return False

def _build_gd_url(item: dict, asset_id: str, account_id: str) -> str:
    """
    Build canonical URL. For Transportation, GovDeals resolves as /asset/{asset}/{account}.
    For other categories, /asset/{account}/{asset}.
    If either id missing, fall back to a search link.
    """
    title = (item.get("assetShortDescription") or item.get("shortDescription") or "").strip()
    if asset_id and account_id:
            return f"https://www.govdeals.com/en/asset/{asset_id}/{account_id}"
    # fallback
    q = " ".join([asset_id or "", title]).strip() or "*"
    return f"https://www.govdeals.com/en/search?kWord={quote_plus(q)}"

# ---------- container parsing ----------

def _parse_items_container(data: Dict[str, Any]) -> List[Dict]:
    for key in ("assetSearchResults", "products", "assets", "items", "results"):
        items = data.get(key)
        if isinstance(items, list):
            return items
    for key in ("data", "payload", "searchResults"):
        obj = data.get(key)
        if isinstance(obj, dict):
            for lkey in ("assetSearchResults", "products", "assets", "items", "results"):
                items = obj.get(lkey)
                if isinstance(items, list):
                    return items
    return []

# ---------- main fetch + normalize ----------

SEVEN_DAYS_DEFAULT = 7 * 86400

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

def fetch_listings(pages: int | None = None,
                   page_delay: float | None = None,
                   horizon_secs: int | None = None) -> list[dict]:
    """
    Scan GovDeals 'Transportation' sorted by auction close ascending and STOP
    when the earliest item on a page is beyond the time horizon (default 7 days).

    Env knobs:
      GOVDEALS_MAX_PAGES (safety cap, default 50)
      GOVDEALS_PAGE_DELAY (seconds between pages, default 4.5)
      GOVDEALS_TIME_HORIZON_SECS (default 604800 = 7 days)
    """
    # env-driven defaults
    max_pages = _env_int("GOVDEALS_MAX_PAGES", 50) if pages is None else pages
    delay     = _env_float("GOVDEALS_PAGE_DELAY", 4.5) if page_delay is None else page_delay
    horizon   = _env_int("GOVDEALS_TIME_HORIZON_SECS", SEVEN_DAYS_DEFAULT) if horizon_secs is None else horizon_secs

    headers = build_headers()
    all_items, seen = [], set()
    total_raw = 0
    page = 1

    dprint(f"[GD] fetch_listings horizon={horizon}s (~{round(horizon/86400,2)}d) max_pages={max_pages} delay={delay}")

    while page <= max_pages:
        # request (with 400 retry fallback you already added)
        try:
            r = requests.post(URL, headers=headers, json=build_payload(page, use_category=True), timeout=30)
            if r.status_code == 400:
                dprint("[GD] 400 with categoryIds — retrying without categoryIds")
                r = requests.post(URL, headers=headers, json=build_payload(page, use_category=False), timeout=30)
        except requests.exceptions.RequestException as e:
            dprint(f"[GD] net error page {page}: {e}")
            add_error("GovDeals", "request", f"network error page {page}: {e}")
            break

        ct = (r.headers.get("Content-Type") or "").lower()
        if r.status_code != 200 or "application/json" not in ct:
            dprint(f"[GD] bad response page {page} ({r.status_code}) body={r.text[:300]}")
            add_error("GovDeals", "http", f"bad response page {page}: {r.status_code}")
            break

        data  = r.json()
        items = _parse_items_container(data)
        n = len(items)
        dprint(f"[GD] page {page}: {n} items")
        total_raw += n

        if n == 0:
            dprint("[GD] no more items; stopping")
            break

        # ---- EARLY STOP CHECK (sorted by auctionclose asc) ----
        # compute the earliest secs on this page using your existing time helper
        try:
            page_secs = []
            for it in items:
                s = _coerce_secs(it)  # same function normalize() uses
                if isinstance(s, int) and s >= 0:
                    page_secs.append(s)
            page_min = min(page_secs) if page_secs else None
        except Exception:
            page_min = None

        if page_min is not None and page_min > horizon:
            dprint(f"[GD] stop: earliest on page {page} is {page_min}s > horizon {horizon}s")
            break
        # -------------------------------------------------------

        # collect (dedupe by asset_id)
        for it in items:
            asset_id = str(it.get("assetId") or it.get("id") or "")
            if asset_id and asset_id not in seen:
                seen.add(asset_id)
                all_items.append(it)

        page += 1
        _time.sleep(max(0.0, delay + random.uniform(-1.0, 1.25)))

    dprint(f"[GD] total raw={total_raw}, unique kept={len(all_items)}")
    rows = normalize(all_items)
    return rows





def normalize(items: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for idx, item in enumerate(items, start=1):
        title = (item.get("assetShortDescription") or item.get("shortDescription") or "").strip()
        desc  = (item.get("assetLongDescription")  or item.get("longDescription")  or "").strip()
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
        secs = _coerce_secs(item)
        # GovDeals is consistently +1h for us — make a local-only correction here.
        if isinstance(secs, (int, float)):
            secs = max(0, int(secs) - 3600)


        # ----- targeting -----
        text = f"{title} {desc} {cat}".lower()
        specialty_text = is_specialty_body(text)
        cat_l = cat.lower()
        specialty_cat = any(kw in cat_l for kw in (
            "dump","bucket","aerial","boom","crane","knuckle","derrick","box","straight truck","van body",
            "ambulance","rescue","fire","wrecker","tow","utility","service","refuse","garbage","roll off",
            "roll-off","vacuum","sewer","tanker","mixer"
        ))
        cummins_or_67 = has_cummins(text) or is_engine_67(text)
        target = specialty_text or specialty_cat or cummins_or_67
        blocked_ld = any(b in text for b in BLOCKED_MODELS)

        tags = annotate_tags(text)

        # ----- ids + URL -----
        raw_asset_id = str(item.get("assetId") or item.get("id") or f"idx-{idx}")
        acct_id, asset_id_for_url = _extract_ids(item, known_asset=raw_asset_id)
        url = _build_gd_url(item, asset_id_for_url, acct_id)

        row = {
            "site": "GovDeals",
            "asset_id": raw_asset_id,          # asset id (for your downstream logic)
            "gd_account_id": acct_id,          # debug visibility
            "gd_asset_id": asset_id_for_url,   # debug visibility (used in URL)
            "title": title or "Untitled",
            "city": city, "state": state,
            "bid_cents": bid,
            "secs": secs,
            "url": url,
            "engine_67": is_engine_67(text),
            "blocked": blocked_ld or (not target),
            "target": target and not blocked_ld,
            "tags": tags,
        }
        out.append(row)
    return out
