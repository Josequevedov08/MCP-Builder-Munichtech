"""Usage numbers, the support inbox and the events behind the admin panel."""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import metrics  # noqa: E402
import receipts  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "use_mock_llm", True)
    monkeypatch.setattr(main.settings, "voice_enabled", False)
    monkeypatch.setattr(main.settings, "rate_limit_builds", 1000)
    monkeypatch.setattr(main.settings, "rate_limit_support", 1000)
    monkeypatch.setattr(main.settings, "rate_limit_events", 1000)
    monkeypatch.setattr(main.settings, "admin_token", "")
    monkeypatch.setattr(main.settings, "support_to", "")
    monkeypatch.setattr(main.settings, "database_url", "")
    with TestClient(main.app) as test_client:
        yield test_client


def build(client, source="database", **extra):
    body = {"server_name": "clinic-db", "source_type": source, "resources": ["patients"] if source == "database" else ["./docs"]}
    body.update(extra)
    response = client.post("/api/build-mcp", json=body)
    assert response.status_code == 200, response.text
    return response.json()["build_id"]


SUPPORT = {"name": "Ana Judge", "email": "Ana@Example.com", "topic": "install", "message": "npm install fails on my machine"}


def test_stats_start_empty_and_are_public(client):
    body = client.get("/api/stats").json()
    assert body["builds"]["total"] == 0 and body["orders"]["total"] == 0 and body["persistent"] is False


def test_a_build_with_an_order_is_counted_with_server_side_prices(client):
    build(client, order_id="MB-ABC123", discount_code="LAUNCH20")
    build(client, "files", order_id="MB-ZZZ999", discount_code="FREE100")
    build(client)  # no order: only a build
    stats = client.get("/api/stats").json()
    assert stats["builds"]["total"] == 3 and stats["builds"]["by_source"] == {"files": 1, "database": 2, "api": 0}
    assert stats["orders"]["total"] == 2 and stats["orders"]["test_volume"] == 17.0
    assert {o["order_id"] for o in stats["orders"]["recent"]} == {"MB-ABC123", "MB-ZZZ999"}
    assert stats["builds"]["avg_seconds"] is not None and stats["builds"]["ai_status"] == {"template": 3}


def test_the_same_order_is_never_counted_twice(client):
    build(client, order_id="MB-ABC123")
    build(client, order_id="MB-ABC123")
    assert client.get("/api/stats").json()["orders"]["total"] == 1


def test_bad_order_data_is_rejected(client):
    body = {"server_name": "clinic-db", "source_type": "api", "order_id": "ORDER-1"}
    assert client.post("/api/build-mcp", json=body).status_code == 422


def test_downloads_are_counted_per_source(client):
    build_id = build(client, "files")
    assert client.post("/api/events/download", json={"build_id": build_id}).json() == {"ok": True}
    assert client.post("/api/events/download", json={"build_id": "0" * 32}).status_code == 404
    downloads = client.get("/api/stats").json()["downloads"]
    assert downloads["total"] == 1 and downloads["by_source"]["files"] == 1


def test_errors_are_counted_by_code(client):
    client.post("/api/events/download", json={"build_id": "1" * 32})
    assert client.get("/api/stats").json()["errors"] == {"build_not_found": 1}


def test_support_messages_are_stored_but_never_public(client, monkeypatch):
    monkeypatch.setattr(main.settings, "admin_token", "secret-token")
    response = client.post("/api/support", json=SUPPORT)
    assert response.status_code == 200
    ticket = response.json()["ticket"]
    assert ticket.startswith("SUP-") and response.json()["notified"] is False

    public = client.get("/api/stats")
    assert public.json()["support"] == {"total": 1, "by_topic": {"install": 1}}
    for private in ("Ana", "example.com", "npm install fails"):
        assert private not in public.text

    inbox = client.get("/api/admin/support", headers={"X-Admin-Token": "secret-token"}).json()["tickets"]
    assert inbox[0]["ticket"] == ticket and inbox[0]["email"] == "ana@example.com" and "npm install" in inbox[0]["message"]


def test_the_admin_inbox_needs_the_token(client, monkeypatch):
    assert client.get("/api/admin/support").status_code == 503
    monkeypatch.setattr(main.settings, "admin_token", "secret-token")
    assert client.get("/api/admin/support").status_code == 401
    assert client.get("/api/admin/support", headers={"X-Admin-Token": "wrong"}).status_code == 401
    assert client.get("/api/admin/support", headers={"X-Admin-Token": "secret-token"}).status_code == 200


def test_support_validation(client):
    bad = [
        {**SUPPORT, "topic": "hacking"},
        {**SUPPORT, "message": "no"},
        {**SUPPORT, "email": "nope"},
        {**SUPPORT, "order_id": "#MB-1"},
        {**SUPPORT, "extra": "field"},
        {**SUPPORT, "message": "x" * 2001},
    ]
    for payload in bad:
        assert client.post("/api/support", json=payload).status_code == 422
    assert client.get("/api/stats").json()["support"]["total"] == 0


def test_the_owner_is_notified_with_a_reply_address(client, monkeypatch):
    sent = []
    monkeypatch.setattr(receipts, "send_email", lambda **kwargs: sent.append(kwargs))
    monkeypatch.setattr(main.settings, "email_enabled", True)
    monkeypatch.setattr(main.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(main.settings, "mail_from", "receipts@example.com")
    monkeypatch.setattr(main.settings, "support_to", "owner@example.com")
    response = client.post("/api/support", json={**SUPPORT, "order_id": "MB-ABC123"})
    assert response.json()["notified"] is True
    assert sent[0]["to"] == "owner@example.com" and sent[0]["reply_to"] == "ana@example.com"
    assert "MB-ABC123" in sent[0]["body"] and response.json()["ticket"] in sent[0]["subject"]


def test_a_failed_notification_still_keeps_the_message(client, monkeypatch):
    def down(**kwargs):
        raise OSError("down")

    monkeypatch.setattr(receipts, "send_email", down)
    monkeypatch.setattr(main.settings, "email_enabled", True)
    monkeypatch.setattr(main.settings, "mail_from", "receipts@example.com")
    monkeypatch.setattr(main.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(main.settings, "support_to", "owner@example.com")
    response = client.post("/api/support", json=SUPPORT)
    assert response.status_code == 200 and response.json()["notified"] is False
    assert client.get("/api/stats").json()["support"]["total"] == 1


def test_receipts_are_counted(client, monkeypatch):
    monkeypatch.setattr(main.settings, "email_enabled", True)
    monkeypatch.setattr(main.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(main.settings, "mail_from", "receipts@example.com")
    client.app.state.services.receipt_limiter = main.RateLimiter(1000)
    monkeypatch.setattr(receipts, "send_email", lambda **kwargs: None)
    build_id = build(client)
    client.post("/api/send-receipt", json={"build_id": build_id, "email": "a@b.com", "order_id": "MB-ABC123"})
    assert client.get("/api/stats").json()["receipts"] == {"sent": 1, "failed": 0}


def test_summarize_is_pure_and_free_of_personal_data():
    events = [
        {"ts": "2026-09-20T01:00:00+00:00", "kind": "build", "data": {"source": "api", "ai_status": "applied", "seconds": 4.0}},
        {"ts": "2026-09-20T01:01:00+00:00", "kind": "build", "data": {"source": "api", "ai_status": "defaults", "seconds": 8.0}},
        {"ts": "2026-09-20T01:02:00+00:00", "kind": "support", "data": {"topic": "other", "email": "x@y.com", "message": "hi there"}},
    ]
    result = metrics.summarize(events, persistent=True)
    assert result["builds"]["avg_seconds"] == 6.0 and result["builds"]["max_seconds"] == 8.0
    assert result["builds"]["ai_status"] == {"applied": 1, "defaults": 1}
    assert "x@y.com" not in json.dumps(result) and "hi there" not in json.dumps(result)


# ---- storage: PostgreSQL is replaced by a small fake ----------------------------------------------
class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    async def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, rows, fail):
        self.rows, self.fail = rows, fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=None):
        if self.fail:
            raise OSError("database down")
        sql = sql.strip().lower()
        if sql.startswith("insert"):
            self.rows.append((datetime.now(timezone.utc), params[0], params[1].obj))
        if sql.startswith("select"):
            return FakeCursor(list(reversed(self.rows))[: params[0]])
        return FakeCursor([])


def fake_database(monkeypatch, rows, fail=False):
    async def connect(self):
        return FakeConn(rows, fail)

    monkeypatch.setattr(metrics.Metrics, "_connect", connect)


def test_events_are_written_to_and_read_from_the_database(monkeypatch):
    async def scenario():
        rows = []
        fake_database(monkeypatch, rows)
        store = metrics.Metrics("postgresql://fake")
        await store.start()
        store.record("build", {"source": "files", "ai_status": "applied", "seconds": 3})
        await store.stop()
        assert len(rows) == 1 and rows[0][1] == "build"

        # A new process (empty memory) still sees the earlier events.
        fresh = metrics.Metrics("postgresql://fake")
        await fresh.start()
        summary = await fresh.summary()
        assert summary["builds"]["total"] == 1 and summary["persistent"] is True

    asyncio.run(scenario())


def test_a_database_failure_falls_back_to_memory(monkeypatch):
    async def scenario():
        fake_database(monkeypatch, [], fail=True)
        store = metrics.Metrics("postgresql://fake")
        await store.start()
        assert store.persistent is False
        store.record("build", {"source": "api", "ai_status": "applied", "seconds": 1})
        summary = await store.summary()
        assert summary["builds"]["total"] == 1 and summary["persistent"] is False

    asyncio.run(scenario())


def test_a_database_that_fails_later_does_not_break_reads(monkeypatch):
    async def scenario():
        rows = []
        fake_database(monkeypatch, rows)
        store = metrics.Metrics("postgresql://fake")
        await store.start()
        store.record("build", {"source": "api", "ai_status": "applied", "seconds": 1})
        await store.stop()
        fake_database(monkeypatch, rows, fail=True)
        summary = await store.summary()
        assert summary["builds"]["total"] == 1 and summary["persistent"] is False

    asyncio.run(scenario())
