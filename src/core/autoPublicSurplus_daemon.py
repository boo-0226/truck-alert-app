# file: src/core/autoPublicSurplus_daemon.py

import json
import logging
import logging.handlers
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tests.auto_public_surplus import scan_public_surplus_once


# ---------- CONFIG ----------
LOOP_SLEEP_SECONDS = 300          # 5 minutes between scans
COOLDOWN_ON_ERROR_SECONDS = 60    # wait 1 minute after an error
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "public_surplus_daemon.log"
HEALTH_FILE = LOG_DIR / "health_public_surplus.json"
# ----------------------------


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("public_surplus_daemon")
    logger.setLevel(logging.INFO)

    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    return logger


def write_health(
    status: str,
    last_error: Optional[str],
    alerts_this_run: int,
    alerts_total: int,
) -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "alerts_this_run": alerts_this_run,
        "alerts_total": alerts_total,
        "last_error": last_error,
    }
    HEALTH_FILE.write_text(json.dumps(payload, indent=2))


def main() -> None:
    logger = setup_logging()
    logger.info("Public Surplus daemon starting up")
    print("\n==============================")
    print("PUBLIC SURPLUS DAEMON STARTED")
    print("==============================")

    alerts_total = 0

    while True:
        loop_start = datetime.now(timezone.utc)
        alerts_this_run = 0

        try:
            print("\n=== PUBLIC SURPLUS SCAN STARTED ===")
            logger.info("Public Surplus scan started at %s", loop_start.isoformat())

            alerts_this_run = scan_public_surplus_once(max_test_listings=None)
            alerts_total += alerts_this_run

            print(f"Public Surplus scan completed. Alerts this run: {alerts_this_run}")
            logger.info(
                "Public Surplus scan completed. Alerts this run: %s | Total alerts: %s",
                alerts_this_run,
                alerts_total,
            )

            write_health(
                status="ok",
                last_error=None,
                alerts_this_run=alerts_this_run,
                alerts_total=alerts_total,
            )

            print(f"Sleeping for {LOOP_SLEEP_SECONDS} seconds before next Public Surplus scan...")
            logger.info("Sleeping %s seconds before next scan", LOOP_SLEEP_SECONDS)
            time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            print(f"Public Surplus scan exception: {e}")
            logger.exception("Public Surplus scan exception: %s", e)

            write_health(
                status="error",
                last_error=str(e),
                alerts_this_run=alerts_this_run,
                alerts_total=alerts_total,
            )

            print(f"Cooling down for {COOLDOWN_ON_ERROR_SECONDS} seconds after exception...")
            logger.info(
                "Cooling down for %s seconds after exception",
                COOLDOWN_ON_ERROR_SECONDS,
            )
            time.sleep(COOLDOWN_ON_ERROR_SECONDS)


if __name__ == "__main__":
    main()
