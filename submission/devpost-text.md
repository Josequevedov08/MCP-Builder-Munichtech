# Devpost project text

Copy each block into the matching Devpost field.

## Project name

MCP Builder

## Elevator pitch (under 200 characters)

Describe what your AI may access in plain words and get a tested MCP server as a .zip. Every build is also read aloud, so blind and low-vision developers can use it too.

## Inspiration

Connecting company data to AI agents through MCP is slow and error-prone. A developer has to learn the SDK, write tool definitions, wire credentials safely and repeat it for every data source.

Accessibility is a second gap. Build tools report progress through terminals and dashboards that assume the reader can see them. We wanted the spoken status of a build to be a core feature, not an afterthought, so a blind or low-vision developer can build AI infrastructure independently.

## What it does

You choose a source (a database, a folder of files or a REST API), list what may be exposed and write your rules in plain language, for example "read only, never show emails". MCP Builder returns a complete TypeScript MCP server as a .zip, ready to connect to Claude Desktop, Cursor or Windsurf.

- An open-weight model on Featherless.ai turns your instructions into a small policy: limits, blocked fields and tool descriptions.
- The page shows the rules the server will enforce, in your language, so you can check what the AI understood.
- The build result is read aloud with an ElevenLabs voice in English, German or Spanish, and the same text is announced to screen readers.
- The result page lets you preview every file and download the .zip.

## How we built it

Hybrid generation. The model never writes the server code. It only derives a JSON policy, which the FastAPI backend validates and clamps (numbers are bounded, identifiers sanitized, secret-looking names such as password or token always blocked). The TypeScript comes from three templates (files, database, API) that are compiled and tested in continuous integration, so a build cannot produce code that fails to compile or lacks the security checks.

Generated servers protect access: the files server resolves real paths and refuses escapes, the database server accepts a single SELECT inside a read-only transaction and never returns blocked columns, and the API server calls only listed endpoints.

Voice uses ElevenLabs text-to-speech in a separate endpoint, so a voice failure can never break a build. The static site is written in HTML and Tailwind with a runtime translation engine (English, German, Spanish). The API runs on Render and the site on GitHub Pages.

## Challenges we ran into

Asking the model for full server code was fragile: it wrapped JSON in fences, nested files and sometimes produced code that did not compile. We changed the design so the model returns only a policy and verified templates produce the code. We also had to make reasoning models fast (reasoning off, small output, a deadline), and prove that the servers work by compiling each one and driving it through a real MCP client in the test suite.

## Accomplishments that we're proud of

- A complete path from the browser to a downloadable, compilable MCP server.
- Generated servers that are compiled and exercised through an MCP client in continuous integration.
- Spoken build reports in three languages with a text equivalent for screen readers.
- Zero axe-core violations on every page in the three languages.
- Secrets that never reach the model or the logs.

## What we learned

Constraining the model to a small, validated output is more reliable than asking it for code, and it makes the security properties of the result something we can test. Accessibility also improves the whole product: the text version of every report helps everyone, not only screen reader users.

## What's next for MCP Builder

Real Stripe test mode with server-side prices, tests against live PostgreSQL and MySQL, sessions with real screen reader users, and real metrics in the admin panel.

## Honest note on what is demo

Payment, the promo code, receipts, the support form, the legal text and the admin panel are demos. Generation, the AI step, the voice report and the download are real. The README lists this in detail.

## Built with

Python, FastAPI, Pydantic, httpx, Featherless.ai (zai-org/GLM-5.2), ElevenLabs, TypeScript, Model Context Protocol SDK, Node.js, Tailwind CSS, JavaScript, pytest, GitHub Actions, GitHub Pages, Render

## Try it out links

- Website: https://mcpbuilder.quevedojose.com
- Repository: https://github.com/Josequevedov08/MCP-Builder-Munichtech
- API health: https://mcpbuilder-api.quevedojose.com/api/health

## Image

Use `site/brand/devpost-project-image-1800x1200.png`.
