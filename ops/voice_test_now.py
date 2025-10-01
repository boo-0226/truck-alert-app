# /ops/voice_test_now.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.alerts import twilio_client, place_call

if __name__ == "__main__":
    c = twilio_client()
    place_call(c, "Test call from your truck alert system. This is only a test.")
    print("✅ Voice call attempted.")
