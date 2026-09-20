"""
Renders complete, verified MCP server projects.

The TypeScript code comes from tested templates. Only a small JSON policy
(access limits, blocked fields and tool descriptions) varies per build, and it is
validated here, so a build can never produce code that fails to compile.
"""

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

TEMPLATES = Path(__file__).parent / "templates"

SOURCES = ("files", "database", "api")

TOOLS: dict[str, tuple[str, ...]] = {
    "files": ("list_files", "read_file", "search_files"),
    "database": ("list_tables", "describe_table", "run_query"),
    "api": ("list_endpoints", "call_endpoint"),
}

SECRET_LIKE = ("password", "passwd", "password_hash", "secret", "token", "api_key", "apikey")

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_EXTENSION = re.compile(r"^\.[a-z0-9]{1,10}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

_BOUNDS = {
    "max_file_bytes": (1_000, 5_000_000),
    "max_results": (1, 200),
    "max_rows": (1, 1000),
    "statement_timeout_ms": (1_000, 60_000),
    "max_response_chars": (500, 100_000),
    "timeout_ms": (1_000, 60_000),
}


def _clean_identifiers(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: dict[str, None] = {}
    for item in values:
        if isinstance(item, str) and _IDENTIFIER.match(item.strip()):
            seen[item.strip().lower()] = None
    return list(seen)[:30]


class Policy(BaseModel):
    """Access rules applied by the generated server. Every value is sanitized."""

    model_config = ConfigDict(extra="ignore")

    notes: str | None = Field(default=None, max_length=500)
    tool_descriptions: dict[str, str] = Field(default_factory=dict)

    allowed_extensions: list[str] = Field(default_factory=lambda: [".md", ".txt", ".csv", ".json"])
    max_file_bytes: int = 1_000_000
    max_results: int = 50

    max_rows: int = 100
    blocked_columns: list[str] = Field(default_factory=list, validate_default=True)
    statement_timeout_ms: int = 15_000

    blocked_fields: list[str] = Field(default_factory=list, validate_default=True)
    max_response_chars: int = 20_000
    timeout_ms: int = 15_000

    @field_validator(*_BOUNDS, mode="before")
    @classmethod
    def clamp_numbers(cls, value: Any, info: Any) -> int:
        low, high = _BOUNDS[info.field_name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        return max(low, min(high, int(value)))

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def clean_extensions(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return [".md", ".txt", ".csv", ".json"]
        cleaned = []
        for item in value:
            if isinstance(item, str):
                ext = item.strip().lower()
                ext = ext if ext.startswith(".") else f".{ext}"
                if _EXTENSION.match(ext) and ext not in cleaned:
                    cleaned.append(ext)
        return cleaned[:20] or [".md", ".txt", ".csv", ".json"]

    @field_validator("blocked_columns", "blocked_fields", mode="before")
    @classmethod
    def clean_blocked(cls, value: Any) -> list[str]:
        merged = _clean_identifiers(value)
        # Secret-like names are always blocked, whatever the model returns.
        return list(dict.fromkeys([*SECRET_LIKE, *merged]))

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        return _CONTROL.sub(" ", value).strip()[:500] or None

    @field_validator("tool_descriptions", mode="before")
    @classmethod
    def clean_descriptions(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        known = {name for names in TOOLS.values() for name in names}
        return {
            key: _CONTROL.sub(" ", text).strip()[:240]
            for key, text in value.items()
            if key in known and isinstance(text, str) and text.strip()
        }


def default_policy() -> Policy:
    """Policy with safe defaults, used when the model is not available."""
    return Policy()


_RULES = {
    "files": {
        "en": [
            "Reads only inside the folders you allow, symbolic links are ignored",
            "Readable file types: {ext}",
            "Files larger than {bytes} bytes are refused",
            "At most {n} results per listing or search",
        ],
        "de": [
            "Liest nur in den von Ihnen erlaubten Ordnern, symbolische Links werden ignoriert",
            "Lesbare Dateitypen: {ext}",
            "Dateien über {bytes} Bytes werden abgelehnt",
            "Höchstens {n} Ergebnisse pro Auflistung oder Suche",
        ],
        "es": [
            "Lee solo dentro de las carpetas que permites, los enlaces simbólicos se ignoran",
            "Tipos de archivo legibles: {ext}",
            "Se rechazan los archivos de más de {bytes} bytes",
            "Como máximo {n} resultados por listado o búsqueda",
        ],
    },
    "database": {
        "en": [
            "Read-only: a single SELECT statement, run in a read-only transaction",
            "At most {rows} rows per query, {seconds} second time limit",
            "Blocked columns: {cols}",
            "Only the tables you listed can be queried",
        ],
        "de": [
            "Nur Lesen: eine einzelne SELECT-Anweisung, ausgeführt in einer schreibgeschützten Transaktion",
            "Höchstens {rows} Zeilen pro Abfrage, Zeitlimit {seconds} Sekunden",
            "Gesperrte Spalten: {cols}",
            "Nur die von Ihnen aufgelisteten Tabellen können abgefragt werden",
        ],
        "es": [
            "Solo lectura: una única sentencia SELECT, ejecutada en una transacción de solo lectura",
            "Máximo {rows} filas por consulta, límite de {seconds} segundos",
            "Columnas bloqueadas: {cols}",
            "Solo se pueden consultar las tablas que indicaste",
        ],
    },
    "api": {
        "en": [
            "Read-only: GET requests to the paths you listed",
            "Removed from every response: {fields}",
            "Responses are cut at {chars} characters",
            "Redirects and full addresses are refused",
        ],
        "de": [
            "Nur Lesen: GET-Anfragen an die von Ihnen aufgelisteten Pfade",
            "Aus jeder Antwort entfernt: {fields}",
            "Antworten werden bei {chars} Zeichen abgeschnitten",
            "Weiterleitungen und vollständige Adressen werden abgelehnt",
        ],
        "es": [
            "Solo lectura: peticiones GET a las rutas que indicaste",
            "Se elimina de cada respuesta: {fields}",
            "Las respuestas se cortan a {chars} caracteres",
            "Se rechazan las redirecciones y las direcciones completas",
        ],
    },
}


def describe_rules(source: str, policy: Policy, language: str = "en") -> list[str]:
    """Plain-language list of the rules that the generated server enforces."""
    values = {
        "ext": ", ".join(policy.allowed_extensions),
        "bytes": f"{policy.max_file_bytes:,}",
        "n": policy.max_results,
        "rows": policy.max_rows,
        "seconds": policy.statement_timeout_ms // 1000,
        "cols": ", ".join(policy.blocked_columns),
        "fields": ", ".join(policy.blocked_fields),
        "chars": f"{policy.max_response_chars:,}",
    }
    templates = _RULES[source].get(language, _RULES[source]["en"])
    return [template.format(**values) for template in templates]


def env_schema(source: str, db_engine: str | None) -> dict[str, Any]:
    """JSON Schema of the environment variables that the generated server reads."""
    if source == "files":
        props = {"MCP_ALLOWED_DIRS": {"type": "string", "description": "Folders the server may read, separated by ; on Windows or : elsewhere."}}
        required = ["MCP_ALLOWED_DIRS"]
    elif source == "database":
        props = {"DATABASE_URL": {"type": "string", "description": f"Connection string of a read-only {db_engine or 'postgresql'} user."}}
        required = ["DATABASE_URL"]
    else:
        props = {
            "API_BASE_URL": {"type": "string", "description": "Base address of the API."},
            "API_TOKEN": {"type": "string", "description": "Access token, if the API needs one."},
            "API_AUTH_HEADER": {"type": "string", "description": "Header that carries the token. Defaults to Authorization."},
            "API_AUTH_SCHEME": {"type": "string", "description": "Token prefix. Defaults to Bearer. Leave empty for raw keys."},
        }
        required = ["API_BASE_URL"]
    return {"type": "object", "properties": props, "required": required}


def _package_json(name: str, source: str, db_engine: str | None) -> str:
    deps = {"@modelcontextprotocol/sdk": "^1.17.0", "zod": "^3.25.0"}
    if source == "database":
        deps["mysql2" if db_engine in ("mysql", "mariadb") else "pg"] = "^3.11.0" if db_engine in ("mysql", "mariadb") else "^8.13.0"
    return json.dumps(
        {
            "name": name,
            "version": "1.0.0",
            "description": "MCP server generated by MCP Builder",
            "type": "module",
            "main": "dist/index.js",
            "scripts": {"build": "tsc", "start": "node dist/index.js"},
            "engines": {"node": ">=18"},
            "dependencies": deps,
            "devDependencies": {"typescript": "^5.6.0", "@types/node": "^22.0.0"},
        },
        indent=2,
    ) + "\n"


def _config_json(name: str, source: str, resources: list[str], db_engine: str | None, policy: Policy) -> str:
    tools = {k: v for k, v in policy.tool_descriptions.items() if k in TOOLS[source]}
    if source == "database":
        resources = [r.split(".")[-1].strip('"`[]').lower() for r in resources]
    config: dict[str, Any] = {"server": {"name": name, "version": "1.0.0"}, "resources": resources}
    if policy.notes:
        config["notes"] = policy.notes
    if source == "files":
        config["policy"] = {
            "allowed_extensions": policy.allowed_extensions,
            "max_file_bytes": policy.max_file_bytes,
            "max_results": policy.max_results,
        }
    elif source == "database":
        config["db_engine"] = db_engine or "postgresql"
        config["policy"] = {
            "max_rows": policy.max_rows,
            "blocked_columns": policy.blocked_columns,
            "statement_timeout_ms": policy.statement_timeout_ms,
        }
    else:
        config["policy"] = {
            "blocked_fields": policy.blocked_fields,
            "max_response_chars": policy.max_response_chars,
            "timeout_ms": policy.timeout_ms,
        }
    if tools:
        config["tool_descriptions"] = tools
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def _env_example(source: str, db_engine: str | None) -> str:
    if source == "files":
        return "# Folders the server may read. Use absolute paths, separated by ; on Windows or : elsewhere.\nMCP_ALLOWED_DIRS=\n"
    if source == "database":
        scheme = "mysql" if db_engine in ("mysql", "mariadb") else "postgresql"
        return f"# Use a database user that can only read. Example: {scheme}://readonly_user:password@localhost/dbname\nDATABASE_URL=\n"
    return (
        "# Base address of the API, for example https://api.example.com/v1\nAPI_BASE_URL=\n"
        "# Access token, if the API needs one\nAPI_TOKEN=\n"
        "# Header and prefix used to send the token\nAPI_AUTH_HEADER=Authorization\nAPI_AUTH_SCHEME=Bearer\n"
    )


def _readme(name: str, source: str, db_engine: str | None, resources: list[str], policy: Policy) -> str:
    env_block = {
        "files": '"MCP_ALLOWED_DIRS": "/absolute/path/to/your/folder"',
        "database": '"DATABASE_URL": "' + ("mysql" if db_engine in ("mysql", "mariadb") else "postgresql") + '://readonly_user:password@localhost/dbname"',
        "api": '"API_BASE_URL": "https://api.example.com/v1",\n        "API_TOKEN": "your-token"',
    }[source]
    rules = "\n".join(f"- {rule}" for rule in describe_rules(source, policy))
    tools = "\n".join(f"- `{tool}`" for tool in TOOLS[source])
    exposed = ", ".join("`" + re.sub(r"[`\r\n]", " ", r).strip() + "`" for r in resources) or "everything the configuration allows"
    return f"""# {name}

MCP server generated by MCP Builder. It connects an AI assistant such as Claude Desktop, Cursor or Windsurf to your {source} source.

## Install

Requires Node.js 18 or newer.

```bash
npm install
npm run build
```

## Connect it to Claude Desktop

Add this to `claude_desktop_config.json`, using the real path of this folder, then restart Claude Desktop:

```json
{{
  "mcpServers": {{
    "{name}": {{
      "command": "node",
      "args": ["/absolute/path/to/{name}/dist/index.js"],
      "env": {{
        {env_block}
      }}
    }}
  }}
}}
```

The same command and environment variables work in any other MCP client.

## Tools

{tools}

Resources exposed: {exposed}.

## Access rules enforced by this server

{rules}

These rules are stored in `mcp.config.json`. Edit that file to change them, then run `npm run build` again.

## Security notes

- Use credentials that have the minimum permissions, ideally read-only.
- Never commit your `.env` file or your tokens.
"""


def render_project(
    server_name: str,
    source: str,
    resources: list[str],
    policy: Policy,
    db_engine: str | None = None,
) -> dict[str, str]:
    """Return every file of the generated project, keyed by relative path."""
    if source not in SOURCES:
        raise ValueError(f"unknown source type: {source}")
    src = TEMPLATES / source / "src"
    files = {
        "package.json": _package_json(server_name, source, db_engine),
        "tsconfig.json": (TEMPLATES / "common" / "tsconfig.json").read_text(encoding="utf-8"),
        "mcp.config.json": _config_json(server_name, source, resources, db_engine, policy),
        ".env.example": _env_example(source, db_engine),
        ".gitignore": "node_modules\ndist\n.env\n",
        "README.md": _readme(server_name, source, db_engine, resources, policy),
    }
    for path in sorted(src.iterdir()):
        files[f"src/{path.name}"] = path.read_text(encoding="utf-8")
    return files
