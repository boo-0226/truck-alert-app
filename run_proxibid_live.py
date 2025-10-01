# file: run_proxibid_live.py
# Opens the Proxibid timed-trucks page headlessly, captures JSON XHR responses,
# normalizes items, then reuses your Twilio alert logic (≤ $5k AND ≤ 10 min).
import os, io, sys, json, time
from datetime import datetime, timezone

# Force UTF-8 logs (Windows emoji fix)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

# Reuse your existing helpers
from govdeals_scraper import (
    ALERT_PRICE_CENTS, ALERT_TIME_SECS,
    load_cache, save_cache, already_alerted, mark_alerted,
    twilio_client, alert_truck, parse_bid_cents, seconds_remaining
)

# Reuse strict filters from core
from src.core.utils import is_engine_67, BLOCKED_MODELS


# NEW: HTML parsing for lotItems fragments
import re
from typing import Optional, List, Dict
from bs4 import BeautifulSoup

LID_RE   = re.compile(r"lid=(\d+)")
MONEY_RE = re.compile(r"(?<!\w)\$?\s?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)")
CITY_ST  = re.compile(r"^\(([^)]+)\)\s*(.*)$")  # "(City, ST) Title..." -> split

# Keep part/accessory blocks
BLOCK_KWS = {
    "tool box", "toolbox", "bedslide", "headache rack", "rack",
    "rim", "rims", "wheel", "wheels", "tire", "tires",
    "hitch", "fifth wheel", "sway control", "trailer",
    "bumper", "axle", "kit", "hoist", "pump"
}

# Must look like a truck body/use-case (dump/bucket/utility/flatbed/pickup/super duty)
BODY_KWS = {"truck", "dump", "bucket", "utility", "flatbed", "pickup", "super duty", "crew cab", "extended cab"}

def is_target_vehicle(title: str) -> bool:
    """
    Strict filter:
      - reject common parts/accessories
      - reject light-duty models (BLOCKED_MODELS from core)
      - require 6.7L diesel (Power Stroke or Cummins)
      - require generic truck body keywords
    """
    t = (title or "").lower()

    if any(b in t for b in BLOCK_KWS):
        return False
    if any(b in t for b in BLOCKED_MODELS):  # f-150 / 1500 / ranger / etc.
        return False
    if not is_engine_67(t):                   # must advertise 6.7L diesel
        return False
    if not any(k in t for k in BODY_KWS):     # must look like a truck body
        return False
    return True



def _secs_from_hm(hours_text: Optional[str], minutes_text: Optional[str]) -> Optional[int]:
    hrs = mins = 0
    if hours_text:
        try: hrs = int(hours_text)
        except: pass
    if minutes_text:
        try: mins = int(minutes_text)
        except: pass
    total = hrs*3600 + mins*60
    return total if total > 0 else None

def parse_html_fragment(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []

    # Find ALL lot links by href pattern (?lid=#####)
    links = soup.find_all("a", href=re.compile(r"LotDetail\.asp\?lid=\d+"))
    seen = set()
    for a in links:
        href = a.get("href", "")
        m = LID_RE.search(href)
        if not m:
            continue
        lid = m.group(1)
        if lid in seen:
            continue
        seen.add(lid)

        # Absolute URL for SMS click-through
        url = href if href.startswith("http") else f"https://www.proxibid.com{href}"

        # Walk up to container to scrape title/price/time
        container = (
            a.find_parent(class_=re.compile(r"(lotContainer|gallery-card|lotInfo)", re.I))
            or a.parent
        )

        # Title + location
        title = (container.select_one(".lotTitle").get_text(strip=True)
                 if container and container.select_one(".lotTitle") else (a.get_text(strip=True) or "Untitled"))
        city, state = "Unknown", ""
        mloc = CITY_ST.match(title)
        if mloc:
            loc_str = mloc.group(1)
            title = (mloc.group(2) or "").strip() or title
            if "," in loc_str:
                city = loc_str.split(",")[0].strip()
                state = loc_str.split(",")[1].strip()[:2]
            else:
                city = loc_str.strip()

        # Price (extract numeric dollars)
        price_text = ""
        if container and container.select_one(".currentPrice .price_dollar_val"):
            price_text = container.select_one(".currentPrice .price_dollar_val").get_text(" ", strip=True)
        if not price_text:
            ctext = container.get_text(" ", strip=True) if container else ""
            price_text = ctext
        bid_cents = None
        if price_text:
            mprice = MONEY_RE.search(price_text)
            if mprice:
                bid_cents = parse_bid_cents(mprice.group(1))

        # Time left (hours/minutes)
        hours_text = minutes_text = None
        timer = container.select_one(".countdownTimer") if container else None
        if timer:
            nums = [x.get_text(strip=True) for x in timer.select(".auctionTimeEntity")]
            if len(nums) >= 1: hours_text = nums[0]
            if len(nums) >= 2: minutes_text = nums[1]
        secs = _secs_from_hm(hours_text, minutes_text)

        out.append({
            "site": "Proxibid",
            "asset_id": lid,
            "title": title,
            "city": city, "state": state,
            "bid_cents": bid_cents,
            "secs": secs,
            "url": url,  # <-- add link for SMS
        })
    return out





PROXIBID_URL = os.getenv(
    "PROXIBID_TIMED_TRUCKS_URL",
    "https://www.proxibid.com/timed-events?tl=0#3817///endingsoonest/timed/all/0/0/3/"
)
DEBUG = os.getenv("DEBUG", "0").lower() in ("1","true","yes","y")

def dprint(*a, **k):
    if DEBUG: print(*a, **k)

def _coerce_item(obj: dict):
    if not isinstance(obj, dict):
        return None

    # Filter out obvious non-lot payloads (help widgets, etc.)
    s = str(obj).lower()
    if any(bad in s for bad in ("zendesk", "intercom", "helpcenter")):
        return None

    # --- ID ---
    asset_id = (
        obj.get("id") or obj.get("itemId") or obj.get("lotId") or obj.get("listingId")
        or (obj.get("item") or {}).get("id") or (obj.get("lot") or {}).get("id")
    )
    if not asset_id:
        return None

    # --- Title ---
    title = (
        obj.get("title") or obj.get("name") or obj.get("lotTitle")
        or (obj.get("item") or {}).get("title")
        or (obj.get("lot") or {}).get("title")
        or ""
    ).strip() or "Untitled"

    # --- Location ---
    loc = obj.get("location") or obj.get("sellerLocation") or {}
    city  = loc.get("city")  or obj.get("city")  or "Unknown"
    state = loc.get("state") or obj.get("state") or ""

    # --- Bid / Price ---
    price_candidates = [
        obj.get("currentBid"),
        obj.get("currentBidAmount"),
        obj.get("highBid"),
        obj.get("price"),
        (obj.get("pricing") or {}).get("currentBid"),
        (obj.get("pricing") or {}).get("currentPrice"),
        (obj.get("currentBid") or {}).get("amount"),
        (obj.get("price") or {}).get("amount"),
        (obj.get("currentPrice") or {}).get("amount"),
        (obj.get("bid") or {}).get("amount"),
        obj.get("currentBidCents"),
        (obj.get("pricing") or {}).get("currentBidCents"),
    ]
    bid_cents = None
    for pc in price_candidates:
        bid_cents = parse_bid_cents(pc)
        if bid_cents is not None:
            break

    # --- End time (seconds/epoch/ISO) ---
    time_payload = {
        "secondsRemaining": obj.get("secondsRemaining") or obj.get("timeLeftInSeconds"),
        "auctionEndEpoch": (
            obj.get("auctionEndEpoch") or obj.get("endEpoch") or obj.get("endTimestamp")
            or obj.get("endDateEpoch") or obj.get("endDateMilliseconds")
        ),
        "endTime": (
            obj.get("endTime") or obj.get("end_time") or obj.get("endDate") or obj.get("endDateTime")
            or obj.get("endDateUtc") or obj.get("closingDate") or obj.get("closeDate")
        ),
        "endDate": obj.get("endDate"),
    }
    secs = seconds_remaining(time_payload)

    return {
        "site": "Proxibid",
        "asset_id": str(asset_id),
        "title": title,
        "city": city, "state": state,
        "bid_cents": bid_cents,
        "secs": secs,
    }


def _extract_items_from_json_text(text: str):
    out = []
    try:
        data = json.loads(text)
    except Exception:
        return out
    # collect dicts likely to be items
    def walk(x):
        if isinstance(x, dict):
            if any(k in x for k in ("id","itemId","lotId","listingId")) and any(k in x for k in ("title","name","lotTitle")):
                m = _coerce_item(x)
                if m: out.append(m)
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(data)
    return out
def _force_fetch_fragments(page, base_cat_id: str = "3817", pages: int = 3):
    """From inside the page context, fetch a few lotItems HTML fragments from BOTH endpoint styles."""
    import urllib.parse as _up

    # Detect category id from page hash if present
    try:
        h = page.url.split("#", 1)[1]
        maybe_cat = "".join(ch for ch in h.split("/")[0] if ch.isdigit())
        if maybe_cat:
            base_cat_id = maybe_cat
    except Exception:
        pass

    urls = []
    for pn in range(0, pages + 1):
        urls.append(
            f"https://www.proxibid.com/core/category/lotItems/category/{base_cat_id}/html"
            f"?sortBy=endingsoonest&auctionType=timed&inventoryType=all&auctionHouseId=0&auctionId=0"
            f"&featured=false&metaDataFilters=&galleryView=true&pageNumber={pn}"
        )
    # metadata/html variant (no pageNumber param observed; still try pn tags)
    urls.append(
        f"https://www.proxibid.com/core/category/lotItems/category/{base_cat_id}/auctionHouseId/0/auctionId/0/metadata/html?auctionType=timed"
    )

    all_rows = []
    for u in urls:
        try:
            body = page.evaluate("""async (u) => {
                const r = await fetch(u, {
                  credentials:'include',
                  headers: {'x-requested-with':'XMLHttpRequest', 'accept':'*/*'}
                });
                return await r.text();
            }""", u)
            if DEBUG:
                print(f"[FORCE] fetched {u} size={len(body or '')}")
            try:
                os.makedirs("logs", exist_ok=True)
                tag = "forced_html"
                if "/metadata/html" in u:
                    tag = "forced_metadata"
                q = _up.urlparse(u).query
                params = dict(_up.parse_qsl(q))
                pn = params.get("pageNumber","X")
                with open(f"logs/proxibid_{tag}_p{pn}.html", "w", encoding="utf-8") as f:
                    f.write(body)
            except Exception:
                pass
            rows = parse_html_fragment(body)
            all_rows.extend(rows)
        except Exception as e:
            if DEBUG:
                print(f"[FORCE] fetch error for {u}: {e}")

    # de-dup by asset_id
    uniq, seen = [], set()
    for r in all_rows:
        if r["asset_id"] in seen: continue
        seen.add(r["asset_id"]); uniq.append(r)
    return uniq


def fetch_via_network(url: str):
    from playwright.sync_api import sync_playwright
    items, seen = [], set()

    with sync_playwright() as p:
        profile_dir = os.path.join(os.getcwd(), ".pwprofile")  # persistent profile saves cookies/challenges
        os.makedirs(profile_dir, exist_ok=True)

        headless = os.getenv("PROXIBID_HEADLESS", "0").lower() in ("1","true","yes","y")

        # Persistent context + realistic client
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
            viewport={"width": 1366, "height": 900},
            locale="en-US",
            timezone_id="America/Chicago",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"),
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        page = context.new_page()

        # Stealth: hide webdriver
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")

        # -------- network capture --------
        def on_response(resp):
            u = resp.url
            ul = u.lower()
            ctype = (resp.headers or {}).get("content-type","").lower()

            def _save_and_parse(label: str, body: str, inferred_pn: str = "0"):
                if not body:
                    if DEBUG: print(f"[NET] {label} empty body -> {u}")
                    return
                if DEBUG:
                    first = (body or "")[:200].replace("\n", " ")
                    print(f"[NET] {label} size={len(body or '')} first200={first!r}")
                try:
                    os.makedirs("logs", exist_ok=True)
                    path = f"logs/proxibid_fragment_{label}_p{inferred_pn}.html"
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(body)
                    if DEBUG:
                        print(f"[Proxibid] Saved fragment -> {path}")
                except Exception:
                    pass
                mapped = parse_html_fragment(body)
                for it in mapped:
                    if it["asset_id"] not in seen:
                        seen.add(it["asset_id"])
                        items.append(it)

            # lotItems HTML
            if "/core/category/lotitems/" in ul and "html" in ul:
                try:
                    body = resp.text()
                except Exception:
                    return
                import urllib.parse as _up
                q = _up.urlparse(u).query
                params = dict(_up.parse_qsl(q))
                pn = params.get("pageNumber","0")
                _save_and_parse("lotitems", body, pn)
                return

            # metadata/html (alternate)
            if "/metadata/html" in ul:
                try:
                    body = resp.text()
                except Exception:
                    return
                _save_and_parse("metadata", body, "0")
                return

            # JSON listings (bonus)
            looks_like_listings = any(s in ul for s in (
                "/api", "search", "items", "lots", "listing",
                "category", "lotsearch", "lot-search"
            ))
            if "application/json" in ctype and looks_like_listings:
                try:
                    text = resp.text()
                except Exception:
                    return
                if not text:
                    if DEBUG: print(f"[NET] json empty body -> {u}")
                    return
                try:
                    os.makedirs("logs", exist_ok=True)
                    if DEBUG and not os.path.exists("logs/proxibid_sample.json"):
                        with open("logs/proxibid_sample.json", "w", encoding="utf-8") as f:
                            f.write(text)
                        print(f"[Proxibid] Saved sample JSON -> logs/proxibid_sample.json")
                except Exception:
                    pass
                mapped = _extract_items_from_json_text(text)
                for it in mapped:
                    if it["asset_id"] not in seen:
                        seen.add(it["asset_id"])
                        items.append(it)
                return

        page.on("response", on_response)

        # -------- navigate once, content-based waits --------
        dprint(f"[Proxibid] Navigating {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
        except Exception as e:
            print(f"[WARN] goto DOMContentLoaded timed out/failed: {e}")

        # Cookie banners: OK / Accept
        for txt in ("OK", "Accept"):
            try:
                page.get_by_text(txt, exact=True).first.click(timeout=2000)
            except Exception:
                pass

        # Wait for lots or give manual time to pass checks
        found_lots = False
        try:
            page.wait_for_selector(".gallery-card, #featuredLots .gallery-card", timeout=20000)
            found_lots = True
        except Exception:
            if not headless:
                print("[ACTION] If you see a cookie/bot prompt in the open browser, handle it now…")
                try:
                    page.wait_for_selector(".gallery-card, #featuredLots .gallery-card", timeout=30000)
                    found_lots = True
                except Exception:
                    found_lots = False

        # Dump + parse rendered page
        dprint("[DEBUG] dumping rendered HTML")
        try:
            os.makedirs("logs", exist_ok=True)
            main_html = page.content()
            with open("logs/proxibid_main.html", "w", encoding="utf-8") as f:
                f.write(main_html)
            rows_main = parse_html_fragment(main_html)
            if DEBUG:
                print(f"[FALLBACK] parsed {len(rows_main)} items from rendered page")
            for it in rows_main:
                if it["asset_id"] not in seen:
                    seen.add(it["asset_id"])
                    items.append(it)
        except Exception as e:
            print(f"[WARN] render parse failed: {e}")

        # Nudge SPA to fire more XHRs
        if found_lots:
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1200)

        time.sleep(6.0)  # allow late XHRs

       # Paginate until no more cards (or until a safety max)
    max_pages = int(os.getenv("PROXIBID_PAGES_MAX", "30"))  # ~900 items at 30/page
    empty_streak_limit = 2  # stop after 2 empty pages in a row
    empty_streak = 0
    page_i = 0

    while page_i <= max_pages:
        frag_rows = _force_fetch_fragments(page, pages=page_i)  # reuses your helper to fetch page_i
        # _force_fetch_fragments(pages=X) fetches pageNumber=X only (as implemented earlier)
        if DEBUG:
            print(f"[FORCE] page={page_i} -> {len(frag_rows)} rows")

        # merge de-duped
        added = 0
        for it in frag_rows:
            if it["asset_id"] not in seen:
                seen.add(it["asset_id"])
                items.append(it)
                added += 1

        if added == 0:
            empty_streak += 1
            if empty_streak >= empty_streak_limit:
                if DEBUG:
                    print(f"[FORCE] stopping pagination after {empty_streak} empty pages")
                break
        else:
            empty_streak = 0

        page_i += 1

        if DEBUG:
            print(f"[FORCE] parsed {len(forced)} items from forced fetch")
        for it in forced:
            if it["asset_id"] not in seen:
                seen.add(it["asset_id"])
                items.append(it)

        # Clean close
        try:
            context.close()
        except Exception:
            pass

    dprint(f"[Proxibid] captured {len(items)} items")
    return items

def run_once(alerts_enabled=True):
    cache = load_cache()
    items = fetch_via_network(PROXIBID_URL)
    dprint(f"[Proxibid] normalized {len(items)} items")
    client = None
    def ensure():
        nonlocal client
        if client is None: client = twilio_client()
        return client
    for itm in items:
        if not is_target_vehicle(itm.get("title", "")):
            dprint(f"[skip-target] id={itm.get('asset_id')} title={itm.get('title')}")
            continue


        bid = itm.get("bid_cents"); secs = itm.get("secs")
        if (bid is None) or (not isinstance(secs, int)):
            dprint(f"[skip] id={itm.get('asset_id')} bid={bid} secs={secs}")
            continue

        if not (bid <= ALERT_PRICE_CENTS and secs <= ALERT_TIME_SECS):
            dprint(f"[skip] id={itm['asset_id']} price_ok={bid <= ALERT_PRICE_CENTS} time_ok={secs <= ALERT_TIME_SECS}")
            continue

        # Prefix title so you know which site called you
        itm["title"] = f"[Proxibid] {itm['title']}"

        key = f"final-Proxibid-{itm['asset_id']}"

        if already_alerted(cache, key):
            dprint(f"[skip] id={itm['asset_id']} already alerted")
            continue
        if alert_truck(ensure(), itm, alerts_enabled=alerts_enabled):
            mark_alerted(cache, key, {"price": bid, "secs": secs, "title": itm["title"]})
            save_cache(cache)

if __name__ == "__main__":
    run_once(alerts_enabled=True)

