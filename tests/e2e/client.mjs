// Runs a scenario against a generated MCP server over stdio.
// Usage (from the server folder): node .e2e-client.mjs scenario.json
import { readFileSync } from "node:fs";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const scenario = JSON.parse(readFileSync(process.argv[2], "utf-8"));

const transport = new StdioClientTransport({
  command: process.execPath,
  args: ["dist/index.js"],
  cwd: process.cwd(),
  env: { ...process.env, ...scenario.env },
  stderr: "pipe",
});
const client = new Client({ name: "e2e", version: "1.0.0" });
await client.connect(transport);

const failures = [];
const check = (label, condition, detail) => {
  if (!condition) failures.push(`${label}: ${detail}`);
};

const listed = (await client.listTools()).tools.map((tool) => tool.name).sort();
check("tools", JSON.stringify(listed) === JSON.stringify([...scenario.tools].sort()), `got ${listed.join(",")}`);

for (const step of scenario.steps) {
  const result = await client.callTool({ name: step.tool, arguments: step.args ?? {} });
  const output = (result.content ?? []).map((item) => item.text ?? "").join("\n");
  const label = `${step.tool}(${JSON.stringify(step.args ?? {})})`;
  check(label, Boolean(result.isError) === Boolean(step.error), `isError=${Boolean(result.isError)} expected ${Boolean(step.error)}: ${output.slice(0, 200)}`);
  for (const text of step.contains ?? []) check(label, output.includes(text), `missing "${text}" in: ${output.slice(0, 300)}`);
  for (const text of step.excludes ?? []) check(label, !output.includes(text), `unexpected "${text}" in: ${output.slice(0, 300)}`);
}

await client.close();
if (failures.length > 0) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`ok: ${scenario.steps.length} calls`);
