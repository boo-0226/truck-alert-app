# /ops/print_config.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core import config as c

print("DEBUG:", c.DEBUG)
print("SEND_VOICE:", c.SEND_VOICE)
print("ALERT_PRICE_CENTS:", c.ALERT_PRICE_CENTS)
print("ALERT_TIME_SECS:", c.ALERT_TIME_SECS)
print("EARLY_TIME_SECS:", c.EARLY_TIME_SECS)
print("ALERTS_SMS_ENABLED:", c.ALERTS_SMS_ENABLED)
print("DIGEST_SMS_ENABLED:", c.DIGEST_SMS_ENABLED)
print("DIGEST_ENABLED:", c.DIGEST_ENABLED, "HOUR:", c.DIGEST_LOCAL_HOUR, "HRS:", c.DIGEST_HOURS)
print("HEALTHCHECK_ENABLED:", c.HEALTHCHECK_ENABLED, "MINUTES:", c.HEALTHCHECK_MINUTES)
print("TWILIO_SID set:", bool(c.TWILIO_SID))
print("TWILIO_TOKEN set:", bool(c.TWILIO_TOKEN))
print("TWILIO_FROM:", c.TWILIO_FROM)
print("TWILIO_MESSAGING_SID:", bool(c.TWILIO_MESSAGING_SID))
print("ALERT_TO:", c.ALERT_TO)
