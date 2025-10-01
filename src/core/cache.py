# /src/core/cache.py
# Purpose: de-dupe across sites
import json, time
from pathlib import Path

CACHE_PATH = Path(".alert_cache.json")
CACHE_TTL_SECS = 2 * 60 * 60

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

def mark_alerted(cache, key, meta):
    cache[key] = {"ts": time.time(), "meta": meta}
