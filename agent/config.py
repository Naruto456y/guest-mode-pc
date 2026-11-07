"""
Конфигурация агента «Гостевой режим ПК».

Все настройки читаются из файла .env, который лежит рядом с этим файлом
(agent/.env). Перед первым запуском скопируйте .env.example в .env и
заполните значения.

ВАЖНО про DRY_RUN:
    DRY_RUN=true  -> тестовый режим. Любое потенциально опасное действие
                      (выключение ПК, закрытие программ, перевёрнутый
                      экран и т.д.) НЕ выполняется, а только пишется
                      в лог и показывается на сайте как
                      "[DRY_RUN] сделал бы то-то".
    DRY_RUN=false -> боевой режим. Действия выполняются по-настоящему.

    Переключается только здесь, руками, на этом ПК. С сайта управления
    изменить DRY_RUN нельзя — это сделано специально, чтобы никто
    не включил боевой режим удалённо.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "да")


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# === ТЕСТОВЫЙ РЕЖИМ (см. докстринг модуля) ===
DRY_RUN: bool = _get_bool("DRY_RUN", True)

# === Подключение к серверу управления ===
SERVER_URL: str = os.getenv("SERVER_URL", "http://127.0.0.1:8000").rstrip("/")
AGENT_TOKEN: str = os.getenv("AGENT_TOKEN", "")

# === Интервалы опроса и отчётности ===
POLL_INTERVAL: float = _get_float("POLL_INTERVAL", 1.0)               # пауза главного цикла (команды приходят мгновенно через long-poll)
POLL_WAIT: float = _get_float("POLL_WAIT", 20.0)                     # сколько сервер держит запрос команд открытым
STATUS_INTERVAL: float = _get_float("STATUS_INTERVAL", 5.0)           # как часто слать статус/процессы
SCREENSHOT_INTERVAL: float = _get_float("SCREENSHOT_INTERVAL", 12.0)  # как часто слать скриншот (обычный режим)
HTTP_TIMEOUT: float = _get_float("HTTP_TIMEOUT", 5.0)                 # таймаут запроса к серверу

# === Живая трансляция экрана (кнопка на сайте) ===
STREAM_INTERVAL: float = _get_float("STREAM_INTERVAL", 0.05)       # мин. пауза между кадрами (~20 кадров/с максимум)
STREAM_QUALITY: int = _get_int("STREAM_QUALITY", 50)               # качество JPEG кадров трансляции
STREAM_WIDTH: int = _get_int("STREAM_WIDTH", 1280)                 # макс. ширина кадра трансляции
STREAM_MAX_SECONDS: float = _get_float("STREAM_MAX_SECONDS", 600)  # автовыключение трансляции, если забыли выключить

# === Файлы и пути ===
LOG_FILE: Path = BASE_DIR / os.getenv("LOG_FILE", "agent.log")
EMERGENCY_FLAG: Path = Path(os.getenv("EMERGENCY_FLAG", r"C:\guest_mode_off.flag"))

# === Окно пароля ===
PASSWORD_TIMEOUT: int = _get_int("PASSWORD_TIMEOUT", 60)  # сек на ввод пароля
# Пароль гостевого окна — открытым текстом, его можно просто прочитать здесь
GUEST_PASSWORD: str = os.getenv("GUEST_PASSWORD", "")

# === Белый список процессов для блокировки приложений ===
_raw_allowed = os.getenv(
    "ALLOWED_PROCESSES",
    "explorer.exe,dwm.exe,svchost.exe,csrss.exe,winlogon.exe,wininit.exe,"
    "services.exe,lsass.exe,taskhostw.exe,sihost.exe,fontdrvhost.exe,"
    "ctfmon.exe,RuntimeBroker.exe,ShellExperienceHost.exe,SearchHost.exe,"
    "StartMenuExperienceHost.exe,python.exe,pythonw.exe,conhost.exe",
)
ALLOWED_PROCESSES: set[str] = {p.strip().lower() for p in _raw_allowed.split(",") if p.strip()}

# Процессы, которые НИКОГДА не трогаем, даже если их забыли внести
# в белый список — защита от случайной попытки закрыть системный процесс.
PROTECTED_PROCESSES: set[str] = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "svchost.exe",
    "dwm.exe", "explorer.exe", "fontdrvhost.exe", "memory compression",
    "python.exe", "pythonw.exe",  # сам агент
}


def validate() -> None:
    """Проверяет обязательные настройки. Вызывается при старте агента."""
    if not AGENT_TOKEN:
        raise RuntimeError(
            "AGENT_TOKEN не задан в agent/.env. Скопируйте .env.example "
            "в .env и укажите тот же токен, что и в server/.env."
        )
