# /run_multi.py
import io
import json
import os
import random
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from src.core.config import (
    BASE_SLEEP,
    DIGEST_ENABLED,
    DIGEST_LOCAL_HOUR,
    FAST_SLEEP,
    SNIPE_SLEEP,
)
from src.core.alerts import evaluate_and_alert
from src.core.cache import load_cache, save_cache
from src.core.digest import try_send_digest
from src.core.utils import dprint
from src.sites import govdeals, proxibid, renebates


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

    rows.extend(govdeals.fetch_listings(pages=5, page_delay=6.0))
    rows.extend(proxibid.fetch_listings(pages=1, page_delay=4.0))

    rb_pages = int(os.getenv("RENEBATES_PAGES", "2"))
    rb_delay = float(os.getenv("RENEBATES_DELAY_SECS", "1.0"))
    budget = float(os.getenv("RENEBATES_BUDGET_SECS", "12"))

    start = time.time()
    try:
        rb_rows = renebates.fetch_listings(pages=rb_pages, page_delay=rb_delay)
        if time.time() - start > budget:
            print("[Renebates] time budget exceeded; moving on")
        rows.extend(rb_rows)
    except Exception as e:
        print(f"[Renebates] fetch error (continuing): {e}")

    rows = [row for row in rows if not row.get("blocked", False)]
    dprint(f"[DEBUG] collected {len(rows)} listings from all sites (after filter)")

    cache = load_cache()
    soonest = evaluate_and_alert(cache, rows, alerts_enabled=alerts_enabled)
    save_cache(cache)
    return soonest, rows


if __name__ == "__main__":
    while True:
        try:
            soonest, rows = one_cycle(alerts_enabled=True)

            try:
                if DIGEST_ENABLED:
                    sent = try_send_digest(rows, DIGEST_LOCAL_HOUR)
                    if sent:
                        print("Daily Check SMS sent.")
            except Exception as e:
                print(f"Daily Check send failed: {e}")

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
