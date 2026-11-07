"""
Конфигурация сервера управления.

Настройки читаются из server/.env — скопируйте server/.env.example
в server/.env и заполните значения перед первым запуском.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))

# Пароль входа в панель — открытым текстом в .env, его можно просто
# прочитать здесь же, если забылся.
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

# Секретный токен, которым агент авторизуется при обращении к API.
# Должен совпадать с AGENT_TOKEN в agent/.env.
AGENT_TOKEN: str = os.getenv("AGENT_TOKEN", "")

# Секрет для подписи сессионных cookie (вход на сайт).
SESSION_SECRET: str = os.getenv("SESSION_SECRET", "")

LOG_FILE: Path = BASE_DIR / os.getenv("LOG_FILE", "server.log")

# Сколько секунд считать агента «онлайн» после последнего полученного статуса
AGENT_ONLINE_TIMEOUT: int = int(os.getenv("AGENT_ONLINE_TIMEOUT", "20"))

# Сколько последних событий лога хранить в памяти для показа на сайте
LOG_HISTORY_SIZE: int = int(os.getenv("LOG_HISTORY_SIZE", "200"))


def validate() -> None:
    missing = []
    if not ADMIN_PASSWORD:
        missing.append("ADMIN_PASSWORD")
    if not AGENT_TOKEN:
        missing.append("AGENT_TOKEN")
    if not SESSION_SECRET:
        missing.append("SESSION_SECRET")
    if missing:
        raise RuntimeError(
            "В server/.env не заданы обязательные настройки: " + ", ".join(missing)
        )
