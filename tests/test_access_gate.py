"""Tests for the evaluator access request and approval gate."""
from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from emporio_agent.access import FirebaseRTDBAccessStore, InMemoryAccessStore
from emporio_agent.api import create_app


class _FakeResponse:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_chat_is_open_when_gate_is_disabled(make_agent):
    agent, _ = make_agent(["Oi"])
    client = TestClient(create_app(agent))
    status = client.get("/api/v1/access/status").json()
    assert status["data"]["gate_enabled"] is False
    assert status["data"]["status"] == "approved"
    assert client.post("/api/v1/chat", json={"message": "Oi"}).status_code == 200


def test_gate_blocks_chat_without_calling_llm(make_agent):
    agent, llm = make_agent(["Oi"])
    store = InMemoryAccessStore()
    client = TestClient(create_app(agent, access_store=store, admin_token="secret-admin"))

    response = client.post("/api/v1/chat", json={"message": "Oi"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_REQUIRED"
    assert llm.requests == []


def test_request_approval_flow_unlocks_chat(make_agent):
    agent, llm = make_agent(["Olá, posso ajudar!"])
    store = InMemoryAccessStore()
    client = TestClient(create_app(agent, access_store=store, admin_token="secret-admin"))

    req = client.post(
        "/api/v1/access/request",
        json={"name": "Avaliadora Ana", "email": "ana@empresa.com", "note": "Processo seletivo"},
    )
    assert req.status_code == 200
    token = req.json()["data"]["token"]
    assert req.json()["data"]["status"] == "pending"

    # Still blocked while pending
    blocked = client.post("/api/v1/chat", json={"message": "Oi"}, headers={"X-Access-Token": token})
    assert blocked.status_code == 403
    assert llm.requests == []

    # Admin lists requests
    listed = client.get("/api/v1/access/admin/requests", headers={"X-Admin-Token": "secret-admin"})
    assert listed.status_code == 200
    items = listed.json()["data"]["requests"]
    assert len(items) == 1
    key = items[0]["key"]

    # Admin approves
    decision = client.post(
        "/api/v1/access/admin/decision",
        json={"key": key, "status": "approved"},
        headers={"X-Admin-Token": "secret-admin"},
    )
    assert decision.status_code == 200
    assert decision.json()["data"]["request"]["status"] == "approved"

    # Status check now shows approved
    status = client.get("/api/v1/access/status", headers={"X-Access-Token": token})
    assert status.json()["data"]["status"] == "approved"

    # Chat now works
    chat = client.post("/api/v1/chat", json={"message": "Oi"}, headers={"X-Access-Token": token})
    assert chat.status_code == 200
    assert chat.json()["data"]["reply"] == "Olá, posso ajudar!"
    assert len(llm.requests) == 1


def test_admin_endpoints_reject_invalid_token(make_agent):
    agent, _ = make_agent([])
    store = InMemoryAccessStore()
    client = TestClient(create_app(agent, access_store=store, admin_token="secret-admin"))

    assert client.get("/api/v1/access/admin/requests", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.post(
        "/api/v1/access/admin/decision",
        json={"key": "abc", "status": "approved"},
        headers={"X-Admin-Token": "wrong"},
    ).status_code == 401


def test_approved_emails_env_auto_approves(make_agent):
    agent, _ = make_agent(["Tudo certo!"])
    store = InMemoryAccessStore()
    client = TestClient(create_app(agent, access_store=store, approved_emails={"vip@empresa.com"}))

    req = client.post("/api/v1/access/request", json={"name": "VIP", "email": "VIP@Empresa.com"})
    assert req.status_code == 200
    assert req.json()["data"]["status"] == "approved"
    token = req.json()["data"]["token"]

    chat = client.post("/api/v1/chat", json={"message": "Oi"}, headers={"X-Access-Token": token})
    assert chat.status_code == 200


def test_firebase_rtdb_store_roundtrip_with_mock_transport():
    db: dict[str, dict] = {}

    def fake_urlopen(req, timeout=8.0):
        url = req.full_url
        method = req.get_method()
        assert "auth=my-secret" in url
        path = url.split(".firebaseio.com/")[1].split(".json")[0]
        parts = path.split("/")
        body = json.loads(req.data.decode("utf-8")) if req.data else None

        if method == "GET":
            result = db if path == "access_requests" else db.get(parts[1])
        elif method == "PUT":
            db[parts[1]] = body
            result = body
        elif method == "PATCH":
            db[parts[1]].update(body)
            result = db[parts[1]]
        else:
            raise AssertionError(f"Unexpected method {method}")

        return _FakeResponse(json.dumps(result).encode("utf-8"))

    store = FirebaseRTDBAccessStore("https://demo-default-rtdb.firebaseio.com", "my-secret", opener=fake_urlopen)
    record, expose = store.request_access("Carlos", "carlos@empresa.com", "Tech Lead")
    assert expose is True
    assert record.status == "pending"
    assert store.get_by_token(record.token).email == "carlos@empresa.com"

    updated = store.set_status(record.key, "approved")
    assert updated is not None and updated.status == "approved"
    assert store.list_requests()[0].status == "approved"
