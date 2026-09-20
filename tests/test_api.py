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
    monkeypatch.setattr(main.settings, "elevenlabs_api_key", "test-key")
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
    monkeypatch.setattr(main.settings, "elevenlabs_api_key", "sk_secret_value")
    client.app.state.services.http._transport = httpx.MockTransport(lambda request: httpx.Response(401, text="invalid key sk_secret_value"))
    response = client.post("/api/voice-status", json={"status": "success"})
    assert response.status_code == 503
    assert "sk_secret_value" not in response.text


def test_rate_limit(client, monkeypatch):
    client.app.state.services.voice_limiter = main.RateLimiter(2)
    statuses = [client.post("/api/voice-status", json={"status": "success"}).status_code for _ in range(4)]
    assert statuses[:2] == [503, 503] and statuses[2:] == [429, 429]


def test_unknown_routes_use_the_envelope(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"
