"""Unit tests for the policy sanitizing and the project renderer."""

import json
import sys
from pathlib import Path, PurePosixPath

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generator import SECRET_LIKE, TOOLS, Policy, default_policy, describe_rules, env_schema, render_project  # noqa: E402


def test_defaults_always_block_secret_like_names():
    policy = default_policy()
    assert set(SECRET_LIKE) <= set(policy.blocked_columns)
    assert set(SECRET_LIKE) <= set(policy.blocked_fields)


def test_hostile_policy_is_clamped_and_cleaned():
    policy = Policy.model_validate(
        {
            "max_rows": 10**9,
            "max_results": -5,
            "max_file_bytes": "huge" if False else 10**12,
            "blocked_columns": ["Email", "bad col!", "x; DROP TABLE y", 42, "phone"],
            "allowed_extensions": ["CSV", "..", "/etc/passwd", ".md"],
            "tool_descriptions": {"run_query": "Line one\nLine two", "not_a_tool": "ignored"},
            "notes": "x" * 5000 if False else "note\x00 with control",
        }
    )
    assert policy.max_rows == 1000
    assert policy.max_results == 1
    assert policy.max_file_bytes == 5_000_000
    assert "email" in policy.blocked_columns and "phone" in policy.blocked_columns
    assert all(c.replace("_", "").isalnum() for c in policy.blocked_columns)
    assert policy.allowed_extensions == [".csv", ".md"]
    assert policy.tool_descriptions == {"run_query": "Line one Line two"}
    assert "\x00" not in (policy.notes or "")


def test_non_numeric_limits_are_rejected():
    with pytest.raises(ValueError):
        Policy.model_validate({"max_rows": "lots"})


@pytest.mark.parametrize(
    "source, engine, resources",
    [("files", None, ["./data"]), ("database", "postgresql", ["public.Orders"]), ("database", "mysql", ["orders"]), ("api", None, ["/products"])],
)
def test_render_project_is_complete_and_safe(source, engine, resources):
    files = render_project("demo-server", source, resources, default_policy(), engine)
    for required in ("package.json", "tsconfig.json", "mcp.config.json", ".env.example", "README.md", "src/index.ts"):
        assert required in files
    for name in files:
        path = PurePosixPath(name)
        assert not path.is_absolute() and ".." not in path.parts
    config = json.loads(files["mcp.config.json"])
    package = json.loads(files["package.json"])
    assert config["server"]["name"] == package["name"] == "demo-server"
    if source == "database":
        assert config["resources"] == [resources[0].split(".")[-1].lower()]
        driver = "mysql2" if engine == "mysql" else "pg"
        assert driver in package["dependencies"]
    assert set(json.loads(files["mcp.config.json"]).get("tool_descriptions", {})) <= set(TOOLS[source])


def test_readme_neutralizes_hostile_resource_names():
    files = render_project("demo-server", "files", ["a`b\n# injected"], default_policy())
    assert "\n# injected" not in files["README.md"]


def test_rules_and_env_schema_describe_every_source():
    for source in ("files", "database", "api"):
        english = describe_rules(source, default_policy())
        assert english and env_schema(source, "postgresql")["required"]
        for language in ("de", "es"):
            translated = describe_rules(source, default_policy(), language)
            assert len(translated) == len(english) and translated != english
            assert not any("{" in rule for rule in translated)
