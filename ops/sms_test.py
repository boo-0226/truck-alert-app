# /ops/sms_test.py
from src.core.alerts import twilio_client, send_sms

if __name__ == "__main__":
    c = twilio_client()
    send_sms(c, "SMS TEST: truck-alert-app is configured. If you see this, SMS works.")
    print("✅ Sent test SMS.")
