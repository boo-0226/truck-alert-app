# /src/core/alerts.py
# Purpose: central alert engine (Twilio + filter logic) used by all sites

from typing import Iterable, Dict, Optional

from src.core.config import (
    ALERT_PRICE_CENTS,
    ALERT_TIME_SECS,
    EARLY_TIME_SECS,
    SEND_VOICE,
    TWILIO_SID,
    TWILIO_TOKEN,
    TWILIO_FROM,
    ALERT_TO,
    DEBUG,
    ALERTS_SMS_ENABLED,
    TWILIO_MESSAGING_SID,   # <-- include here
)
from src.core.utils import dprint, format_dollars
from src.core.cache import mark_alerted, save_cache

try:
    from twilio.rest import Client
except Exception:
    Client = None


def twilio_client():
    if Client is None:
        raise RuntimeError("Twilio client not available. pip install twilio")
    if not (TWILIO_SID and TWILIO_TOKEN):
        raise RuntimeError("Missing TWILIO_SID/TWILIO_TOKEN")
    return Client(TWILIO_SID, TWILIO_TOKEN)


def send_sms(client, body):
    try:
        if TWILIO_MESSAGING_SID:
            msg = client.messages.create(
                to=ALERT_TO,
                messaging_service_sid=TWILIO_MESSAGING_SID,
                body=body
            )
        else:
            msg = client.messages.create(
                to=ALERT_TO,
                from_=TWILIO_FROM,
                body=body
            )
        print(f"✅ SMS sent successfully (SID={msg.sid})")
        return True
    except Exception as e:
        print(f"❌ SMS failed: {e}")
        return False



def place_call(client, say_text: str):
    twiml = f'<Response><Say voice="Polly.Matthew">{say_text}</Say></Response>'
    client.calls.create(to=ALERT_TO, from_=TWILIO_FROM, twiml=twiml)


def evaluate_and_alert(cache: dict, listings: Iterable[Dict], alerts_enabled: bool) -> Optional[int]:
    """
    listings: iterable of dicts with keys:
      site, asset_id, title, city, state, bid_cents, secs
    Returns: soonest secs (under price cap) for adaptive sleep.
    """
    client = None

    def _reasons(itm, is_final: bool):
        r = []
        bid = itm.get("bid_cents")
        secs = itm.get("secs")
        if bid is None: r.append("no current bid")
        elif bid > ALERT_PRICE_CENTS: r.append(f"over price cap")
        if not isinstance(secs, int): r.append("no time parsed")
        else:
            limit = ALERT_TIME_SECS if is_final else EARLY_TIME_SECS
            if limit <= 0: r.append(("final" if is_final else "early") + " window disabled")
            elif secs > limit: r.append(f"time too high ({secs}s > {limit}s)")
        return r


    def ensure_client():
        nonlocal client
        if client is None:
            client = twilio_client()
        return client

    soonest: Optional[int] = None

    for itm in listings:
        # Enforce specialty targeting here (single place)
        if itm.get("blocked"):
            continue
        if not itm.get("target", False):
            continue

        bid = itm.get("bid_cents")
        secs = itm.get("secs")



        # Track soonest under price cap for adaptive sleep
        # Track soonest under price cap for adaptive sleep (must be > 0)
        if isinstance(secs, int) and secs > 0 and bid is not None and bid <= ALERT_PRICE_CENTS:
            soonest = secs if (soonest is None or secs < soonest) else soonest


                # ---- Early (30-minute window) — CALL + optional SMS ----
        # only consider items that still have time left
        if EARLY_TIME_SECS > 0 and isinstance(secs, int) and secs > 0 and bid is not None:
            if bid <= ALERT_PRICE_CENTS and 0 < secs <= EARLY_TIME_SECS:

                key = f"early-{itm['site']}-{itm['asset_id']}"
                if key not in cache:
                    dollars = format_dollars(bid)
                    mins, rem = secs // 60, secs % 60
                    url = itm.get("url")

                    # Voice: if we have a link, tell user we texted it
                    if url:
                        say_text = (
                            f"Early alert. {itm['site']}. {itm['title']}. "
                            f"Current bid {dollars}. Time left {mins} minutes {rem} seconds. "
                            f"I have texted you the link."
                        )
                    else:
                        say_text = (
                            f"Early alert. {itm['site']}. {itm['title']}. "
                            f"Current bid {dollars}. Time left {mins} minutes {rem} seconds."
                        )

                    # SMS body (put link on its own line so it’s clickable)
                    msg = (
                        f"{itm['site']} EARLY: {itm['title']} | {itm['city']}, {itm['state']} | "
                        f"{dollars} | {mins}m {rem}s"
                    )
                    if url:
                        msg += f"\n{url}"

                    print("🔔 " + msg.replace("\n", " | "))

                    # Voice call at 30-minute mark
                    if alerts_enabled and SEND_VOICE:
                        try:
                            place_call(ensure_client(), say_text)
                            print("📞 Early voice call placed.")
                        except Exception as e:
                            print(f"⚠️ Early voice failed: {e}")

                    # Optional SMS at 30-minute mark (behind your flag)
                    if alerts_enabled and ALERTS_SMS_ENABLED:
                        try:
                            send_sms(ensure_client(), msg)
                            print("✉️  Early SMS sent.")
                        except Exception as e:
                            print(f"⚠️ Early SMS failed: {e}")

                    mark_alerted(cache, key, {"price": bid, "secs": secs})
                    save_cache(cache)

        # ---- Final (voice/SMS) ----
        # must have a positive time remaining to alert, under price cap, and within final window
        if isinstance(secs, int) and secs > 0 and bid is not None \
           and bid <= ALERT_PRICE_CENTS and secs <= ALERT_TIME_SECS:

            final_key = f"final-{itm['site']}-{itm['asset_id']}"
            if final_key in cache:
                continue

            dollars = format_dollars(bid)
            mins, rem = secs // 60, secs % 60
            url = itm.get("url")

            # Voice: mention link only if we’ll text one
            if url:
                say_text = (
                    f"{itm['site']} alert. {itm['title']}. "
                    f"Current bid {dollars}. Time left {mins} minutes {rem} seconds. "
                    f"I have texted you the link."
                )
            else:
                say_text = (
                    f"{itm['site']} alert. {itm['title']}. "
                    f"Current bid {dollars}. Time left {mins} minutes {rem} seconds."
                )

            # SMS body + URL on new line if present
            line = (
                f"{itm['site']} ALERT: {itm['title']} | {itm['city']}, {itm['state']} | "
                f"{dollars} | {mins}m {rem}s"
            )
            if url:
                line += f"\n{url}"

            print("🚨 " + line.replace("\n", " | "))

            ok = False
            if alerts_enabled and SEND_VOICE:
                try:
                    place_call(ensure_client(), say_text)
                    print("📞 Voice call placed.")
                    ok = True
                except Exception as e:
                    print(f"⚠️ Voice failed: {e}")

            if alerts_enabled and ALERTS_SMS_ENABLED:
                try:
                    send_sms(ensure_client(), line)
                    print("✉️  SMS sent.")
                    ok = True
                except Exception as e:
                    print(f"⚠️ SMS failed: {e}")

            if ok:
                mark_alerted(cache, final_key, {"price": bid, "secs": secs, "title": itm["title"]})
                save_cache(cache)

    return soonest
