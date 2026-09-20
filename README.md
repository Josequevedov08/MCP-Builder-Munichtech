# MCP Builder

MCP Builder generates Model Context Protocol (MCP) servers from a short configuration of a database, a set of files or an external API. Inference runs on open-weight models through Featherless.ai, and every build outcome can be announced by voice through ElevenLabs so that blind and low-vision developers can build AI infrastructure on their own.

Built for the MunichTech EXPO Hackathon.

## Table of contents

- [Inspiration](#inspiration)
- [What it does](#what-it-does)
- [How we built it](#how-we-built-it)
- [Project structure](#project-structure)
- [API reference](#api-reference)
- [Accessibility](#accessibility)
- [Security](#security)
- [Challenges we ran into](#challenges-we-ran-into)
- [Accomplishments](#accomplishments)
- [Roadmap](#roadmap)
- [Local setup](#local-setup)
- [Deployment](#deployment)
- [Team](#team)
- [Hackathon and technology partners](#hackathon-and-technology-partners)

## Inspiration

Connecting corporate data to AI agents through MCP is slow and error-prone. A developer has to learn the SDK, write tool definitions, wire credentials safely and repeat the process for every data source. Small teams in Europe often skip it because the setup cost is higher than the first benefit.

Accessibility is a second gap. Build tools report progress through terminals and dashboards that assume the reader can see them. A developer who uses a screen reader still gets logs, but not a clear, timely signal of what happened to a build. We wanted the spoken status of a build to be a core part of the product and not an afterthought.

## What it does

- Accepts a build request with the server name, the source type (database, files or API), the resources to expose and optional instructions for the AI.
- Asks an open-weight model on Featherless.ai to produce a JSON configuration schema and the base TypeScript code of the MCP server (`package.json`, `src/index.ts`, `.env.example` and more).
- Validates the model output before returning it, then returns the files and the schema to the client.
- Turns any build result or error into a spoken MP3 with ElevenLabs, in English, German or Spanish.
- Returns the same message as plain text (`spoken_summary`) so screen readers and ARIA live regions can use it directly.
- Ships a static marketing site in English, German and Spanish. Its quote builder calls the API, and its checkout step is a demo that does not charge anything.

## How we built it

Backend: Python with FastAPI. Routes are asynchronous, request and response bodies are validated with Pydantic v2, and configuration comes from environment variables loaded with python-dotenv.

Inference: a client for the Featherless.ai chat completions API, which is OpenAI compatible. The default model is `zai-org/GLM-5.2` and it can be changed with an environment variable. Reasoning is switched off by default to keep builds fast, and the whole exchange is capped by a deadline. When no API key is set, a deterministic template generator produces valid output so the full flow can be demonstrated offline.

Voice and accessibility: a voice service calls the ElevenLabs text-to-speech API on demand and returns the MP3 directly. The frontend requests it after a build succeeds or fails.

Credentials: secrets, when a client sends them, are encrypted with Fernet as soon as they reach the server. Only the variable names are ever sent to the model, and the generated `.env.example` contains names without values.

Frontend: static HTML with Tailwind CSS. It includes the landing page, documentation, support and legal pages, and a demo admin panel. The site is available in English (default), German and Spanish. `site/i18n.js` holds the dictionaries and the language switcher, and the chosen language is remembered in the browser. You can also force one with `?lang=de`. `site/api.js` is the small client that talks to the API.

Build flow:

1. The user fills in the quote builder and the frontend sends `POST /api/build-mcp`.
2. Pydantic validates the payload. Invalid requests are rejected with `422` and a list of the fields that failed.
3. Credentials, if any, are encrypted and stored against a new `build_id`.
4. The Featherless.ai client asks the model for the schema and the code, and the response is parsed and validated.
5. The API answers with the generated files and a `spoken_summary`.
6. The frontend calls `POST /api/voice-status` and plays the MP3 that comes back. The same call announces errors.

## Project structure

```
MCP Builder Munichtech/
  main.py                      FastAPI application, services and routes
  requirements.txt             Python dependencies
  .env.example                 Environment variable template
  .gitignore                   Files excluded from version control
  prompts.txt                  Internal planning notes and prompt drafts
  .github/workflows/deploy.yml GitHub Pages deployment (publishes only site/)
  site/                        Static website, the only folder that is published
    index.html                 Landing page, quote builder and demo checkout
    success.html               Post-purchase page
    admin.html                 Demo admin panel (sample data)
    docs.html                  Product documentation
    support.html               Support page and contact form
    politics.html              Terms, privacy, refunds and license
    i18n.js                    Translations (en, de, es) and language switcher
    api.js                     Client for the MCP Builder API
```

Excluded from version control: `.env`, `.venv/`, `__pycache__/` and other local files.

Inside `main.py` the code is organized in these sections, in order: settings, errors, Pydantic schemas, spoken messages, credential vault and build store, Featherless.ai client, ElevenLabs voice service, application wiring, error handlers and routes.

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/build-mcp` | Generate an MCP server scaffold from a configuration |
| POST | `/api/voice-status` | Return an MP3 that announces a build result or error |
| GET | `/api/health` | Service and integration status |

Interactive documentation is available at `/docs` while the API is running.

### POST /api/build-mcp

Request body. Unknown fields are rejected.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `server_name` | string | yes | Lowercase kebab-case, 3 to 40 characters, must start with a letter |
| `source_type` | string | yes | `files` (or its alias `local`), `database` or `api` |
| `db_engine` | string | no | `postgresql`, `mysql` or `mariadb` |
| `resources` | string[] | no | Tables, folders or endpoints to expose. Up to 50 items of 200 characters |
| `instructions` | string | no | Rules for the AI, up to 1000 characters |
| `credentials` | object | no | Secrets keyed by environment variable name such as `DB_PASSWORD`. Up to 20 entries |
| `language` | string | no | Language of `spoken_summary`: `en`, `de` or `es`. Defaults to `en` |

Successful response (`200`): `build_id`, `status`, `server_name`, `source_type`, `config_schema`, `files` and `spoken_summary`.

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/build-mcp \
  -H "Content-Type: application/json" \
  -d '{"server_name":"shop-db","source_type":"database","resources":["orders","customers"],"instructions":"Read-only access.","language":"en"}'
```

### POST /api/voice-status

Request body. Unknown fields are rejected.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `status` | string | yes | `success` or `error` |
| `server_name` | string | no | Same format as in the build request |
| `file_count` | integer | no | Number of generated files, mentioned in the success message |
| `message` | string | no | Detail spoken after an error, up to 300 characters |
| `language` | string | no | `en`, `de` or `es`. Defaults to `en` |

The response is `audio/mpeg` with the spoken message.

```bash
curl -X POST http://127.0.0.1:8000/api/voice-status \
  -H "Content-Type: application/json" \
  -d '{"status":"success","server_name":"shop-db","file_count":4}' \
  --output status.mp3
```

### Errors

Every error uses the same JSON envelope and never includes internal details or submitted values:

```json
{"error": {"code": "model_timeout", "message": "The code generation service took too long to respond."}}
```

Validation errors add a `fields` list with the name of each invalid field and the reason.

| Status | Code | Meaning |
| --- | --- | --- |
| 422 | `invalid_request` | The request body failed validation |
| 429 | `model_busy` | The model service is rate limiting requests |
| 502 | `model_unavailable` | The model service failed or returned an invalid response |
| 502 | `model_bad_output` | The model output could not be validated |
| 503 | `model_not_configured` | The model service rejected the server credentials |
| 504 | `model_timeout` | The model service exceeded the deadline |
| 503 | `voice_unavailable` | Voice is not enabled or the voice service is unavailable |
| 503 | `voice_not_configured` | The voice service rejected the server credentials |
| 504 | `voice_timeout` | The voice service took too long |
| 500 | `internal_error` | Unexpected internal error |

## Accessibility

Accessibility is the main differentiator of the project.

- Every build outcome, success or failure, can be turned into a spoken message with ElevenLabs.
- The same message is returned as text in `spoken_summary`, so a client can place it in an ARIA live region and let the screen reader announce it without playing audio.
- On the success page, the summary sits in a polite live region and a button replays the audio, which covers browsers that block autoplay.
- Failures in the quote builder are shown in an alert region and are also spoken.
- Error messages are written in plain language so they read clearly when spoken.
- The static site uses semantic HTML, visible focus outlines and a language switcher that updates the `lang` attribute of the page.

## Security

- Secret values, when a client sends them, are encrypted with Fernet on arrival and are never logged or returned by any endpoint. The site itself sends only variable names, never tokens.
- The model receives only the names of the environment variables, never their values.
- Files returned by the model are validated. Absolute paths and `..` segments are rejected.
- Generated code is returned to the client and is never executed by the server.
- API keys are read from environment variables only. They are not part of the source code or the frontend.
- Error responses are generic and validation errors never echo submitted values.
- CORS is limited to the origins listed in `ALLOWED_ORIGINS`.
- Never commit your `.env` file. `.gitignore` blocks `.env` and its variants, private keys, certificates, credential files and other local files, and keeps only `.env.example`.
- Only the `site/` folder is published to GitHub Pages, so backend code, planning notes and local files are never served publicly.

## Challenges we ran into

Unreliable model output. Language models wrap JSON in markdown fences, add reasoning blocks or return JSON files such as `package.json` as nested objects instead of text. We extract the JSON object defensively, convert structured files to text, validate everything against a Pydantic model, and reject file paths that are absolute or contain `..`.

Slow reasoning models. A large reasoning model can spend minutes thinking. We disable reasoning, ask for compact code, limit the output size and enforce a total deadline so a request always ends in a bounded time.

Keeping secrets away from the model. The prompt is built from a structured specification that contains only credential names. Values are encrypted on arrival and are never logged or returned.

Voice must never break a build. Text-to-speech is a separate endpoint, so a voice failure cannot affect the build result. The frontend treats audio as optional and shows the same information as text.

Free-tier voices. Some ElevenLabs library voices need a paid plan through the API, so the default is a premade voice that works on free accounts.

Demo without credentials. The model client has a template fallback when no key is set, so the project runs on a clean machine.

A multilingual static site without a build step. The interface is translated at runtime from a single dictionary file, with English written directly in the HTML so the page never flashes another language before the script loads.

## Accomplishments

- A complete path from the quote builder in the browser to generated MCP server files, with strict validation at every boundary.
- A real integration with Featherless.ai and ElevenLabs, verified end to end.
- Spoken build status for both success and failure, in three languages, with a text equivalent for screen readers.
- Credential handling designed so that secret values never reach the model or the logs.
- A single, predictable error format that the frontend maps to translated messages.
- A landing page in three languages with a working promo code flow, an interactive FAQ and an installation demo.

## Roadmap

Current limits and next steps:

- Replace the demo checkout with a real Stripe test mode integration.
- Stream the model response to shorten the perceived wait, which can reach one or two minutes.
- Package the generated files as a downloadable `.zip` and add automatic deployment of the generated server.
- Persist builds in a database instead of memory.
- Add an automated test suite to the repository and run it in continuous integration.

## Local setup

Requirements: Python 3.10 or newer.

1. Clone the repository and enter the folder.

```bash
git clone <repository-url>
cd <repository-folder>
```

2. Create and activate a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate        # macOS and Linux
.venv\Scripts\activate           # Windows
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create your environment file and fill in the keys you have.

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

| Variable | Description |
| --- | --- |
| `FEATHERLESS_API_KEY` | Featherless.ai key. If empty, the template generator is used |
| `FEATHERLESS_MODEL` | Open-weight model id. Defaults to `zai-org/GLM-5.2` |
| `FEATHERLESS_BASE_URL` | API base URL. Defaults to `https://api.featherless.ai/v1` |
| `FEATHERLESS_MAX_TOKENS` | Output limit for the model. Defaults to `4096` |
| `FEATHERLESS_TIMEOUT` | Total deadline in seconds for one generation. Defaults to `120` |
| `FEATHERLESS_THINKING` | Set to `true` to let the model reason before answering. Defaults to `false` |
| `FEATHERLESS_MOCK` | Set to `true` to force the template generator |
| `ELEVENLABS_API_KEY` | ElevenLabs key. If empty, voice status audio is disabled |
| `ELEVENLABS_VOICE_ID` | Voice used for announcements. Must be available on your plan |
| `CREDENTIALS_ENCRYPTION_KEY` | Fernet key. If empty, an ephemeral key is generated at startup |
| `ALLOWED_ORIGINS` | Comma separated list of allowed CORS origins |
| `SERVE_SITE` | Serve the `site/` folder from the API process. Defaults to `true` |
| `HOST` and `PORT` | Address used when running `python main.py`. Default `127.0.0.1:8000` |

Generate an encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

5. Start the API. It also serves the website.

```bash
python main.py
```

Open `http://127.0.0.1:8000` for the site, `http://127.0.0.1:8000/api/health` to check the API and `http://127.0.0.1:8000/docs` for the interactive documentation. Use a local server instead of opening the HTML files directly so that `i18n.js` and `api.js` load correctly.

To serve the site separately, run `python -m http.server 5500` inside `site/`. The site then calls the API at `http://127.0.0.1:8000`, which is already allowed by the default `ALLOWED_ORIGINS`.

## Deployment

Static site: `.github/workflows/deploy.yml` publishes only the `site/` folder to GitHub Pages on every push to `main`. Enable Pages in the repository settings and select GitHub Actions as the source. Everything outside `site/`, including `main.py`, `prompts.txt` and any local file, stays out of the published site.

API: GitHub Pages cannot run Python. Deploy `main.py` to any host that runs ASGI applications, for example Railway or Koyeb, with this start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set the environment variables from the table above in the hosting dashboard, and add the public URL of the static site to `ALLOWED_ORIGINS`.

Then point the site at the deployed API by adding this line before the `api.js` script tag in `site/index.html` and `site/success.html`:

```html
<script>window.MCP_API_BASE = 'https://your-api.example.com';</script>
```

## Team

| Member | Role | Responsibilities |
| --- | --- | --- |
| [Jose Quevedo](https://github.com/Josequevedov08) | Lead Developer and Technical Architect | Backend with FastAPI, AI integrations with Featherless.ai, MCP server architecture |
| [Nolayita](https://github.com/NOLAYITA) | Product Strategy, Documentation and Internationalization Lead | Product strategy, official documentation, English adaptation of the interface, content management |

## Hackathon and technology partners

- MunichTech EXPO Hackathon: add the official event page link here.
- Featherless.ai, open-weight model inference: https://featherless.ai
- ElevenLabs, text-to-speech: https://elevenlabs.io
