"""
Авторизация на сайте управления: вход по паролю + сессия (через
SessionMiddleware из Starlette, cookie подписывается SESSION_SECRET).

Отдельно — проверка токена агента для API-запросов с ПК (не связана
с сессией сайта, это две независимые системы авторизации).

Пароль хранится в server/.env открытым текстом (ADMIN_PASSWORD) —
это не публичный сервис с чужими учётками, а домашняя панель на
своём ПК, так что хэш с солью здесь не даёт ничего, кроме того, что
забытый пароль было бы не посмотреть, а пришлось бы сбрасывать.
Сравнение всё равно идёт через hmac.compare_digest — это ничего не
стоит, но не даёт угадать пароль по времени ответа.
"""
import hmac
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

import config


def check_password(password: str) -> bool:
    if not config.ADMIN_PASSWORD:
        return False
    return hmac.compare_digest(password, config.ADMIN_PASSWORD)


# --- защита от подбора пароля: после MAX_FAILS неудач с одного IP вход
# блокируется на LOCKOUT_SECONDS (счётчик в памяти, как и всё состояние) ---
MAX_FAILS = 5
LOCKOUT_SECONDS = 300
_fails: dict[str, list[float]] = {}


def is_locked_out(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS


def register_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


def clear_fails(ip: str) -> None:
    _fails.pop(ip, None)


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("logged_in"))


def require_login(request: Request):
    """Вызывается в начале защищённых страниц. Если пользователь не
    залогинен — возвращает редирект на /login, иначе None."""
    if not is_logged_in(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


def check_agent_token(token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(token, config.AGENT_TOKEN)
