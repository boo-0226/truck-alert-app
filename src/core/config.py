# /src/core/config.py
# Purpose: load env + global thresholds/channels in one place
import os
from dotenv import load_dotenv

load_dotenv()

def _int_env(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    try:
        return int(v) if v else default
    except ValueError:
        return default

def _dollars_to_cents_env(name: str, default_dollars: int) -> int:
    v = os.getenv(name, "").strip().replace("$","").replace(",","")
    try:
        return int(round(float(v) * 100)) if v else default_dollars * 100
    except ValueError:
        return default_dollars * 100

DEBUG               = os.getenv("DEBUG", "0").lower() in ("1","true","yes","y")
SEND_SMS            = os.getenv("SEND_SMS", "1").lower() in ("1","true","yes","y")
SEND_VOICE          = os.getenv("SEND_VOICE", "1").lower() in ("1","true","yes","y")
ALERT_PRICE_CENTS   = _dollars_to_cents_env("ALERT_PRICE_DOLLARS", 5000)
ALERT_TIME_SECS     = _int_env("ALERT_TIME_SECS", 600)     # 10 min default per your latest
EARLY_TIME_SECS     = _int_env("EARLY_TIME_SECS", 0)
BASE_SLEEP          = _int_env("BASE_SLEEP", 600)
FAST_SLEEP          = _int_env("FAST_SLEEP", 120)
SNIPE_SLEEP         = _int_env("SNIPE_SLEEP", 45)

TWILIO_SID          = os.getenv("TWILIO_SID", "")
TWILIO_TOKEN        = os.getenv("TWILIO_TOKEN", "")
TWILIO_FROM         = os.getenv("TWILIO_FROM", "")
ALERT_TO            = os.getenv("ALERT_TO", "")

# Daily digest (SMS list of upcoming trucks)
DIGEST_ENABLED      = os.getenv("DIGEST_ENABLED", "1").lower() in ("1","true","yes","y")
DIGEST_LOCAL_HOUR   = _int_env("DIGEST_LOCAL_HOUR", 9)  # send after this local hour
DIGEST_HOURS        = _int_env("DIGEST_HOURS", 48)      # list items ending within next N hours
DIGEST_MAX_LINES    = _int_env("DIGEST_MAX_LINES", 10)  # limit lines in SMS


# Prefer Messaging Service for SMS (handles carrier rules/A2P better)
TWILIO_MESSAGING_SID = os.getenv("TWILIO_MESSAGING_SID", "")


# Healthcheck (daily heartbeat SMS)
HEALTHCHECK_ENABLED = os.getenv("HEALTHCHECK_ENABLED", "1").lower() in ("1","true","yes","y")
HEALTHCHECK_MINUTES = _int_env("HEALTHCHECK_MINUTES", 24 * 60)  # default: once per day

# Separate SMS controls (so digest can send while per-item alerts are muted)
ALERTS_SMS_ENABLED  = os.getenv("ALERTS_SMS_ENABLED", "0").lower() in ("1","true","yes","y")  # per-vehicle SMS
DIGEST_SMS_ENABLED  = os.getenv("DIGEST_SMS_ENABLED", "1").lower() in ("1","true","yes","y")  # daily list SMS


