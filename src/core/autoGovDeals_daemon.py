# file: src/core/govdeals_daemon.py

import json
import logging
import logging.handlers
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from tests.autoGovDealsMoney import scan_govdeals_once
from tests.auto_public_surplus import scan_public_surplus_once


# ---------- CONFIG ----------
LOOP_SLEEP_SECONDS = 300          # 5 minutes between scans
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "govdeals_daemon.log"
HEALTH_FILE = LOG_DIR / "health_govdeals.json"
# ----------------------------


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("govdeals_daemon")
    logger.setLevel(logging.INFO)

    # Small rotating log so disk doesn't fill up.
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Also log to stdout for local testing and service logs.
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
    logger.info("GovDeals/Public Surplus daemon starting up")

    alerts_total = 0

    while True:
        print("\n==============================")
        print("STARTING SCAN CYCLE")
        print("==============================")

        loop_start = datetime.now(timezone.utc)
        logger.info("STARTING SCAN CYCLE at %s", loop_start.isoformat())

        alerts_this_run = 0
        scan_errors = []

        try:
            print("\n=== GOVDEALS SCAN ===")
            logger.info("=== GOVDEALS SCAN ===")
            govdeals_alerts = scan_govdeals_once()
            alerts_this_run += govdeals_alerts
            alerts_total += govdeals_alerts
        except Exception as e:
            message = f"GovDeals scan error: {e}"
            print(message)
            logger.exception(message)
            scan_errors.append(message)

        try:
            print("\n=== PUBLIC SURPLUS SCAN ===")
            logger.info("=== PUBLIC SURPLUS SCAN ===")
            public_surplus_alerts = scan_public_surplus_once()
            alerts_this_run += public_surplus_alerts
            alerts_total += public_surplus_alerts
        except Exception as e:
            message = f"Public Surplus scan error: {e}"
            print(message)
            logger.exception(message)
            scan_errors.append(message)

        write_health(
            status="error" if scan_errors else "ok",
            last_error=" | ".join(scan_errors) if scan_errors else None,
            alerts_this_run=alerts_this_run,
            alerts_total=alerts_total,
        )

        logger.info(
            "Cycle finished. Alerts this run: %s | Total alerts: %s",
            alerts_this_run,
            alerts_total,
        )
        print("\nCycle complete. Sleeping for 300 seconds...")
        logger.info("Cycle complete. Sleeping for %s seconds...", LOOP_SLEEP_SECONDS)
        time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
