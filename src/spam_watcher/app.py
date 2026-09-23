"""Entry point: build config, wire dependencies, and run the poll loop (FR-001/FR-012)."""

from __future__ import annotations

import logging
import time

from .config import ConfigError, load_settings
from .detector import SpamDetectorClient
from .logging_setup import configure_logging
from .mailbox import Mailbox
from .notifier import Notifier
from .processor import Processor


def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        configure_logging()
        logging.getLogger("spam_watcher").error("config_invalid: %s", exc)
        return 2

    configure_logging(secrets=settings.secret_values())
    log = logging.getLogger("spam_watcher.app")
    log.info("startup", extra={"poll_interval_seconds": settings.poll_interval_seconds})

    detector = SpamDetectorClient(settings)
    processor = Processor(settings, Mailbox(settings), detector, Notifier(settings))

    try:
        while True:
            try:
                processor.run_once()
            except Exception:  # noqa: BLE001 - never let one poll cycle crash the watcher
                log.exception("poll_cycle_error")
            time.sleep(settings.poll_interval_seconds)
    finally:
        detector.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
