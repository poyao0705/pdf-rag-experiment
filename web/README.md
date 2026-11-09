# Web

React 19 + OpenUI `AgentInterface`, built with Vite+ and Tailwind CSS v4.

## Commands

```sh
vp install
vp run generate  # generate the shared library spec before starting the API
vp run dev      # regenerate and start Vite+
vp run verify   # checks, tests, production build, generated-artifact checks
```

Use `vp run dev` and `vp run build`, not just `vp dev`/`vp build`: the scripts explicitly generate the OpenUI spec. Direct built-ins bypass this generation step. Start the API separately from `api/`; development `/api` requests are proxied to port 8000.

## Component library and chat history

`src/library.ts` is the canonical library export. Both the renderer and the CLI use it. The generated `src/generated/spec.json` is ignored; regenerate it after library changes and restart the API to reload its prompt.

Threads and received messages are saved under the `pdf-rag-openui` localStorage namespace. They are browser-local, not synced or stored in a shared backend session. Restricted/unavailable storage falls back to memory. Clearing browser data removes saved history. The backend accepts text conversation history; attachments are not supported.

The transport uses OpenUI's message formatter and NDJSON adapter. A small framing/error wrapper surfaces FastAPI's safe HTTP details and NDJSON stream errors that this SDK version otherwise ignores.

## Tailwind CSS v4

The official `@tailwindcss/vite` plugin runs alongside React in `vite.config.ts`. The HTML stylesheet entry loads `src/style.css`, which imports OpenUI's styles and Tailwind. `@source "./"` scans `src/`; use normal utility classes in TSX components. No legacy PostCSS configuration is needed.

`scripts/verify-build.mjs` checks that production CSS actually contains the full-screen utilities used by App, as well as a valid generated library spec. OpenUI's packaged styles remain intact.

## Production

`vp run build` produces `dist/` and the shared spec. Configure your host/reverse proxy to send `/api` requests to FastAPI, and provide the generated spec to that API. No Gateway credentials belong in this package or in `VITE_*` variables.
