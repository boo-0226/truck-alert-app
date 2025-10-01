# /ops/force_alert.py
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.alerts import evaluate_and_alert
from src.core.cache import load_cache, save_cache

if __name__ == "__main__":
    cache = load_cache()
    listings = [{
        "site": "GovDeals",
        "asset_id": f"test-{int(time.time())}",
        "title": "FORCE TEST TRUCK",
        "city": "Dallas", "state": "TX",
        "bid_cents": 123400,         # $1,234
        "secs": 120                  # 2 minutes -> should meet any alert window
    }]
    soonest = evaluate_and_alert(cache, listings, alerts_enabled=True)
    save_cache(cache)
    print("soonest:", soonest)
