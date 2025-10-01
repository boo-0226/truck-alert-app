# /ops/send_digest_now.py
from src.sites import govdeals, proxibid
from src.core.digest import compose_digest, _twilio_client, _send_sms
from src.core.config import DIGEST_SMS_ENABLED

def main():
    rows = []
    rows.extend(govdeals.fetch_listings(pages=3, page_delay=5.0))
    rows.extend(proxibid.fetch_listings(pages=1, page_delay=4.0))
    body = compose_digest(rows)
    print("\n=== DIGEST PREVIEW ===\n")
    print(body)
    print("\n======================\n")
    if DIGEST_SMS_ENABLED:
        _send_sms(body)
        print("SMS sent.")
    else:
        print("DIGEST_SMS_ENABLED=0 (preview only).")

if __name__ == "__main__":
    main()
