# file: govdeals_scraper.py
import os
import re
import json
import time
import uuid
import random
import requests
import sys
import typing
from datetime import datetime, timezone
from pathlib import Path
from argparse import ArgumentParser
from dotenv import load_dotenv

load_dotenv()

# ---- Twilio (optional) ----
try:
    from twilio.rest import Client
except Exception:
    Client = None

# DEBUG flag: enable verbose logs via --debug or DEBUG=1 in .env
DEBUG = os.getenv("DEBUG", "0").lower() in ("1", "true", "yes", "y")

def dprint(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)


URL = "https://maestro.lqdt1.com/search/list"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
]

# ---- Alert thresholds (env-overridable) ----
# ---- Alert thresholds (env-overridable) ----
def _int_env(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(str(v).strip())
    except ValueError:
        return default

def _dollars_to_cents_env(name: str, default_dollars: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default_dollars * 100
    s = str(v).strip().replace("$","").replace(",","")
    try:
        x = float(s)
        return int(round(x * 100))
    except ValueError:
        return default_dollars * 100

ALERT_PRICE_CENTS = _dollars_to_cents_env("ALERT_PRICE_DOLLARS", 5000)          # e.g. 10000 => $10,000
ALERT_TIME_SECS   = _int_env("ALERT_TIME_SECS", 18 * 3600 + 10 * 60)            # seconds
EARLY_TIME_SECS   = _int_env("EARLY_TIME_SECS", 10 * 60)                        # seconds

dprint(f"[DEBUG] Thresholds -> price_cap={ALERT_PRICE_CENTS} cents "
       f"({ALERT_PRICE_CENTS/100:.2f}), alert_time_secs={ALERT_TIME_SECS}, early_time_secs={EARLY_TIME_SECS}")


# ---- Dedupe cache ----
CACHE_PATH     = Path(".alert_cache.json")
CACHE_TTL_SECS = 2 * 60 * 60

# ---- Keywords ----
DUMP_KWS   = {"dump", "dumptruck", "dump truck", "dump-body"}
BUCKET_KWS = {
    "bucket", "bucket truck", "aerial", "boom", "cherry picker",
    "altec", "terex", "hi-ranger", "versalift", "lift-all", "at37", "aa600"
}

MONEY_RE = re.compile(r"[\$,]")

# ---- Alert channel toggles (env) ----
SEND_SMS   = os.getenv("SEND_SMS", "1").lower() in ("1","true","yes","y")
SEND_VOICE = os.getenv("SEND_VOICE", "1").lower() in ("1","true","yes","y")

# ---------------- CLI ----------------
def parse_args():
    p = ArgumentParser(description="GovDeals trucks scraper: dump/bucket alerts")
    p.add_argument("--pages", type=int, default=5, help="Pages to scan per cycle (default 5)")
    p.add_argument("--page-delay", type=float, default=6.0, help="Delay between page requests (sec)")
    p.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    p.add_argument("--no-alerts", action="store_true", help="Print only; no Twilio")
    return p.parse_args()

# ---------------- HTTP ----------------
def build_headers():
    return {
        "accept": "application/json, text/plain, */*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
        "connection": "keep-alive",
        "content-type": "application/json",
        "host": "maestro.lqdt1.com",
        "origin": "https://www.govdeals.com",
        "referer": "https://www.govdeals.com/en/trucks",
        "ocp-apim-subscription-key": "cf620d1d8f904b5797507dc5fd1fdb80",
        "x-api-key": "af93060f-337e-428c-87b8-c74b5837d6cd",
        "user-agent": random.choice(USER_AGENTS),
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Microsoft Edge";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "x-api-correlation-id": str(uuid.uuid4()),
        "x-ecom-session-id": str(uuid.uuid4()),
        "x-page-unique-id": "aHR0cHM6Ly93d3cuZ292ZGVhbHMuY29tL2VuL3RydWNrcw==",
        "x-referer": "https://www.govdeals.com/en/trucks",
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
        # Try "ending soon" sort; if ignored server falls back.
        "sortField": "auctionclose",   # UI shows sf=auctionclose
        "sortOrder": "asc",            # so=asc
        "sessionId": str(uuid.uuid4()),
        "requestType": "search",
        "responseStyle": "productsOnly",
        "facets": [
            "categoryName","auctionTypeID","condition","saleEventName","sellerDisplayName",
            "product_pricecents","isReserveMet","hasBuyNowPrice","isReserveNotMet",
            "sellerType","warehouseId","region","currencyTypeCode","categoryName","tierId",
        ],
        # Server-side: Trucks categories from /en/trucks
        "facetsFilter": [
            '{!tag=product_category_external_id}product_category_external_id:"t6"',
            '{!tag=product_category_external_id}product_category_external_id:"94C"',
        ],
        "timeType": "",
        "sellerTypeId": None,
        "accountIds": [],
    }

# ---------------- parsing ----------------
def parse_bid_cents(value):
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 250_000 else value * 100
    if isinstance(value, float):
        return int(round(value * 100))
    if isinstance(value, str):
        s = MONEY_RE.sub("", value).strip()
        if not s:
            return None
        try:
            return int(round(float(s) * 100))
        except ValueError:
            return None
    return None

def seconds_remaining(item) -> typing.Optional[int]:
    """Return seconds remaining or None."""
    # 1) direct seconds fields
    for k in ("secondsRemaining", "timeLeftInSeconds", "timeRemaining", "secondsToEnd"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v >= 0:
            return int(v)

    # 2) epoch seconds/millis
    now = datetime.now(timezone.utc).timestamp()
    for k in ("assetAuctionEndDateEpoch", "auctionEndEpoch", "endTimeEpochMs", "endDate", "auctionEndDate"):
        v = item.get(k)
        if isinstance(v, (int, float)) and v > 0:
            if v > 10_000_000_000:  # ms → s
                v = v / 1000.0
            return max(0, int(v - now))

    # 3) string/display times
    candidates = []
    for k in ("assetAuctionEndDate", "assetAuctionEndDateDisplay", "endTimeDisplay", "auctionEndDateDisplay"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())

    import re as _re
    cleaned = []
    for s in candidates:
        m = _re.search(r"\(([^)]+)\)", s)  # e.g., "Aug 10 (UTC)"
        cleaned.append(m.group(1).strip() if m else s)

    # Add naive ISO format without timezone (assume UTC)
    fmts = (
        "%m/%d/%Y %I:%M %p %Z",
        "%m/%d/%Y %H:%M %Z",
        "%B %d, %Y %I:%M %p %Z",
        "%b %d, %Y %I:%M %p %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",    # <— THIS was missing
    )

    for s in cleaned:
        # First try Python's ISO parser (handles many cases)
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, int(dt.timestamp() - now))
        except Exception:
            pass

        # Then try the explicit formats list
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return max(0, int(dt.timestamp() - now))
            except Exception:
                continue

    return None


def format_dollars(cents):
    if cents is None:
        return "N/A"
    return f"${cents/100:,.2f}"

# ---------------- cache + twilio ----------------
def load_cache():
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text())
            ts = time.time()
            return {k:v for k,v in data.items() if (ts - v.get("ts",0) <= CACHE_TTL_SECS)}
        except Exception:
            return {}
    return {}

def save_cache(cache):
    try:
        CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass

def already_alerted(cache, asset_id):
    return asset_id in cache

def mark_alerted(cache, asset_id, meta):
    cache[asset_id] = {"ts": time.time(), "meta": meta}

def twilio_client():
    if Client is None:
        raise RuntimeError("Twilio client not available. pip install twilio")
    sid   = os.environ.get("TWILIO_SID")
    token = os.environ.get("TWILIO_TOKEN")
    if not sid or not token:
        raise RuntimeError("Missing TWILIO_SID / TWILIO_TOKEN")
    return Client(sid, token)

def send_sms(client, body):
    from_ = os.environ.get("TWILIO_FROM")
    to    = os.environ.get("ALERT_TO")
    client.messages.create(to=to, from_=from_, body=body)

def place_call(client, say_text):
    from_ = os.environ.get("TWILIO_FROM")
    to    = os.environ.get("ALERT_TO")
    twiml = f'<Response><Say voice="Polly.Matthew">{say_text}</Say></Response>'
    client.calls.create(to=to, from_=from_, twiml=twiml)

def alert_truck(client, itm, alerts_enabled=True):
    """Try SMS and Voice; treat as success if either works."""
    bid_cents = itm.get("bid_cents")
    secs = itm.get("secs")
    if (bid_cents is None) or (not isinstance(secs, int)):
        return False

    site  = (itm.get("site") or "Alert").upper()
    title = itm.get("title") or "Untitled"
    city  = itm.get("city") or "Unknown"
    state = itm.get("state") or ""
    url   = itm.get("url")  # may be None on some sources

    dollars = format_dollars(bid_cents)
    mins, secs_rem = secs // 60, secs % 60
    end_human = f"{mins}m {secs_rem}s"

    # SMS body with link if available
    if url:
        msg = f"{site}: {title} | {city}, {state} | {dollars} | {end_human}\n{url}"
    else:
        msg = f"{site}: {title} | {city}, {state} | {dollars} | {end_human}"

    # Voice: keep it clean; tell user to check text for link
    say_text = (
        f"{site} alert. {title}. Current bid {dollars}. "
        f"Time left {mins} minutes {secs_rem} seconds. "
        f"I've texted you the link."
        if url else
        f"{site} alert. {title}. Current bid {dollars}. "
        f"Time left {mins} minutes {secs_rem} seconds."
    )

    print("🚨 " + msg.replace("\n", " | "))
    if not alerts_enabled:
        return True

    ok = False
    if SEND_SMS:
        try:
            send_sms(client, msg)
            print("✉️  SMS sent.")
            ok = True
        except Exception as e:
            print(f"⚠️  SMS failed: {e}")
    if SEND_VOICE:
        try:
            place_call(client, say_text)
            print("📞 Voice call placed.")
            ok = True
        except Exception as e:
            print(f"⚠️  Voice failed: {e}")
    return ok


# ---------------- main cycle ----------------
def run_cycle(pages, page_delay, alerts_enabled):
    """Returns soonest secs (under $5k) seen this cycle for adaptive sleep, or None."""
    headers = build_headers()
    all_listings = []
    seen_ids = set()

    for page in range(1, pages + 1):
        payload = build_payload(page=page)
        print(f"🔎 Requesting page {page} from maestro.lqdt1.com …")
        try:
            r = requests.post(URL, headers=headers, json=payload, timeout=15)
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Page {page}: network error: {e}")
            break

        ct = r.headers.get("Content-Type", "")
        print(f"HTTP {r.status_code} | Content-Type: {ct}")

        if r.status_code == 429:
            print("⚠️ Rate limited (HTTP 429). Stopping this cycle.")
            break
        if r.status_code >= 500:
            print(f"⚠️ Server error {r.status_code}. Stopping this cycle.")
            break
        if "application/json" not in ct.lower():
            print("⚠️ Non-JSON (likely blocked). First 400 chars:")
            print(r.text[:400])
            break

        data = r.json()
        listings = data.get("assetSearchResults", []) or []
        print(f"📄 Page {page}: {len(listings)} items")

        # quick debug dump (titles/make/category) BEFORE filtering
        for i, it in enumerate(listings[:24], start=1):
            print(f"    {i:02d}.", it.get("assetShortDescription"), "|", it.get("makebrand"), "|", it.get("categoryName"))

        if not listings:
            break

        # de-dupe across pages
        for it in listings:
            asset_id = str(it.get("assetId") or it.get("id") or "")
            if asset_id and asset_id in seen_ids:
                continue
            seen_ids.add(asset_id)
            all_listings.append(it)

        # throttle between pages (jitter)
        jitter = random.uniform(-1.0, 1.5)
        time.sleep(max(0.0, page_delay + jitter))

    print(f"\n📋 Received total {len(all_listings)} items across up to {min(pages, page)} page(s)\n")

    # ---- soft filtering into Dump/Bucket ----
    dumps, buckets = [], []

    for idx, item in enumerate(all_listings, start=1):
        title = item.get("assetShortDescription", "No title") or ""
        city  = item.get("locationCity", "Unknown")
        state = item.get("locationState", "")
        desc  = item.get("assetLongDescription", "") or ""
        cat   = item.get("categoryName", "") or ""
        text  = " ".join([title, desc, cat]).lower()

        # price
        bid_cents = None
        for k in ("product_pricecents", "currentBidCents", "currentBid"):
            v = item.get(k)
            bid_cents = parse_bid_cents(v)
            if bid_cents is not None:
                break

        # time remaining: use robust parser that handles multiple fields/formats
        secs = seconds_remaining(item)

        # DEBUG: if still None, show any time-like fields so we can see what's coming back
        if secs is None:
            timeish = {k: v for k, v in item.items()
               if any(t in k.lower() for t in ("time", "end", "remain", "epoch", "close"))}
            print(f"[DEBUG] Could not parse time for asset_id={item.get('assetId') or item.get('id')} -> fields={timeish}")




        # pretty print time
        if isinstance(secs, int):
            h, m = secs // 3600, (secs % 3600) // 60
            end_human = f"{h}h {m}m"
        else:
            end_human = "N/A"

        asset_id = str(item.get("assetId") or item.get("id") or f"idx-{idx}")
        row = {
            "asset_id": asset_id,
            "title": title, "city": city, "state": state,
            "bid_cents": bid_cents, "secs": secs,
            "display": f"[{idx}] {title} | {city}, {state} | 💰 {format_dollars(bid_cents)} | ⏰ {end_human} | id={asset_id}"
        }

        if any(kw in text for kw in DUMP_KWS):
            dumps.append(row)
        if any(kw in text for kw in BUCKET_KWS):
            buckets.append(row)

           

    print("\n=== 🚛 Dump Trucks ===")
    if dumps:
        for r in dumps: print(r["display"])
    else:
        print("No dump trucks found.")

    print("\n=== 🪣 Bucket Trucks ===")
    if buckets:
        for r in buckets: print(r["display"])
    else:
        print("No bucket trucks found.")

    def _eligibility_reasons(itm, is_final: bool):
        reasons = []
        bid_cents = itm["bid_cents"]
        secs = itm["secs"]

        if bid_cents is None:
            reasons.append("no current bid")
        elif bid_cents > ALERT_PRICE_CENTS:
            reasons.append(f"over price cap ({format_dollars(bid_cents)} > {format_dollars(ALERT_PRICE_CENTS)})")

        if not isinstance(secs, int):
            reasons.append("no time parsed")
        else:
            limit = ALERT_TIME_SECS if is_final else EARLY_TIME_SECS
            name  = "ALERT_TIME_SECS" if is_final else "EARLY_TIME_SECS"
            if limit <= 0:
                reasons.append(f"{name} disabled (<= 0)")
            elif secs > limit:
                reasons.append(f"time not low enough ({secs}s > {limit}s)")

        return reasons


    # ---- Alerts ----
    cache = load_cache()
    client = None
    def ensure_client():
        nonlocal client
        if client is None:
            client = twilio_client()
        return client

    soonest = None  # for adaptive sleep

    # Early heads-up (typically SMS-only)
    for group in (dumps, buckets):
        for itm in group:
            bid_cents = itm["bid_cents"]; secs = itm["secs"]
            if isinstance(secs, int) and bid_cents is not None and bid_cents <= ALERT_PRICE_CENTS:
                soonest = secs if (soonest is None or secs < soonest) else soonest

            reasons = _eligibility_reasons(itm, is_final=False)
            if reasons:
                dprint(f"[DEBUG] Early skip id={itm['asset_id']} -> " + "; ".join(reasons))
                continue

            key = f"early-{itm['asset_id']}"
            if already_alerted(cache, key):
                dprint(f"[DEBUG] Early skip id={itm['asset_id']} -> already alerted early")
                continue

            msg = f"GD EARLY: {itm['title']} | {itm['city']}, {itm['state']} | {format_dollars(bid_cents)} | {secs//60}m {secs%60}s"
            print("🔔 " + msg)
            if alerts_enabled and SEND_SMS:
                try:
                    send_sms(ensure_client(), msg)
                    dprint(f"[DEBUG] Early SMS sent id={itm['asset_id']}")
                except Exception as e:
                    print(f"⚠️  Early SMS failed: {e}")
            mark_alerted(cache, key, {"price": bid_cents, "secs": secs})
            save_cache(cache)

    # Final alert: try Voice and/or SMS (based on env)
    for group in (dumps, buckets):
        for itm in group:
            bid_cents = itm["bid_cents"]; secs = itm["secs"]

            if already_alerted(cache, itm["asset_id"]):
                dprint(f"[DEBUG] Final skip id={itm['asset_id']} -> already alerted final")
                continue

            reasons = _eligibility_reasons(itm, is_final=True)
            if reasons:
                dprint(f"[DEBUG] Final skip id={itm['asset_id']} -> " + "; ".join(reasons))
                continue

            try:
                dprint(f"[DEBUG] Final eligible id={itm['asset_id']} -> "
                    f"title='{itm['title']}', price={format_dollars(bid_cents)}, secs={secs}, "
                    f"SEND_SMS={SEND_SMS}, SEND_VOICE={SEND_VOICE}, alerts_enabled={alerts_enabled}")
                if alert_truck(ensure_client(), itm, alerts_enabled=alerts_enabled):
                    mark_alerted(cache, itm["asset_id"], {"price": bid_cents, "secs": secs, "title": itm["title"]})
                    save_cache(cache)
            except Exception as e:
                print(f"❌ Alert error: {e}")


    return soonest

# ---------------- runner (24/7) ----------------
if __name__ == "__main__":
    args = parse_args()

    if args.once:
        run_cycle(args.pages, args.page_delay, alerts_enabled=not args.no_alerts)
        sys.exit(0)

    BASE_SLEEP  = int(os.getenv("BASE_SLEEP",  "600"))  # 10 min
    FAST_SLEEP  = int(os.getenv("FAST_SLEEP",  "120"))  # 2 min
    SNIPE_SLEEP = int(os.getenv("SNIPE_SLEEP", "75"))   # ~1–1.5 min

    while True:
        try:
            soonest = run_cycle(args.pages, args.page_delay, alerts_enabled=not args.no_alerts)
            # Adaptive sleep based on hottest under-$5k item
            sleep_secs = BASE_SLEEP
            if isinstance(soonest, int):
                if soonest <= 10*60:
                    sleep_secs = SNIPE_SLEEP
                elif soonest <= 30*60:
                    sleep_secs = FAST_SLEEP
            time.sleep(sleep_secs + random.randint(-5, 10))
        except requests.exceptions.RequestException as e:
            print(f"Net error, backing off: {e}")
            time.sleep(180)
        except Exception as e:
            print(f"Unexpected error: {e}")
            time.sleep(120)
