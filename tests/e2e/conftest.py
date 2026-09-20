"""Helpers that build, compile and run generated MCP servers for real."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from generator import Policy, default_policy, render_project  # noqa: E402

NPM = shutil.which("npm") or "npm"
NODE = shutil.which("node")


def _run(cmd: list[str], cwd: Path, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, shell=sys.platform == "win32")


def write_project(target: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def build_project(target: Path, files: dict[str, str], extra_install: list[str] | None = None) -> None:
    """Writes the project, installs its dependencies and compiles it with tsc."""
    write_project(target, files)
    install = _run([NPM, "install", "--no-audit", "--no-fund", *(extra_install or [])], target)
    assert install.returncode == 0, install.stderr[-2000:]
    build = _run([NPM, "run", "build"], target)
    assert build.returncode == 0, build.stdout[-2000:] + build.stderr[-2000:]
    shutil.copy(Path(__file__).with_name("client.mjs"), target / ".e2e-client.mjs")


def run_scenario(target: Path, scenario: dict) -> subprocess.CompletedProcess:
    (target / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    return _run([NODE, ".e2e-client.mjs", "scenario.json"], target, timeout=120)


def pytest_collection_modifyitems(config, items):
    if NODE is None:
        skip = pytest.mark.skip(reason="Node.js is not installed")
        for item in items:
            item.add_marker(skip)


__all__ = ["Policy", "default_policy", "render_project", "build_project", "run_scenario"]
