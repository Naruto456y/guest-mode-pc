"""
Общее состояние сервера хранится в памяти процесса (без базы данных —
для одного агента этого достаточно, и так проще для понимания
и отладки). Если сервер перезапустится, состояние (последний скриншот,
очередь команд, лог событий) сбросится — это осознанное упрощение,
см. README.md.

Доступ к состоянию защищён обычным threading.Lock, потому что FastAPI
обрабатывает синхронные обработчики (def, не async def) в пуле потоков,
и несколько запросов могут прийти одновременно.
"""
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field


# Команды старше этого возраста (сек) агент уже не получит — pop_command
# их тихо выбросит. Нужно, чтобы при переподключении агента (он был
# офлайн, вы тем временем жали кнопки) не было «проигрывания» всех
# старых нажатий подряд с задержкой — то, что выглядело как «команды
# выполняются очень долго, стоят в очереди».
STALE_COMMAND_MAX_AGE = 25.0

# Пауза между статусами (сек), после которой агент считается «пропадавшим»
ONLINE_EVENT_GAP = 20.0


@dataclass
class AgentStatus:
    online: bool = False
    dry_run: bool = True
    mode: str = "normal"  # "normal" | "locked"
    blocking_enabled: bool = False
    processes: list = field(default_factory=list)
    allowed_processes: list = field(default_factory=list)
    last_seen: float = 0.0
    lock_remaining: int | None = None  # сек до автовыключения, пока открыто окно пароля
    streaming: bool = False
    pranks_active: list = field(default_factory=list)  # что сейчас «включено» (экран, мышь)


class State:
    def __init__(self, log_history_size: int = 200, events_file: str | None = None) -> None:
        self._lock = threading.Lock()
        self.events_file = events_file
        self.status = AgentStatus()
        self.last_screenshot: bytes | None = None
        self.last_screenshot_at: float = 0.0
        self.command_queue: deque = deque()
        self.events: deque = deque(maxlen=log_history_size)
        if events_file:
            self._load_events()

    # --- статус агента ---
    def update_status(self, online: bool, dry_run: bool, mode: str,
                       blocking_enabled: bool, processes: list,
                       allowed_processes: list | None = None,
                       lock_remaining: int | None = None, streaming: bool = False,
                       pranks_active: list | None = None) -> None:
        with self._lock:
            was_offline = time.time() - self.status.last_seen > ONLINE_EVENT_GAP
            old_mode = self.status.mode
            self.status = AgentStatus(
                online=online, dry_run=dry_run, mode=mode,
                blocking_enabled=blocking_enabled, processes=processes,
                allowed_processes=allowed_processes or [],
                last_seen=time.time(),
                lock_remaining=lock_remaining, streaming=streaming,
                pranks_active=pranks_active or [],
            )
        # События в журнал — уже без удержания блокировки
        if was_offline:
            self.add_event("info", "Агент на связи" + (" (ТЕСТОВЫЙ режим)" if dry_run else " (БОЕВОЙ режим)"))
        if old_mode != mode:
            self.add_event("info", "Окно пароля показано гостю" if mode == "locked" else "Окно пароля закрыто")

    def get_status(self, online_timeout: int) -> AgentStatus:
        with self._lock:
            status = self.status
            if time.time() - status.last_seen > online_timeout:
                status.online = False
            return status

    # --- скриншот ---
    def set_screenshot(self, data: bytes) -> None:
        with self._lock:
            self.last_screenshot = data
            self.last_screenshot_at = time.time()

    def get_screenshot(self) -> tuple[bytes | None, float]:
        with self._lock:
            return self.last_screenshot, self.last_screenshot_at

    # --- очередь команд агенту ---
    def push_command(self, command: dict) -> None:
        command = {**command, "ts": time.time()}
        with self._lock:
            self.command_queue.append(command)
        self.add_event("info", f"Команда поставлена в очередь: {command.get('type')}")

    def push_command_front(self, command: dict) -> None:
        """Как push_command, но ставит команду в начало очереди (для
        аварийных команд, которые должны выполниться раньше остальных)."""
        command = {**command, "ts": time.time()}
        with self._lock:
            self.command_queue.appendleft(command)

    def pop_command(self) -> dict | None:
        fresh_command = None
        dropped_types: list[str] = []
        with self._lock:
            while self.command_queue:
                command = self.command_queue.popleft()
                age = time.time() - command.get("ts", 0)
                if age <= STALE_COMMAND_MAX_AGE:
                    fresh_command = command
                    break
                dropped_types.append(str(command.get("type")))

        # Лог пишем уже без удержания self._lock, чтобы не блокировать
        # другие запросы на время записи события
        for cmd_type in dropped_types:
            self.add_event("warning", f"Устаревшая команда пропущена (не выполнена): {cmd_type}")

        return fresh_command

    def queue_length(self) -> int:
        with self._lock:
            return len(self.command_queue)

    # --- журнал событий для сайта ---
    def add_event(self, level: str, message: str) -> None:
        event = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": message,
        }
        with self._lock:
            self.events.appendleft(event)
            self._persist(event)

    def _persist(self, event: dict) -> None:
        """Дописывает событие в файл, чтобы журнал переживал перезапуск
        сервера. Ошибки записи не должны ломать работу."""
        if not self.events_file:
            return
        try:
            with open(self.events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _load_events(self) -> None:
        try:
            with open(self.events_file, encoding="utf-8") as f:
                lines = f.readlines()[-self.events.maxlen:]
        except OSError:
            return
        for line in lines:
            try:
                self.events.appendleft(json.loads(line))
            except ValueError:
                continue

    def clear_events(self) -> None:
        with self._lock:
            self.events.clear()
            if self.events_file:
                try:
                    open(self.events_file, "w").close()
                except OSError:
                    pass

    def get_events(self) -> list:
        with self._lock:
            return list(self.events)


# Единственный экземпляр состояния на весь процесс сервера
import config  # noqa: E402

state = State(
    log_history_size=config.LOG_HISTORY_SIZE,
    events_file=str(config.BASE_DIR / "events.jsonl"),
)
