import time

import state as state_mod
from conftest import AGENT


def test_requires_login(client):
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/dashboard_data").status_code == 401
    assert client.post("/control/lock").status_code == 401


def test_wrong_password_and_lockout(client):
    for _ in range(5):
        r = client.post("/login", data={"password": "bad"}, follow_redirects=False)
        assert r.headers["location"] == "/login?error=1"
    # после 5 неудач даже верный пароль не пускает
    r = client.post("/login", data={"password": "secret-pass"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=1"


def test_agent_token_required(client):
    assert client.get("/api/agent/poll").status_code == 403
    assert client.get("/api/agent/poll", headers={"X-Agent-Token": "nope"}).status_code == 403
    assert client.get("/api/agent/poll", headers=AGENT).json() == {"command": None}


def test_command_roundtrip(logged_in):
    logged_in.post("/control/lock")
    cmd = logged_in.get("/api/agent/poll", headers=AGENT).json()["command"]
    assert cmd["type"] == "show_password_window"


def test_disable_goes_first(logged_in):
    logged_in.post("/control/lock")
    logged_in.post("/control/disable_guest_mode")
    cmd = logged_in.get("/api/agent/poll", headers=AGENT).json()["command"]
    assert cmd["type"] == "disable_guest_mode"


def test_prank_validation(logged_in):
    assert logged_in.post("/control/prank/format_c").status_code == 400
    assert logged_in.post("/control/prank/rotate_180").status_code == 200


def test_open_url_only_http(logged_in):
    r = logged_in.post("/control/open_url", json={"url": "file:///C:/Windows/System32/cmd.exe"})
    assert r.status_code == 400
    assert logged_in.post("/control/open_url", json={"url": "https://example.com"}).status_code == 200


def test_status_flow(logged_in):
    logged_in.post("/api/agent/status", headers=AGENT, json={
        "dry_run": True, "mode": "locked", "blocking_enabled": True,
        "processes": [{"pid": 1, "name": "a.exe"}], "allowed_processes": ["a.exe"],
        "lock_remaining": 42, "streaming": True, "pranks_active": ["экран повёрнут (2)"],
    })
    d = logged_in.get("/api/dashboard_data").json()
    assert d["online"] and d["mode"] == "locked" and d["lock_remaining"] == 42
    assert d["streaming"] and d["pranks_active"]
    msgs = [e["message"] for e in d["events"]]
    assert any("Агент на связи" in m for m in msgs)
    assert any("Окно пароля показано" in m for m in msgs)


def test_screenshot_upload_and_limit(logged_in):
    files = {"screenshot": ("s.jpg", b"\xff\xd8jpegdata", "image/jpeg")}
    assert logged_in.post("/api/agent/screenshot", headers=AGENT, files=files).status_code == 200
    assert logged_in.get("/screenshot.jpg").content == b"\xff\xd8jpegdata"
    big = {"screenshot": ("s.jpg", b"0" * (10 * 1024 * 1024 + 1), "image/jpeg")}
    assert logged_in.post("/api/agent/screenshot", headers=AGENT, files=big).status_code == 413


def test_csrf_foreign_origin_rejected(logged_in):
    r = logged_in.post("/control/lock", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert logged_in.post("/control/lock", headers={"Origin": "http://testserver"}).status_code == 200


def test_stale_commands_dropped(logged_in):
    state_mod.state.push_command({"type": "old"})
    state_mod.state.command_queue[0]["ts"] -= 100
    assert logged_in.get("/api/agent/poll", headers=AGENT).json() == {"command": None}


def test_events_persist(tmp_path):
    f = tmp_path / "ev.jsonl"
    s1 = state_mod.State(events_file=str(f))
    s1.add_event("info", "один")
    s1.add_event("warning", "два")
    s2 = state_mod.State(events_file=str(f))
    assert [e["message"] for e in s2.get_events()] == ["два", "один"]
    s2.clear_events()
    assert state_mod.State(events_file=str(f)).get_events() == []


def test_healthz(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_long_poll_returns_fast_and_times_out(logged_in):
    t = time.monotonic()
    assert logged_in.get("/api/agent/poll?wait=0.3", headers=AGENT).json() == {"command": None}
    assert time.monotonic() - t >= 0.25  # держал запрос открытым
    logged_in.post("/control/lock")
    t = time.monotonic()
    cmd = logged_in.get("/api/agent/poll?wait=5", headers=AGENT).json()["command"]
    assert cmd["type"] == "show_password_window" and time.monotonic() - t < 1


def test_rotations_removed(logged_in):
    assert logged_in.post("/control/prank/rotate_90").status_code == 400
    assert logged_in.post("/control/prank/rotate_270").status_code == 400


def test_open_url_adds_https(logged_in):
    assert logged_in.post("/control/open_url", json={"url": "youtube.com"}).status_code == 200
    cmd = logged_in.get("/api/agent/poll", headers=AGENT).json()["command"]
    assert cmd["params"]["url"] == "https://youtube.com"


def test_remote_validation(logged_in):
    ok = [
        {"action": "click_at", "x": 0.2, "y": 0.9, "button": "left", "double": True},
        {"action": "move", "dx": 10, "dy": 0},
        {"action": "click", "button": "right"},
        {"action": "scroll", "amount": 3},
        {"action": "type", "text": "hi"},
        {"action": "hotkey", "combo": "Ctrl+C"},
        {"action": "open_app", "name": "notepad"},
        {"action": "search", "query": "x", "engine": "youtube"},
    ]
    for body in ok:
        assert logged_in.post("/control/remote", json=body).status_code == 200, body
    bad = [
        {"action": "click_at", "x": 2, "y": 0.5},
        {"action": "click", "button": "x"},
        {"action": "hotkey", "combo": "ctrl+alt+delete"},
        {"action": "open_app", "name": "https://evil"},
        {"action": "search", "query": "x", "engine": "google"},
        {"action": "rm -rf"},
    ]
    for body in bad:
        assert logged_in.post("/control/remote", json=body).status_code == 400, body
    cmd = logged_in.get("/api/agent/poll", headers=AGENT).json()["command"]
    assert cmd == {"type": "remote", "params": ok[0]} or cmd["type"] == "remote"


def test_file_upload_roundtrip(logged_in):
    r = logged_in.post("/control/upload", files={"file": ("../../evil.txt", b"hello")})
    assert r.status_code == 200
    cmd = logged_in.get("/api/agent/poll", headers=AGENT).json()["command"]
    assert cmd["type"] == "download_file" and cmd["params"]["name"] == "evil.txt"
    file_url = "/api/agent/file/" + cmd["params"]["id"]
    assert logged_in.get(file_url).status_code == 403  # без токена агента нельзя
    assert logged_in.get(file_url, headers=AGENT).content == b"hello"
    assert logged_in.get(file_url, headers=AGENT).status_code == 404  # отдаётся один раз
