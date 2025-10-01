# /run_multi.py
import io, sys, time, random, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
from src.core.config import (
    BASE_SLEEP, FAST_SLEEP, SNIPE_SLEEP,
    HEALTHCHECK_ENABLED, HEALTHCHECK_MINUTES,
    DIGEST_ENABLED, DIGEST_LOCAL_HOUR,
)
from src.core.cache import load_cache, save_cache
from src.core.alerts import evaluate_and_alert, twilio_client, send_sms
from src.core.healthcheck import should_send, mark_sent
from src.core.digest import try_send_digest
from src.core.utils import dprint, format_dollars
from src.sites import govdeals, proxibid, renebates

# --- ReneBates round-robin state ---
RB_STATE = ".renebates_state.json"

def _load_rb_offset() -> int:
    try:
        with open(RB_STATE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return int(data.get("offset", 0))
    except Exception:
        return 0

def _save_rb_offset(offset: int) -> None:
    try:
        with open(RB_STATE, "w", encoding="utf-8") as f:
            json.dump({"offset": int(offset)}, f)
    except Exception:
        pass

def one_cycle(alerts_enabled=True):
    rows = []
    # GovDeals
    rows.extend(govdeals.fetch_listings(pages=5, page_delay=6.0))
    # Proxibid
    rows.extend(proxibid.fetch_listings(pages=1, page_delay=4.0))
    # ReneBates (use env knobs for speed)
        # ReneBates (use env knobs + optional time budget)
    rb_pages = int(os.getenv("RENEBATES_PAGES", "2"))
    rb_delay = float(os.getenv("RENEBATES_DELAY_SECS", "1.0"))
    budget = float(os.getenv("RENEBATES_BUDGET_SECS", "12"))  # max seconds per cycle

    start = time.time()
    try:
        rb_rows = renebates.fetch_listings(pages=rb_pages, page_delay=rb_delay)
        if time.time() - start > budget:
            print("[Renebates] time budget exceeded; moving on")
        rows.extend(rb_rows)
    except Exception as e:
        print(f"[Renebates] fetch error (continuing): {e}")

    # Only keep items adapters didn’t block
    rows = [r for r in rows if not r.get("blocked", False)]
    dprint(f"[DEBUG] collected {len(rows)} listings from all sites (after filter)")

    cache = load_cache()
    soonest = evaluate_and_alert(cache, rows, alerts_enabled=alerts_enabled)
    save_cache(cache)
    return soonest, rows



def _compose_health_msg(rows):
    n = len(rows)
    if n == 0:
        return "HEALTHCHECK: scraper alive, but 0 listings returned."
    it = rows[0]
    title = it.get("title") or "Untitled"
    site  = it.get("site") or "Unknown"
    city  = it.get("city") or "Unknown"
    state = it.get("state") or ""
    price = format_dollars(it.get("bid_cents"))
    secs  = it.get("secs")
    mmss  = f"{secs//60}m {secs%60}s" if isinstance(secs, int) else "N/A"
    url   = it.get("url") or ""
    base  = f"HEALTHCHECK OK: {n} listings. First: [{site}] {title} | {city}, {state} | {price} | {mmss}"
    return f"{base}\n{url}" if url else base

if __name__ == "__main__":
    while True:
        try:
            soonest, rows = one_cycle(alerts_enabled=True)

            # Daily digest (one SMS listing all targets ending within the next N hours)
            try:
                if DIGEST_ENABLED:
                    sent = try_send_digest(rows, DIGEST_LOCAL_HOUR)
                    if sent:
                        print("📬 Daily digest SMS sent.")
            except Exception as e:
                print(f"⚠️ Digest send failed: {e}")

            # Healthcheck heartbeat
            if HEALTHCHECK_ENABLED and should_send(None, HEALTHCHECK_MINUTES):
                try:
                    client = twilio_client()
                    send_sms(client, _compose_health_msg(rows))
                    print("💓 Healthcheck SMS sent.")
                    mark_sent()
                except Exception as e:
                    print(f"⚠️ Healthcheck send failed: {e}")

            # Adaptive sleep
            sleep_secs = BASE_SLEEP
            if isinstance(soonest, int):
                if soonest <= 10 * 60:
                    sleep_secs = SNIPE_SLEEP
                elif soonest <= 30 * 60:
                    sleep_secs = FAST_SLEEP

            time.sleep(sleep_secs + random.randint(-5, 10))
        except Exception as e:
            print(f"Unexpected loop error: {e}")
            time.sleep(120)
