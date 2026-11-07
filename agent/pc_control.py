"""
Команды управления ПК, которые не являются розыгрышами: обычные
системные действия, которые владелец компьютера может захотеть выполнить
удалённо (заблокировать сеанс, открыть ссылку на экране у гостя).

Как и везде в проекте: в DRY_RUN реальных действий не происходит,
только запись в лог.
"""
import ctypes
import logging
import os

import config

log = logging.getLogger("guest_agent.pc_control")

user32 = ctypes.windll.user32


def lock_workstation() -> None:
    """Аналог Win+L — блокирует сеанс Windows (показывает экран входа).
    Полностью штатное и обратимое действие: снимается обычным входом
    в систему, ничего не теряется."""
    if config.DRY_RUN:
        log.info("[DRY_RUN] заблокировал бы сеанс Windows (как Win+L)")
        return
    user32.LockWorkStation()
    log.info("Сеанс заблокирован (LockWorkStation)")


def open_url(url: str) -> None:
    """Открывает ссылку в браузере по умолчанию на экране у гостя.
    Принимает только http(s)-ссылки — защита от попытки «открыть»
    произвольный локальный файл или команду через file:// и т.п."""
    url = (url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        log.warning("Отклонён open_url с недопустимым адресом: %r", url)
        return
    if config.DRY_RUN:
        log.info("[DRY_RUN] открыл бы ссылку в браузере: %s", url)
        return
    try:
        os.startfile(url)
        log.info("Открыта ссылка в браузере по умолчанию: %s", url)
    except OSError:
        log.exception("Не удалось открыть ссылку: %s", url)
