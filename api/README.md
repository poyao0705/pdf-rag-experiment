# API

FastAPI serving OpenUI chat through the OpenAI Agents SDK's `SandboxAgent`.

## Setup

1. From `web/`, run `vp install && vp run generate`.
2. From `api/`, copy `.env.example` to `.env` and configure your Gateway key in your editor.
3. Run `uv run fastapi dev`.

The shared AsyncOpenAI client opens/closes with the application lifespan. Each request gets a fresh agent configured with the library-derived cloud prompt. Missing/invalid specs fail startup with the generation command.

### Environment

- `THESYS_API_KEY`: required server-only secret.
- `THESYS_BASE_URL`: defaults to `https://api.thesys.dev/v1/embed`.
- `OPENUI_MODEL`: defaults to `google/gemini-3.6-flash-free`; select another supported Gateway model as needed.
- `OPENUI_SPEC_PATH`: defaults to `../web/src/generated/spec.json` relative to `api/`. Overrides resolve relative to `api/`, or may be absolute.
- `LOG_LEVEL`: defaults to `INFO`.

The `.env` location is anchored to `api/`, not the process working directory. The prompt is loaded once at startup; restart after regenerating the spec.

## Chat contract

`POST /api/chat` accepts `{ "messages": [{ "role": "user", "content": "Hello" }] }`.

Send full history with user/assistant text messages, ending in a nonblank user message. OpenAI text-part arrays are also accepted. Client system/developer/tool roles and attachments are rejected. Additional transport metadata does not create server sessions.

Successful responses use `application/x-ndjson` Chat Completions chunks. Only assistant output-text deltas are exposed; the final stop chunk means the whole agent run succeeded. Pre-stream failures use sanitized HTTP errors. Midstream failures emit a safe `error.message` record without a successful finish marker. Request IDs are preserved. Disconnects cancel priming or an active run; an already-disconnected request may be recorded as 499.

The existing `GET /` health response is unchanged. The agent retains `UnixLocalSandboxClient` configuration and a 20-turn bound. No PDF tools or retrieval features have been added.

## Tests and packaging

Run `uv run pytest -q`. Tests are offline and provide their own fake configuration/model responses.

When packaging separately from the web source, ship the generated spec and set `OPENUI_SPEC_PATH` to its location. Serve the frontend separately with same-origin `/api` routing. Never bundle the key into web assets or expose this unauthenticated local sandbox API publicly.
