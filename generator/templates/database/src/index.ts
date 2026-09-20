import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync } from "node:fs";

interface DatabaseConfig {
  server: { name: string; version: string };
  db_engine: "postgresql" | "mysql" | "mariadb";
  resources: string[];
  notes?: string;
  policy: { max_rows: number; blocked_columns: string[]; statement_timeout_ms: number };
  tool_descriptions?: Record<string, string>;
}

type Row = Record<string, unknown>;

interface Db {
  query(sql: string, params?: unknown[]): Promise<Row[]>;
  close(): Promise<void>;
}

const config: DatabaseConfig = JSON.parse(
  readFileSync(new URL("../mcp.config.json", import.meta.url), "utf-8"),
);
const allowedTables = new Set(config.resources.map((table) => table.toLowerCase()));
const blockedColumns = config.policy.blocked_columns.map((column) => column.toLowerCase());
const maxRows = config.policy.max_rows;
const timeoutMs = config.policy.statement_timeout_ms;
const isPostgres = config.db_engine === "postgresql";

const describe = (tool: string, fallback: string): string => config.tool_descriptions?.[tool] ?? fallback;
const text = (value: string) => ({ content: [{ type: "text" as const, text: value }] });
const failure = (message: string) => ({ isError: true, content: [{ type: "text" as const, text: message }] });
const toJson = (value: unknown): string =>
  JSON.stringify(value, (_key, item) => (typeof item === "bigint" ? item.toString() : item), 2);

// Every statement runs inside a read-only transaction that is always rolled back.
async function connect(): Promise<Db> {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set.");

  if (isPostgres) {
    const pg: any = await import("pg");
    const Pool = (pg.default ?? pg).Pool;
    const pool = new Pool({
      connectionString: url,
      max: 3,
      statement_timeout: timeoutMs,
      connectionTimeoutMillis: 10000,
    });
    return {
      async query(sql, params) {
        const client = await pool.connect();
        try {
          await client.query("BEGIN READ ONLY");
          const result = await client.query(sql, params);
          return result.rows as Row[];
        } finally {
          try {
            await client.query("ROLLBACK");
          } catch {
            // The connection is released either way.
          }
          client.release();
        }
      },
      close: () => pool.end(),
    };
  }

  const mysql: any = await import("mysql2/promise");
  const pool = (mysql.default ?? mysql).createPool({ uri: url, connectionLimit: 3, connectTimeout: 10000 });
  return {
    async query(sql, params) {
      const connection = await pool.getConnection();
      try {
        await connection.query("SET SESSION TRANSACTION READ ONLY");
        await connection.beginTransaction();
        const [rows] = await connection.query({ sql, timeout: timeoutMs }, params);
        return (Array.isArray(rows) ? rows : []) as Row[];
      } finally {
        try {
          await connection.rollback();
        } catch {
          // The connection is released either way.
        }
        connection.release();
      }
    },
    close: () => pool.end(),
  };
}

let dbPromise: Promise<Db> | null = null;
const getDb = (): Promise<Db> => (dbPromise ??= connect());

// Turns driver errors into advice. Only the error code is shown, never the connection string.
function describeError(error: unknown): string {
  const failureCode = String((error as { code?: unknown }).code ?? "");
  if (["ECONNREFUSED", "ENOTFOUND", "ETIMEDOUT", "EAI_AGAIN", "EHOSTUNREACH", "ECONNRESET"].includes(failureCode)) {
    return `Could not reach the database (${failureCode}). Check the host and port in DATABASE_URL and that the database accepts connections from this machine.`;
  }
  if (["28P01", "28000", "ER_ACCESS_DENIED_ERROR"].includes(failureCode)) return "The database refused the user or the password in DATABASE_URL.";
  if (["3D000", "ER_BAD_DB_ERROR"].includes(failureCode)) return "The database name in DATABASE_URL does not exist.";
  if (failureCode === "57014") return "The query took too long and was stopped.";
  if (/invalid (url|connection)/i.test((error as Error).message ?? "")) return "DATABASE_URL is not a valid connection string.";
  return (error as Error).message ?? "Unexpected error.";
}

// ---- SQL guard -------------------------------------------------------------

const FORBIDDEN_KEYWORDS =
  /\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|merge|replace|lock|execute|vacuum|reindex|attach|detach|into|outfile|dumpfile|load_file|set_config|dblink\w*|lo_\w+|pg_\w+|sleep|benchmark)\b/i;

// Removes string literals and comments so that keyword and table scans ignore them.
function stripLiteralsAndComments(sql: string): string {
  return sql.replace(/'(?:[^']|'')*'|--[^\n]*|\/\*[\s\S]*?\*\//g, (match) => (match.startsWith("'") ? "''" : " "));
}

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function normalizeTable(reference: string): string {
  const last = reference.split(".").pop() ?? reference;
  return last.replace(/[`"\[\]]/g, "").toLowerCase();
}

// Accepts a single read-only SELECT that only touches the allowed tables and columns.
function validateQuery(rawSql: string): string {
  const sql = rawSql.trim().replace(/;+\s*$/, "");
  if (sql === "") throw new Error("The query is empty.");
  const cleaned = stripLiteralsAndComments(sql);
  if (cleaned.includes(";")) throw new Error("Only one statement is allowed.");
  if (!/^\s*\(?\s*(select|with)\b/i.test(cleaned)) throw new Error("Only SELECT queries are allowed.");

  const keywordView = cleaned.replace(/"[^"]*"|`[^`]*`/g, '""');
  const forbidden = keywordView.match(FORBIDDEN_KEYWORDS);
  if (forbidden) throw new Error(`The keyword "${forbidden[0]}" is not allowed in queries.`);

  for (const column of blockedColumns) {
    if (new RegExp(`\\b${escapeRegExp(column)}\\b`, "i").test(cleaned)) {
      throw new Error(`The column "${column}" is blocked by the access policy.`);
    }
  }

  if (allowedTables.size > 0) {
    const ctes = new Set<string>();
    for (const match of cleaned.matchAll(
      /\bwith\s+(?:recursive\s+)?([\w$]+)\s+as\b|,\s*([\w$]+)\s+as\s*(?:not\s+materialized\s*|materialized\s*)?\(/gi,
    )) {
      ctes.add((match[1] ?? match[2]).toLowerCase());
    }
    const withoutFunctions = cleaned.replace(/\b(extract|substring|trim|overlay|position)\s*\((?:[^()]|\([^()]*\))*\)/gi, " fn() ");
    for (const match of withoutFunctions.matchAll(
      /\b(?:from|join)\s+([`"\[]?[\w$]+[`"\]]?(?:\.[`"\[]?[\w$]+[`"\]]?)*)/gi,
    )) {
      const table = normalizeTable(match[1]);
      if (!ctes.has(table) && !allowedTables.has(table)) {
        throw new Error(`The table "${table}" is not in the allowed list: ${[...allowedTables].join(", ")}.`);
      }
    }
  }
  return sql;
}

function stripBlocked(row: Row): Row {
  if (blockedColumns.length === 0) return row;
  return Object.fromEntries(Object.entries(row).filter(([name]) => !blockedColumns.includes(name.toLowerCase())));
}

function tableAllowed(table: string): boolean {
  return allowedTables.size === 0 || allowedTables.has(table.toLowerCase());
}

// ---- Tools -----------------------------------------------------------------

const server = new McpServer({ name: config.server.name, version: config.server.version });

server.registerTool(
  "list_tables",
  { description: describe("list_tables", "List the tables that this server is allowed to query."), inputSchema: {} },
  async () => {
    try {
      const sql = isPostgres
        ? "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' ORDER BY table_name"
        : "SELECT table_name AS table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name";
      const rows = await (await getDb()).query(sql);
      const names = rows.map((row) => String(row.table_name)).filter(tableAllowed);
      return text(names.length > 0 ? names.join("\n") : "No allowed tables were found.");
    } catch (error) {
      return failure(describeError(error));
    }
  },
);

server.registerTool(
  "describe_table",
  {
    description: describe("describe_table", "Show the columns and data types of one allowed table."),
    inputSchema: { table: z.string().min(1).describe("Name of the table.") },
  },
  async ({ table }) => {
    try {
      if (!tableAllowed(table)) throw new Error(`The table "${table}" is not in the allowed list.`);
      const sql = isPostgres
        ? "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = $1 ORDER BY ordinal_position"
        : "SELECT column_name AS column_name, data_type AS data_type, is_nullable AS is_nullable FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = ? ORDER BY ordinal_position";
      const rows = await (await getDb()).query(sql, [table]);
      const visible = rows.filter((row) => !blockedColumns.includes(String(row.column_name).toLowerCase()));
      if (visible.length === 0) throw new Error(`The table "${table}" was not found.`);
      return text(toJson(visible));
    } catch (error) {
      return failure(describeError(error));
    }
  },
);

server.registerTool(
  "run_query",
  {
    description: describe(
      "run_query",
      `Run one read-only SQL SELECT query. At most ${maxRows} rows are returned, so include a LIMIT.`,
    ),
    inputSchema: { sql: z.string().min(1).describe("A single SELECT statement.") },
  },
  async ({ sql }) => {
    try {
      const rows = await (await getDb()).query(validateQuery(sql));
      const visible = rows.slice(0, maxRows).map(stripBlocked);
      return text(toJson({ row_count: visible.length, truncated: rows.length > maxRows, rows: visible }));
    } catch (error) {
      return failure(describeError(error));
    }
  },
);

async function shutdown(): Promise<void> {
  if (dbPromise) {
    try {
      await (await dbPromise).close();
    } catch {
      // Nothing left to clean up.
    }
  }
  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

server.connect(new StdioServerTransport()).catch((error) => {
  console.error(error);
  process.exit(1);
});
