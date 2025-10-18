import os
from dotenv import load_dotenv
load_dotenv()

from src.core.utils import is_target_vehicle, annotate_tags, format_dollars
from src.sites import govdeals

ALERT_CAP = int(os.getenv("ALERT_PRICE_DOLLARS", "5000"))
EARLY = int(os.getenv("EARLY_TIME_SECS", "1800"))
FINAL = int(os.getenv("ALERT_TIME_SECS", "600"))
SEND_VOICE = os.getenv("SEND_VOICE", "0")
ALERTS_SMS_ENABLED = os.getenv("ALERTS_SMS_ENABLED", "0")

print("ALERT_PRICE_DOLLARS =", ALERT_CAP)
print("EARLY_TIME_SECS =", EARLY, "FINAL_TIME_SECS =", FINAL)
print("SEND_VOICE =", SEND_VOICE, "ALERTS_SMS_ENABLED =", ALERTS_SMS_ENABLED)

rows = govdeals.fetch_listings(pages=3, page_delay=0.0)

def row_text(r):
    return (r.get("title","") + " " + r.get("description","")).lower()

cands = [r for r in rows if "f-750" in r.get("title","").lower() or "f750" in r.get("title","").lower()]
print(f"\nFound {len(cands)} possible F-750 listings:\n")

for r in cands:
    txt = row_text(r)
    ok = is_target_vehicle(txt)
    tags = annotate_tags(txt)
    bid = r.get("bid_cents")
    secs = r.get("secs")
    print("------------------------------------------------------------")
    print("TITLE:", r.get("title"))
    print("URL:", r.get("url"))
    print("Bid:", format_dollars(bid))
    print("Seconds until close:", secs)
    print("Target match?", ok)
    print("Tags:", tags)
    print("Blocked:", r.get("blocked"))
