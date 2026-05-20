# file: src/core/autoPublicSurplus_daemon.py

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    from .decision_log import cleanup_legacy_log_files, cleanup_old_decision_logs
except ImportError:
    from decision_log import cleanup_legacy_log_files, cleanup_old_decision_logs


# ---------- CONFIG ----------
LOOP_SLEEP_SECONDS = 300          # 5 minutes between scans
LOG_DIR = Path("logs")
HEALTH_FILE = LOG_DIR / "health_public_surplus.json"
# ----------------------------


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("public_surplus_daemon")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    logger.propagate = False

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
    deleted_logs = cleanup_old_decision_logs()
    logger.info("Decision log retention cleanup deleted %s old files", deleted_logs)
    deleted_legacy_logs = cleanup_legacy_log_files()
    logger.info("Legacy log cleanup deleted %s old files", deleted_legacy_logs)
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

            from tests.auto_public_surplus import scan_public_surplus_once

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

        except Exception as e:
            print(f"Error: {e}")
            logger.exception("Public Surplus scan exception: %s", e)

            write_health(
                status="error",
                last_error=str(e),
                alerts_this_run=alerts_this_run,
                alerts_total=alerts_total,
            )

        print("Sleeping 300 seconds...")
        logger.info("Sleeping %s seconds before next scan", LOOP_SLEEP_SECONDS)
        time.sleep(LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
