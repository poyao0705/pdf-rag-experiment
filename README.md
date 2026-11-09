# PDF RAG — OpenUI chat foundation

FastAPI + SandboxAgent backend, with a React/OpenUI frontend and Tailwind CSS v4. This implements the chat foundation; PDF upload and retrieval are not implemented yet.

## Start locally

Prerequisites: Python 3.15+, uv, and Vite+ (`vp`). The web project selects pnpm through its package-manager configuration.

Generate the component spec **before** starting the API:

```sh
cd web
vp install
vp run generate
cd ../api
cp .env.example .env
```

Edit `api/.env` in your own editor and set `THESYS_API_KEY` to your OpenUI Gateway key. Choose a supported `OPENUI_MODEL` if overriding the default. Never put credentials in frontend variables.

In separate terminals:

```sh
cd api
uv run fastapi dev
```

```sh
cd web
vp run dev
```

Open the frontend URL printed by Vite+ (normally http://localhost:5173). Its `/api` proxy targets FastAPI at http://localhost:8000.

## How it works

- `web/src/library.ts` exports the library rendered by `AgentInterface`. The CLI generates `web/src/generated/spec.json` from it.
- FastAPI loads that spec at startup and puts the matching OpenUI cloud configuration and form rules in the agent instructions.
- Browser-local threads send their full user/assistant text history to `POST /api/chat`.
- A fresh `SandboxAgent` executes through the shared Gateway client. Assistant text is streamed as NDJSON, while tool arguments and internal events stay private.
- The frontend handles streaming errors and saves received messages locally. There is no shared SQLite session or server-side chat persistence.

## Verify offline

```sh
(cd api && uv run pytest -q)
(cd web && vp run verify)
```

Tests use fake model responses, not live inference or real credentials. Frontend verification includes format/lint/type checks, tests, build, spec validation, and compiled Tailwind utility checks.

## Packaging and safety

`cd web && vp run build` generates the spec and builds `web/dist/`. Production hosting must route `/api` to FastAPI; the development proxy is not part of the built application. Supply the same generated spec to the API, using `OPENUI_SPEC_PATH` if it is packaged elsewhere. Restart the API after changing/regenerating the component library.

This is an unauthenticated development application. `UnixLocalSandboxClient` runs locally; do not expose the API publicly with host-level sandbox access without designing authentication, isolation, and resource limits.

See [API details](api/README.md) and [web/Tailwind details](web/README.md).
