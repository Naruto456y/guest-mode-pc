"""
Сервер управления «Гостевой режим ПК».

Два «фасада» в одном FastAPI-приложении:
    1. Веб-панель для вас (вход по паролю, кнопки управления, просмотр
       статуса/скриншота/лога) — обычные HTML-страницы с сессией.
    2. API для агента на ПК (опрос команд, отправка статуса/скриншота/лога)
       — авторизация отдельным секретным токеном в заголовке
       X-Agent-Token, без сессии и без пароля сайта.

Запуск (из папки server/):
    python main.py
или, для автоперезагрузки при разработке:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import asyncio
import logging
import secrets
import time
from urllib.parse import urlparse

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import auth
import config
from state import state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("guest_server")

config.validate()

app = FastAPI(title="Гостевой режим ПК — панель управления")
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET)


@app.middleware("http")
async def same_origin_only(request: Request, call_next):
    """Защита от CSRF: POST-запросы панели (не API агента) принимаются
    только если Origin/Referer указывает на тот же хост, что и сам сайт."""
    if request.method == "POST" and not request.url.path.startswith("/api/agent/"):
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            log.warning("Отклонён POST с чужим Origin: %s", origin)
            return Response("Чужой Origin", status_code=403)
    return await call_next(request)


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ========================= Веб-панель =========================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None):
    if auth.is_logged_in(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    ip = request.client.host if request.client else "?"
    if auth.is_locked_out(ip):
        log.warning("Вход заблокирован (слишком много попыток) для %s", ip)
        return RedirectResponse(url="/login?error=1", status_code=303)
    if auth.check_password(password):
        auth.clear_fails(ip)
        request.session["logged_in"] = True
        log.info("Успешный вход в панель управления")
        return RedirectResponse(url="/", status_code=303)
    auth.register_fail(ip)
    log.warning("Неудачная попытка входа в панель управления с %s", ip)
    return RedirectResponse(url="/login?error=1", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    redirect = auth.require_login(request)
    if redirect:
        return redirect
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/control/clear_events")
def control_clear_events(request: Request):
    _require_login_api(request)
    state.clear_events()
    return {"ok": True}


@app.get("/api/dashboard_data")
def dashboard_data(request: Request):
    if not auth.is_logged_in(request):
        raise HTTPException(status_code=401, detail="Не авторизован")
    status = state.get_status(config.AGENT_ONLINE_TIMEOUT)
    _, screenshot_at = state.get_screenshot()
    return {
        "online": status.online,
        "dry_run": status.dry_run,
        "mode": status.mode,
        "blocking_enabled": status.blocking_enabled,
        "processes": status.processes,
        "allowed_processes": status.allowed_processes,
        "screenshot_at": screenshot_at,
        "queue_length": state.queue_length(),
        "lock_remaining": status.lock_remaining,
        "streaming": status.streaming,
        "pranks_active": status.pranks_active,
        "last_seen": status.last_seen,
        "events": state.get_events(),
    }


@app.get("/screenshot.jpg")
def screenshot(request: Request):
    if not auth.is_logged_in(request):
        raise HTTPException(status_code=401, detail="Не авторизован")
    data, _ = state.get_screenshot()
    if not data:
        raise HTTPException(status_code=404, detail="Скриншотов ещё не было")
    return Response(content=data, media_type="image/jpeg")


@app.get("/stream.mjpeg")
async def stream(request: Request):
    """Живая трансляция экрана: отдаёт multipart/x-mixed-replace поток
    JPEG-кадров. Браузер умеет показывать такой поток прямо в <img>, без
    JavaScript — он сам перерисовывает картинку на каждый новый кадр.

    Сервер здесь ничего не снимает сам — он просто быстро переотдаёт тот
    же последний кадр, что агент прислал через /api/agent/screenshot.
    «Живость» трансляции зависит от того, как часто агент присылает
    кадры: обычно раз в SCREENSHOT_INTERVAL секунд, но пока открыт этот
    поток, агент сам переключается в быстрый режим (см. команды
    start_stream/stop_stream и agent/agent.py)."""
    if not auth.is_logged_in(request):
        raise HTTPException(status_code=401, detail="Не авторизован")

    boundary = "frame"

    async def _frames():
        last_sent_at = 0.0
        try:
            while True:
                if await request.is_disconnected():
                    break
                data, captured_at = state.get_screenshot()
                if data and captured_at != last_sent_at:
                    last_sent_at = captured_at
                    yield (
                        f"--{boundary}\r\nContent-Type: image/jpeg\r\n\r\n"
                    ).encode("utf-8") + data + b"\r\n"
                await asyncio.sleep(0.02)
        finally:
            log.info("Клиент отключился от живой трансляции /stream.mjpeg")

    return StreamingResponse(
        _frames(), media_type=f"multipart/x-mixed-replace; boundary={boundary}"
    )


# ===================== Кнопки управления (сайт) =====================

def _require_login_api(request: Request) -> None:
    if not auth.is_logged_in(request):
        raise HTTPException(status_code=401, detail="Не авторизован")


@app.post("/control/lock")
def control_lock(request: Request):
    _require_login_api(request)
    state.push_command({"type": "show_password_window"})
    return {"ok": True}


@app.post("/control/let_in")
def control_let_in(request: Request):
    _require_login_api(request)
    state.push_command({"type": "let_in"})
    return {"ok": True}


@app.post("/control/block_apps_on")
def control_block_apps_on(request: Request):
    _require_login_api(request)
    state.push_command({"type": "block_apps_on"})
    return {"ok": True}


@app.post("/control/block_apps_off")
def control_block_apps_off(request: Request):
    _require_login_api(request)
    state.push_command({"type": "block_apps_off"})
    return {"ok": True}


ALLOWED_PRANKS = {
    "rotate_180", "rotate_normal",
    "minimize_all", "switch_layout", "play_sound",
    "hide_cursor", "jitter_cursor",
    "toggle_mute", "volume_up", "volume_down",
    "swap_mouse_buttons", "restore_mouse_buttons",
    "message_box",
}


@app.post("/control/prank/{name}")
async def control_prank(name: str, request: Request):
    _require_login_api(request)
    if name not in ALLOWED_PRANKS:
        raise HTTPException(status_code=400, detail="Неизвестный розыгрыш")
    # Для message_box можно передать свой текст телом запроса {"text": "..."}
    params: dict = {"name": name}
    if name == "message_box":
        try:
            body = await request.json()
        except Exception:
            body = {}
        if body.get("text"):
            params["text"] = str(body["text"])[:300]
    state.push_command({"type": "prank", "params": params})
    return {"ok": True}


@app.post("/control/prank_restore_all")
def control_prank_restore_all(request: Request):
    _require_login_api(request)
    state.push_command({"type": "prank_restore_all"})
    return {"ok": True}


@app.post("/control/disable_guest_mode")
def control_disable_guest_mode(request: Request):
    # Аварийная кнопка — сознательно не требует ничего, кроме входа в
    # панель, и ставит команду в начало очереди, чтобы она выполнилась
    # раньше любых других уже поставленных команд. Используем
    # push_command_front, а не push_command, чтобы не терять место
    # в начале очереди (и чтобы у команды тоже была метка времени).
    _require_login_api(request)
    state.push_command_front({"type": "disable_guest_mode"})
    state.add_event("warning", "Нажата аварийная кнопка «Отключить режим»")
    return {"ok": True}


# ===================== Белый список приложений =====================

@app.post("/control/whitelist")
async def control_whitelist(request: Request):
    _require_login_api(request)
    data = await request.json()
    processes = data.get("processes", [])
    if not isinstance(processes, list) or len(processes) > 500:
        raise HTTPException(status_code=400, detail="processes должен быть списком строк (до 500)")
    processes = [str(p)[:100] for p in processes]
    state.push_command({"type": "set_whitelist", "params": {"processes": processes}})
    state.add_event("info", f"Белый список обновлён с сайта ({len(processes)} программ)")
    return {"ok": True}


# ===================== Прочее управление ПК =====================

@app.post("/control/lock_workstation")
def control_lock_workstation(request: Request):
    _require_login_api(request)
    state.push_command({"type": "lock_workstation"})
    return {"ok": True}


@app.post("/control/snapshot_now")
def control_snapshot_now(request: Request):
    _require_login_api(request)
    state.push_command({"type": "snapshot_now"})
    return {"ok": True}


@app.post("/control/open_url")
async def control_open_url(request: Request):
    _require_login_api(request)
    data = await request.json()
    url = str(data.get("url", "")).strip()
    if not url:
        raise HTTPException(status_code=400, detail="url не задан")
    if "://" not in url:
        url = "https://" + url  # «youtube.com» → «https://youtube.com»
    if not url.lower().startswith(("http://", "https://")) or len(url) > 2000:
        raise HTTPException(status_code=400, detail="Разрешены только http(s)-ссылки")
    state.push_command({"type": "open_url", "params": {"url": url}})
    return {"ok": True}


# ===================== Вкладка «Управление ПК» =====================

REMOTE_BUTTONS = {"left", "right", "middle"}
REMOTE_HOTKEYS = {
    "enter", "esc", "backspace", "tab", "space", "delete",
    "left", "up", "right", "down", "home", "end", "pageup", "pagedown", "f5", "f11",
    "alt+tab", "alt+f4", "win", "win+d", "win+e", "win+r", "win+l",
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+a", "ctrl+s", "ctrl+f",
    "ctrl+t", "ctrl+w", "ctrl+shift+t", "ctrl+l", "ctrl+r", "ctrl+shift+esc",
    "shift+tab", "win+shift+s",
}


def _validate_remote(data: dict) -> dict:
    """Проверяет команду мыши/клавиатуры и возвращает чистые параметры."""
    action = data.get("action")
    try:
        if action == "click_at":
            x, y = float(data["x"]), float(data["y"])
            if not (0 <= x <= 1 and 0 <= y <= 1):
                raise ValueError
            button = data.get("button", "left")
            if button not in REMOTE_BUTTONS:
                raise ValueError
            return {"action": action, "x": x, "y": y, "button": button, "double": bool(data.get("double"))}
        if action == "move":
            dx, dy = int(data.get("dx", 0)), int(data.get("dy", 0))
            if abs(dx) > 5000 or abs(dy) > 5000:
                raise ValueError
            return {"action": action, "dx": dx, "dy": dy}
        if action == "click":
            button = data.get("button", "left")
            if button not in REMOTE_BUTTONS:
                raise ValueError
            return {"action": action, "button": button, "double": bool(data.get("double"))}
        if action == "scroll":
            amount = int(data.get("amount", 0))
            if not -50 <= amount <= 50:
                raise ValueError
            return {"action": action, "amount": amount}
        if action == "type":
            text = str(data.get("text", ""))
            if not text or len(text) > 2000:
                raise ValueError
            return {"action": action, "text": text}
        if action == "hotkey":
            combo = str(data.get("combo", "")).lower()
            if combo not in REMOTE_HOTKEYS:
                raise ValueError
            return {"action": action, "combo": combo}
        if action == "open_app":
            name = str(data.get("name", "")).strip()
            if not name or len(name) > 200 or "://" in name:
                raise ValueError
            return {"action": action, "name": name}
        if action == "search":
            query = str(data.get("query", "")).strip()
            engine = data.get("engine", "yandex")
            if not query or len(query) > 500 or engine not in {"yandex", "youtube"}:
                raise ValueError
            return {"action": action, "query": query, "engine": engine}
    except (KeyError, TypeError, ValueError):
        pass
    raise HTTPException(status_code=400, detail="Некорректная команда управления")


@app.post("/control/remote")
async def control_remote(request: Request):
    _require_login_api(request)
    try:
        data = await request.json()
    except Exception:
        data = {}
    state.push_command({"type": "remote", "params": _validate_remote(data if isinstance(data, dict) else {})})
    return {"ok": True}


# Файлы, загруженные с сайта и ещё не забранные агентом: id -> (имя, данные, время)
MAX_UPLOAD = 50 * 1024 * 1024
_uploads: dict[str, tuple[str, bytes, float]] = {}


@app.post("/control/upload")
async def control_upload(request: Request, file: UploadFile):
    _require_login_api(request)
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Файл больше 50 МБ")
    # Старые незабранные файлы не копим: держим не больше 5 и не дольше часа
    now = time.time()
    for key in [k for k, v in _uploads.items() if now - v[2] > 3600][:]:
        _uploads.pop(key, None)
    while len(_uploads) >= 5:
        _uploads.pop(next(iter(_uploads)))
    file_id = secrets.token_hex(8)
    name = (file.filename or "file").replace("\\", "/").split("/")[-1][:150] or "file"
    _uploads[file_id] = (name, data, now)
    state.push_command({"type": "download_file", "params": {"id": file_id, "name": name}})
    state.add_event("info", f"Файл «{name}» отправлен на ПК ({len(data) // 1024} КБ)")
    return {"ok": True}


@app.post("/control/start_stream")
def control_start_stream(request: Request):
    _require_login_api(request)
    state.push_command({"type": "start_stream"})
    return {"ok": True}


@app.post("/control/stop_stream")
def control_stop_stream(request: Request):
    _require_login_api(request)
    state.push_command({"type": "stop_stream"})
    return {"ok": True}


# ========================= API для агента =========================

def _require_agent_token(request: Request) -> None:
    token = request.headers.get("X-Agent-Token")
    if not auth.check_agent_token(token):
        raise HTTPException(status_code=403, detail="Неверный токен агента")


@app.get("/api/agent/poll")
async def agent_poll(request: Request, wait: float = 0):
    """Long-poll: если команд нет, держим запрос открытым до `wait` секунд
    (не больше 30) и отдаём команду сразу, как только она появилась —
    кнопки на сайте срабатывают мгновенно, а не раз в несколько секунд."""
    _require_agent_token(request)
    deadline = time.monotonic() + max(0.0, min(wait, 30.0))
    while True:
        command = state.pop_command()
        if command or time.monotonic() >= deadline:
            return {"command": command}
        if await request.is_disconnected():
            return {"command": None}
        await asyncio.sleep(0.05)


@app.post("/api/agent/status")
async def agent_status(request: Request):
    _require_agent_token(request)
    data = await request.json()
    state.update_status(
        online=True,
        dry_run=bool(data.get("dry_run", True)),
        mode=data.get("mode", "normal"),
        blocking_enabled=bool(data.get("blocking_enabled", False)),
        processes=data.get("processes", []),
        allowed_processes=data.get("allowed_processes", []),
        lock_remaining=data.get("lock_remaining"),
        streaming=bool(data.get("streaming", False)),
        pranks_active=data.get("pranks_active", []),
    )
    return {"ok": True}


@app.post("/api/agent/screenshot")
async def agent_screenshot(request: Request, screenshot: UploadFile):
    _require_agent_token(request)
    data = await screenshot.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Скриншот слишком большой")
    state.set_screenshot(data)
    return {"ok": True}


@app.get("/api/agent/file/{file_id}")
def agent_file(file_id: str, request: Request):
    _require_agent_token(request)
    item = _uploads.pop(file_id, None)
    if item is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    return Response(content=item[1], media_type="application/octet-stream")


@app.post("/api/agent/log")
async def agent_log(request: Request):
    _require_agent_token(request)
    data = await request.json()
    state.add_event(data.get("level", "info"), data.get("message", ""))
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
