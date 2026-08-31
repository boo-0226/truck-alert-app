# file: src/core/collect.py
from __future__ import annotations

import os
import time as _time
from typing import Dict, List

# --- local utilities (be defensive if modules move) ---
try:
    from utils import dprint
except Exception:  # pragma: no cover
    def dprint(*args, **kwargs):
        print(*args)

try:
    from utils import add_error
except Exception:  # pragma: no cover
    def add_error(site: str, kind: str, msg: str):
        dprint(f"[ERR] [{site}] {kind}: {msg}")

# --- site adapters ---
# Keep these imports aligned with your project layout.
# If your modules live under src.sites, leave as-is. Otherwise, adjust.
from src.sites import govdeals
from src.sites import renebates
from src.sites import proxibid

from src.core.utils import format_dollars, is_target_vehicle


STRATEGY_PASSTHROUGH_FIELDS = (
    "target_strategy",
    "strategies_considered",
    "classification",
    "discovery_reasons",
    "decision_reasons",
    "positive_signals",
    "negative_signals",
    "block_reasons",
    "score",
    "consumer_gas_score",
    "consumer_gas_model_key",
    "next_action",
    "carvana_score",
    "carvana_model_key",
    "carvana_positive_signals",
    "carvana_negative_signals",
    "carvana_block_reasons",
    "carvana_next_action",
    "vin",
    "year",
    "model_year",
    "vehicle_age",
    "make",
    "model",
    "trim",
    "cab",
    "drivetrain",
    "engine",
    "fuel",
    "mileage",
    "mileage_display",
    "parsed_make",
    "parsed_model",
    "parsed_year",
    "parsed_vehicle_age",
    "parsed_engine",
    "parsed_mileage",
    "parsed_trim",
    "parsed_cab",
    "parsed_drivetrain",
    "parsed_fuel",
)


# ======================
# Config (env-driven)
# ======================
def _get_env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def _get_env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

# GovDeals knobs (new)
GOVDEALS_PAGES: int = _get_env_int("GOVDEALS_PAGES", 20)
GOVDEALS_PAGE_DELAY: float = _get_env_float("GOVDEALS_PAGE_DELAY", 4.5)

# Optional knobs for other sites (kept for symmetry; use if you wire them)
RENEBATES_PAGES: int = _get_env_int("RENEBATES_PAGES", 2)
RENEBATES_DELAY_SECS: float = _get_env_float("RENEBATES_DELAY_SECS", 1.0)

PROXIBID_PAGES_MAX: int = _get_env_int("PROXIBID_PAGES_MAX", 30)  # already in your .env for other code paths


def _normalize_row(row: Dict) -> Dict:
    """
    Keep adapter rows flexible, but guarantee the old alert-facing basics.
    Unknown fields are intentionally preserved for strategy/report metadata.
    """
    out = dict(row or {})

    text_for_target = " ".join(
        str(out.get(key) or "")
        for key in ("title", "desc", "description", "category", "city", "state", "tags")
    )

    if out.get("target") is None:
        out["target"] = is_target_vehicle(text_for_target)
    if out.get("blocked") is None:
        out["blocked"] = not bool(out.get("target", False))
    if "bid_display" not in out:
        out["bid_display"] = format_dollars(out.get("bid_cents"))

    for field in STRATEGY_PASSTHROUGH_FIELDS:
        if field in row:
            out[field] = row[field]

    return out


# ======================
# Collectors per site
# ======================
def _collect_govdeals() -> List[Dict]:
    """
    Collect Transportation listings from GovDeals.

    Uses env:
      - GOVDEALS_PAGES (default 20) → max pages to scan (stops early when a page is empty)
      - GOVDEALS_PAGE_DELAY (default 4.5s) → polite delay between pages (with jitter inside govdeals.py, if any)
    """
    rows: List[Dict] = []
    try:
        dprint(f"[GD] collect: pages={GOVDEALS_PAGES} delay={GOVDEALS_PAGE_DELAY}")
        rows = govdeals.fetch_listings()
        dprint(f"[GD] collect done: {len(rows)} rows")
    except Exception as e:
        add_error("GovDeals", "collect", f"exception: {e}")
        dprint(f"[GD] collect exception: {e}")
    return rows


def _collect_renebates() -> List[Dict]:
    rows: List[Dict] = []
    try:
        # If your renebates.fetch_listings accepts pages/delay, pass them.
        # If not, it will ignore extra args; adjust as per your adapter signature.
        dprint(f"[RB] collect: pages={RENEBATES_PAGES} delay={RENEBATES_DELAY_SECS}")
        rows = renebates.fetch_listings(pages=RENEBATES_PAGES, page_delay=RENEBATES_DELAY_SECS)
        dprint(f"[RB] collect done: {len(rows)} rows")
    except TypeError:
        # Older signature without knobs
        rows = renebates.fetch_listings()
        dprint(f"[RB] collect done (no knobs): {len(rows)} rows")
    except Exception as e:
        add_error("ReneBates", "collect", f"exception: {e}")
        dprint(f"[RB] collect exception: {e}")
    return rows


def _collect_proxibid() -> List[Dict]:
    rows: List[Dict] = []
    try:
        # Your proxibid module may already read its own env (PROXIBID_PAGES_MAX, test knobs, etc.)
        dprint(f"[PX] collect: (proxibid adapter controls its own paging)")
        rows = proxibid.fetch_listings()
        dprint(f"[PX] collect done: {len(rows)} rows")
    except Exception as e:
        add_error("Proxibid", "collect", f"exception: {e}")
        dprint(f"[PX] collect exception: {e}")
    return rows


# ======================
# Public entrypoints
# ======================
def collect_all() -> List[Dict]:
    """
    Collect from all sites, merge, dedupe, return normalized rows.

    This function used to cap GovDeals at pages=2 in some versions.
    That is removed: GovDeals depth is controlled by GOVDEALS_PAGES in .env.
    """
    # clear/rotate any site-level error buffers if your project uses it
    try:
        from utils import clear_errors  # optional
        clear_errors()
    except Exception:
        pass

    out: List[Dict] = []

    # Order can matter if you want GovDeals first
    gd = _collect_govdeals()
    rb = _collect_renebates()
    px = _collect_proxibid()

    # Merge
    out.extend(gd)
    out.extend(rb)
    out.extend(px)

    # Dedupe by stable key (prefer asset_id; fallback to url)
    seen = set()
    deduped: List[Dict] = []
    for r in out:
        key = str(r.get("asset_id") or r.get("id") or r.get("url") or "")
        if not key:
            # last resort: hash title+site if absolutely nothing else
            key = f"{r.get('site','')}::{r.get('title','')}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_normalize_row(r))

    dprint(f"[COLLECT] merged={len(out)} deduped={len(deduped)}")
    return deduped


def collect_upcoming() -> List[Dict]:
    """
    Convenience wrapper if your API route maps /api/listings?mode=upcoming here.
    Keeps the name explicit in case you add other modes later.
    """
    return collect_all()


# If this module is invoked directly for a quick test:
if __name__ == "__main__":
    rows = collect_all()
    dprint(f"[COLLECT] final rows: {len(rows)}")
    # tiny peek to validate shape
    for r in rows[:5]:
        dprint("[ROW]", r.get("site"), r.get("title"), r.get("secs"), r.get("bid_cents"))
