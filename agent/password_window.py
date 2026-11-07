"""
Окно второго пароля — главная защита «Гостевого режима».

Как работает:
    * Окно разворачивается на весь экран, поверх всех окон, без рамки
      и без кнопки закрытия.
    * Alt+F4 перехватывается и игнорируется — закрыть окно можно только
      правильным паролем (или командой «Впустить» с сайта, или аварийным
      флагом-файлом — см. agent.py).
    * Таймер (PASSWORD_TIMEOUT секунд) отсчитывает время на ввод пароля.
      Если время вышло и пароль не введён — ПК выключается
      (shutdown /s /t 0), если это не DRY_RUN.
    * В DRY_RUN окно НЕ разворачивается на весь экран, у него есть обычная
      кнопка закрытия (крестик), и по истечении таймера вместо выключения
      просто пишется запись в лог.

Известное ограничение: Alt+Tab штатными средствами tkinter перехватить
нельзя (нужен низкоуровневый системный хук), поэтому он не блокируется.
Основная защита — то, что окно всегда поверх всех остальных (topmost)
и без рамки, так что просто так его не свернуть и не закрыть иначе,
как паролем.

ВАЖНО про потоки: tkinter нельзя использовать из нескольких потоков за
время жизни процесса — рано или поздно это роняет сам интерпретатор Tcl
с ошибкой «Tcl_AsyncDelete: async handler deleted by the wrong thread»
(именно так агент падал в бою). Поэтому во всём агенте tkinter живёт
в ОДНОМ выделенном потоке (ensure_ui_thread), который держит один скрытый
корень Tk() на весь процесс, а каждое окно пароля — это Toplevel поверх
него, а не отдельный Tk(). run_in_thread() вызывается из главного цикла
агента (из другого потока) и только кладёт задачу в очередь — саму
работу с виджетами делает исключительно UI-поток.

Пароль хранится в agent/.env открытым текстом (GUEST_PASSWORD) — его
можно просто посмотреть в файле, не нужно ничего генерировать заново.
"""
import hmac
import logging
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import font as tkfont

import config

log = logging.getLogger("guest_agent.password_window")

# Окно сейчас открыто?
_window_open = threading.Event()
# Если выставлен — окно должно закрыться само, без ввода пароля
_force_close = threading.Event()

# --- единственный UI-поток для всего tkinter в агенте ---
_ui_queue: "queue.Queue" = queue.Queue()
_ui_thread: threading.Thread | None = None
_ui_root: tk.Tk | None = None  # создаётся один раз внутри UI-потока


def is_open() -> bool:
    return _window_open.is_set()


_remaining: int | None = None


def seconds_left() -> int | None:
    """Сколько секунд осталось до автовыключения (None, если окно закрыто)."""
    return _remaining if _window_open.is_set() else None


def request_close() -> None:
    """Вызывается извне (из главного цикла агента), чтобы снять окно
    без ввода пароля — например, по команде «Впустить» с сайта или
    по аварийному флагу-файлу."""
    _force_close.set()


def _check_password(entered: str) -> bool:
    if not config.GUEST_PASSWORD:
        # Пароль ещё не задан в .env — не блокируем человека наглухо
        # без возможности войти.
        log.warning("GUEST_PASSWORD не задан в agent/.env — проверка пароля пропущена")
        return True
    return hmac.compare_digest(entered, config.GUEST_PASSWORD)


def _do_shutdown(reason: str) -> None:
    if config.DRY_RUN:
        log.info("[DRY_RUN] выключил бы ПК (причина: %s)", reason)
        return
    log.warning("Таймер истёк — выключаю ПК (причина: %s)", reason)
    subprocess.run(["shutdown", "/s", "/t", "0"], shell=False, check=False)


def _show_window() -> None:
    _window_open.set()
    _force_close.clear()
    try:
        _build_and_run()
    except Exception:
        # _build_and_run больше не блокирует (Toplevel, не mainloop) —
        # если тут ошибка, значит окно не построилось вовсе, и флаг
        # «окно открыто» нужно сразу снять. А если построилось успешно,
        # флаг снимает уже сам _build_and_run в момент закрытия окна
        # (см. _finish внутри неё) — здесь его трогать нельзя.
        log.exception("Ошибка в окне пароля")
        _window_open.clear()


def _build_and_run() -> None:
    global _remaining
    _remaining = config.PASSWORD_TIMEOUT
    # Toplevel поверх уже существующего скрытого корня _ui_root — НЕ новый
    # Tk()/новый Tcl-интерпретатор. Это и есть тот самый фикс падения.
    root = tk.Toplevel(_ui_root)
    root.title("Гостевой режим")
    root.configure(bg="#111318")

    if config.DRY_RUN:
        # Тестовый режим: обычное окно, можно закрыть крестиком
        root.geometry("480x340")
        root.resizable(False, False)
    else:
        # Боевой режим: окно на весь экран, без рамки, без кнопки закрытия
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        root.geometry(f"{screen_w}x{screen_h}+0+0")
        root.overrideredirect(True)      # убирает рамку и системную кнопку закрытия
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", lambda: None)

    remaining = {"seconds": config.PASSWORD_TIMEOUT}
    unlocked = {"value": False}

    def _finish() -> None:
        """Единая точка закрытия окна: снимает флаг «окно открыто» и
        уничтожает Toplevel. Вызывать вместо голого root.destroy() —
        иначе is_open()/seconds_left() продолжат врать, что окно ещё
        открыто."""
        _window_open.clear()
        root.destroy()

    title_font = tkfont.Font(family="Segoe UI", size=22, weight="bold")
    label_font = tkfont.Font(family="Segoe UI", size=12)
    timer_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")

    tk.Label(
        root, text="Введите пароль, чтобы продолжить",
        font=title_font, fg="#f5f5f5", bg="#111318",
    ).pack(pady=(60, 10))

    tk.Label(
        root, text="Компьютер в гостевом режиме.",
        font=label_font, fg="#aaaaaa", bg="#111318",
    ).pack(pady=(0, 30))

    entry_var = tk.StringVar()
    entry = tk.Entry(
        root, textvariable=entry_var, show="•", font=label_font,
        width=24, justify="center",
    )
    entry.pack(pady=10)
    entry.focus_set()

    error_label = tk.Label(root, text="", font=label_font, fg="#ff6b6b", bg="#111318")
    error_label.pack(pady=5)

    timer_label = tk.Label(root, text="", font=timer_font, fg="#f5a623", bg="#111318")
    timer_label.pack(pady=20)

    def try_unlock(_event=None) -> None:
        if _check_password(entry_var.get()):
            unlocked["value"] = True
            log.info("Пароль введён верно — окно снимается")
            _finish()
        else:
            error_label.config(text="Неверный пароль, попробуйте ещё раз")
            entry_var.set("")

    entry.bind("<Return>", try_unlock)
    tk.Button(root, text="Разблокировать", command=try_unlock, font=label_font).pack(pady=10)

    # Блокируем Alt+F4
    root.bind("<Alt-F4>", lambda e: "break")

    def tick() -> None:
        if unlocked["value"]:
            return
        if _force_close.is_set():
            log.info("Окно снято принудительно (команда с сайта / аварийный флаг)")
            _finish()
            return
        remaining["seconds"] -= 1
        global _remaining
        _remaining = remaining["seconds"]
        timer_label.config(text=f"Автовыключение через {remaining['seconds']} сек")
        if remaining["seconds"] <= 0:
            _do_shutdown("таймер окна пароля истёк")
            _finish()
            return
        root.after(1000, tick)

    timer_label.config(text=f"Автовыключение через {remaining['seconds']} сек")
    root.after(1000, tick)

    # Проверяем принудительное закрытие почаще, не дожидаясь тика таймера
    def watch_force_close() -> None:
        if unlocked["value"]:
            return
        if _force_close.is_set():
            _finish()
            return
        root.after(300, watch_force_close)

    root.after(300, watch_force_close)

    if not config.DRY_RUN:
        root.focus_force()  # без рамки окно иначе может не получить фокус ввода

    # Отдельный mainloop здесь не нужен и не вызывается: это Toplevel,
    # события для него обрабатывает mainloop уже запущенного _ui_root
    # (см. _ui_loop) — именно поэтому окно не блокирует этот поток
    # и не создаёт второй Tcl-интерпретатор.


def _ui_loop() -> None:
    """Работает в единственном выделенном потоке на весь процесс агента.
    Создаёт один скрытый корень Tk() и дальше только обслуживает очередь
    задач (_ui_queue) да сам mainloop — никакой другой код не должен
    напрямую трогать tkinter из других потоков."""
    global _ui_root
    _ui_root = tk.Tk()
    _ui_root.withdraw()  # сам корень невидим, нужен только как держатель интерпретатора

    def drain_queue() -> None:
        try:
            while True:
                task = _ui_queue.get_nowait()
                try:
                    task()
                except Exception:
                    log.exception("Ошибка при обработке задачи окна пароля")
        except queue.Empty:
            pass
        _ui_root.after(50, drain_queue)

    _ui_root.after(50, drain_queue)
    _ui_root.mainloop()


def ensure_ui_thread() -> None:
    """Запускает единственный UI-поток, если он ещё не запущен. Можно
    (и нужно) вызвать один раз при старте агента — но на всякий случай
    run_in_thread() тоже это делает сама."""
    global _ui_thread
    if _ui_thread and _ui_thread.is_alive():
        return
    _ui_thread = threading.Thread(target=_ui_loop, name="tk-ui", daemon=True)
    _ui_thread.start()


def run_in_thread() -> None:
    """Просит UI-поток показать окно пароля, если оно ещё не открыто.
    Вызывается из главного цикла агента (другого потока) — сама функция
    tkinter не трогает, только кладёт задачу в очередь для UI-потока."""
    ensure_ui_thread()
    if _window_open.is_set():
        log.debug("Окно пароля уже открыто — повторный запуск пропущен")
        return
    _ui_queue.put(_show_window)
