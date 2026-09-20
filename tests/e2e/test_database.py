"""Compiles and runs the generated database servers against simulated drivers.

The drivers are replaced by small stand-ins that log every statement, so the tests can
prove which SQL reaches the database and that it always runs in a read-only transaction.
"""

import json
from pathlib import Path

import pytest

from conftest import Policy, build_project, default_policy, render_project, run_scenario

pytestmark = pytest.mark.e2e

PG_STUB = r"""
const fs = require("fs");
const log = (line) => fs.appendFileSync(process.env.DB_STUB_LOG, line.replace(/\s+/g, " ").trim() + "\n");
const people = [
  { id: 1, name: "Ana", email: "ana@example.com", password_hash: "h1" },
  { id: 2, name: "Luis", email: "luis@example.com", password_hash: "h2" },
  { id: 3, name: "Marta", email: "marta@example.com", password_hash: "h3" },
];
exports.Pool = class Pool {
  async connect() {
    return {
      async query(sql) {
        log(sql);
        if (/^(BEGIN|ROLLBACK)/.test(sql)) return { rows: [] };
        if (/information_schema\.tables/.test(sql)) return { rows: [{ table_name: "customers" }, { table_name: "orders" }, { table_name: "secrets_vault" }] };
        if (/information_schema\.columns/.test(sql)) return { rows: [
          { column_name: "id", data_type: "integer", is_nullable: "NO" },
          { column_name: "name", data_type: "text", is_nullable: "YES" },
          { column_name: "email", data_type: "text", is_nullable: "YES" },
          { column_name: "password_hash", data_type: "text", is_nullable: "YES" } ] };
        return { rows: people };
      },
      release() {},
    };
  }
  async end() {}
};
"""

MYSQL_STUB = r"""
const fs = require("fs");
const log = (line) => fs.appendFileSync(process.env.DB_STUB_LOG, line.replace(/\s+/g, " ").trim() + "\n");
const people = [
  { id: 1, name: "Ana", email: "ana@example.com", password_hash: "h1" },
  { id: 2, name: "Luis", email: "luis@example.com", password_hash: "h2" },
];
exports.createPool = () => ({
  async getConnection() {
    return {
      async query(arg) {
        const sql = typeof arg === "string" ? arg : arg.sql;
        log(sql);
        if (/information_schema\.tables/.test(sql)) return [[{ table_name: "customers" }, { table_name: "secrets_vault" }]];
        return [people];
      },
      async beginTransaction() { log("BEGIN"); },
      async rollback() { log("ROLLBACK"); },
      release() {},
    };
  },
  async end() {},
});
"""


def _install_stub(project: Path, module: str, code: str) -> None:
    package, _, subpath = module.partition("/")
    folder = project / "node_modules" / package
    folder.mkdir(parents=True, exist_ok=True)
    entry = f"{subpath}.js" if subpath else "index.js"
    exports = {".": "./index.js"}
    if subpath:
        exports[f"./{subpath}"] = f"./{entry}"
    manifest = {"name": package, "main": "index.js", "exports": exports}
    (folder / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "index.js").write_text(code, encoding="utf-8")
    (folder / entry).write_text(code, encoding="utf-8")


def _project_without_driver(engine: str, policy: Policy) -> dict[str, str]:
    files = render_project("shop-db", "database", ["customers", "orders"], policy, engine)
    package = json.loads(files["package.json"])
    for driver in ("pg", "mysql2"):
        package["dependencies"].pop(driver, None)
    files["package.json"] = json.dumps(package, indent=2)
    return files


@pytest.fixture(scope="module")
def pg_project(tmp_path_factory):
    project = tmp_path_factory.mktemp("pg-server")
    policy = Policy.model_validate({"max_rows": 2, "blocked_columns": ["email"]})
    build_project(project, _project_without_driver("postgresql", policy))
    _install_stub(project, "pg", PG_STUB)
    return project


def test_postgres_server_is_read_only_and_guarded(pg_project):
    log = pg_project / "db.log"
    scenario = {
        "env": {"DATABASE_URL": "postgresql://stub/stub", "DB_STUB_LOG": str(log)},
        "tools": ["list_tables", "describe_table", "run_query"],
        "steps": [
            {"tool": "list_tables", "contains": ["customers", "orders"], "excludes": ["secrets_vault"]},
            {"tool": "describe_table", "args": {"table": "customers"}, "contains": ["name"], "excludes": ["password_hash", "email"]},
            {"tool": "describe_table", "args": {"table": "secrets_vault"}, "error": True},
            # Allowed reads. Blocked columns are removed from results and the result is capped at 2 rows.
            {"tool": "run_query", "args": {"sql": "SELECT id, name FROM customers LIMIT 5"}, "contains": ["Ana", '"truncated": true'], "excludes": ["h1", "ana@example.com", "Marta"]},
            {"tool": "run_query", "args": {"sql": "SELECT * FROM customers"}, "contains": ["Ana"], "excludes": ["password_hash", "email"]},
            {"tool": "run_query", "args": {"sql": "WITH x AS (SELECT id FROM customers) SELECT * FROM x"}, "contains": ["Ana"]},
            {"tool": "run_query", "args": {"sql": "SELECT extract(year from now()) AS y, name FROM customers"}, "contains": ["Ana"]},
            {"tool": "run_query", "args": {"sql": "SELECT 'from secrets_vault' AS text FROM customers -- DROP TABLE x"}, "contains": ["Ana"]},
            {"tool": "run_query", "args": {"sql": "SELECT o.id FROM orders o JOIN customers c ON c.id = o.id"}, "contains": ["Ana"]},
            # Attacks that must never reach the database.
            {"tool": "run_query", "args": {"sql": "DROP TABLE customers"}, "error": True},
            {"tool": "run_query", "args": {"sql": "DELETE FROM customers"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT 1; DELETE FROM customers"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT * INTO backup FROM customers"}, "error": True},
            {"tool": "run_query", "args": {"sql": "UPDATE customers SET name = 'x'"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT * FROM secrets_vault"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT * FROM customers c JOIN secrets_vault s ON true"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT password_hash FROM customers"}, "error": True},
            {"tool": "run_query", "args": {"sql": 'SELECT "email" FROM customers'}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT pg_read_file('/etc/passwd')"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT pg_sleep(30)"}, "error": True},
            # A whole row, or a JSON copy of it, would carry blocked columns inside one value.
            {"tool": "run_query", "args": {"sql": "SELECT c FROM customers c"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT customers FROM customers"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT to_json(c) FROM customers c"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT row_to_json(c) FROM customers c"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT concat(c.*) FROM customers c"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT c::text FROM customers c"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT row(c.*) FROM customers c"}, "error": True},
            # Other ways around the table list: comma joins, subqueries and table functions.
            {"tool": "run_query", "args": {"sql": "SELECT * FROM customers c, secrets_vault s"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT * FROM (SELECT id FROM customers) t"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT * FROM generate_series(1, 3)"}, "error": True},
            {"tool": "run_query", "args": {"sql": "SELECT nextval('s')"}, "error": True},
            # Normal queries keep working, including semicolons and comment marks inside text.
            {"tool": "run_query", "args": {"sql": "SELECT id FROM customers WHERE name = 'a;b'"}, "contains": ["Ana"]},
            {"tool": "run_query", "args": {"sql": "SELECT count(*) AS total FROM customers c JOIN orders o ON o.id = c.id"}, "contains": ["Ana"]},
        ],
    }
    result = run_scenario(pg_project, scenario)
    assert result.returncode == 0, result.stdout + result.stderr

    statements = log.read_text(encoding="utf-8").splitlines()
    assert statements.count("BEGIN READ ONLY") == statements.count("ROLLBACK") > 0
    # Every SELECT ran between BEGIN READ ONLY and ROLLBACK, and nothing that writes ever arrived.
    assert not any(line.upper().startswith(("DROP", "DELETE", "UPDATE", "INSERT")) for line in statements)
    assert not any("pg_read_file" in line or "pg_sleep" in line or "secrets_vault" in line and "FROM secrets_vault" in line and "SELECT *" in line for line in statements)
    depth = 0
    for line in statements:
        if line == "BEGIN READ ONLY":
            depth += 1
        elif line == "ROLLBACK":
            depth -= 1
        elif line.upper().startswith(("SELECT", "WITH")):
            assert depth == 1, f"statement outside a read-only transaction: {line}"


def test_mysql_server_uses_a_read_only_transaction(tmp_path):
    project = tmp_path / "mysql-server"
    build_project(project, _project_without_driver("mysql", Policy()))
    _install_stub(project, "mysql2/promise", MYSQL_STUB)
    log = project / "db.log"
    scenario = {
        "env": {"DATABASE_URL": "mysql://stub/stub", "DB_STUB_LOG": str(log)},
        "tools": ["list_tables", "describe_table", "run_query"],
        "steps": [
            {"tool": "list_tables", "contains": ["customers"], "excludes": ["secrets_vault"]},
            {"tool": "run_query", "args": {"sql": "SELECT id, name FROM customers"}, "contains": ["Ana"], "excludes": ["h1"]},
            {"tool": "run_query", "args": {"sql": "DROP TABLE customers"}, "error": True},
        ],
    }
    result = run_scenario(project, scenario)
    assert result.returncode == 0, result.stdout + result.stderr
    statements = log.read_text(encoding="utf-8").splitlines()
    assert "SET SESSION TRANSACTION READ ONLY" in statements
    assert statements.index("SET SESSION TRANSACTION READ ONLY") < statements.index("BEGIN")
    assert not any(line.upper().startswith("DROP") for line in statements)


def test_database_server_explains_connection_problems_without_leaking_the_password(tmp_path):
    project = tmp_path / "real-driver-server"
    build_project(project, render_project("shop-db", "database", ["customers"], default_policy(), "postgresql"))
    unreachable = {
        "env": {"DATABASE_URL": "postgresql://user:SuperSecret123@127.0.0.1:1/nodb"},
        "tools": ["list_tables", "describe_table", "run_query"],
        "steps": [
            {"tool": "list_tables", "error": True, "contains": ["Could not reach the database", "DATABASE_URL"], "excludes": ["SuperSecret123"]},
            {"tool": "run_query", "args": {"sql": "SELECT * FROM customers"}, "error": True, "contains": ["Could not reach the database"], "excludes": ["SuperSecret123"]},
            # Wrong SQL is refused before any connection is tried, with a reason a person can act on.
            {"tool": "run_query", "args": {"sql": "DROP TABLE customers"}, "error": True, "contains": ["Only SELECT"]},
        ],
    }
    result = run_scenario(project, unreachable)
    assert result.returncode == 0, result.stdout + result.stderr

    missing = {
        "env": {"DATABASE_URL": ""},
        "tools": ["list_tables", "describe_table", "run_query"],
        "steps": [{"tool": "list_tables", "error": True, "contains": ["DATABASE_URL is not set"]}],
    }
    result = run_scenario(project, missing)
    assert result.returncode == 0, result.stdout + result.stderr
