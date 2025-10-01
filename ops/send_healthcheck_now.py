# /ops/send_healthcheck_now.py
from src.core.alerts import twilio_client, send_sms
from src.core.utils import format_dollars
from src.sites import govdeals, proxibid

def build_preview():
    rows = []
    rows.extend(govdeals.fetch_listings(pages=1, page_delay=0))
    rows.extend(proxibid.fetch_listings(pages=1, page_delay=0))
    if not rows:
        return "HEALTHCHECK: scraper alive, but 0 listings returned."
    it = rows[0]
    price = format_dollars(it.get("bid_cents"))
    secs = it.get("secs")
    mmss = f"{secs//60}m {secs%60}s" if isinstance(secs, int) else "N/A"
    url = it.get("url") or ""
    base = f"HEALTHCHECK TEST: First: [{it.get('site')}] {it.get('title')} | {it.get('city')}, {it.get('state')} | {price} | {mmss}"
    return f"{base}\n{url}" if url else base

if __name__ == "__main__":
    client = twilio_client()
    msg = build_preview()
    send_sms(client, msg)
    print("✅ Test health SMS sent.")
