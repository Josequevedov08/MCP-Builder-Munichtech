import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync } from "node:fs";

interface ApiConfig {
  server: { name: string; version: string };
  resources: string[];
  notes?: string;
  policy: { blocked_fields: string[]; max_response_chars: number; timeout_ms: number };
  tool_descriptions?: Record<string, string>;
}

const config: ApiConfig = JSON.parse(
  readFileSync(new URL("../mcp.config.json", import.meta.url), "utf-8"),
);
const allowedEndpoints = config.resources.map((endpoint) => "/" + endpoint.replace(/^\/+|\/+$/g, ""));
const blockedFields = config.policy.blocked_fields.map((field) => field.toLowerCase());
const maxChars = config.policy.max_response_chars;
const timeoutMs = config.policy.timeout_ms;

const describe = (tool: string, fallback: string): string => config.tool_descriptions?.[tool] ?? fallback;
const text = (value: string) => ({ content: [{ type: "text" as const, text: value }] });
const failure = (message: string) => ({ isError: true, content: [{ type: "text" as const, text: message }] });

function endpointAllowed(pathname: string): boolean {
  if (allowedEndpoints.length === 0) return true;
  return allowedEndpoints.some((endpoint) => pathname === endpoint || pathname.startsWith(endpoint + "/"));
}

// Builds the request address from a relative path and guarantees it stays on the configured API.
function buildUrl(requested: string, query?: Record<string, string>): URL {
  const baseUrl = process.env.API_BASE_URL;
  if (!baseUrl) throw new Error("API_BASE_URL is not set.");
  if (/^[a-z][a-z0-9+.-]*:/i.test(requested) || requested.startsWith("//")) {
    throw new Error("Use a path such as /products, not a full address.");
  }
  const parsed = new URL("http://placeholder/" + requested.replace(/^\/+/, ""));
  const pathname = parsed.pathname.replace(/\/+$/, "") || "/";
  if (!endpointAllowed(pathname)) {
    throw new Error(`The path "${pathname}" is not allowed. Allowed paths: ${allowedEndpoints.join(", ")}.`);
  }
  const url = new URL(baseUrl.replace(/\/+$/, "") + pathname);
  parsed.searchParams.forEach((value, key) => url.searchParams.set(key, value));
  for (const [key, value] of Object.entries(query ?? {})) url.searchParams.set(key, value);
  return url;
}

function authHeaders(): Record<string, string> {
  const token = process.env.API_TOKEN;
  if (!token) return {};
  const header = process.env.API_AUTH_HEADER ?? "Authorization";
  const scheme = process.env.API_AUTH_SCHEME ?? "Bearer";
  return { [header]: scheme ? `${scheme} ${token}` : token };
}

function removeBlockedFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(removeBlockedFields);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([key]) => !blockedFields.includes(key.toLowerCase()))
        .map(([key, item]) => [key, removeBlockedFields(item)]),
    );
  }
  return value;
}

function formatBody(body: string): string {
  let output = body;
  try {
    output = JSON.stringify(removeBlockedFields(JSON.parse(body)), null, 2);
  } catch {
    // Not JSON: return the text as it is.
  }
  return output.length > maxChars
    ? `${output.slice(0, maxChars)}\n... [truncated to ${maxChars} characters]`
    : output;
}

const server = new McpServer({ name: config.server.name, version: config.server.version });

server.registerTool(
  "list_endpoints",
  { description: describe("list_endpoints", "List the API paths that this server is allowed to call."), inputSchema: {} },
  async () =>
    text(allowedEndpoints.length > 0 ? allowedEndpoints.join("\n") : "Every path of the configured API is allowed."),
);

server.registerTool(
  "call_endpoint",
  {
    description: describe("call_endpoint", "Send a read-only GET request to one allowed API path and return the response."),
    inputSchema: {
      path: z.string().min(1).describe("Path of the endpoint, for example /products."),
      query: z.record(z.string()).optional().describe("Optional query string parameters."),
    },
  },
  async ({ path, query }) => {
    try {
      const response = await fetch(buildUrl(path, query), {
        method: "GET",
        headers: { Accept: "application/json", ...authHeaders() },
        redirect: "manual",
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (response.status >= 300 && response.status < 400) {
        throw new Error(`The API answered with a redirect (${response.status}). Redirects are not followed.`);
      }
      const body = await response.text();
      if (!response.ok) throw new Error(`The API answered with status ${response.status}: ${body.slice(0, 300)}`);
      return text(formatBody(body));
    } catch (error) {
      const message = (error as Error).name === "TimeoutError" ? "The API did not answer in time." : (error as Error).message;
      return failure(message);
    }
  },
);

server.connect(new StdioServerTransport()).catch((error) => {
  console.error(error);
  process.exit(1);
});
