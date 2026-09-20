# MCP Builder

MCP Builder generates working Model Context Protocol (MCP) servers for a database, a folder of files or a REST API. You describe the access rules in plain language, an open-weight model on Featherless.ai turns them into a validated policy, and the service returns a complete TypeScript project as a `.zip`. Every build result is also spoken aloud with ElevenLabs, so blind and low-vision developers can build AI infrastructure without looking at the screen.

Built for the MunichTech EXPO Hackathon.

- Website: https://mcpbuilder.quevedojose.com
- API health: https://mcpbuilder-api.quevedojose.com/api/health

## Table of contents

- [For judges: the 30 second path](#for-judges-the-30-second-path)
- [What is real and what is demo](#what-is-real-and-what-is-demo)
- [Inspiration](#inspiration)
- [What it does](#what-it-does)
- [How we built it](#how-we-built-it)
- [Accessibility](#accessibility)
- [Tests](#tests)
- [Project structure](#project-structure)
- [API reference](#api-reference)
- [Security](#security)
- [Challenges we ran into](#challenges-we-ran-into)
- [Accomplishments](#accomplishments)
- [Roadmap](#roadmap)
- [Local setup](#local-setup)
- [Deployment](#deployment)
- [Team](#team)
- [Hackathon and technology partners](#hackathon-and-technology-partners)

## For judges: the 30 second path

1. Open the website. The "Live service status" card calls the API and shows whether the model and the voice are available.
2. In the quote builder, choose a source (for example Database), name the server, list a few tables and write an instruction such as "read only, never show emails".
3. Click the generate button. In the demo checkout, click "Fill in test card" (test card `4242 4242 4242 4242`, any future date, any CVC). Nothing is charged.
4. On the result page, press "Listen" to hear the spoken build report, read the rules the AI derived from your instruction, preview any generated file and press "Download server.zip".
5. Unzip it and run `npm install` and `npm run build`. The README inside the zip shows how to connect it to Claude Desktop.

The first request to the API can take about a minute if the free Render plan was asleep. Open the health URL above a few minutes before testing.

## What is real and what is demo

| Part | Status | Notes |
| --- | --- | --- |
| Server generation | Real | The API produces a full TypeScript project on every build |
| AI step (Featherless.ai, `zai-org/GLM-5.2`) | Real | Turns your instructions into a JSON policy. If the model is unavailable, safe defaults are applied and the response says so in `ai_status` |
| Spoken report (ElevenLabs) | Real | English, German and Spanish, plus the same text for screen readers |
| `.zip` download | Real | Built in the browser from the generated files |
| Generated servers | Real | Compiled with TypeScript and exercised through a real MCP client in the test suite |
| Payment | Test mode | Simulated. No card data is collected or sent anywhere. The order itself is recorded, with the price computed on the server |
| Promo code `LAUNCH20` | Real rule | Applied by the server to the recorded order and the receipt. Test amounts only |
| Receipt | Real | Shown on the result page, downloadable as a text file and, if you give an email, sent with the server .zip attached. The amounts are computed on the server. No card is charged |
| Recovering a closed download | Real | The last build is kept in the browser, and the home page links back to it. It does not sync across devices |
| Support form | Real | Messages are stored, given a ticket number and forwarded by email to the owner. Replies go to the address the user typed |
| Terms, privacy and refund text | Demo | Template text, not a legal document |
| Usage page (`admin.html`) | Real | Every number comes from real events on the server: builds, downloads, test orders, voice reports, receipts, errors. The support inbox needs an admin token |

Database servers are tested against simulated drivers that log every statement, not against a live PostgreSQL or MySQL instance. The SQL guard and the read-only transaction are verified, but a full run against a real database is on the roadmap.

## Inspiration

Connecting company data to AI agents through MCP is slow and error-prone. A developer has to learn the SDK, write tool definitions, wire credentials safely and repeat the process for every data source. Small teams often skip it because the setup cost is higher than the first benefit.

Accessibility is a second gap. Build tools report progress through terminals and dashboards that assume the reader can see them. A developer who uses a screen reader still gets logs, but not a clear, timely signal of what happened to a build. We wanted the spoken status of a build to be a core part of the product and not an afterthought.

## What it does

- Accepts a build request with the server name, the source type (database, files or API), the resources to expose and optional instructions in natural language.
- Asks an open-weight model on Featherless.ai to convert the instructions into a small policy: limits, blocked fields and tool descriptions.
- Validates and clamps that policy, then renders a complete project from verified templates: `package.json`, `tsconfig.json`, `src/index.ts`, `mcp.config.json`, `.env.example` and a README.
- Returns the rules the server will enforce, written in the chosen language, so the user can check what the AI understood.
- Turns any build result or error into a spoken MP3 in English, German or Spanish, and returns the same message as plain text.
- Ships a static website in English, German and Spanish with a quote builder, a demo checkout, a result page with a real download, and documentation.

## How we built it

Hybrid generation. The model never writes the server code. It only derives a JSON policy, which the backend validates and clamps (numbers are bounded, identifiers are sanitized, names such as `password` or `token` are always blocked). The TypeScript comes from three templates (files, database, API) that are compiled and tested in continuous integration. This means a build cannot produce code that fails to compile or that lacks the security checks, whatever the model says.

Backend: Python with FastAPI. Routes are asynchronous, bodies are validated with Pydantic v2, errors use one JSON envelope, and configuration comes from environment variables.

Inference: a client for the Featherless.ai chat completions API (OpenAI compatible). The default model is `zai-org/GLM-5.2`, with reasoning off to keep builds under a few seconds. If no key is set or the call fails, the build continues with safe default rules and reports `ai_status` as `template` or `defaults`.

Voice: a service calls ElevenLabs text-to-speech (`eleven_multilingual_v2`) on demand and returns the MP3.

Credentials: when a client sends secrets, they are encrypted with Fernet on arrival. Only variable names are ever sent to the model.

Frontend: static HTML with Tailwind CSS. `site/i18n.js` holds the dictionaries and the language switcher (English by default, German and Spanish), `site/api.js` is the API client and `site/zip.js` is a small ZIP writer used for the download.

Build flow:

1. The quote builder sends `POST /api/build-mcp`.
2. Pydantic validates the payload. Invalid requests get `422` with the failing fields.
3. The model derives a policy from the instructions. The backend validates it, or falls back to safe defaults.
4. The backend renders the project from the templates and returns the files, the rules and a spoken summary.
5. The result page builds the `.zip` in the browser and calls `POST /api/voice-status` to play the report.

What the generated servers protect against:

- Files: every path is resolved to its real location inside the allowed folders (so `../` and symbolic links pointing outside are refused), only allowed extensions are read, and file size and result count are limited.
- Database: a single `SELECT` only, forbidden keywords refused, only exposed tables readable, blocked columns never returned, and execution inside a read-only transaction with a time limit.
- API: only listed endpoints can be called, full URLs and redirects are refused, blocked JSON fields are removed and long responses are truncated.

## Accessibility

Accessibility is the main differentiator of the project.

How a blind developer uses it, step by step:

1. Jump by headings to the build section. Every form field has a label and a hint.
2. Fill in the server name, the source, what to expose, the instructions and the voice language.
3. Activate the build button. Progress and errors are announced through live regions.
4. On the result page the spoken report can play automatically (this can be turned off in the form) and has a replay button, which also covers browsers that block autoplay.
5. The same report is always written as text in a polite live region, so it works with no audio, with a braille display and when the voice service is down.
6. Download the `.zip` and follow the plain-text README inside it.

What we did:

- Spoken report for success and failure, in three languages.
- Text equivalent of every spoken message.
- Keyboard use for every control, focus moved into dialogs and returned when they close, `Escape` closes them.
- Language switcher that updates the `lang` attribute of the page.
- Automated audits with axe-core report zero violations on every page in the three languages.
- Documentation includes an Accessibility section with the same steps.

Honest limits: automated audits cover structure and labels, but we have not yet tested with a group of real screen reader users. Audio depends on the ElevenLabs service being reachable, which is why the text version always exists. A quick manual check is possible with Windows Narrator (`Win` + `Ctrl` + `Enter`) or NVDA.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -m "not e2e" -q     # unit tests: API and generator
python -m pytest tests/e2e -q              # needs Node.js and network access
```

- Unit tests cover the policy sanitizing (hostile values are clamped and cleaned), the project renderer, the localized rules, the API contract, the ElevenLabs backup key and the receipt email (server-side amounts, one email per build, no leaked secrets).
- End-to-end tests render real projects, install their dependencies, compile them with TypeScript and talk to them through the official MCP client over stdio. They check that path escapes are refused in the files server, that the API server calls only allowed endpoints and reports upstream errors, and that the database servers run inside a read-only transaction and reject unsafe SQL (against simulated drivers).
- A test also unpacks the ZIP produced by the browser writer with a standard tool and verifies its integrity and UTF-8 content.
- GitHub Actions runs both groups on every push (`.github/workflows/tests.yml`).

## Project structure

```
MCP-Builder-Munichtech/
  main.py                      FastAPI application, services and routes
  receipts.py                  Receipt email: server-side amounts, ZIP attachment and SMTP sending
  metrics.py                   Usage events, PostgreSQL storage with a memory fallback, and the public numbers
  generator/
    __init__.py                Policy validation, rules text and project renderer
    templates/                 Verified TypeScript templates (files, database, api, common)
  tests/
    test_api.py                API contract tests
    test_generator.py          Policy and renderer tests
    e2e/                       Compile and run the generated servers through an MCP client
  requirements.txt             Python dependencies
  requirements-dev.txt         Test dependencies
  pytest.ini                   Test configuration
  .env.example                 Environment variable template
  render.yaml                  Deployment blueprint for the API on Render
  .github/workflows/
    deploy.yml                 GitHub Pages deployment (publishes only site/)
    tests.yml                  Continuous integration
  site/                        Static website, the only folder that is published
    index.html                 Landing page, live status, quote builder, demo checkout
    success.html               Result page: spoken report, rules, preview and .zip download
    docs.html                  Documentation, including the Accessibility section
    support.html               Support page (demo form)
    politics.html              Terms, privacy and refunds (demo text)
    admin.html                 Demo admin panel (sample data)
    i18n.js                    Translations (en, de, es) and language switcher
    api.js                     Client for the MCP Builder API
    zip.js                     ZIP writer used by the download
    config.js                  Production API address, selected by hostname
    brand/                     Logo, favicon and Devpost image
```

Excluded from version control: `.env`, `.venv/`, `__pycache__/` and other local files.

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/build-mcp` | Generate an MCP server project from a configuration |
| POST | `/api/voice-status` | Return an MP3 that announces a build result or error |
| POST | `/api/send-receipt` | Email the receipt and the generated server as a .zip, once per build |
| GET | `/api/stats` | Public usage numbers (no personal data) |
| POST | `/api/events/download` | Count a download of a generated server |
| POST | `/api/support` | Store a support message and forward it by email |
| GET | `/api/admin/support` | The support inbox, protected with the `X-Admin-Token` header |
| GET | `/api/health` | Service and integration status |

Interactive documentation is available at `/docs` while the API is running.

### POST /api/build-mcp

Request body. Unknown fields are rejected.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `server_name` | string | yes | Lowercase kebab-case, 3 to 40 characters, must start with a letter |
| `source_type` | string | yes | `files` (or its alias `local`), `database` or `api` |
| `db_engine` | string | no | `postgresql`, `mysql` or `mariadb` |
| `resources` | string[] | no | Folders, table names or endpoints to expose. Up to 50 items of 200 characters |
| `instructions` | string | no | Rules for the AI, up to 1000 characters |
| `credentials` | object | no | Secrets keyed by environment variable name. Up to 20 entries |
| `language` | string | no | Language of `spoken_summary` and `applied_rules`: `en`, `de` or `es`. Defaults to `en` |

Successful response (`200`): `build_id`, `status`, `server_name`, `source_type`, `ai_status` (`applied`, `defaults` or `template`), `applied_rules`, `config_schema`, `files` and `spoken_summary`.

```bash
curl -X POST http://127.0.0.1:8000/api/build-mcp \
  -H "Content-Type: application/json" \
  -d '{"server_name":"shop-db","source_type":"database","resources":["orders","customers"],"instructions":"Read-only access. Never show emails.","language":"en"}'
```

### POST /api/voice-status

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | string | yes | `success` or `error` |
| `server_name` | string | no | Same format as in the build request |
| `file_count` | integer | no | Number of generated files, mentioned in the success message |
| `message` | string | no | Detail spoken after an error, up to 300 characters |
| `language` | string | no | `en`, `de` or `es`. Defaults to `en` |

The response is `audio/mpeg`.

```bash
curl -X POST http://127.0.0.1:8000/api/voice-status \
  -H "Content-Type: application/json" \
  -d '{"status":"success","server_name":"shop-db","file_count":8}' \
  --output status.mp3
```

### POST /api/send-receipt

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `build_id` | string | yes | The id returned by `/api/build-mcp`. The build must still be in server memory |
| `email` | string | yes | Recipient address |
| `order_id` | string | yes | Format `MB-` plus 6 letters or digits |
| `discount_code` | string | no | `LAUNCH20` gives 20% off. Any other code is ignored |
| `language` | string | no | `en`, `de` or `es` |

The price is taken from the source type of the build and the discount from the code, so the client cannot set an amount. Each build can be emailed once. The endpoint answers `503 email_unavailable` when SMTP is not configured, and `404 build_not_found` when the build has left the in-memory store (for example after a restart).

### Errors

Every error uses the same JSON envelope and never includes internal details or submitted values:

```json
{"error": {"code": "model_timeout", "message": "The code generation service took too long to respond."}}
```

| Status | Code | Meaning |
| --- | --- | --- |
| 422 | `invalid_request` | The request body failed validation |
| 429 | `rate_limited` | Too many requests from this client |
| 429 | `model_busy` | The service is busy or the model is rate limiting requests |
| 502 | `model_unavailable` | The model service failed or returned an invalid response |
| 503 | `model_not_configured` | The model service rejected the server credentials |
| 504 | `model_timeout` | The model service exceeded the deadline |
| 503 | `voice_unavailable` | Voice is not enabled or the voice service is unavailable |
| 503 | `voice_not_configured` | The voice service rejected the server credentials |
| 504 | `voice_timeout` | The voice service took too long |
| 404 | `build_not_found` | The build to email is no longer in server memory |
| 503 | `email_unavailable` | Receipt emails are not enabled, or the mail server failed |
| 503 | `email_not_configured` | The mail server rejected the configured credentials |
| 500 | `internal_error` | Unexpected internal error |

## Security

- The model never writes executable code. It only proposes a policy that is validated and clamped, and secret-looking names are always blocked.
- Secret values, when a client sends them, are encrypted with Fernet on arrival and are never logged or returned. The website sends only variable names.
- The model receives only the names of the environment variables, never their values.
- Generated code is returned to the client and is never executed by the API.
- API keys are read from environment variables only. They are not part of the source code or the frontend.
- Error responses are generic and validation errors never echo submitted values.
- Requests are rate limited per client IP and simultaneous generations are capped, which protects the model and voice quotas of a public deployment.
- CORS is limited to the origins listed in `ALLOWED_ORIGINS`.
- Never commit your `.env` file. `.gitignore` blocks `.env` and its variants, private keys and certificates, and keeps only `.env.example`.
- Only the `site/` folder is published to GitHub Pages.

## Challenges we ran into

Unreliable model output. Language models wrap JSON in markdown fences, add reasoning blocks or return nested structures. Asking the model for full code was fragile, so we changed the design: the model returns only a small policy, and verified templates produce the code. This removed the whole class of "the generated server does not compile" failures.

Slow reasoning models. A large reasoning model can spend minutes thinking. We disable reasoning, keep the model output small and enforce a deadline, so a build ends in a few seconds.

Proving the servers work. Templates are only useful if they run, so the test suite compiles each one and drives it through a real MCP client. Getting the database tests to run in continuous integration without a live database led us to simulate the drivers and log every statement.

Keeping secrets away from the model. The prompt is built from a structured specification that contains only credential names.

Voice must never break a build. Text-to-speech is a separate endpoint and every spoken message also exists as text.

Free-tier voices. Some ElevenLabs library voices need a paid plan through the API, so the default is a premade voice that works on free accounts.

A multilingual static site without a build step. The interface is translated at runtime from one dictionary file, with English written directly in the HTML so the page never flashes another language.

## Accomplishments

- A complete path from the browser to a downloadable, compilable MCP server, with validation at every boundary.
- Real integrations with Featherless.ai and ElevenLabs, verified end to end in production.
- Generated servers that are compiled and exercised through an MCP client in continuous integration.
- Spoken build status for success and failure in three languages, with a text equivalent for screen readers.
- Zero axe-core violations on every page in the three languages.
- Credential handling designed so that secret values never reach the model or the logs.

## Roadmap

- Real Stripe test mode checkout, with the price and promo code checked on the server.
- A verified sending domain for receipt emails, so they reach any address (the test sender only reaches the account owner).
- Tests against live PostgreSQL and MySQL instances.
- Manual testing with real screen reader users and fixes from their feedback.
- Persist builds in a database instead of memory.
- Automatic deployment of the generated server.

## Local setup

Requirements: Python 3.10 or newer, and Node.js 18 or newer to run the generated servers or the end-to-end tests.

```bash
git clone <repository-url>
cd <repository-folder>
python -m venv .venv
source .venv/bin/activate        # macOS and Linux
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
```

Fill in the keys you have in `.env`:

| Variable | Description |
| --- | --- |
| `FEATHERLESS_API_KEY` | Featherless.ai key. If empty, safe default rules are used |
| `FEATHERLESS_MODEL` | Open-weight model id. Defaults to `zai-org/GLM-5.2` |
| `FEATHERLESS_BASE_URL` | API base URL. Defaults to `https://api.featherless.ai/v1` |
| `FEATHERLESS_MAX_TOKENS` | Output limit for the model. Defaults to `1024` |
| `FEATHERLESS_TIMEOUT` | Deadline in seconds for the model call. Defaults to `60` |
| `FEATHERLESS_THINKING` | Set to `true` to let the model reason before answering. Defaults to `false` |
| `FEATHERLESS_MOCK` | Set to `true` to skip the model and use safe defaults |
| `ELEVENLABS_API_KEY` | ElevenLabs key. If empty, voice audio is disabled |
| `ELEVENLABS_API_KEY_2` | Optional backup ElevenLabs key. Used only when the main key returns 401, 402, 403 or 429 |
| `RESEND_API_KEY` and `MAIL_FROM` | Receipt emails through the Resend HTTPS API (recommended: some hosts block SMTP ports). `MAIL_FROM` is a verified sender such as `MCP Builder <receipts@yourdomain.com>` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURITY` | Alternative: any SMTP account (Brevo, a Gmail app password). `SMTP_SECURITY` is `starttls`, `ssl` or `none` (local test servers only). With neither Resend nor SMTP set, receipt emails are disabled |
| `DATABASE_URL` | PostgreSQL connection string. With it, the usage numbers and support messages survive restarts. Without it they live in memory |
| `ADMIN_TOKEN` | Secret that unlocks the support inbox (`X-Admin-Token`). Without it the inbox is disabled |
| `SUPPORT_TO` | Address that receives a notice for each support message |
| `RATE_LIMIT_SUPPORT_PER_MINUTE`, `RATE_LIMIT_EVENTS_PER_MINUTE` | Support messages (default `3`) and stats or download events (default `60`) per client IP each minute |
| `RATE_LIMIT_RECEIPTS_PER_MINUTE` | Receipt emails allowed per client IP each minute. Defaults to `3` |
| `ELEVENLABS_VOICE_ID` | Voice used for announcements. Must be available on your plan |
| `CREDENTIALS_ENCRYPTION_KEY` | Fernet key. If empty, an ephemeral key is generated at startup |
| `ALLOWED_ORIGINS` | Comma separated list of allowed CORS origins |
| `SERVE_SITE` | Serve the `site/` folder from the API process. Defaults to `true` |
| `RATE_LIMIT_BUILDS_PER_MINUTE` | Build requests per client IP each minute. Defaults to `5` |
| `RATE_LIMIT_VOICE_PER_MINUTE` | Voice requests per client IP each minute. Defaults to `20` |
| `MAX_CONCURRENT_BUILDS` | Generations that may run at the same time. Defaults to `3` |
| `HOST` and `PORT` | Address used by `python main.py`. Default `127.0.0.1:8000` |

Generate an encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Start the API. It also serves the website:

```bash
python main.py
```

Open `http://127.0.0.1:8000` for the site, `/api/health` to check the API and `/docs` for the interactive documentation. Use a local server instead of opening the HTML files directly so that the scripts load correctly.

## Deployment

The project runs as two pieces: the static site on GitHub Pages and the API on a Python host. The examples use the domain `quevedojose.com`. Replace the names to use your own.

| Piece | Address | Host |
| --- | --- | --- |
| Website | `mcpbuilder.quevedojose.com` | GitHub Pages |
| API | `mcpbuilder-api.quevedojose.com` | Render |

1. API on Render: create a Blueprint from this repository (it reads `render.yaml`), enter `FEATHERLESS_API_KEY` and `ELEVENLABS_API_KEY` when asked, check `/api/health`, and add the custom domain `mcpbuilder-api.quevedojose.com`.
2. Website on GitHub Pages: `.github/workflows/deploy.yml` publishes only `site/` on every push to `main`. In Settings, Pages, choose GitHub Actions as the source and set the custom domain.
3. DNS: add a `CNAME` for `mcpbuilder` pointing to `<github-user>.github.io` and a `CNAME` for `mcpbuilder-api` pointing to the target shown by Render.
4. `site/config.js` maps the hostname of the website to the API address, and `ALLOWED_ORIGINS` on the API must contain the public address of the website.

The free Render plan sleeps after a period without traffic, so the first request can take about a minute.

To run the API on another host:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
```

## Team

| Member | Role | Responsibilities |
| --- | --- | --- |
| [Jose Quevedo](https://github.com/Josequevedov08) | Lead Developer and Technical Architect | Backend with FastAPI, AI integrations with Featherless.ai, MCP server architecture |
| [Nolayita](https://github.com/NOLAYITA) | Product Strategy, Documentation and Internationalization Lead | Product strategy, official documentation, English adaptation of the interface, content management |

## Hackathon and technology partners

- MunichTech EXPO Hackathon: https://munichtech-expo.devpost.com/
- Featherless.ai, open-weight model inference: https://featherless.ai
- ElevenLabs, text-to-speech: https://elevenlabs.io
