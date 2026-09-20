"""The browser ZIP writer must produce archives that standard tools open and verify."""

import subprocess
import zipfile

import pytest

from conftest import NODE, ROOT

pytestmark = pytest.mark.e2e


def test_browser_zip_is_valid_and_keeps_utf8(tmp_path):
    script = tmp_path / "make.cjs"
    script.write_text(
        f"""
const {{ build }} = require({str(ROOT / "site" / "zip.js")!r});
const files = {{
  "package.json": '{{"name":"demo"}}',
  "src/index.ts": "console.log('hola, canción');\\n".repeat(2000),
  "README.md": "# Título ñ\\n",
}};
build(files, "demo-server").arrayBuffer().then((buffer) => require("fs").writeFileSync({str(tmp_path / "out.zip")!r}, Buffer.from(buffer)));
""",
        encoding="utf-8",
    )
    subprocess.run([NODE, str(script)], check=True, timeout=60)

    with zipfile.ZipFile(tmp_path / "out.zip") as archive:
        assert archive.testzip() is None
        assert sorted(archive.namelist()) == ["demo-server/README.md", "demo-server/package.json", "demo-server/src/index.ts"]
        assert archive.read("demo-server/README.md").decode("utf-8") == "# Título ñ\n"
        assert archive.read("demo-server/src/index.ts").decode("utf-8").startswith("console.log('hola, canción');")
        archive.extractall(tmp_path / "unzipped")
    assert (tmp_path / "unzipped" / "demo-server" / "package.json").read_text() == '{"name":"demo"}'
