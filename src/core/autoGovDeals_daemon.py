# file: src/core/govdeals_daemon.py

import json
import logging
import logging.handlers
import time
from datetime import datetime, timezone
from pathlib import Path


from tests.autoGovDealsMoney import scan_govdeals_once
from typing import Optional


# ---------- CONFIG ----------
LOOP_SLEEP_SECONDS = 300          # 5 minutes between scans
COOLDOWN_ON_ERROR_SECONDS = 60    # wait 1 minute after an error
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "govdeals_daemon.log"
HEALTH_FILE = LOG_DIR / "health_govdeals.json"
# ----------------------------


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("govdeals_daemon")
    logger.setLevel(logging.INFO)

    # Small rotating log so disk doesn't fill up
    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=1_000_000, backupCount=3
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Also log to stdout (useful for local testing and systemd)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    return logger


def write_health(status: str,
                 last_error: Optional[str],
                 alerts_this_run: int,
                 alerts_total: int) -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,  # "ok" or "error"
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "alerts_this_run": alerts_this_run,
        "alerts_total": alerts_total,
        "last_error": last_error,
    }
    HEALTH_FILE.write_text(json.dumps(payload, indent=2))


def main() -> None:
    logger = setup_logging()
    logger.info("GovDeals daemon starting up")

    alerts_total = 0

    while True:
        loop_start = datetime.now(timezone.utc)
        logger.info("Starting scan loop at %s", loop_start.isoformat())

        alerts_this_run = 0

        try:
            # 🔁 One *full* pass of your existing logic
            alerts_this_run = scan_govdeals_once()
            alerts_total += alerts_this_run

            write_health(
                status="ok",
                last_error=None,
                alerts_this_run=alerts_this_run,
                alerts_total=alerts_total,
            )

            logger.info(
                "Scan finished. Alerts this run: %s | Total alerts: %s",
                alerts_this_run,
                alerts_total,
            )
            logger.info("Sleeping %s seconds before next scan", LOOP_SLEEP_SECONDS)
            time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            # Never let one crash kill the whole daemon
            logger.exception("Fatal error during scan loop: %s", e)

            write_health(
                status="error",
                last_error=str(e),
                alerts_this_run=alerts_this_run,
                alerts_total=alerts_total,
            )

            logger.info(
                "Cooling down for %s seconds after error",
                COOLDOWN_ON_ERROR_SECONDS,
            )
            time.sleep(COOLDOWN_ON_ERROR_SECONDS)


if __name__ == "__main__":
    main()
