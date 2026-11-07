import os
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent / "server"
PASSWORD = "secret-pass"

os.environ.update({
    "ADMIN_PASSWORD": PASSWORD,
    "AGENT_TOKEN": "agent-token-123",
    "SESSION_SECRET": "x" * 32,
    "LOG_FILE": "test_server.log",
})
os.chdir(SERVER)  # main.py ждёт static/ и templates/ рядом
sys.path.insert(0, str(SERVER))


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    import auth
    from main import app
    from state import state

    state.events_file = None  # не пишем в настоящий events.jsonl
    state.command_queue.clear()
    state.events.clear()
    auth._fails.clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def logged_in(client):
    r = client.post("/login", data={"password": PASSWORD}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    return client


AGENT = {"X-Agent-Token": "agent-token-123"}
