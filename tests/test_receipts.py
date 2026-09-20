"""Receipt emails: amounts come from the server, one mail per build, and SMTP is replaced in tests."""

import io
import smtplib
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
import receipts  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "use_mock_llm", True)
    monkeypatch.setattr(main.settings, "rate_limit_builds", 1000)
    monkeypatch.setattr(main.settings, "rate_limit_receipts", 1000)
    monkeypatch.setattr(main.settings, "email_enabled", True)
    monkeypatch.setattr(main.settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(main.settings, "mail_from", "receipts@example.com")
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture()
def sent(monkeypatch):
    messages = []
    monkeypatch.setattr(receipts, "send_email", lambda **kwargs: messages.append(kwargs))
    return messages


def build(client, source="database"):
    body = {"server_name": "clinic-db", "source_type": source, "resources": ["patients"] if source == "database" else ["./docs"]}
    return client.post("/api/build-mcp", json=body).json()["build_id"]


def receipt(build_id, **extra):
    payload = {"build_id": build_id, "email": "judge@example.com", "order_id": "MB-ABC123", "language": "en"}
    payload.update(extra)
    return payload


def test_receipt_is_sent_once_with_the_server_attached(client, sent):
    build_id = build(client)
    first = client.post("/api/send-receipt", json=receipt(build_id, discount_code="LAUNCH20"))
    assert first.status_code == 200 and first.json() == {"sent": True}
    assert len(sent) == 1

    mail = sent[0]
    assert mail["to"] == "judge@example.com"
    assert "#MB-ABC123" in mail["subject"]
    assert "Total: $12.00" in mail["body"] and "LAUNCH20 (-20%)" in mail["body"]
    name, data = mail["attachment"]
    assert name == "clinic-db.zip"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        assert "clinic-db/package.json" in archive.namelist()

    second = client.post("/api/send-receipt", json=receipt(build_id))
    assert second.status_code == 200 and second.json()["already_sent"] is True
    assert len(sent) == 1


def test_amounts_are_never_taken_from_the_client(client, sent):
    build_id = build(client, "files")
    rejected = client.post("/api/send-receipt", json=receipt(build_id, total=0.01))
    assert rejected.status_code == 422

    client.post("/api/send-receipt", json=receipt(build_id, discount_code="FREE100"))
    assert "Total: $5.00" in sent[0]["body"] and "Discount: None" in sent[0]["body"]


def test_unknown_build_and_bad_addresses_are_refused(client, sent):
    assert client.post("/api/send-receipt", json=receipt("0" * 32)).status_code == 404
    build_id = build(client)
    for email in ("not-an-email", "a@b.com\nBcc: victim@example.com", "x@y"):
        assert client.post("/api/send-receipt", json=receipt(build_id, email=email)).status_code == 422
    assert client.post("/api/send-receipt", json=receipt(build_id, order_id="ORDER-1")).status_code == 422
    assert sent == []


def test_receipt_is_unavailable_without_email_settings(client, monkeypatch):
    monkeypatch.setattr(main.settings, "email_enabled", False)
    response = client.post("/api/send-receipt", json=receipt("0" * 32))
    assert response.status_code == 503 and response.json()["error"]["code"] == "email_unavailable"


def test_smtp_failures_do_not_leak_details(client, monkeypatch):
    def refuse(**kwargs):
        raise smtplib.SMTPAuthenticationError(535, b"bad password hunter2")

    monkeypatch.setattr(receipts, "send_email", refuse)
    response = client.post("/api/send-receipt", json=receipt(build(client)))
    assert response.status_code == 503 and response.json()["error"]["code"] == "email_not_configured"
    assert "hunter2" not in response.text

    monkeypatch.setattr(receipts, "send_email", lambda **kwargs: (_ for _ in ()).throw(OSError("connection refused")))
    response = client.post("/api/send-receipt", json=receipt(build(client)))
    assert response.status_code == 502 and "refused" not in response.text


def test_the_receipt_can_be_retried_after_a_failed_send(client, monkeypatch):
    build_id = build(client)
    monkeypatch.setattr(receipts, "send_email", lambda **kwargs: (_ for _ in ()).throw(OSError("down")))
    assert client.post("/api/send-receipt", json=receipt(build_id)).status_code == 502
    delivered = []
    monkeypatch.setattr(receipts, "send_email", lambda **kwargs: delivered.append(kwargs))
    assert client.post("/api/send-receipt", json=receipt(build_id)).status_code == 200
    assert len(delivered) == 1


@pytest.mark.parametrize("language, expected", [("en", "Total"), ("de", "Gesamt"), ("es", "Total")])
def test_receipt_text_exists_in_every_language(language, expected):
    subject, body = receipts.compose_receipt(language, "clinic-db", "api", "MB-ABC123", None)
    assert "#MB-ABC123" in subject and expected in body and "$20.00" in body
    assert "{" not in body


class FakeSmtp:
    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.calls = [("connect", host, port)]
        FakeSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append(("starttls",))

    def login(self, user, password):
        self.calls.append(("login", user))

    def send_message(self, message):
        self.calls.append(("send", message))


@pytest.mark.parametrize("security, port", [("starttls", 587), ("ssl", 465)])
def test_send_email_builds_a_safe_message(monkeypatch, security, port):
    FakeSmtp.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    receipts.send_email(
        host="smtp.test", port=port, user="apikey", password="secret", sender="receipts@example.com",
        security=security, to="judge@example.com", subject="Receipt #MB-ABC123", body="Hello\n",
        attachment=("clinic-db.zip", b"PK"),
    )
    calls = FakeSmtp.instances[0].calls
    assert ("starttls",) in calls if security == "starttls" else ("starttls",) not in calls
    assert ("login", "apikey") in calls
    message = [c for c in calls if c[0] == "send"][0][1]
    assert message["To"] == "judge@example.com" and "receipts@example.com" in message["From"]
    assert [part.get_filename() for part in message.iter_attachments()] == ["clinic-db.zip"]


def test_resend_api_is_used_when_configured(client, monkeypatch):
    import base64
    import httpx
    import json

    monkeypatch.setattr(main.settings, "resend_api_key", "re_test")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "abc"})

    client.app.state.services.http._transport = httpx.MockTransport(handler)
    response = client.post("/api/send-receipt", json=receipt(build(client)))
    assert response.status_code == 200
    assert seen["url"] == "https://api.resend.com/emails" and seen["auth"] == "Bearer re_test"
    assert seen["body"]["to"] == ["judge@example.com"] and "MCP Builder" in seen["body"]["from"]
    assert base64.b64decode(seen["body"]["attachments"][0]["content"])[:2] == b"PK"


@pytest.mark.parametrize("status, code, http_status", [(401, "email_not_configured", 503), (422, "email_unavailable", 502)])
def test_resend_errors_are_mapped_without_leaking(client, monkeypatch, status, code, http_status):
    import httpx

    monkeypatch.setattr(main.settings, "resend_api_key", "re_secret_key")
    client.app.state.services.http._transport = httpx.MockTransport(lambda request: httpx.Response(status, text="bad re_secret_key"))
    response = client.post("/api/send-receipt", json=receipt(build(client)))
    assert response.status_code == http_status and response.json()["error"]["code"] == code
    assert "re_secret_key" not in response.text


def test_the_address_is_lowercased_before_sending(client, sent):
    client.post("/api/send-receipt", json=receipt(build(client), email="Judge.Name@Example.COM"))
    assert sent[0]["to"] == "judge.name@example.com"
