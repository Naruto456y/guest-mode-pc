"""Смоке-тесты агента в DRY_RUN (реальных действий нет)."""
import importlib
import os
import sys
from pathlib import Path

import pytest

AGENT = Path(__file__).resolve().parent.parent / "agent"


@pytest.fixture()
def agent_mods(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("AGENT_TOKEN", "t")
    monkeypatch.setenv("EMERGENCY_FLAG", str(AGENT / "no_such.flag"))
    monkeypatch.syspath_prepend(str(AGENT))
    names = ("config", "app_blocker", "password_window", "pranks", "pc_control", "remote_control", "reporter", "agent")
    saved = {n: sys.modules.pop(n, None) for n in names}  # у сервера тоже есть config
    yield {n: importlib.import_module(n) for n in ("config", "app_blocker", "pranks", "password_window", "agent")}
    for n in names:
        sys.modules.pop(n, None)
        if saved[n] is not None:
            sys.modules[n] = saved[n]


def test_whitelist_normalised(agent_mods):
    ab = agent_mods["app_blocker"]
    ab.set_whitelist([" Notepad.EXE ", "", "calc.exe"])
    assert ab.get_whitelist() == ["calc.exe", "notepad.exe"]
    assert ab._is_allowed("explorer.exe")  # защищённый всегда разрешён


def test_pranks_state_and_restore(agent_mods):
    p = agent_mods["pranks"]
    assert p.apply("rotate_180") and p.apply("swap_mouse_buttons")
    assert len(p.active()) == 2
    p.restore_all()
    assert p.active() == []
    assert not p.apply("nonexistent")


def test_emergency_restores_pranks(agent_mods):
    a, p = agent_mods["agent"], agent_mods["pranks"]
    p.apply("rotate_180")
    a._disable_everything("тест")  # раньше выходила досрочно и не снимала розыгрыши
    assert p.active() == []


def test_open_url_rejects_non_http(agent_mods, caplog):
    import pc_control
    pc_control.open_url("file:///C:/x.exe")
    assert "Отклонён" in caplog.text


def test_unknown_command_does_not_crash(agent_mods):
    agent_mods["agent"].handle_command({"type": "wat"})


def test_remote_actions_dry_run(agent_mods, caplog):
    import logging
    caplog.set_level(logging.INFO)
    a = agent_mods["agent"]
    for params in (
        {"action": "click_at", "x": 0.5, "y": 0.5, "button": "right"},
        {"action": "move", "dx": 50, "dy": -50},
        {"action": "scroll", "amount": -3},
        {"action": "type", "text": "привет"},
        {"action": "hotkey", "combo": "alt+tab"},
        {"action": "open_app", "name": "notepad"},
        {"action": "search", "query": "котики", "engine": "youtube"},
    ):
        a.handle_command({"type": "remote", "params": params})
    assert caplog.text.count("[DRY_RUN]") >= 7


def test_remote_rejects_unknown_hotkey(agent_mods, caplog):
    import remote_control
    remote_control.hotkey("ctrl+alt+delete")
    assert "Отклонена" in caplog.text
