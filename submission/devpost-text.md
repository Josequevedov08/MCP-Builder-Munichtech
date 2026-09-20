# Devpost project text

Copy each block into the matching Devpost field. The story goes in "About the project" (Markdown).

## Project name

MCP Builder

## Elevator pitch (under 200 characters)

Describe in plain words what your AI may access and get a tested MCP server as a .zip. Every build is read aloud, so blind and low-vision developers can use it too.

## About the project (paste this)

## Inspiration

Connecting company data to AI assistants through the Model Context Protocol (MCP) is slow and error-prone. A developer has to learn the SDK, write tool definitions, wire credentials safely and repeat it for every data source. Small teams in Europe often skip it because the setup costs more than the first benefit.

Accessibility is a second gap. Build tools report progress through terminals and dashboards that assume the reader can see them. With the European Accessibility Act in force since June 2025, inclusive tooling is no longer a nice extra. We wanted the spoken status of a build to be a core feature, so a blind or low-vision developer can build AI infrastructure independently.

## What it does

Problem: giving an AI assistant safe, read-only access to files, a database or a REST API takes days of careful work.

Solution: you choose a source, list what may be exposed and write your rules in plain language, for example "read only, never show phone numbers". MCP Builder returns a complete TypeScript MCP server as a .zip, ready for Claude Desktop, Cursor or Windsurf.

- An open-weight model on Featherless.ai turns your instructions into a small policy: limits, blocked fields and tool descriptions. The page shows the resulting rules in your language so you can check what the AI understood.
- The build result is read aloud with an ElevenLabs voice in English, German or Spanish, and the same text is announced to screen readers. It also tells you the next step.
- You can preview every file, download the .zip, and receive a receipt by email with the server attached.

Target users: developers and small teams who want to connect their data to an AI assistant, and blind or low-vision developers who need non-visual feedback.

Why it matters for Europe: open-weight models keep the AI layer replaceable and self-hostable. The generated servers run on the user's own machine, so company data never has to leave it. The credentials never reach the model. The interface and the voice reports work in English, German and Spanish.

## How we built it

Hybrid generation. The model never writes the server code. It only derives a JSON policy, which the FastAPI backend validates and clamps (numbers are bounded, identifiers sanitized, secret-looking names such as password or token always blocked). The TypeScript comes from three templates (files, database, API) that are compiled and tested in continuous integration, so a build cannot produce code that fails to compile or lacks the security checks.

What the generated servers enforce:
- Files: real paths are resolved so `../` and symbolic links cannot escape the allowed folders, only allowed extensions are read, and size and result limits apply.
- Database: a single SELECT only, in a read-only transaction with a time limit, only exposed tables, and blocked columns are never returned.
- API: only listed endpoints can be called, full URLs and redirects are refused, and blocked fields are removed from responses.

Architecture: a static site in HTML and Tailwind (GitHub Pages) with a runtime translation engine, a FastAPI backend (Render), PostgreSQL for real usage numbers, Featherless.ai (zai-org/GLM-5.2) for the policy, ElevenLabs text-to-speech in a separate endpoint with a backup key, and Resend for receipt emails. Errors use one JSON envelope, requests are rate limited per IP, and CORS is restricted.

Quality: 64 automated tests, including end-to-end tests that compile each generated server and drive it through the official MCP client. axe-core reports zero accessibility violations on every page in the three languages.

## Challenges we ran into

Asking the model for full server code was fragile: it wrapped JSON in fences, nested files and sometimes produced code that did not compile. We changed the design so the model returns only a policy and verified templates produce the code. We also made a reasoning model fast (reasoning off, small output, a deadline) and proved that the servers work by compiling each one and driving it through a real MCP client. Finally, we kept voice optional: every spoken message also exists as text, so audio problems never block the build.

## Accomplishments that we're proud of

- A complete path from the browser to a downloadable, compilable MCP server.
- Generated servers that are compiled and exercised through an MCP client in continuous integration.
- Spoken build reports in three languages with a text equivalent for screen readers.
- Real usage numbers, a real support inbox and real receipt emails, all connected.
- Secrets that never reach the model or the logs.

## What we learned

Constraining the model to a small, validated output is more reliable than asking it for code, and it makes the security properties of the result something we can test. Accessibility also improves the whole product: the text version of every report helps everyone, not only screen reader users.

## Business, ethical and deployment considerations

- Business: one price per generated server ($5 files, $15 database, $20 API), with no subscription. Payments run in test mode in this version.
- Ethics and privacy: servers are read-only by default, secret-like fields are always blocked, credentials never reach the model, and the support inbox with personal data is private.
- Deployment: free hosting plans today, so the first request can take about a minute. Nothing in the design needs more than a small container and a database.

## What's next for MCP Builder

Real Stripe test mode, tests of the generated servers against live PostgreSQL and MySQL, sessions with real screen reader users, and the option to run the AI step on a self-hosted open-weight model.

## Honest note on what is demo

Payment runs in test mode and the legal text is a template. Generation, the AI step, the voice report, the download, the receipt email (with the server .zip attached), the support form and the usage page are real, and the usage page counts real events. The README lists this in detail.

## Testing instructions for the judges

1. Open https://mcpbuilder.quevedojose.com. The status card shows the live service and the real number of servers generated.
2. Build a server (for example a Database source with "read only, never show emails"). In the demo checkout click "Fill in test card". Payment is in test mode: nothing is charged.
3. On the result page: listen to the spoken report, read the rules the AI derived, download the .zip, and check the receipt email if you typed your address.
4. Open https://mcpbuilder.quevedojose.com/admin.html. Every number is a real event on the server, including the purchase you just made.
5. Support: send a message from the Support page and note your ticket number. The counters and the activity list on the usage page change. The support inbox itself is private by design because it contains personal data, so it needs an admin token.
6. The first request can take about a minute if the free server was asleep.

## Built with (tags)

featherless-ai, elevenlabs, model-context-protocol, mcp, fastapi, python, typescript, node-js, postgresql, tailwindcss, github-pages, render, github-actions, pytest, accessibility, screen-reader

## Try it out links

- https://mcpbuilder.quevedojose.com
- https://github.com/Josequevedov08/MCP-Builder-Munichtech
- https://mcpbuilder-api.quevedojose.com/api/health

## Images

Thumbnail: `site/brand/devpost-project-image-1800x1200.png`. Gallery: the same image plus screenshots of the home page with the live status card, the result page with the rules, and the usage page (3:2 ratio if possible).

## Prize tracks

Keep "MunichTech EXPO Grand Challenge Award" selected.
