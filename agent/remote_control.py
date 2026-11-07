"""
Удалённое управление мышью и клавиатурой с сайта (вкладка «Управление ПК»).

Всё сделано на чистом ctypes через WinAPI SendInput, без лишних библиотек:
    - клик в точку экрана по координатам с трансляции (доли 0..1 от всего
      виртуального экрана — того же, что снимает reporter через mss);
    - сдвиг курсора, клики ЛКМ/ПКМ/СКМ, двойной клик, колёсико;
    - ввод текста (Unicode, поэтому русский тоже работает);
    - горячие клавиши из белого списка HOTKEYS;
    - открытие программы и поиск в интернете.

Как и везде в проекте: в DRY_RUN реальных действий нет, только лог.
"""
import ctypes
import logging
import os
import time
import webbrowser
from ctypes import wintypes
from urllib.parse import quote_plus

import config

log = logging.getLogger("guest_agent.remote")

user32 = ctypes.windll.user32

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
WHEEL_DELTA = 120

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(*inputs: INPUT) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags: int, data: int = 0) -> INPUT:
    return INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=MOUSEINPUT(0, 0, ctypes.c_ulong(data & 0xFFFFFFFF).value, flags, 0, 0)))


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


# Виртуальные коды клавиш, из которых собираются горячие клавиши
VK = {
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
    "enter": 0x0D, "esc": 0x1B, "backspace": 0x08, "tab": 0x09, "space": 0x20, "delete": 0x2E,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "f5": 0x74, "f11": 0x7A,
    **{c: ord(c.upper()) for c in "acdefilrstvwxz"},
}

# Белый список комбинаций, которые можно нажать с сайта
HOTKEYS = {
    "enter", "esc", "backspace", "tab", "space", "delete",
    "left", "up", "right", "down", "home", "end", "pageup", "pagedown", "f5", "f11",
    "alt+tab", "alt+f4", "win", "win+d", "win+e", "win+r", "win+l",
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+a", "ctrl+s", "ctrl+f",
    "ctrl+t", "ctrl+w", "ctrl+shift+t", "ctrl+l", "ctrl+r", "ctrl+shift+esc",
    "shift+tab", "win+shift+s",
}
VK["f4"] = 0x73

BUTTONS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


def _virtual_screen() -> tuple[int, int, int, int]:
    """Левый верхний угол и размер всего виртуального экрана (все мониторы)."""
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))


def _click(button: str = "left", double: bool = False) -> None:
    down, up = BUTTONS[button]
    for _ in range(2 if double else 1):
        _send(_mouse(down), _mouse(up))
        time.sleep(0.05)


def click_at(x: float, y: float, button: str = "left", double: bool = False) -> None:
    left, top, width, height = _virtual_screen()
    px, py = left + int(x * width), top + int(y * height)
    if config.DRY_RUN:
        log.info("[DRY_RUN] кликнул бы %s%s в точке (%d, %d)", button, " дважды" if double else "", px, py)
        return
    user32.SetCursorPos(px, py)
    _click(button, double)


def move(dx: int, dy: int) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] сдвинул бы курсор на (%d, %d)", dx, dy)
        return
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetCursorPos(pt.x + dx, pt.y + dy)


def click(button: str = "left", double: bool = False) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] нажал бы кнопку мыши %s%s", button, " дважды" if double else "")
        return
    _click(button, double)


def scroll(amount: int) -> None:
    """amount > 0 — прокрутка вверх, < 0 — вниз (в «щелчках» колёсика)."""
    if config.DRY_RUN:
        log.info("[DRY_RUN] прокрутил бы колёсико на %d", amount)
        return
    _send(_mouse(MOUSEEVENTF_WHEEL, amount * WHEEL_DELTA))


def type_text(text: str) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] напечатал бы текст из %d символов", len(text))
        return
    for ch in text:
        if ch == "\n":
            _send(_key(VK["enter"]), _key(VK["enter"], flags=KEYEVENTF_KEYUP))
            continue
        code = ord(ch)
        _send(_key(scan=code, flags=KEYEVENTF_UNICODE),
              _key(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))


def hotkey(combo: str) -> None:
    combo = combo.lower()
    if combo not in HOTKEYS:
        log.warning("Отклонена неизвестная комбинация клавиш: %r", combo)
        return
    if config.DRY_RUN:
        log.info("[DRY_RUN] нажал бы %s", combo)
        return
    keys = [VK[k] for k in combo.split("+")]
    _send(*[_key(k) for k in keys], *[_key(k, flags=KEYEVENTF_KEYUP) for k in reversed(keys)])


def open_app(name: str) -> None:
    """Запускает программу так же, как Win+R: notepad, calc, chrome, mspaint…"""
    name = name.strip()
    if config.DRY_RUN:
        log.info("[DRY_RUN] запустил бы программу: %s", name)
        return
    try:
        os.startfile(name)
        log.info("Запущена программа: %s", name)
    except OSError:
        log.exception("Не удалось запустить программу: %s", name)


SEARCH_URLS = {
    "yandex": "https://yandex.ru/search/?text={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
}


def search(query: str, engine: str = "yandex") -> None:
    url = SEARCH_URLS.get(engine, SEARCH_URLS["yandex"]).format(quote_plus(query))
    if config.DRY_RUN:
        log.info("[DRY_RUN] открыл бы поиск: %s", url)
        return
    webbrowser.open(url)
    log.info("Открыт поиск: %s", url)


def handle(params: dict) -> None:
    """Разбор команды {"type": "remote", "params": {...}} от сервера."""
    action = params.get("action")
    try:
        if action == "click_at":
            click_at(float(params["x"]), float(params["y"]), params.get("button", "left"), bool(params.get("double")))
        elif action == "move":
            move(int(params.get("dx", 0)), int(params.get("dy", 0)))
        elif action == "click":
            click(params.get("button", "left"), bool(params.get("double")))
        elif action == "scroll":
            scroll(int(params.get("amount", 0)))
        elif action == "type":
            type_text(str(params.get("text", "")))
        elif action == "hotkey":
            hotkey(str(params.get("combo", "")))
        elif action == "open_app":
            open_app(str(params.get("name", "")))
        elif action == "search":
            search(str(params.get("query", "")), str(params.get("engine", "yandex")))
        else:
            log.warning("Неизвестное действие управления: %r", action)
    except (KeyError, ValueError, TypeError):
        log.exception("Некорректные параметры управления: %r", params)
