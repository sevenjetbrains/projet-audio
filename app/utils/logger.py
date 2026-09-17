"""Configuration du logging applicatif → logs/application.log."""

import logging

from app.config.constants import LOG_FILE_NAME
from app.config.settings import LOGS_DIR, ensure_runtime_dirs

_configured = False


def setup_logging() -> logging.Logger:
    global _configured

    logger = logging.getLogger("audiocut")

    if _configured:
        return logger

    ensure_runtime_dirs()

    log_path = LOGS_DIR / LOG_FILE_NAME
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    console_handler = logging.StreamHandler()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _configured = True
    return logger
