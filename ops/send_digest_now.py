# file: ops/send_digest_now.py

from src.core.config import DIGEST_SMS_ENABLED
from src.core.digest import _send_sms
from src.core.service_health import compose_daily_check_message


def main():
    body = compose_daily_check_message()
    print("\n=== DAILY CHECK PREVIEW ===\n")
    print(body)
    print("\n===========================\n")
    if DIGEST_SMS_ENABLED:
        _send_sms(body)
        print("Daily Check SMS sent.")
    else:
        print("DIGEST_SMS_ENABLED=0 (preview only).")


if __name__ == "__main__":
    main()
