# Live web demo for the shebanq MCP — design

**Date:** 2026-06-10
**Status:** approved design, pending implementation plan
**Scope:** Sub-project 2 of 2 (the live demo web app). Depends on the deployed
engine from sub-project 1 (`docs/specs/2026-06-09-mcp-deploy-design.md`), but
runs as its own service and reuses the same Docker image.

## Goal

A link-shared web page where anyone (ETCBC, a few scholars) can type a
plain-language question about the Hebrew Bible, watch it become a **real MQL
query**, and see **real results** from the live Emdros/BHSA engine. The query is
always shown and editable. "AI as a way in, not a way around": the generated MQL
is the centre of the page, not a hidden step.

This replaces the static mock showcase (`demo/index.html`, which faked the
Generate/Run steps) with a page that actually calls the engine.

## Audience & exposure

Link-shared, not advertised: ETCBC and a handful of scholars. Low traffic, low
abuse risk. Cost is bounded by an **Anthropic workspace spend cap ($10/month)**
set in the Console, plus a small in-app rate cap. No auth, no accounts.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend home | A **second Render service from the same Docker image**, LLM enabled | Reuses the whole `translate → validate → run` pipeline; the public keyless MCP stays a separate, untouched service. |
| Front-end hosting | The web service **serves the page itself** at `/` (same origin as the API) | Same origin means **no CORS**. One service, one URL, no second platform (no Netlify). |
| NL→MQL | Reuse `search_bhsa` / `translate.py` with `LLM_PROVIDER=anthropic` | The translation seam already exists; no reimplementation. |
| Cost backstop | Anthropic **workspace spend cap** + tiny per-IP rate cap | Hard ceiling by construction; nothing to meter in code. |
| Curated examples | **Live** — each runs against the real engine on click | More convincing than pre-baked results; reuses `/api/run`. |
| Repo | The live page **replaces** `demo/`; the offline static showcase is retired | One front end to maintain. |
| Front-end change cost | Front-end files are **baked into the image** | Accepted: a front-end change deploys via image rebuild (fast if Render's layer cache holds; we iterate locally during dev and bake the final page). |

## Architecture

Two Render services, one Docker image, distinguished by env:

1. **`shebanq-mcp`** (existing) — the public, keyless MCP. `WEB_API` unset,
   `LLM_PROVIDER=none`. Unchanged.
2. **`shebanq-web`** (new) — the demo. Same image, run with `WEB_API=on` and
   `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`. It serves:
   - `GET /` and static assets → the live front-end page.
   - `POST /api/ask` and `POST /api/run` → the browser-friendly JSON API.
   - `GET /health` → the existing startup self-test (unchanged).
   - (`/mcp` is still served by the same process but unused on this service.)

The web routes and the static mount are **only registered when `WEB_API=on`**,
so the public MCP service never exposes them.

### Backend web API (new)

- **`POST /api/ask`** `{question}` → `{question, mql, result_count, results,
  results_truncated?}`.
  Internally: the existing `handle_search_bhsa` with the Anthropic translator on
  (translate → `_run_pipeline` = validate + run + cap).
  **Graceful degrade:** wrap the call; if translation fails (spend cap reached,
  Anthropic error), return `{question, degraded: true, guidance, hint}` (the
  same concise primer the keyless path returns) so the UI shows "auto-translate
  paused — write or edit the query yourself" instead of an error.
- **`POST /api/run`** `{mql}` → runs a supplied MQL (reuses `handle_run_mql`):
  `{mql, result_count, results, results_truncated?}` or
  `{error, validation_errors}`. Powers the editable-query trust feature and the
  live curated examples. The read-only validator still applies (mutating MQL is
  rejected).
- **Rate cap:** a small in-memory per-IP token bucket (e.g. ~10 requests/min);
  over-limit returns HTTP 429 with a clear message. Protects the spend cap from
  a single scripted burst. In-memory is fine for one small instance. The client
  IP must be read from the **`X-Forwarded-For`** header (Render terminates TLS at
  a proxy, so the socket peer is the proxy, not the client); otherwise every
  request looks like one IP and the cap would throttle everyone together.
- No CORS needed (same origin). No auth.

### Front end (replaces `demo/`)

Reuses the serif design/CSS from the current `demo/template.html`. One page:

- **Header** — title, one-line framing, a short "AI as a way in" note.
- **Ask box** — a free-form input ("Ask the Hebrew Bible…") + Ask button.
  On submit → `POST /api/ask` → render:
  - the **MQL prominently** in an editable code box,
  - the **results** (vocalized Hebrew, lexeme gloss, verse reference *when
    present*, the true `result_count`, a truncation note when applicable),
  - honest **"0 results"** (distinguish "query is wrong" from "phenomenon
    absent"),
  - an **"open in SHEBANQ"** link for the MQL.
- **Run button** on the editable MQL box → `POST /api/run` → re-renders results.
  The scholar can correct the AI's query and re-run.
- **Curated examples gallery** (from `showcase.json`) — each example shows its
  question + MQL and a **Run** button calling `/api/run` for live results.
- **States**, all honest: idle, "translating…", "waking the server…" (cold
  start), "running…", results, zero-results, validation error, and **degraded**
  (auto-translate paused → show the primer + the editable Run path).

The front end is static files (HTML/CSS/JS); the JS calls same-origin
`/api/ask` and `/api/run`. No backend URL to configure (same origin).

## Data flow

```
question → POST /api/ask → translate (Anthropic) → validate → run (Emdros, capped)
        → { mql, result_count, results } → UI shows MQL + results
edited MQL → POST /api/run → validate → run → results
curated example → POST /api/run(example.mql) → live results
```

## Configuration (env, `shebanq-web` service)

| Var | Value | Notes |
|---|---|---|
| `WEB_API` | `on` | Registers `/api/*` + the static page mount |
| `LLM_PROVIDER` | `anthropic` | Enables NL→MQL |
| `ANTHROPIC_API_KEY` | (secret) | Set in Render's dashboard; `sync: false` in the blueprint. Scoped to the capped workspace. |
| `MCP_TRANSPORT` | `http` | Same server entrypoint |
| `MCP_ALLOWED_HOSTS` | the web service's host | Host allowlist (as on the MCP service) |
| `WEB_RATE_PER_MIN` | e.g. `10` | Per-IP request cap |
| `BHSA_SQLITE`, `QUERY_TIMEOUT_SECONDS`, `MAX_CONCURRENT_QUERIES`, `MAX_RESULTS` | as deployed | Inherited engine guardrails |

## Cost & abuse

- **$10 Anthropic workspace cap** = hard backstop; when reached, `/api/ask`
  degrades.
- **Per-IP rate cap** stops a single burst from draining the cap.
- **Unadvertised link**; read-only engine; mutating MQL already rejected.

## Deploy

- `render.yaml` gains a second service `shebanq-web` (same `dockerfilePath`),
  with the env above. `ANTHROPIC_API_KEY` declared with `sync: false` and set in
  the dashboard. Same free tier / starter choice as the MCP service.
- The Dockerfile copies the front-end static dir into the image.
- Both services auto-deploy from `main`.

## Testing

- **Unit:** `/api/ask` happy path (mocked translator + executor) returns the
  expected shape; `/api/ask` degrade path (translator raises → degraded payload);
  `/api/run` validation-rejection and success (mocked executor); the rate
  limiter (N allowed, N+1 → 429); `WEB_API` gating (routes absent when off).
- **Integration (CI):** the image boots in `WEB_API=on` mode; `GET /` serves the
  page; `/api/run` with the bara MQL returns 48 (emdros-backed, in the
  docker-smoke or a sibling job); mutating MQL via `/api/run` is rejected.
- **Manual acceptance:** against the deployed `shebanq-web` URL — ask a free-form
  question, see MQL + real results, edit + re-run, run a curated example, and
  confirm a mutating query is refused. Trip the rate cap. (Optionally) confirm
  graceful degrade by temporarily pointing at an exhausted/invalid key.

## Success criteria

- A link-shared URL where a free-form question yields a **real, shown MQL** and
  **real BHSA results**, with the query editable and re-runnable.
- Curated examples run live.
- Read-only holds: a mutating query via `/api/run` is rejected.
- When the Anthropic cap is hit (or the key fails), the page **degrades
  gracefully** instead of breaking.
- The public keyless MCP service is **untouched** and stays separate.
- No API key in the repo or in the page source; it lives only in the
  `shebanq-web` service's secret env.

## Out of scope (deliberately)

- Response caching, auth/accounts, multi-instance.
- Verse references in results (separate task; rendered "when present").
- Retiring or maintaining the old offline static showcase (it is replaced).
- Streaming/partial results; a single request/response per query is enough.

## Open implementation questions (resolve at plan time)

- Exact FastMCP mechanism for serving static files + the `/api/*` POST routes
  (custom_route handlers vs mounting a Starlette sub-app on
  `streamable_http_app()`), confirmed against the pinned `mcp` version.
- Whether `/api/run` for the curated gallery should run on page load or only on
  click (default: on click, to bound cold-start cost).
- Front-end build: plain static files vs a tiny build step to inline
  `showcase.json` (reuse `scripts/build_demo.py` pattern).
