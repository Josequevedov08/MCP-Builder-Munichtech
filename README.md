# MCP Builder

MCP Builder generates Model Context Protocol (MCP) servers from a short configuration of a database, a set of files or an external API. Inference runs on open-weight models through Featherless.ai, and every build outcome is announced by voice through ElevenLabs so that blind and low-vision developers can build AI infrastructure on their own.

Built for the MunichTech EXPO Hackathon.

## Inspiration

Connecting corporate data to AI agents through MCP is slow and error-prone. A developer has to learn the SDK, write tool definitions, wire credentials safely and repeat the process for every data source. Small teams in Europe often skip it because the setup cost is higher than the first benefit.

Accessibility is a second gap. Build tools report progress through terminals and dashboards that assume the reader can see them. A developer who uses a screen reader still gets logs, but not a clear, timely signal of what happened to a build. We wanted the spoken status of a build to be a core part of the product and not an afterthought.

## What it does

- Accepts a build request with the server name, the source type (database, files or API), the resources to expose, optional instructions for the AI and credentials.
- Asks an open-weight model on Featherless.ai to produce a JSON configuration schema and the base TypeScript code of the MCP server (`package.json`, `src/index.ts`, `.env.example`).
- Validates the model output before returning it, then returns the files and the schema to the client.
- Generates a spoken notification with ElevenLabs when a build succeeds and when it fails, available as an MP3 endpoint.
- Returns the same message as plain text (`spoken_summary`) so screen readers and ARIA live regions can use it directly.
- Ships a static marketing site with a simulated checkout, an installation demo and a demo admin panel with sample metrics.

## How we built it

Backend: Python with FastAPI. Routes are asynchronous, request and response bodies are validated with Pydantic v2, and configuration comes from environment variables loaded with python-dotenv.

Inference: a client for the Featherless.ai chat completions API, which is OpenAI compatible. The default model is `Qwen/Qwen2.5-Coder-32B-Instruct` and it can be changed with an environment variable. When no API key is set, a deterministic template generator produces valid output so the full flow can be demonstrated offline.

Voice and accessibility: a notifier service calls the ElevenLabs text-to-speech API. It runs as a background task after the build response is decided, in English or Spanish, and stores the audio so clients can fetch it later.

Credentials: secrets are encrypted with Fernet as soon as they reach the server. Only the variable names are ever sent to the model, and the generated `.env.example` contains names without values.

Frontend: static HTML with Tailwind CSS. It includes the landing page, documentation, support and legal pages, and a demo admin panel.

Repository layout:

```
main.py            FastAPI application and services
requirements.txt   Python dependencies
.env.example       Environment variable template
index.html         Landing page and demo checkout
admin.html         Demo admin panel (sample data)
docs.html          Documentation
support.html       Support page
politics.html      Terms and privacy
success.html       Post-purchase page
```

API summary:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/build-mcp` | Generate an MCP server from a configuration |
| GET | `/build-mcp/{build_id}` | Build and audio status |
| GET | `/build-mcp/{build_id}/audio` | Spoken notification as `audio/mpeg` |
| GET | `/health` | Service and integration status |

## Challenges we ran into

Unreliable model output. Language models wrap JSON in markdown fences or add prose. We extract the JSON object defensively and validate it against a Pydantic model, and we reject file paths that are absolute or contain `..` so a bad response cannot describe files outside the project folder.

Keeping secrets away from the model. The prompt is built from a structured specification that contains only credential names. Values are encrypted on arrival and are never logged or returned.

Voice must never break a build. Text-to-speech can fail or be slow. The notification runs in a background task that catches its own errors and updates an audio status field, so the build result is unaffected. Tasks keep a strong reference so they are not garbage collected, and shutdown waits for pending voice jobs.

Announcing failures. FastAPI drops background tasks attached to a request that ends in an exception, so the failure path schedules its voice notification explicitly before raising the HTTP error.

Demo without credentials. Both external services have a fallback (template generator for the model, disabled audio for voice) so the project runs on a clean machine.

## Accomplishments

- A complete request path from configuration to generated MCP server files, with strict validation at every boundary.
- Spoken build status for both success and failure, with a text equivalent for screen readers.
- Credential handling designed so that secret values never reach the model or the logs.
- Verified end to end with automated calls against a mocked ElevenLabs endpoint: successful build, request validation errors, upstream failure and audio retrieval.
- A polished landing page with a working promo code flow, an interactive FAQ and an installation demo.

Current limits: the landing page generator and checkout are simulated and are not yet connected to `/build-mcp`, build records are stored in memory, and automatic deployment of the generated server is not implemented.

## Local setup

Requirements: Python 3.10 or newer.

1. Clone the repository and enter the folder.

```bash
git clone <repository-url>
cd "MCP Builder"
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

Generate an encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

5. Start the API.

```bash
uvicorn main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs` to try the endpoints in the interactive documentation. An example request:

```bash
curl -X POST http://127.0.0.1:8000/build-mcp \
  -H "Content-Type: application/json" \
  -d '{"server_name":"shop-db","source_type":"database","db_engine":"postgresql","resources":["orders","customers"],"credentials":{"DB_PASSWORD":"example"},"language":"en"}'
```

6. Serve the static site in a second terminal.

```bash
python -m http.server 5500
```

Then open `http://127.0.0.1:5500/index.html`.

## Hackathon and technology partners

- MunichTech EXPO Hackathon: add the official event page link here.
- Featherless.ai, open-weight model inference: https://featherless.ai
- ElevenLabs, text-to-speech: https://elevenlabs.io
