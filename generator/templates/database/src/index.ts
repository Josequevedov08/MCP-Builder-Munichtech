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
  /\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|merge|replace|lock|execute|vacuum|reindex|attach|detach|into|outfile|dumpfile|load_file|set_config|dblink\w*|lo_\w+|pg_\w+|sleep|benchmark|nextval|setval|currval|lastval|to_json|to_jsonb|row_to_json|json_agg|jsonb_agg)\b/i;

// Removes string literals and comments so that keyword and table scans ignore them.
function stripLiteralsAndComments(sql: string): string {
  return sql.replace(/'(?:[^']|'')*'|--[^\n]*|\/\*[\s\S]*?\*\//g, (match) => (match.startsWith("'") ? "''" : " "));
}

const escapeRegExp = (value: string): string => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function normalizeTable(reference: string): string {
  const last = reference.split(".").pop() ?? reference;
  return last.replace(/[`"\[\]]/g, "").toLowerCase();
}

const CLAUSE_END = new Set(["where", "group", "order", "having", "limit", "offset", "union", "intersect", "except", "window", "fetch", "for", "returning"]);
const JOIN_WORDS = new Set(["join", "inner", "left", "right", "full", "cross", "natural", "lateral", "outer"]);
const NOT_ALIASES = new Set([...CLAUSE_END, ...JOIN_WORDS, "on", "using", "as", "select", "from", "and", "or", "not", "is", "in", "distinct"]);

const tokenize = (sql: string): string[] => sql.match(/"[^"]*"|`[^`]*`|[A-Za-z_][\w$]*|\d+(?:\.\d+)?|::|[(),.*]|\S/g) ?? [];
const bare = (token: string): string => token.replace(/^["`]|["`]$/g, "").toLowerCase();

// Rules that a plain keyword scan cannot express: which tables are read, and how rows are returned.
function checkStructure(tokens: string[], names: Set<string>): void {
  const lower = tokens.map((token) => token.toLowerCase());

  // FROM lists: no subqueries, no comma joins (they would skip the table check) and no table functions.
  for (let i = 0; i < lower.length; i++) {
    if (lower[i] !== "from" || lower[i - 1] === "distinct") continue;
    let depth = 0;
    let inOn = false;
    for (let j = i + 1; j < lower.length; j++) {
      const token = lower[j];
      const previous = lower[j - 1];
      if (token === "(") {
        if (depth === 0 && (previous === "from" || JOIN_WORDS.has(previous))) {
          throw new Error("Subqueries in FROM are not allowed. Use WITH instead.");
        }
        depth++;
      } else if (token === ")") {
        depth--;
        if (depth < 0) break;
      } else if (depth === 0) {
        if (CLAUSE_END.has(token)) break;
        if (token === ",") throw new Error("Comma-separated tables are not allowed. Use JOIN instead.");
        if (token === "on") inOn = true;
        else if (JOIN_WORDS.has(token)) inOn = false;
        else if (!inOn && lower[j + 1] === "(" && !NOT_ALIASES.has(token)) throw new Error("Functions in FROM are not allowed.");
      }
    }
  }

  // Select lists: a whole row (for example "SELECT p FROM patients p" or "to_json(p)") would carry blocked columns inside one value.
  for (let i = 0; i < lower.length; i++) {
    if (lower[i] !== "select") continue;
    let depth = 0;
    for (let j = i + 1; j < lower.length; j++) {
      const token = lower[j];
      if (token === "(") depth++;
      else if (token === ")") {
        depth--;
        if (depth < 0) break;
      } else if (depth === 0 && token === "from") break;
      if (!/^["`A-Za-z_]/.test(tokens[j]) || !names.has(bare(token)) || lower[j - 1] === "." || lower[j - 1] === "as") continue;
      if (lower[j + 1] === ".") {
        if (lower[j + 2] === "*" && depth > 0) throw new Error("A table followed by .* is only allowed at the top level of the select list.");
      } else if (lower[j + 1] !== "(") {
        throw new Error("Whole-row references are not allowed. Select the columns you need by name.");
      }
    }
  }
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

  if (/\brow\s*\(/i.test(cleaned)) throw new Error("The keyword \"row\" is not allowed in queries.");

  const ctes = new Set<string>();
  for (const match of cleaned.matchAll(
    /\bwith\s+(?:recursive\s+)?([\w$]+)\s+as\b|,\s*([\w$]+)\s+as\s*(?:not\s+materialized\s*|materialized\s*)?\(/gi,
  )) {
    ctes.add((match[1] ?? match[2]).toLowerCase());
  }
  const withoutFunctions = cleaned.replace(/\b(extract|substring|trim|overlay|position)\s*\((?:[^()]|\([^()]*\))*\)/gi, " fn() ");
  const names = new Set<string>([...allowedTables, ...ctes]);
  for (const match of withoutFunctions.matchAll(
    /\b(?:from|join)\s+([`"\[]?[\w$]+[`"\]]?(?:\.[`"\[]?[\w$]+[`"\]]?)*)(?:\s+(?:as\s+)?([a-z_][\w$]*))?/gi,
  )) {
    const table = normalizeTable(match[1]);
    names.add(table);
    if (match[2] && !NOT_ALIASES.has(match[2].toLowerCase())) names.add(match[2].toLowerCase());
    if (allowedTables.size > 0 && !ctes.has(table) && !allowedTables.has(table)) {
      throw new Error(`The table "${table}" is not in the allowed list: ${[...allowedTables].join(", ")}.`);
    }
  }
  checkStructure(tokenize(withoutFunctions), names);
  return sql;
}

// Removes blocked columns from a row, and blocked keys from any JSON value inside it.
function scrub(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scrub);
  if (value !== null && typeof value === "object" && !(value instanceof Date) && !Buffer.isBuffer(value)) {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([name]) => !blockedColumns.includes(name.toLowerCase()))
        .map(([name, item]) => [name, scrub(item)]),
    );
  }
  return value;
}

function stripBlocked(row: Row): Row {
  if (blockedColumns.length === 0) return row;
  return scrub(row) as Row;
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
