"""
Блокировка приложений: закрывает процессы, которых нет в белом списке.
Работает в отдельном потоке циклом с паузой.

Белый список по умолчанию берётся из ALLOWED_PROCESSES в agent/.env, но
может быть изменён «на лету» с сайта (команда set_whitelist) — поэтому
здесь это изменяемое множество в памяти, а не константа из config.
Изменения с сайта НЕ сохраняются в .env и сбрасываются при перезапуске
агента — это осознанно: базовый список (в т.ч. системные программы)
задаётся на ПК, с сайта его можно только дополнять/сокращать на время.

«Мягко» (как требует ТЗ — не терять несохранённые файлы) означает: мы
посылаем окну процесса сообщение WM_CLOSE — ровно то же самое, что
происходит, когда пользователь сам нажимает на крестик окна. Если
в приложении есть несохранённые изменения, оно само покажет диалог
«Сохранить изменения?» и не закроется, пока пользователь не ответит.
Принудительный kill()/terminate() мы НЕ используем — это было бы
уже не «мягким» закрытием, а потерей данных.

Если у процесса нет видимых окон (фоновая служба, консольная утилита) —
мы его не трогаем вообще: WM_CLOSE послать некуда, а убивать такие
процессы принудительно запрещено требованиями безопасности.
"""
import ctypes
import ctypes.wintypes as wt
import logging
import threading
import time

import psutil

import config

log = logging.getLogger("guest_agent.app_blocker")

user32 = ctypes.windll.user32
WM_CLOSE = 0x0010

_enabled = threading.Event()
_stop = threading.Event()
_thread: threading.Thread | None = None
_whitelist_lock = threading.Lock()

# Рабочий (изменяемый) белый список — стартует со значений из .env
_whitelist: set[str] = set(config.ALLOWED_PROCESSES)

CHECK_INTERVAL = 2.0  # сек, как часто проверять список процессов
RECLOSE_COOLDOWN = 15.0  # сек до повторного WM_CLOSE тому же процессу
_last_close: dict[int, float] = {}


def is_enabled() -> bool:
    return _enabled.is_set()


def enable() -> None:
    _enabled.set()
    log.info("Блокировка приложений включена")


def disable() -> None:
    _enabled.clear()
    log.info("Блокировка приложений выключена")


def get_whitelist() -> list[str]:
    with _whitelist_lock:
        return sorted(_whitelist)


def set_whitelist(names: list[str]) -> None:
    """Полностью заменяет белый список (вызывается командой set_whitelist
    с сайта). Защищённые процессы (PROTECTED_PROCESSES) и так всегда
    разрешены — их можно не включать в список."""
    cleaned = {str(n).strip().lower() for n in names if str(n).strip()}
    with _whitelist_lock:
        _whitelist.clear()
        _whitelist.update(cleaned)
    log.info("Белый список обновлён с сайта: %s", ", ".join(sorted(cleaned)) or "(пусто)")


def add_to_whitelist(name: str) -> None:
    name = name.strip().lower()
    if not name:
        return
    with _whitelist_lock:
        _whitelist.add(name)
    log.info("В белый список добавлено: %s", name)


def _is_allowed(name: str) -> bool:
    if name in config.PROTECTED_PROCESSES:
        return True
    with _whitelist_lock:
        return name in _whitelist


def _windows_of_pid(pid: int) -> list[int]:
    """Возвращает handle'ы видимых окон верхнего уровня, принадлежащих
    процессу с данным pid."""
    windows: list[int] = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        owner_pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == pid:
            windows.append(hwnd)
        return True

    user32.EnumWindows(_callback, 0)
    return windows


def _close_process(pid: int, name: str) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] закрыл бы процесс: %s (pid=%s)", name, pid)
        return

    windows = _windows_of_pid(pid)
    if not windows:
        log.debug("У процесса %s (pid=%s) нет видимых окон — пропускаю", name, pid)
        return

    # Не долбим одно и то же окно каждые 2 сек: если висит диалог
    # «Сохранить изменения?», повторный WM_CLOSE только раздражает
    now = time.monotonic()
    if now - _last_close.get(pid, 0.0) < RECLOSE_COOLDOWN:
        return
    _last_close[pid] = now
    for hwnd in windows:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    log.info("Отправлен сигнал закрытия (WM_CLOSE) процессу вне белого списка: %s (pid=%s)", name, pid)


def _sweep_once() -> None:
    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info.get("name") or "").lower()
        if not name or _is_allowed(name):
            continue
        _close_process(proc.info["pid"], proc.info["name"])


def _loop() -> None:
    log.info("Поток блокировки приложений запущен")
    while not _stop.is_set():
        if _enabled.is_set():
            try:
                _sweep_once()
            except Exception:
                log.exception("Ошибка при проверке процессов")
        time.sleep(CHECK_INTERVAL)
    log.info("Поток блокировки приложений остановлен")


def start() -> None:
    """Запускает фоновый поток наблюдения. Саму блокировку это не
    включает — для этого нужно отдельно вызвать enable()."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="app-blocker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    _enabled.clear()
