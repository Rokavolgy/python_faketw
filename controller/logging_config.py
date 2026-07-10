import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DEFAULT_LOG_LEVEL = logging.INFO


def _log_directory():
    local_app_data = os.environ.get("LOCALAPPDATA")
    base_directory = Path(local_app_data) if local_app_data else Path.home()
    return base_directory / "Fwitter" / "logs"


def configure_logging():
    """Configure application logging once and return the active log path."""
    root_logger = logging.getLogger()
    existing_handler = next(
        (
            handler
            for handler in root_logger.handlers
            if getattr(handler, "_fwitter_handler", False)
        ),
        None,
    )
    if existing_handler:
        return getattr(existing_handler, "baseFilename", None)

    level_name = os.environ.get("FWTTER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, DEFAULT_LOG_LEVEL)
    root_logger.setLevel(level)

    formatter = logging.Formatter(LOG_FORMAT)
    log_path = None
    try:
        log_directory = _log_directory()
        log_directory.mkdir(parents=True, exist_ok=True)
        log_path = log_directory / "fwitter.log"
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        file_handler._fwitter_handler = True
        root_logger.addHandler(file_handler)
    except OSError:
        # The app should still start if the user profile is read-only.
        logging.getLogger(__name__).exception("Could not create the application log file")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    console_handler._fwitter_handler = True
    root_logger.addHandler(console_handler)
    return str(log_path) if log_path else None
