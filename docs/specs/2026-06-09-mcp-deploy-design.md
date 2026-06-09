# Deploy the shebanq MCP server — design

**Date:** 2026-06-09
**Status:** approved design, pending implementation plan
**Scope:** Sub-project 1 of 2 (deploy the MCP). The demo web app is a separate
spec/plan that depends on this endpoint.

## Goal

Stand up a single, always-on, **public remote MCP endpoint** for the existing
shebanq-mcp server, reachable at a stable HTTPS URL on Render Pro. Any MCP client
(Claude Desktop, the future demo web app, any other host) connects by URL. The
endpoint is a **pure query engine**: no LLM, no API key, no per-request cost.

### Why remote HTTP (not the usual stdio)

stdio is the most common MCP transport, but it runs the server on the user's own
machine, which would force every scholar to build Emdros from source and build
the BHSA SQLite database locally (the painful multi-step build documented in
CLAUDE.md). Remote streamable-HTTP lets us build Emdros + bake the BHSA data
**once**, host it, and let clients point at a URL with nothing to install. That
install-avoidance is the whole reason to go remote.

## Audience

Both, equally:
- The future demo web app (an MCP-over-HTTP client).
- Scholars who add the URL to their own MCP client and use the three tools
  directly.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM seam | `LLM_PROVIDER=none` on the deploy | Pure engine. No API key or per-request cost on a public endpoint; trivial to rate-limit; fully LLM-agnostic; faithful to "trust is the product." Scholars' own host model translates; the web app's own backend will translate (its concern, not this deploy's). |
| Transport | Both stdio + streamable-HTTP, selected by `MCP_TRANSPORT` | One server, one branch in `main()`. Hosted URL serves everyone; stdio stays for local power users and the existing test harness. |
| DB in image | Built in the image (multi-stage) | Self-contained and reproducible from source; matches the CI recipe already trusted. Slower builds, but Render caches layers. |
| Protection | Open + safety guardrails | No auth/token friction for scholars. A per-query timeout and concurrency cap stop a pathological MQL from pinning the single container. |

## Behavior of the three tools on the deploy

- `lookup_feature` — unchanged; works.
- `run_mql` — unchanged: validate → run on Emdros → glossed results. The workhorse.
- `search_bhsa` — returns its existing "no translator configured, use run_mql"
  guidance (because `LLM_PROVIDER=none`). The connecting client's own model does
  NL→MQL and then calls `run_mql`.

## Architecture

### Transport selection (`server.py`)

`main()` reads `MCP_TRANSPORT` (default `stdio`):
- `stdio` → `mcp.run()` (unchanged behavior; local/dev/test).
- `http` → streamable-HTTP bound to `0.0.0.0:$PORT` (Render supplies `PORT`).

A lightweight `GET /health` route (cheap fixed query or static OK) is registered
for Render's health check.

### Configuration (env)

| Var | Purpose | Deploy value |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` or `http` | `http` |
| `BHSA_SQLITE` | path to the baked DB | `/app/data/bhsa.sqlite3` |
| `LLM_PROVIDER` | translation provider | `none` |
| `PORT` | bind port (Render-supplied) | (Render) |
| `QUERY_TIMEOUT_SECONDS` | per-query wall-clock limit | tuned during impl |
| `MAX_CONCURRENT_QUERIES` | simultaneous Emdros executions | tuned during impl |

### Image (multi-stage Dockerfile)

- **Build stage:** the CI recipe. Build Emdros `rel-3-9-0` from source (SQLite
  backend + Python3 bindings; GUI/`doc` stripped, `pdflatex` stubbed). Download
  the ETCBC MQL dump, build `bhsa.sqlite3` with the `mql` CLI, relocate the file
  (the dump's `CREATE DATABASE 'shebanq_etcbc2021'` makes `mql` write under that
  internal name, not the `-d` path).
- **Runtime stage:** slim Python base + only the Emdros shared libs and the
  `EmdrosPy3` bindings (`EmdrosPy3.py` + `_EmdrosPy3.so` from
  `/usr/local/lib/emdros`, plus the emdros `.so`s and their deps), the
  `bhsa.sqlite3` file, and our installed package. No `mql` CLI and no build
  toolchain at runtime.
- `render.yaml` blueprint pins the service: Docker, Pro plan, health-check path,
  and the env vars above (`MCP_TRANSPORT=http`, `LLM_PROVIDER=none`, etc.).

### Guardrails

- **Concurrency cap:** a small pool of warm worker processes, each holding an
  open `EmdrosEnv`. `run_mql` dispatches a query into the pool. Caps simultaneous
  Emdros executions at `MAX_CONCURRENT_QUERIES`. Warm workers avoid re-opening the
  env per query.
- **Per-query timeout:** a query exceeding `QUERY_TIMEOUT_SECONDS` causes its
  worker process to be terminated and respawned; the client gets a clean timeout
  error. Process termination is the robust way to actually interrupt Emdros's
  synchronous C call (signals/threads can't reliably cancel it), so one
  pathological MQL cannot pin the container.

This worker-pool layer sits between the tool handlers and `runner.run_query`. The
existing single-process `run_query` path stays usable for stdio/local/tests; the
pool is engaged in `http` mode.

## CI / verification

- The existing `emdros-tests` workflow stays unchanged (verifies the engine and
  extracts showcase data).
- Add a **Docker smoke job**: build the image, run the container in `http` mode,
  curl `/health`, and make one real MCP `run_mql` call asserting a known count
  (e.g. `lex='BR>['` → 48). This catches deploy-breaking changes before Render
  does.
- Render auto-deploys from the repo on push to `main` via the Dockerfile.

## Testing strategy

- Existing unit tests unchanged (run in stdio/local path).
- New unit tests:
  - `main()` transport selection: `MCP_TRANSPORT` picks the right run path
    (assert on the wiring without binding a real socket).
  - Guardrails: a slow/fake query trips the timeout and returns a clean error;
    the concurrency cap bounds simultaneous executions.
- New integration (CI, Emdros-backed): the Docker smoke job above.
- Manual acceptance: add the deployed URL to Claude Desktop as a remote
  connector; call all three tools.

## Success criteria

- A stable public HTTPS MCP URL.
- Claude Desktop (added as a remote connector) can call all three tools;
  `run_mql` returns the verified counts (e.g. `sp=verb` 73710, bara 48);
  `search_bhsa` returns its guidance message.
- A future web app can connect as an MCP-over-HTTP client.
- A runaway query is bounded by the timeout and does not take down the container.
- The image builds reproducibly from source.

## Out of scope (deliberately)

- The demo web app and any server-side NL→MQL.
- Auth/tokens.
- Autoscaling / multi-instance.
- Legacy HTTP+SSE transport (deprecated; not used).

## Open implementation questions (resolve at plan time)

- Exact FastMCP streamable-HTTP invocation and how `/health` is registered
  (custom route vs. underlying Starlette app).
- Whether Claude Desktop reaches the streamable-HTTP endpoint directly or via the
  `mcp-remote` bridge; document whichever works.
- Tuned default values for `QUERY_TIMEOUT_SECONDS` and `MAX_CONCURRENT_QUERIES`.
- Worker-pool implementation detail (e.g. `ProcessPoolExecutor` with
  terminate-on-timeout vs. a hand-rolled queue of warm workers).
