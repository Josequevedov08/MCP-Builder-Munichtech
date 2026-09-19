# MCP Builder

MCP Builder generates Model Context Protocol (MCP) servers from a short configuration of a database, a set of files or an external API. Inference runs on open-weight models through Featherless.ai, and every build outcome is announced by voice through ElevenLabs so that blind and low-vision developers can build AI infrastructure on their own.

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

- Accepts a build request with the server name, the source type (database, files or API), the resources to expose, optional instructions for the AI and credentials.
- Asks an open-weight model on Featherless.ai to produce a JSON configuration schema and the base TypeScript code of the MCP server (`package.json`, `src/index.ts`, `.env.example`).
- Validates the model output before returning it, then returns the files and the schema to the client.
- Generates a spoken notification with ElevenLabs when a build succeeds and when it fails, available as an MP3 endpoint.
- Returns the same message as plain text (`spoken_summary`) so screen readers and ARIA live regions can use it directly.
- Ships a static marketing site in English, German and Spanish, with a simulated checkout, an installation demo and a demo admin panel with sample metrics.

## How we built it

Backend: Python with FastAPI. Routes are asynchronous, request and response bodies are validated with Pydantic v2, and configuration comes from environment variables loaded with python-dotenv.

Inference: a client for the Featherless.ai chat completions API, which is OpenAI compatible. The default model is `Qwen/Qwen2.5-Coder-32B-Instruct` and it can be changed with an environment variable. When no API key is set, a deterministic template generator produces valid output so the full flow can be demonstrated offline.

Voice and accessibility: a notifier service calls the ElevenLabs text-to-speech API. It runs as a background task after the build outcome is decided, in English or Spanish, and stores the audio so clients can fetch it later.

Credentials: secrets are encrypted with Fernet as soon as they reach the server. Only the variable names are ever sent to the model, and the generated `.env.example` contains names without values.

Frontend: static HTML with Tailwind CSS. It includes the landing page, documentation, support and legal pages, and a demo admin panel. The site is available in English (default), German and Spanish. `site/i18n.js` holds the dictionaries and the language switcher, and the chosen language is remembered in the browser. You can also force one with `?lang=de`.

Build flow:

1. The client sends `POST /build-mcp` with the configuration.
2. Pydantic validates the payload. Invalid requests are rejected with `422`.
3. The credentials are encrypted and stored against a new `build_id`.
4. The Featherless.ai client asks the model for the schema and the code, and the response is parsed and validated.
5. The API answers with the generated files and a `spoken_summary`.
6. In parallel, a background task asks ElevenLabs for the audio version of that summary. The same happens when a build fails.
7. The client polls `GET /build-mcp/{build_id}` and downloads the audio from `GET /build-mcp/{build_id}/audio` when it is ready.

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
```

Generated at runtime and excluded from version control: `.env`, `.venv/`, `__pycache__/` and `audio_out/` (the synthesized MP3 files).

Inside `main.py` the code is organized in these sections, in order: settings, domain errors, Pydantic schemas, credential vault and build store, Featherless.ai client, ElevenLabs voice notifier, application wiring and routes.

## API reference

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/build-mcp` | Generate an MCP server from a configuration |
| GET | `/build-mcp/{build_id}` | Build status and audio status |
| GET | `/build-mcp/{build_id}/audio` | Spoken notification as `audio/mpeg` |
| GET | `/health` | Service and integration status |

Interactive documentation is available at `/docs` while the API is running.

Request body of `POST /build-mcp`:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `server_name` | string | yes | Lowercase kebab-case, 3 to 40 characters, must start with a letter |
| `source_type` | string | yes | `files`, `database` or `api` |
| `db_engine` | string | when `source_type` is `database` | `postgresql`, `mysql` or `mariadb` |
| `resources` | string[] | no | Tables, folders or endpoints to expose. Up to 50 items of 200 characters |
| `instructions` | string | no | Rules for the AI, up to 1000 characters |
| `credentials` | object | no | Secrets keyed by environment variable name such as `DB_PASSWORD`. Up to 20 entries |
| `notify_voice` | boolean | no | Defaults to `true` |
| `language` | string | no | Language of the spoken message, `en` or `es`. Defaults to `en` |

Successful response (`201`): `build_id`, `status`, `server_name`, `config_schema`, `files`, `spoken_summary`, `audio_status` and `audio_url`.

`audio_status` is `pending` while the audio is being synthesized, `ready` when it can be downloaded, `failed` if synthesis did not work and `disabled` when voice notifications are off.

Errors:

| Status | Meaning |
| --- | --- |
| 404 | Unknown `build_id` |
| 409 | Audio requested while it is still being generated |
| 422 | Invalid request body |
| 502 | The model service failed or returned output that did not validate |
| 504 | The model service timed out |
| 500 | Unexpected internal error |

Failed builds return a `detail` object with `build_id`, `message`, `spoken_summary` and `audio_url`, so the failure can also be announced by voice.

Example:

```bash
curl -X POST http://127.0.0.1:8000/build-mcp \
  -H "Content-Type: application/json" \
  -d '{"server_name":"shop-db","source_type":"database","db_engine":"postgresql","resources":["orders","customers"],"credentials":{"DB_PASSWORD":"example"},"language":"en"}'
```

## Accessibility

Accessibility is the main differentiator of the project.

- Every build outcome, success or failure, has a spoken version generated with ElevenLabs.
- The same message is returned as text in `spoken_summary`, so a client can place it in an ARIA live region and let the screen reader announce it without playing audio.
- Error messages are written in plain language so they read clearly when spoken.
- The audio is fetched from a stable URL (`audio_url`), so a client can play it automatically as soon as `audio_status` becomes `ready`.
- The static site uses semantic HTML, visible focus outlines and a language switcher that updates the `lang` attribute of the page.

## Security

- Credentials are encrypted with Fernet on arrival and are never logged or returned by any endpoint.
- The model receives only the names of the environment variables, never their values.
- Files returned by the model are validated. Absolute paths and `..` segments are rejected.
- Generated code is returned to the client and is never executed by the server.
- CORS is limited to the origins listed in `ALLOWED_ORIGINS`.
- Never commit your `.env` file. `.gitignore` blocks `.env` and its variants, private keys, certificates, credential files and generated audio, and keeps only `.env.example`.
- Only the `site/` folder is published to GitHub Pages, so backend code, planning notes and local files are never served publicly.

## Challenges we ran into

Unreliable model output. Language models wrap JSON in markdown fences or add prose. We extract the JSON object defensively and validate it against a Pydantic model, and we reject file paths that are absolute or contain `..` so a bad response cannot describe files outside the project folder.

Keeping secrets away from the model. The prompt is built from a structured specification that contains only credential names. Values are encrypted on arrival and are never logged or returned.

Voice must never break a build. Text-to-speech can fail or be slow. The notification runs in a background task that catches its own errors and updates an audio status field, so the build result is unaffected. Tasks keep a strong reference so they are not garbage collected, and shutdown waits for pending voice jobs.

Announcing failures. FastAPI drops background tasks attached to a request that ends in an exception, so the failure path schedules its voice notification explicitly before raising the HTTP error.

Demo without credentials. Both external services have a fallback (template generator for the model, disabled audio for voice) so the project runs on a clean machine.

A multilingual static site without a build step. The interface is translated at runtime from a single dictionary file, with English written directly in the HTML so the page never flashes another language before the script loads.

## Accomplishments

- A complete request path from configuration to generated MCP server files, with strict validation at every boundary.
- Spoken build status for both success and failure, with a text equivalent for screen readers.
- Credential handling designed so that secret values never reach the model or the logs.
- Verified end to end with automated calls against a mocked ElevenLabs endpoint: successful build, request validation errors, upstream failure and audio retrieval.
- A landing page in three languages with a working promo code flow, an interactive FAQ and an installation demo.

## Roadmap

Current limits and next steps:

- Connect the landing page quote builder to `POST /build-mcp`. Today the generator and the checkout on the site are simulated.
- Replace the simulated checkout with a real Stripe test mode integration.
- Persist builds and credentials in a database instead of memory.
- Package the generated files as a downloadable `.zip` and add automatic deployment of the generated server.
- Add German to the spoken notifications, matching the languages of the site.
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
| `FEATHERLESS_MODEL` | Open-weight model id |
| `FEATHERLESS_MOCK` | Set to `true` to force the template generator |
| `ELEVENLABS_API_KEY` | ElevenLabs key. If empty, voice notifications are disabled |
| `ELEVENLABS_VOICE_ID` | Voice used for notifications |
| `CREDENTIALS_ENCRYPTION_KEY` | Fernet key. If empty, an ephemeral key is generated at startup |
| `ALLOWED_ORIGINS` | Comma separated list of allowed CORS origins |
| `AUDIO_OUTPUT_DIR` | Folder where synthesized audio is stored. Defaults to `audio_out` |
| `HOST` and `PORT` | Address used when running `python main.py`. Default `127.0.0.1:8000` |

Generate an encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

5. Start the API.

```bash
uvicorn main:app --reload --port 8000
```

Check that it is running at `http://127.0.0.1:8000/health`, then try the endpoints at `http://127.0.0.1:8000/docs`.

6. Serve the static site in a second terminal.

```bash
cd site
python -m http.server 5500
```

Then open `http://127.0.0.1:5500/index.html`. Use a local server instead of opening the file directly so that `i18n.js` loads correctly.

## Deployment

Static site: `.github/workflows/deploy.yml` publishes only the `site/` folder to GitHub Pages on every push to `main`. Enable Pages in the repository settings and select GitHub Actions as the source. Everything outside `site/`, including `main.py`, `prompts.txt` and any local file, stays out of the published site.

API: GitHub Pages cannot run Python. Deploy `main.py` to any host that runs ASGI applications, for example Railway or Koyeb, with this start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Set the environment variables from the table above in the hosting dashboard, and add the public URL of the static site to `ALLOWED_ORIGINS`.

## Team

| Member | Role | Responsibilities |
| --- | --- | --- |
| [Jose Quevedo](https://github.com/Josequevedov08) | Lead Developer and Technical Architect | Backend with FastAPI, AI integrations with Featherless.ai, MCP server architecture |
| [Nolayita](https://github.com/NOLAYITA) | Product Strategy, Documentation and Internationalization Lead | Product strategy, official documentation, English adaptation of the interface, content management |

## Hackathon and technology partners

- MunichTech EXPO Hackathon: add the official event page link here.
- Featherless.ai, open-weight model inference: https://featherless.ai
- ElevenLabs, text-to-speech: https://elevenlabs.io
