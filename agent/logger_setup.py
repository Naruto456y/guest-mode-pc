"""
Логирование агента: все события пишутся в файл (с ротацией, чтобы лог
не рос бесконечно) и дублируются в консоль. Остальные модули получают
логгер через logging.getLogger("guest_agent.<имя_модуля>").
"""
import logging
from logging.handlers import RotatingFileHandler

import config


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("guest_agent")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        # Логгер уже настроен (повторный вызов setup_logging) — не дублируем хендлеры
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    return logger
