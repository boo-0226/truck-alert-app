# /run_proxibid.py
# Purpose: run ONLY Proxibid in its own loop, independent from other sites
import time, random
from src.core.config import BASE_SLEEP, FAST_SLEEP, SNIPE_SLEEP
from src.core.cache import load_cache, save_cache
from src.core.alerts import evaluate_and_alert
from src.core.utils import dprint
from src.sites import proxibid

def one_cycle(alerts_enabled=True):
    listings = proxibid.fetch_listings(pages=1, page_delay=4.0)
    dprint(f"[DEBUG] Proxibid collected {len(listings)} listings")
    cache = load_cache()
    soonest = evaluate_and_alert(cache, listings, alerts_enabled=alerts_enabled)
    save_cache(cache)
    return soonest

if __name__ == "__main__":
    while True:
        try:
            soonest = one_cycle(alerts_enabled=True)
            sleep_secs = BASE_SLEEP
            if isinstance(soonest, int):
                if soonest <= 10*60:
                    sleep_secs = SNIPE_SLEEP
                elif soonest <= 30*60:
                    sleep_secs = FAST_SLEEP
            time.sleep(sleep_secs + random.randint(-5, 10))
        except Exception as e:
            print(f"[Proxibid] loop error: {e}")
            time.sleep(120)
