import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { promises as fs, readFileSync } from "node:fs";
import path from "node:path";

interface FilesConfig {
  server: { name: string; version: string };
  resources: string[];
  notes?: string;
  policy: { allowed_extensions: string[]; max_file_bytes: number; max_results: number };
  tool_descriptions?: Record<string, string>;
}

const config: FilesConfig = JSON.parse(
  readFileSync(new URL("../mcp.config.json", import.meta.url), "utf-8"),
);
const extensions = config.policy.allowed_extensions.map((ext) => ext.toLowerCase());
const maxFileBytes = config.policy.max_file_bytes;
const maxResults = config.policy.max_results;

// Folders the server may read. MCP_ALLOWED_DIRS overrides the folders from mcp.config.json.
const configuredRoots = (
  process.env.MCP_ALLOWED_DIRS ? process.env.MCP_ALLOWED_DIRS.split(path.delimiter) : config.resources
).filter((root) => root.trim() !== "");

const describe = (tool: string, fallback: string): string => config.tool_descriptions?.[tool] ?? fallback;
const text = (value: string) => ({ content: [{ type: "text" as const, text: value }] });
const failure = (message: string) => ({ isError: true, content: [{ type: "text" as const, text: message }] });

let realRoots: string[] | null = null;

async function getRoots(): Promise<string[]> {
  if (!realRoots) {
    const resolved: string[] = [];
    for (const root of configuredRoots) {
      try {
        resolved.push(await fs.realpath(path.resolve(root)));
      } catch {
        // Missing folders are ignored.
      }
    }
    realRoots = resolved;
  }
  return realRoots;
}

function isInside(root: string, target: string): boolean {
  const relative = path.relative(root, target);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

// Resolves a user supplied path and guarantees that it stays inside an allowed folder.
async function resolveSafe(input: string): Promise<string> {
  const roots = await getRoots();
  const candidates = path.isAbsolute(input) ? [input] : roots.map((root) => path.resolve(root, input));
  for (const candidate of candidates) {
    let real: string;
    try {
      real = await fs.realpath(candidate);
    } catch {
      continue;
    }
    if (roots.some((root) => isInside(root, real))) return real;
  }
  throw new Error("The path does not exist or is outside the allowed folders.");
}

function extensionAllowed(file: string): boolean {
  return extensions.includes(path.extname(file).toLowerCase());
}

// Lists allowed files below a folder. Symbolic links and hidden folders are skipped.
async function collectFiles(dir: string, found: string[], limit: number): Promise<void> {
  if (found.length >= limit) return;
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  entries.sort((a, b) => a.name.localeCompare(b.name));
  for (const entry of entries) {
    if (found.length >= limit) return;
    if (entry.isSymbolicLink() || entry.name.startsWith(".") || entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await collectFiles(full, found, limit);
    } else if (entry.isFile() && extensionAllowed(entry.name)) {
      found.push(full);
    }
  }
}

async function baseFolders(directory?: string): Promise<string[]> {
  if (directory) return [await resolveSafe(directory)];
  const roots = await getRoots();
  if (roots.length === 0) throw new Error("No allowed folder is available. Check MCP_ALLOWED_DIRS.");
  return roots;
}

const server = new McpServer({ name: config.server.name, version: config.server.version });

server.registerTool(
  "list_files",
  {
    description: describe("list_files", "List the files that this server is allowed to read."),
    inputSchema: {
      directory: z.string().optional().describe("Optional folder inside the allowed folders."),
    },
  },
  async ({ directory }) => {
    try {
      const found: string[] = [];
      for (const base of await baseFolders(directory)) {
        await collectFiles(base, found, maxResults);
      }
      if (found.length === 0) return text("No matching files were found.");
      const lines: string[] = [];
      for (const file of found) {
        const info = await fs.stat(file);
        lines.push(`${file} (${info.size} bytes)`);
      }
      return text(lines.join("\n"));
    } catch (error) {
      return failure((error as Error).message);
    }
  },
);

server.registerTool(
  "read_file",
  {
    description: describe("read_file", "Read the text content of one allowed file."),
    inputSchema: {
      path: z.string().describe("Absolute path, or a path relative to an allowed folder."),
    },
  },
  async ({ path: requested }) => {
    try {
      const file = await resolveSafe(requested);
      const info = await fs.stat(file);
      if (!info.isFile()) throw new Error("The path is not a file.");
      if (!extensionAllowed(file)) throw new Error(`Only these file types can be read: ${extensions.join(", ")}.`);
      if (info.size > maxFileBytes) throw new Error(`The file is larger than the limit of ${maxFileBytes} bytes.`);
      return text(await fs.readFile(file, "utf-8"));
    } catch (error) {
      return failure((error as Error).message);
    }
  },
);

server.registerTool(
  "search_files",
  {
    description: describe("search_files", "Search for text inside the allowed files and return matching lines."),
    inputSchema: {
      query: z.string().min(1).describe("Text to look for. The search ignores upper and lower case."),
      directory: z.string().optional().describe("Optional folder inside the allowed folders."),
    },
  },
  async ({ query, directory }) => {
    try {
      const needle = query.toLowerCase();
      const files: string[] = [];
      for (const base of await baseFolders(directory)) {
        await collectFiles(base, files, 1000);
      }
      const matches: string[] = [];
      for (const file of files) {
        if (matches.length >= maxResults) break;
        const info = await fs.stat(file);
        if (info.size > maxFileBytes) continue;
        const lines = (await fs.readFile(file, "utf-8")).split(/\r?\n/);
        for (let index = 0; index < lines.length && matches.length < maxResults; index++) {
          if (lines[index].toLowerCase().includes(needle)) {
            matches.push(`${file}:${index + 1}: ${lines[index].trim().slice(0, 200)}`);
          }
        }
      }
      return text(matches.length > 0 ? matches.join("\n") : "No matches were found.");
    } catch (error) {
      return failure((error as Error).message);
    }
  },
);

async function main(): Promise<void> {
  if (configuredRoots.length === 0) {
    console.error("No folder is configured. Set MCP_ALLOWED_DIRS to one or more absolute folder paths.");
    process.exit(1);
  }
  await server.connect(new StdioServerTransport());
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
