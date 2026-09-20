"""Compiles and runs the generated servers for the file and API sources."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import Policy, build_project, default_policy, render_project, run_scenario

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def files_project(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    (data / "notes.md").write_text("# Notes\nThe launch date is 21 September.\n", encoding="utf-8")
    (data / "budget.csv").write_text("item,cost\nservers,120\n", encoding="utf-8")
    (data / "photo.png").write_bytes(b"\x89PNG")
    (data / "sub").mkdir()
    (data / "sub" / "deep.txt").write_text("nested secret plan\n", encoding="utf-8")
    outside = tmp_path_factory.mktemp("outside")
    (outside / "private.txt").write_text("TOP SECRET", encoding="utf-8")

    policy = Policy.model_validate({"allowed_extensions": [".md", ".txt"], "max_results": 5})
    project = tmp_path_factory.mktemp("files-server")
    build_project(project, render_project("docs-files", "files", [str(data)], policy))
    return project, data, outside


def test_files_server_enforces_the_sandbox(files_project):
    project, data, outside = files_project
    scenario = {
        "env": {"MCP_ALLOWED_DIRS": str(data)},
        "tools": ["list_files", "read_file", "search_files"],
        "steps": [
            {"tool": "list_files", "contains": ["notes.md", "deep.txt"], "excludes": ["budget.csv", "photo.png"]},
            {"tool": "read_file", "args": {"path": "notes.md"}, "contains": ["launch date"]},
            {"tool": "read_file", "args": {"path": "sub/deep.txt"}, "contains": ["nested secret plan"]},
            {"tool": "search_files", "args": {"query": "LAUNCH"}, "contains": ["notes.md:2"]},
            # Attacks: none of these may leak data outside the allowed folder or type list.
            {"tool": "read_file", "args": {"path": "../" + outside.name + "/private.txt"}, "error": True, "excludes": ["TOP SECRET"]},
            {"tool": "read_file", "args": {"path": str(outside / "private.txt")}, "error": True, "excludes": ["TOP SECRET"]},
            {"tool": "read_file", "args": {"path": "budget.csv"}, "error": True},
            {"tool": "list_files", "args": {"directory": str(outside)}, "error": True, "excludes": ["private.txt"]},
        ],
    }
    result = run_scenario(project, scenario)
    assert result.returncode == 0, result.stdout + result.stderr


class _Api(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload, headers=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.headers.get("Authorization") != "Bearer test-token":
            return self._send(401, {"error": "unauthorized"})
        if self.path.startswith("/v1/products"):
            return self._send(200, [{"id": 1, "name": "Coffee", "password": "hunter2", "owner": {"api_key": "abc"}}])
        if self.path.startswith("/v1/orders"):
            return self._send(200, {"orders": []})
        if self.path.startswith("/v1/admin"):
            return self._send(200, {"admin": True})
        if self.path.startswith("/v1/moved"):
            return self._send(302, {}, {"Location": "http://example.com/"})
        return self._send(404, {"error": "not found"})


@pytest.fixture(scope="module")
def api_server():
    server = HTTPServer(("127.0.0.1", 0), _Api)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()


def test_api_server_calls_only_allowed_endpoints(tmp_path, api_server):
    project = tmp_path / "api-server"
    build_project(project, render_project("shop-api", "api", ["/products", "orders"], default_policy()))
    scenario = {
        "env": {"API_BASE_URL": api_server, "API_TOKEN": "test-token"},
        "tools": ["list_endpoints", "call_endpoint"],
        "steps": [
            {"tool": "list_endpoints", "contains": ["/products", "/orders"]},
            {"tool": "call_endpoint", "args": {"path": "/products"}, "contains": ["Coffee"], "excludes": ["hunter2", "abc"]},
            {"tool": "call_endpoint", "args": {"path": "orders", "query": {"page": "2"}}, "contains": ["orders"]},
            # Attacks: other paths, full addresses, traversal and redirects must be refused.
            {"tool": "call_endpoint", "args": {"path": "/admin"}, "error": True, "excludes": ["true"]},
            {"tool": "call_endpoint", "args": {"path": "http://example.com/steal"}, "error": True},
            {"tool": "call_endpoint", "args": {"path": "/products/../admin"}, "error": True},
            {"tool": "call_endpoint", "args": {"path": "//example.com/products"}, "error": True},
            # Encoded characters that the API could decode into another path.
            {"tool": "call_endpoint", "args": {"path": "/products/..%2fadmin"}, "error": True},
            {"tool": "call_endpoint", "args": {"path": "/products%2F..%2Fadmin"}, "error": True},
            {"tool": "call_endpoint", "args": {"path": "/products/%00admin"}, "error": True},
        ],
    }
    result = run_scenario(project, scenario)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_server_reports_upstream_errors(tmp_path, api_server):
    project = tmp_path / "api-server-401"
    build_project(project, render_project("shop-api", "api", ["/products"], default_policy()))
    scenario = {
        "env": {"API_BASE_URL": api_server, "API_TOKEN": "wrong"},
        "tools": ["list_endpoints", "call_endpoint"],
        "steps": [{"tool": "call_endpoint", "args": {"path": "/products"}, "error": True, "contains": ["401"]}],
    }
    result = run_scenario(project, scenario)
    assert result.returncode == 0, result.stdout + result.stderr


def test_api_server_explains_a_wrong_or_missing_address(tmp_path):
    project = tmp_path / "api-server-bad-address"
    build_project(project, render_project("shop-api", "api", ["/products"], default_policy()))
    unreachable = {
        "env": {"API_BASE_URL": "http://127.0.0.1:1/v1", "API_TOKEN": "tok_SuperSecret"},
        "tools": ["list_endpoints", "call_endpoint"],
        "steps": [{"tool": "call_endpoint", "args": {"path": "/products"}, "error": True, "contains": ["Could not reach the API", "API_BASE_URL"], "excludes": ["tok_SuperSecret"]}],
    }
    result = run_scenario(project, unreachable)
    assert result.returncode == 0, result.stdout + result.stderr

    missing = {
        "env": {"API_BASE_URL": ""},
        "tools": ["list_endpoints", "call_endpoint"],
        "steps": [{"tool": "call_endpoint", "args": {"path": "/products"}, "error": True, "contains": ["API_BASE_URL is not set"]}],
    }
    result = run_scenario(project, missing)
    assert result.returncode == 0, result.stdout + result.stderr
