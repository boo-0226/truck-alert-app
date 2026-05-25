# file: ops/send_healthcheck_now.py

from src.core.digest import _send_sms
from src.core.service_health import compose_daily_check_message


if __name__ == "__main__":
    msg = compose_daily_check_message()
    _send_sms(msg)
    print("Daily Check test sent.")
