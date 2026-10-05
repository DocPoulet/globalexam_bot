import logging
from pathlib import Path


def setup_logger():
    base_dir = Path(__file__).resolve().parent.parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("globalexam_bot")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(
        log_dir / "bot.log",
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(file_handler)

    return logger
