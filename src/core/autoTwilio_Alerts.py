# file: core/autoTwilio_Alerts.py
import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER")
TWILIO_TO = os.getenv("TWILIO_TO_NUMBER")

_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_alert(message: str):
    """
    Send both:
      - SMS with full details (message)
      - Phone call with a short spoken alert
    """
    print(f">>> Twilio SMS alert body:\n{message}")

    # 1) Send SMS
    try:
        _client.messages.create(
            body=message,
            from_=TWILIO_FROM,
            to=TWILIO_TO,
        )
        print(">>> Twilio SMS sent.")
    except Exception as e:
        print(f"Twilio SMS send failed: {e}")

    # 2) Place a voice call with a simple message
    try:
        call = _client.calls.create(
            twiml=(
                "<Response>"
                "<Say voice='alice'>GovDeals alert. "
                "A target truck matched your filters. "
                "Check your text message for full details.</Say>"
                "</Response>"
            ),
            from_=TWILIO_FROM,
            to=TWILIO_TO,
        )
        print(f">>> Twilio call started. Call SID: {call.sid}")
    except Exception as e:
        print(f"Twilio call failed: {e}")
