"""Shared test setup.

FakeLLM stands in for the real model. We script exactly what the 'model' says
or which tool it asks for, so the tests check OUR code (safety, validation,
state, handoff, fallbacks) deterministically, without a key or network.
What the real model actually says is checked separately, by hand (docs/TEST_RESULTS.md).
"""
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.llm import LLMUnavailable


def text(content):
    return SimpleNamespace(content=content, tool_calls=None)


def tool(name, **args):
    call = SimpleNamespace(id=f"call_{name}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))
    return SimpleNamespace(content="", tool_calls=[call])


class FakeLLM:
    def __init__(self):
        self.script = []      # responses to return, in order
        self.calls = []       # every message list we were sent
        self.fail = False

    def chat(self, messages, tools):
        self.calls.append(messages)
        if self.fail:
            raise LLMUnavailable("simulated outage")
        if not self.script:
            return text("Okay.")
        return self.script.pop(0)


@pytest.fixture
def fake(tmp_path, monkeypatch):
    db.connect(str(tmp_path / "test.db"))
    f = FakeLLM()
    monkeypatch.setattr(main, "llm", f)
    main._hits.clear()
    return f


@pytest.fixture
def client(fake):
    return TestClient(main.app)


@pytest.fixture
def session(client):
    return client.post("/api/session").json()["session_id"]


def send(client, sid, msg):
    r = client.post("/api/chat", json={"session_id": sid, "message": msg})
    assert r.status_code == 200, r.text
    return r.json()
