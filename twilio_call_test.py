## twilio_call_test.py
from dotenv import load_dotenv
from twilio.rest import Client
import os
import sys

load_dotenv()  # loads .env in the current folder

SID   = os.getenv("TWILIO_SID")
TOKEN = os.getenv("TWILIO_TOKEN")
FROM  = os.getenv("TWILIO_FROM")
TO    = os.getenv("ALERT_TO")

missing = [name for name, val in {
    "TWILIO_SID": SID,
    "TWILIO_TOKEN": TOKEN,
    "TWILIO_FROM": FROM,
    "ALERT_TO": TO,
}.items() if not val]
if missing:
    sys.exit(f"Missing env var(s): {', '.join(missing)}")

client = Client(SID, TOKEN)

twiml = '<Response><Say voice="alice">Test call from your GovDeals alert system. This is only a test.</Say></Response>'

try:
    call = client.calls.create(to=TO, from_=FROM, twiml=twiml)
    print("✅ Call placed. SID:", call.sid)
except Exception as e:
    print("❌ Call failed:", e)
