"""
Отчётность агента: статус, список процессов и скриншоты отправляются
на сервер управления. Если сервер недоступен — просто логируем
предупреждение и пробуем снова на следующем цикле; работу агента
это не останавливает (ТЗ: «если сервер недоступен, агент продолжает
работать автономно и не падает»).
"""
import io
import logging
import os
import time

import mss
import psutil
import requests
from PIL import Image

import app_blocker
import config

log = logging.getLogger("guest_agent.reporter")

def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"X-Agent-Token": config.AGENT_TOKEN})
    return session


# Отдельные сессии (и соединения keep-alive) для разных потоков, чтобы
# долгий опрос команд не тормозил ни статус, ни кадры трансляции
_session = _new_session()
_poll_session = _new_session()
_stream_session = _new_session()


def _post(path: str, **kwargs):
    url = f"{config.SERVER_URL}{path}"
    try:
        resp = _session.post(url, timeout=config.HTTP_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp
    except requests.RequestException as exc:
        log.warning("Не удалось отправить %s на сервер: %s", path, exc)
        return None


def get_process_list() -> list[dict]:
    processes = []
    for proc in psutil.process_iter(["pid", "name"]):
        name = proc.info.get("name")
        if not name:
            continue
        processes.append({"pid": proc.info["pid"], "name": name})
    return processes


def send_status(mode: str, blocking_enabled: bool, lock_remaining: int | None = None,
                streaming: bool = False, pranks_active: list | None = None) -> None:
    payload = {
        "lock_remaining": lock_remaining,
        "streaming": streaming,
        "pranks_active": pranks_active or [],
        "online": True,
        "dry_run": config.DRY_RUN,
        "mode": mode,  # "normal" | "locked"
        "blocking_enabled": blocking_enabled,
        "processes": get_process_list(),
        "allowed_processes": app_blocker.get_whitelist(),
    }
    _post("/api/agent/status", json=payload)


def _encode(shot, quality: int, max_width: int | None) -> bytes:
    # BGRX-буфер mss читается напрямую — это заметно быстрее shot.rgb
    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    if max_width and img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, max(int(img.height * ratio), 1)), Image.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def send_screenshot(quality: int = 60, max_width: int | None = None) -> None:
    """Делает скриншот и отправляет его на сервер (для периодических
    снимков и кнопки «Снимок сейчас»)."""
    try:
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[0])  # весь виртуальный экран
        jpeg_bytes = _encode(shot, quality, max_width)
    except Exception:
        log.exception("Не удалось сделать скриншот")
        return

    _post(
        "/api/agent/screenshot",
        files={"screenshot": ("screenshot.jpg", jpeg_bytes, "image/jpeg")},
    )


def run_stream(is_active, min_interval: float, quality: int, max_width: int) -> None:
    """Цикл живой трансляции: пока is_active() — снимает экран и шлёт кадры
    без лишних пауз (одна mss-сессия и одно keep-alive соединение на весь
    сеанс, пауза только если кадр ушёл быстрее min_interval)."""
    url = f"{config.SERVER_URL}/api/agent/screenshot"
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            while is_active():
                started = time.monotonic()
                try:
                    jpeg = _encode(sct.grab(monitor), quality, max_width)
                    _stream_session.post(
                        url, files={"screenshot": ("f.jpg", jpeg, "image/jpeg")},
                        timeout=config.HTTP_TIMEOUT,
                    ).raise_for_status()
                except requests.RequestException as exc:
                    log.warning("Кадр трансляции не отправлен: %s", exc)
                    time.sleep(1.0)
                    continue
                spare = min_interval - (time.monotonic() - started)
                if spare > 0:
                    time.sleep(spare)
    except Exception:
        log.exception("Трансляция остановлена из-за ошибки")


def download_file(file_id: str, name: str) -> None:
    """Забирает с сервера файл, загруженный с сайта, и кладёт в «Загрузки»."""
    name = os.path.basename(name.replace("\\", "/")) or "file"
    folder = os.path.join(os.path.expanduser("~"), "Downloads")
    if config.DRY_RUN:
        log.info("[DRY_RUN] сохранил бы файл %s в %s", name, folder)
        return
    try:
        resp = _session.get(f"{config.SERVER_URL}/api/agent/file/{file_id}", timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Не удалось скачать файл %s: %s", name, exc)
        return
    base, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 1
    while os.path.exists(path):  # не перезаписываем существующие файлы
        path, n = os.path.join(folder, f"{base} ({n}){ext}"), n + 1
    os.makedirs(folder, exist_ok=True)
    with open(path, "wb") as f:
        f.write(resp.content)
    log.info("Файл сохранён: %s", path)


def send_log(level: str, message: str) -> None:
    _post("/api/agent/log", json={"level": level, "message": message})


def poll_command(wait: float = 0.0) -> dict | None:
    """Спрашивает команду. При wait > 0 сервер держит запрос открытым
    до wait секунд и отвечает сразу, как только команда появилась."""
    url = f"{config.SERVER_URL}/api/agent/poll"
    try:
        resp = _poll_session.get(
            url, params={"wait": wait} if wait else None,
            timeout=(config.HTTP_TIMEOUT, wait + config.HTTP_TIMEOUT),
        )
        resp.raise_for_status()
        return resp.json().get("command")
    except requests.RequestException as exc:
        log.debug("Опрос сервера не удался: %s", exc)
        return None
