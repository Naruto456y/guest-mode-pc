"""
Главный цикл агента «Гостевой режим ПК».

Что делает:
    1. Раз в POLL_INTERVAL секунд спрашивает у сервера, есть ли новая команда
       (окно пароля, блокировка приложений и её белый список, розыгрыши,
       блокировка сеанса, открыть ссылку, снимок экрана по требованию,
       включить/выключить живую трансляцию).
    2. Раз в STATUS_INTERVAL секунд отправляет статус, список процессов
       и текущий белый список приложений.
    3. Раз в SCREENSHOT_INTERVAL секунд отправляет скриншот (а во время
       живой трансляции — гораздо чаще, см. STREAM_INTERVAL).
    4. Каждый цикл проверяет аварийный флаг-файл (config.EMERGENCY_FLAG) —
       если он появился, агент немедленно снимает все блокировки и не
       показывает окно пароля, пока файл не удалят.

Если сервер недоступен, агент не падает и продолжает работать
автономно — просто новые команды с сайта временно не приходят.

Запуск (из папки agent/):
    python agent.py
"""
import logging
import sys
import threading
import time

import app_blocker
import config
import password_window
import pc_control
import pranks
import remote_control
import reporter
from logger_setup import setup_logging

log = logging.getLogger("guest_agent")

_mode = {"stream_started_at": 0.0}
_stream_on = threading.Event()  # включена ли живая трансляция


def _emergency_flag_present() -> bool:
    return config.EMERGENCY_FLAG.exists()


def _send_status() -> None:
    # «Заблокирован» = окно пароля реально открыто (а не флаг, который
    # раньше оставался True навсегда после ввода пароля)
    mode = "locked" if password_window.is_open() else "normal"
    reporter.send_status(
        mode, app_blocker.is_enabled(),
        lock_remaining=password_window.seconds_left(),
        streaming=_stream_on.is_set(),
        pranks_active=pranks.active(),
    )


def _disable_everything(reason: str) -> None:
    # Розыгрыши снимаем всегда (экран мог быть повёрнут и без блокировок),
    # остальное — только если что-то реально включено
    if password_window.is_open() or app_blocker.is_enabled():
        log.warning("Отключаю все блокировки (причина: %s)", reason)
        password_window.request_close()
        app_blocker.disable()
    pranks.restore_all()


def handle_command(command: dict) -> None:
    cmd_type = command.get("type")
    log.info("Получена команда с сервера: %s", cmd_type)

    if cmd_type == "show_password_window":
        password_window.run_in_thread()

    elif cmd_type == "let_in":
        _disable_everything("команда «Впустить» с сайта")

    elif cmd_type == "block_apps_on":
        app_blocker.enable()

    elif cmd_type == "block_apps_off":
        app_blocker.disable()

    elif cmd_type == "set_whitelist":
        processes = command.get("params", {}).get("processes", [])
        app_blocker.set_whitelist(processes)

    elif cmd_type == "prank":
        params = dict(command.get("params", {}))
        prank_name = params.pop("name", "")
        pranks.apply(prank_name, **params)

    elif cmd_type == "prank_restore_all":
        pranks.restore_all()

    elif cmd_type == "lock_workstation":
        pc_control.lock_workstation()

    elif cmd_type == "open_url":
        url = command.get("params", {}).get("url", "")
        pc_control.open_url(url)

    elif cmd_type == "remote":
        remote_control.handle(command.get("params", {}))

    elif cmd_type == "download_file":
        params = command.get("params", {})
        reporter.download_file(str(params.get("id", "")), str(params.get("name", "file")))

    elif cmd_type == "snapshot_now":
        reporter.send_screenshot()

    elif cmd_type == "start_stream":
        _mode["stream_started_at"] = time.time()
        _stream_on.set()
        log.info("Включена живая трансляция экрана")

    elif cmd_type == "stop_stream":
        if _stream_on.is_set():
            log.info("Выключена живая трансляция экрана")
        _stream_on.clear()

    elif cmd_type == "disable_guest_mode":
        _stream_on.clear()
        _disable_everything("команда «Отключить режим» с сайта")

    else:
        log.warning("Неизвестный тип команды: %s", cmd_type)


def main() -> None:
    setup_logging()
    config.validate()

    log.info("=" * 60)
    log.info("Агент «Гостевой режим ПК» запущен")
    log.info("DRY_RUN = %s  (меняется только в agent/.env, не с сайта)", config.DRY_RUN)
    log.info("=" * 60)

    if config.DRY_RUN:
        log.info("Работаю в ТЕСТОВОМ режиме: опасные действия будут только логироваться")
    else:
        log.warning("Работаю в БОЕВОМ режиме: действия выполняются по-настоящему")

    if _emergency_flag_present():
        log.warning(
            "Аварийный флаг %s уже существует при старте — блокировки не будут включаться",
            config.EMERGENCY_FLAG,
        )

    app_blocker.start()
    threading.Thread(target=_command_worker, name="commands", daemon=True).start()
    threading.Thread(target=_stream_worker, name="stream", daemon=True).start()

    last_status = 0.0
    last_screenshot = 0.0

    while True:
        try:
            now = time.time()
            flag = _emergency_flag_present()
            if flag:
                _disable_everything(f"обнаружен файл {config.EMERGENCY_FLAG}")
                _stream_on.clear()

            if now - last_status >= config.STATUS_INTERVAL:
                _send_status()
                last_status = now

            if _stream_on.is_set():
                if now - _mode["stream_started_at"] > config.STREAM_MAX_SECONDS:
                    log.warning(
                        "Трансляция выключена автоматически — прошло больше %s сек (забыли выключить?)",
                        config.STREAM_MAX_SECONDS,
                    )
                    _stream_on.clear()
            elif not flag and now - last_screenshot >= config.SCREENSHOT_INTERVAL:
                reporter.send_screenshot()
                last_screenshot = now

        except Exception:
            log.exception("Непредвиденная ошибка в главном цикле — продолжаю работу")

        time.sleep(min(config.POLL_INTERVAL, 1.0))


def _command_worker() -> None:
    """Отдельный поток: держит long-poll к серверу, поэтому команды с сайта
    выполняются сразу, а не раз в несколько секунд."""
    while True:
        try:
            if _emergency_flag_present():
                time.sleep(1.0)  # пока лежит флаг — команды не принимаем
                continue
            command = reporter.poll_command(wait=config.POLL_WAIT)
            if command:
                handle_command(command)
            else:
                time.sleep(0.05)  # сервер недоступен — не крутимся вхолостую
        except Exception:
            log.exception("Ошибка при обработке команды — продолжаю работу")
            time.sleep(1.0)


def _stream_worker() -> None:
    """Отдельный поток трансляции: ждёт включения и шлёт кадры максимально часто."""
    while True:
        _stream_on.wait()
        reporter.run_stream(
            _stream_on.is_set, config.STREAM_INTERVAL,
            config.STREAM_QUALITY, config.STREAM_WIDTH,
        )
        time.sleep(0.2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nАгент остановлен пользователем (Ctrl+C)")
        sys.exit(0)
