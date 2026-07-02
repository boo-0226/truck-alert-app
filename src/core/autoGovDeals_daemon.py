# file: src/core/govdeals_daemon.py

import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from tests.autoGovDealsMoney import get_last_scan_error, scan_govdeals_once

try:
    from .decision_log import cleanup_legacy_log_files, cleanup_old_decision_logs
    from .digest import try_send_daily_check
    from .service_health import write_service_health, utc_now_iso
except ImportError:
    from decision_log import cleanup_legacy_log_files, cleanup_old_decision_logs
    from digest import try_send_daily_check
    from service_health import write_service_health, utc_now_iso


# ---------- CONFIG ----------
LOOP_SLEEP_SECONDS = 300          # 5 minutes between scans
COOLDOWN_ON_ERROR_SECONDS = 60    # wait 1 minute after an error
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "govdeals.log"
ERROR_LOG_FILE = LOG_DIR / "govdeals_error.log"
HEALTH_FILE = LOG_DIR / "health_govdeals.json"
MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5
# ----------------------------


class _BelowErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.ERROR


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("govdeals_daemon")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.addFilter(_BelowErrorFilter())
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    file_handler.setLevel(logging.INFO)
    file_handler.addFilter(_BelowErrorFilter())
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    error_file_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
        delay=True,
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(formatter)
    logger.addHandler(error_file_handler)

    logger.propagate = False

    return logger


def write_health(
    scan_started: str,
    scan_completed: str,
    success: bool,
    alerts_this_run: int,
    error_message: Optional[str] = None,
) -> None:
    write_service_health(
        path=HEALTH_FILE,
        source="GovDeals",
        service_name="GovDealsSniper",
        scan_started=scan_started,
        scan_completed=scan_completed,
        success=success,
        alerts_this_run=alerts_this_run,
        error_message=error_message,
    )


def send_daily_check_if_due(logger: logging.Logger) -> None:
    try:
        if try_send_daily_check():
            logger.info("Daily Check SMS sent")
    except Exception as exc:
        logger.exception("Daily Check send failed: %s", exc)


def main() -> None:
    logger = setup_logging()
    logger.info("GovDeals daemon starting up")
    deleted_logs = cleanup_old_decision_logs()
    logger.info("Decision log retention cleanup deleted %s old files", deleted_logs)
    deleted_legacy_logs = cleanup_legacy_log_files()
    logger.info("Legacy log cleanup deleted %s old files", deleted_legacy_logs)

    alerts_total = 0

    while True:
        loop_start = utc_now_iso()
        logger.info("Starting scan loop at %s", loop_start)

        alerts_this_run = 0

        try:
            alerts_this_run = scan_govdeals_once()
            alerts_total += alerts_this_run
            loop_completed = utc_now_iso()
            scan_error = get_last_scan_error()

            write_health(
                scan_started=loop_start,
                scan_completed=loop_completed,
                success=not bool(scan_error),
                alerts_this_run=alerts_this_run,
                error_message=scan_error,
            )
            send_daily_check_if_due(logger)

            if scan_error:
                logger.error("GovDeals scan completed with API error: %s", scan_error)

            logger.info(
                "Scan finished. Alerts this run: %s | Total alerts: %s",
                alerts_this_run,
                alerts_total,
            )
            logger.info("Sleeping %s seconds before next scan", LOOP_SLEEP_SECONDS)
            time.sleep(LOOP_SLEEP_SECONDS)

        except Exception as e:
            logger.exception("Fatal error during scan loop: %s", e)
            loop_completed = utc_now_iso()

            write_health(
                scan_started=loop_start,
                scan_completed=loop_completed,
                success=False,
                alerts_this_run=alerts_this_run,
                error_message=str(e),
            )
            send_daily_check_if_due(logger)

            logger.info(
                "Cooling down for %s seconds after error",
                COOLDOWN_ON_ERROR_SECONDS,
            )
            time.sleep(COOLDOWN_ON_ERROR_SECONDS)


if __name__ == "__main__":
    main()
