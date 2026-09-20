"""API tests. External services are replaced, so no network access or keys are needed."""

import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main.settings, "use_mock_llm", True)
    monkeypatch.setattr(main.settings, "voice_enabled", False)
    monkeypatch.setattr(main.settings, "rate_limit_builds", 1000)
    monkeypatch.setattr(main.settings, "rate_limit_voice", 1000)
    with TestClient(main.app) as test_client:
        yield test_client


BUILD = {"server_name": "shop-db", "source_type": "database", "resources": ["orders", "customers"], "instructions": "Read-only."}


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"


def test_build_returns_a_complete_project(client):
    response = client.post("/api/build-mcp", json=BUILD)
    assert response.status_code == 200
    body = response.json()
    assert body["ai_status"] == "template"
    assert {"package.json", "src/index.ts", "mcp.config.json", "README.md"} <= set(body["files"])
    assert body["applied_rules"]
    assert "DATABASE_URL" in body["config_schema"]["properties"]
    assert "shop db" in body["spoken_summary"]


def test_local_is_an_alias_for_files(client):
    response = client.post("/api/build-mcp", json={"server_name": "docs-files", "source_type": "local", "resources": ["./data"]})
    assert response.status_code == 200
    assert response.json()["source_type"] == "files"


def test_validation_errors_use_the_envelope_and_never_echo_values(client):
    response = client.post(
        "/api/build-mcp",
        json={"server_name": "Bad Name", "source_type": "api", "credentials": {"lower": "topsecret-value"}, "extra": 1},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert {f["field"] for f in body["error"]["fields"]} >= {"server_name", "credentials", "extra"}
    assert "topsecret-value" not in response.text


def test_database_resources_must_be_table_names(client):
    response = client.post("/api/build-mcp", json={**BUILD, "resources": ["orders; DROP TABLE users"]})
    assert response.status_code == 422


def test_unknown_language_is_rejected(client):
    assert client.post("/api/build-mcp", json={**BUILD, "language": "fr"}).status_code == 422


def test_model_failure_falls_back_to_safe_defaults(client, monkeypatch):
    monkeypatch.setattr(main.settings, "use_mock_llm", False)

    async def broken(self, request):
        raise main.ApiError(504, "model_timeout", "slow")

    monkeypatch.setattr(main.FeatherlessClient, "_complete", broken)
    body = client.post("/api/build-mcp", json=BUILD).json()
    assert body["ai_status"] == "defaults"
    assert "password" in json.loads(body["files"]["mcp.config.json"])["policy"]["blocked_columns"]


def test_model_policy_is_applied_and_sanitized(client, monkeypatch):
    monkeypatch.setattr(main.settings, "use_mock_llm", False)

    async def answer(self, request):
        return '```json\n{"max_rows": 25, "blocked_columns": ["Email", "x y"], "tool_descriptions": {"run_query": "Runs SQL."}}\n```'

    monkeypatch.setattr(main.FeatherlessClient, "_complete", answer)
    body = client.post("/api/build-mcp", json=BUILD).json()
    config = json.loads(body["files"]["mcp.config.json"])
    assert body["ai_status"] == "applied"
    assert config["policy"]["max_rows"] == 25
    assert "email" in config["policy"]["blocked_columns"] and "x y" not in config["policy"]["blocked_columns"]
    assert config["tool_descriptions"] == {"run_query": "Runs SQL."}


def test_voice_is_unavailable_without_a_key(client):
    response = client.post("/api/voice-status", json={"status": "success"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "voice_unavailable"


def test_voice_returns_audio_in_the_requested_language(client, monkeypatch):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["test-key"])
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["key"] = request.headers["xi-api-key"]
        return httpx.Response(200, content=b"ID3audio")

    client.app.state.services.http._transport = httpx.MockTransport(handler)
    response = client.post("/api/voice-status", json={"status": "success", "server_name": "shop-db", "file_count": 4, "language": "de"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert seen["model_id"] == "eleven_multilingual_v2"
    assert "Build abgeschlossen" in seen["text"] and "4 Dateien" in seen["text"]

    client.post("/api/voice-status", json={"status": "error", "message": "Fallo de esquema", "language": "es"})
    assert "La compilación falló. Fallo de esquema" == seen["text"]


def test_voice_errors_never_expose_the_key(client, monkeypatch):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["sk_secret_value"])
    client.app.state.services.http._transport = httpx.MockTransport(lambda request: httpx.Response(401, text="invalid key sk_secret_value"))
    response = client.post("/api/voice-status", json={"status": "success"})
    assert response.status_code == 503
    assert "sk_secret_value" not in response.text


@pytest.mark.parametrize("failure", [401, 402, 429])
def test_voice_switches_to_the_backup_key_when_the_main_one_fails(client, monkeypatch, failure):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["main-key", "backup-key"])
    used = []

    def handler(request: httpx.Request) -> httpx.Response:
        used.append(request.headers["xi-api-key"])
        if request.headers["xi-api-key"] == "main-key":
            return httpx.Response(failure, text="quota")
        return httpx.Response(200, content=b"ID3audio")

    client.app.state.services.http._transport = httpx.MockTransport(handler)
    first = client.post("/api/voice-status", json={"status": "success"})
    assert first.status_code == 200 and first.content == b"ID3audio"
    assert used == ["main-key", "backup-key"]

    # The working key is remembered, so the spent one is not tried first again (new sentence, so no cache hit).
    used.clear()
    assert client.post("/api/voice-status", json={"status": "success", "server_name": "other-name"}).status_code == 200
    assert used == ["backup-key"]


def test_voice_fails_cleanly_when_both_keys_fail(client, monkeypatch):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["main-key", "backup-key"])
    client.app.state.services.http._transport = httpx.MockTransport(lambda request: httpx.Response(429, text="quota main-key backup-key"))
    response = client.post("/api/voice-status", json={"status": "success"})
    assert response.status_code == 502
    assert "main-key" not in response.text and "backup-key" not in response.text


def test_voice_does_not_retry_on_timeouts(client, monkeypatch):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["main-key", "backup-key"])
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    client.app.state.services.http._transport = httpx.MockTransport(handler)
    assert client.post("/api/voice-status", json={"status": "success"}).status_code == 504
    assert len(calls) == 1


def test_rate_limit(client, monkeypatch):
    client.app.state.services.voice_limiter = main.RateLimiter(2)
    statuses = [client.post("/api/voice-status", json={"status": "success"}).status_code for _ in range(4)]
    assert statuses[:2] == [503, 503] and statuses[2:] == [429, 429]


def test_unknown_routes_use_the_envelope(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


@pytest.mark.parametrize(
    "body, reason",
    [
        ({"server_name": "shop-db", "source_type": "database", "resources": []}, "tables_required"),
        ({"server_name": "shop-db", "source_type": "database", "resources": ["orders; DROP TABLE users"]}, "invalid_tables"),
        ({"server_name": "shop-api", "source_type": "api", "resources": []}, "endpoints_required"),
        ({"server_name": "shop-api", "source_type": "api", "resources": ["https://evil.example.com/x"]}, "invalid_endpoints"),
        ({"server_name": "shop-api", "source_type": "api", "resources": ["/../admin"]}, "invalid_endpoints"),
        ({"server_name": "shop-fil", "source_type": "files", "resources": ["../../etc"]}, "invalid_folders"),
        ({"server_name": "shop-fil", "source_type": "files", "resources": ["C:/"]}, "invalid_folders"),
        ({"server_name": "shop-fil", "source_type": "files", "resources": ["/"]}, "invalid_folders"),
    ],
)
def test_wrong_resources_are_refused_with_a_readable_reason(client, body, reason):
    response = client.post("/api/build-mcp", json=body)
    assert response.status_code == 422
    fields = response.json()["error"]["fields"]
    assert {"field": "resources", "message": reason} in fields


def test_reasonable_resources_are_accepted(client):
    good = [
        {"server_name": "shop-db", "source_type": "database", "resources": ["orders", "public.customers"]},
        {"server_name": "shop-api", "source_type": "api", "resources": ["/products", "orders/{id}"]},
        {"server_name": "shop-fil", "source_type": "files", "resources": ["./docs", "C:/Company/Reports"]},
        {"server_name": "shop-fil", "source_type": "files", "resources": []},
    ]
    for body in good:
        assert client.post("/api/build-mcp", json=body).status_code == 200, body


def test_identical_voice_sentences_are_served_from_memory(client, monkeypatch):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["test-key"])
    calls = []
    client.app.state.services.http._transport = httpx.MockTransport(lambda request: (calls.append(1), httpx.Response(200, content=b"ID3audio"))[1])
    for _ in range(3):
        assert client.post("/api/voice-status", json={"status": "success", "server_name": "shop-db"}).status_code == 200
    assert len(calls) == 1


def test_the_voice_service_has_a_daily_ceiling(client, monkeypatch):
    monkeypatch.setattr(main.settings, "voice_enabled", True)
    monkeypatch.setattr(main.settings, "elevenlabs_api_keys", ["test-key"])
    client.app.state.services.http._transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ID3audio"))
    client.app.state.services.voice._daily = main.DailyCap(2)
    statuses = [client.post("/api/voice-status", json={"status": "success", "server_name": f"srv-{i}x"}).status_code for i in range(4)]
    assert statuses == [200, 200, 429, 429]


def test_a_forged_forwarded_address_does_not_reset_the_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main.settings, "trusted_proxy_hops", 1)
    client.app.state.services.support_limiter = main.RateLimiter(2)
    payload = {"name": "Ana", "email": "ana@example.com", "topic": "other", "message": "hello there"}
    statuses = [
        client.post("/api/support", json=payload, headers={"X-Forwarded-For": f"9.9.9.{i}, 203.0.113.7"}).status_code
        for i in range(5)
    ]
    assert statuses == [200, 200, 429, 429, 429]
    other = client.post("/api/support", json=payload, headers={"X-Forwarded-For": "9.9.9.1, 198.51.100.9"})
    assert other.status_code == 200


def test_the_forwarded_header_is_ignored_when_no_proxy_is_trusted(client, monkeypatch):
    monkeypatch.setattr(main.settings, "trusted_proxy_hops", 0)
    client.app.state.services.support_limiter = main.RateLimiter(1)
    payload = {"name": "Ana", "email": "ana@example.com", "topic": "other", "message": "hello there"}
    first = client.post("/api/support", json=payload, headers={"X-Forwarded-For": "1.1.1.1"})
    second = client.post("/api/support", json=payload, headers={"X-Forwarded-For": "2.2.2.2"})
    assert (first.status_code, second.status_code) == (200, 429)


def test_oversized_and_unsized_bodies_are_refused(client, monkeypatch):
    monkeypatch.setattr(main.settings, "max_body_bytes", 1000)
    big = client.post("/api/build-mcp", content='{"a":"' + "x" * 2000 + '"}', headers={"Content-Type": "application/json"})
    assert big.status_code == 413 and big.json()["error"]["code"] == "payload_too_large"
    ok = client.post("/api/build-mcp", json=BUILD)
    assert ok.status_code == 200


def test_security_headers_and_health_head(client):
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert client.head("/api/health").status_code == 200
    secure = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert "max-age" in secure.headers["strict-transport-security"]


def test_null_bytes_in_the_path_are_a_plain_404(client):
    response = client.get("/api/%00health")
    assert response.status_code == 404 and response.json()["error"]["code"] == "http_error"


def test_the_daily_build_ceiling_answers_with_a_clear_error(client):
    client.app.state.services.daily_builds = main.DailyCap(1)
    assert client.post("/api/build-mcp", json=BUILD).status_code == 200
    second = client.post("/api/build-mcp", json=BUILD)
    assert second.status_code == 429 and second.json()["error"]["code"] == "daily_limit"
