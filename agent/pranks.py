"""
Розыгрыши и мелкие команды управления ПК — только безобидные и полностью
обратимые эффекты. Ничего здесь не удаляет файлы, не закрывает программы
и не выключает ПК.

apply("имя", **kwargs) применяет один розыгрыш (kwargs — необязательные
параметры конкретного розыгрыша, например текст для message_box).
restore_all() отменяет сразу все эффекты, у которых есть что отменять
(кнопка «Всё вернуть как было» на сайте).
"""
import ctypes
import ctypes.wintypes as wt
import logging
import random
import threading
import time
import winsound

import config

log = logging.getLogger("guest_agent.pranks")

user32 = ctypes.windll.user32
_lock = threading.Lock()

# Что из обратимого сейчас включено — нужно для restore_all()
_state = {
    "orientation": None,     # None | 90 | 180 | 270 (текущий поворот экрана)
    "mouse_swapped": False,  # поменяны ли местами кнопки мыши
}


# ============================================================
# Поворот экрана (перевернуть / повернуть на 90°/270°)
# ============================================================
DM_DISPLAYORIENTATION = 0x00000080   # ВАЖНО: именно этот бит, а не произвольный
ENUM_CURRENT_SETTINGS = -1
CDS_UPDATEREGISTRY = 0x01
DISP_CHANGE_SUCCESSFUL = 0

DMDO_DEFAULT = 0
DMDO_90 = 1
DMDO_180 = 2
DMDO_270 = 3


class DEVMODE(ctypes.Structure):
    # ВАЖНО: в реальной структуре DEVMODE поля dmPosition/dmDisplayOrientation/
    # dmDisplayFixedOutput лежат в union с «принтерскими» полями
    # (dmOrientation, dmPaperSize, ...) — то есть занимают ТЕ ЖЕ 16 байт.
    # Если объявить dmDisplayOrientation как отдельное поле ПОСЛЕ принтерских
    # полей (как было в первой версии), запись в него уйдёт мимо структуры
    # и ChangeDisplaySettingsW её просто не увидит. Поэтому здесь явно
    # используется «экранный» вариант union, а не «принтерский».
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", wt.WORD),
        ("dmDriverVersion", wt.WORD),
        ("dmSize", wt.WORD),
        ("dmDriverExtra", wt.WORD),
        ("dmFields", wt.DWORD),
        # --- начало union (16 байт): для экрана используем позицию+поворот ---
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wt.DWORD),
        ("dmDisplayFixedOutput", wt.DWORD),
        # --- конец union ---
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", wt.WORD),
        ("dmBitsPerPel", wt.DWORD),
        ("dmPelsWidth", wt.DWORD),
        ("dmPelsHeight", wt.DWORD),
        ("dmDisplayFlags", wt.DWORD),
        ("dmDisplayFrequency", wt.DWORD),
        ("dmICMMethod", wt.DWORD),
        ("dmICMIntent", wt.DWORD),
        ("dmMediaType", wt.DWORD),
        ("dmDitherType", wt.DWORD),
        ("dmReserved1", wt.DWORD),
        ("dmReserved2", wt.DWORD),
        ("dmPanningWidth", wt.DWORD),
        ("dmPanningHeight", wt.DWORD),
    ]


def _set_orientation(orientation: int) -> bool:
    devmode = DEVMODE()
    devmode.dmSize = ctypes.sizeof(DEVMODE)
    if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
        log.error("Не удалось получить текущие настройки экрана")
        return False

    # При повороте на 90/270 ширина и высота экрана меняются местами —
    # Windows это требует явно, иначе ChangeDisplaySettingsW откажет.
    was_rotated = devmode.dmDisplayOrientation in (DMDO_90, DMDO_270)
    will_be_rotated = orientation in (DMDO_90, DMDO_270)
    if was_rotated != will_be_rotated:
        devmode.dmPelsWidth, devmode.dmPelsHeight = devmode.dmPelsHeight, devmode.dmPelsWidth

    devmode.dmDisplayOrientation = orientation
    devmode.dmFields = DM_DISPLAYORIENTATION
    result = user32.ChangeDisplaySettingsW(ctypes.byref(devmode), CDS_UPDATEREGISTRY)
    return result == DISP_CHANGE_SUCCESSFUL


def _rotate(orientation: int, label: str) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] повернул бы экран: %s", label)
        _state["orientation"] = orientation
        return
    if _set_orientation(orientation):
        log.info("Экран повёрнут: %s", label)
        _state["orientation"] = orientation
    else:
        log.error("Не удалось повернуть экран (%s)", label)


def rotate_180() -> None:
    _rotate(DMDO_180, "вверх ногами")


def rotate_normal() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] вернул бы экран в нормальное положение")
        _state["orientation"] = None
        return
    if _set_orientation(DMDO_DEFAULT):
        log.info("Экран возвращён в нормальное положение")
        _state["orientation"] = None


# Сохранено для обратной совместимости (старые команды с сайта/логов)
flip_screen_on = rotate_180
flip_screen_off = rotate_normal


# ============================================================
# Свернуть все окна (аналог Win+D)
# ============================================================
WM_COMMAND = 0x0111
MINIMIZE_ALL_TOGGLE = 419  # команда трея "Показать рабочий стол" / "Показать окна"


def minimize_all() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] свернул бы все окна")
        return
    tray = user32.FindWindowW("Shell_TrayWnd", None)
    if tray:
        user32.PostMessageW(tray, WM_COMMAND, MINIMIZE_ALL_TOGGLE, 0)
        log.info("Отправлена команда «свернуть все окна»")
    else:
        log.error("Не найдено окно панели задач Shell_TrayWnd")


# ============================================================
# Смена раскладки (имитирует стандартное Alt+Shift)
# ============================================================
VK_MENU = 0x12
VK_LSHIFT = 0xA0
KEYEVENTF_KEYUP = 0x0002


def switch_layout() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] переключил бы раскладку клавиатуры")
        return
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_LSHIFT, 0, 0, 0)
    user32.keybd_event(VK_LSHIFT, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    log.info("Отправлено сочетание переключения раскладки (Alt+Shift)")


# ============================================================
# Звук
# ============================================================
def play_sound() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] проиграл бы звук")
        return
    try:
        winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        log.info("Звук воспроизведён")
    except RuntimeError:
        log.exception("Не удалось воспроизвести звук")


VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF


def _press_media_key(vk: int, times: int = 1) -> None:
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.05)


def toggle_mute() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] переключил бы звук вкл/выкл")
        return
    _press_media_key(VK_VOLUME_MUTE)
    log.info("Звук приглушён/включён (toggle mute)")


def volume_up(steps: int = 5) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] сделал бы звук громче")
        return
    _press_media_key(VK_VOLUME_UP, steps)
    log.info("Громкость увеличена")


def volume_down(steps: int = 5) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] сделал бы звук тише")
        return
    _press_media_key(VK_VOLUME_DOWN, steps)
    log.info("Громкость уменьшена")


# ============================================================
# Спрятать курсор на N секунд
# ============================================================
OCR_IDS = (
    32512, 32513, 32514, 32515, 32516,
    32640, 32641, 32642, 32643, 32644, 32648, 32649,
)
SPI_SETCURSORS = 0x0057


def _make_blank_cursor():
    and_mask = (ctypes.c_ubyte * (32 * 32 // 8))(*([0xFF] * (32 * 32 // 8)))
    xor_mask = (ctypes.c_ubyte * (32 * 32 // 8))(*([0x00] * (32 * 32 // 8)))
    return user32.CreateCursor(None, 0, 0, 32, 32, and_mask, xor_mask)


def hide_cursor(seconds: float = 5.0) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] спрятал бы курсор на %s сек", seconds)
        return

    def _worker():
        for cursor_id in OCR_IDS:
            blank = _make_blank_cursor()
            if blank:
                user32.SetSystemCursor(blank, cursor_id)
        log.info("Курсор спрятан на %s сек", seconds)
        time.sleep(seconds)
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
        log.info("Курсор восстановлен")

    threading.Thread(target=_worker, name="hide-cursor", daemon=True).start()


# ============================================================
# Подёргать курсор мыши несколько секунд (не трогая окна)
# ============================================================
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def jitter_cursor(seconds: float = 3.0) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] подёргал бы курсор мыши %s сек", seconds)
        return

    def _worker():
        origin = POINT()
        user32.GetCursorPos(ctypes.byref(origin))
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        end = time.monotonic() + seconds
        log.info("Курсор мыши дёргается %s сек", seconds)
        while time.monotonic() < end:
            x = random.randint(0, max(screen_w - 1, 0))
            y = random.randint(0, max(screen_h - 1, 0))
            user32.SetCursorPos(x, y)
            time.sleep(0.08)
        log.info("Подёргивание курсора закончено")

    threading.Thread(target=_worker, name="jitter-cursor", daemon=True).start()


# ============================================================
# Поменять местами кнопки мыши
# ============================================================
def swap_mouse_buttons() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] поменял бы местами кнопки мыши")
        _state["mouse_swapped"] = True
        return
    user32.SwapMouseButton(True)
    _state["mouse_swapped"] = True
    log.info("Кнопки мыши поменяны местами")


def restore_mouse_buttons() -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] вернул бы кнопки мыши как было")
        _state["mouse_swapped"] = False
        return
    user32.SwapMouseButton(False)
    _state["mouse_swapped"] = False
    log.info("Кнопки мыши возвращены в обычный порядок")


# ============================================================
# Всплывающее сообщение (можно с произвольным текстом)
# ============================================================
JOKE_MESSAGES = [
    "Компьютер в гостевом режиме 👋",
    "Привет! Это не баг, это розыгрыш.",
    "Хозяин ПК за тобой наблюдает 👀",
    "Нажми ОК, чтобы продолжить веселье.",
]

MB_OK = 0x00000000
MB_ICONINFORMATION = 0x00000040
MB_TOPMOST = 0x00040000
MB_SETFOREGROUND = 0x00010000
VK_MENU_KEY = 0x12


def message_box(text: str | None = None, title: str = "Гостевой режим") -> None:
    text = text or random.choice(JOKE_MESSAGES)
    if config.DRY_RUN:
        log.info("[DRY_RUN] показал бы сообщение: %r", text)
        return

    def _worker():
        # Фоновому процессу Windows не даёт выводить окно на передний план —
        # оно «висит» свёрнутым в панели задач. «Нажатие» Alt снимает запрет.
        user32.keybd_event(VK_MENU_KEY, 0, 0, 0)
        user32.keybd_event(VK_MENU_KEY, 0, KEYEVENTF_KEYUP, 0)
        user32.MessageBoxW(
            None, text, title,
            MB_OK | MB_ICONINFORMATION | MB_TOPMOST | MB_SETFOREGROUND | 0x00001000,
        )

    threading.Thread(target=_worker, name="message-box", daemon=True).start()
    log.info("Показано сообщение: %r", text)


# ============================================================
# Применение / снятие розыгрышей
# ============================================================
PRANK_HANDLERS = {
    "flip_screen": rotate_180,        # старое имя — оставлено для совместимости
    "rotate_180": rotate_180,
    "rotate_normal": rotate_normal,
    "minimize_all": minimize_all,
    "switch_layout": switch_layout,
    "play_sound": play_sound,
    "hide_cursor": lambda **kw: hide_cursor(float(kw.get("seconds", 5.0))),
    "jitter_cursor": lambda **kw: jitter_cursor(float(kw.get("seconds", 3.0))),
    "toggle_mute": toggle_mute,
    "volume_up": volume_up,
    "volume_down": volume_down,
    "swap_mouse_buttons": swap_mouse_buttons,
    "restore_mouse_buttons": restore_mouse_buttons,
    "message_box": lambda **kw: message_box(text=kw.get("text")),
}

# Имена, которые можно выбрать кнопкой на сайте (используется и сервером,
# и для проверки на всякий случай в самом агенте)
PRANK_NAMES = tuple(PRANK_HANDLERS.keys())


def apply(prank_name: str, **kwargs) -> bool:
    handler = PRANK_HANDLERS.get(prank_name)
    if not handler:
        log.warning("Неизвестный розыгрыш: %s", prank_name)
        return False
    with _lock:
        handler(**kwargs)
    return True


def active() -> list[str]:
    """Человекочитаемый список включённых сейчас обратимых эффектов."""
    result = []
    if _state["orientation"] is not None:
        result.append(f"экран повёрнут ({_state['orientation']})")
    if _state["mouse_swapped"]:
        result.append("кнопки мыши поменяны")
    return result


def restore_all() -> None:
    """Кнопка «Всё вернуть как было»: отменяет все обратимые эффекты,
    у которых есть что отменять."""
    log.info("Восстановление всех розыгрышей")
    with _lock:
        rotate_normal()
        if _state["mouse_swapped"]:
            restore_mouse_buttons()
        if not config.DRY_RUN:
            user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
