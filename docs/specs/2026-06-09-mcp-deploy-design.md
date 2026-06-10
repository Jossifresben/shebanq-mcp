# Deploy the shebanq MCP server — design

**Date:** 2026-06-09
**Status:** revised after adversarial review (read-only safety added, health
check hardened, reproducibility pinned, guardrail corrected, lifecycle deferred
to measurement). Pending plan execution.
**Scope:** Sub-project 1 of 2 (deploy the MCP). The demo web app is a separate
spec/plan that depends on this endpoint.

## Goal

Stand up a single **public remote MCP endpoint** for the existing shebanq-mcp
server, reachable at a stable HTTPS URL on Render. Any MCP client (Claude
Desktop, the future demo web app, any other host) connects by URL. The endpoint
is a **read-only, pure query engine**: no LLM, no API key, no per-request cost,
and no way for a caller to mutate the database.

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

**Adoption-friction caveat (honest):** the direct-MCP path is not as frictionless
as "paste a URL." Native custom connectors are gated behind paid Claude plans and
may expect OAuth this server does not implement; the `mcp-remote` fallback
requires editing a JSON config and installing Node. The README must state these
requirements plainly rather than imply one-click setup. Many scholars will in
practice reach the engine through the web app (sub-project 2); the direct-MCP
path primarily serves power users.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **Read-only safety** | Validator allowlists read-only MQL **and** the DB is opened/served read-only (non-root, file `chmod 444`) | An open, unauthenticated, arbitrary-MQL endpoint must not be able to mutate or drop the database. Defense in depth: clean rejection at validation, hard stop at the filesystem. |
| LLM seam | `LLM_PROVIDER=none` on the deploy | Pure engine. No API key or per-request cost on a public endpoint; fully LLM-agnostic; faithful to "trust is the product." Scholars' own host model translates; the web app's own backend will translate (its concern, not this deploy's). |
| Transport | Both stdio + streamable-HTTP, selected by `MCP_TRANSPORT` | One server, one branch in `main()`. Hosted URL serves everyone; stdio stays for local power users and the existing test harness. |
| DB in image | Built in the image (multi-stage) from a **pinned** ETCBC commit | Self-contained; matches the trusted CI recipe. Pinning the dump source (not `master`) is what makes "reproducible" true and keeps the smoke-test counts stable. |
| Instance lifecycle | **Decide after measuring** cold-start time | Pre-feedback, niche, mostly-idle service. Build lifecycle-agnostic; measure real cold-start on the built image; then choose smallest-always-on (instant, modest fixed cost) vs scale-to-zero (cost-first, cold-start latency + client-timeout risk). |
| Protection | Open + read-only + bounded resources | No auth/token friction. Read-only removes the data-integrity threat. A per-query timeout (with hard kill) and a concurrency cap bound CPU/RAM. IP rate-limiting is deferred (see Known limitations) — explicitly, not hand-waved. |

## Read-only safety (critical)

The endpoint accepts arbitrary MQL from anonymous callers. MQL is not
SELECT-only: it includes `CREATE`, `DROP`, `UPDATE OBJECTS … SET`, `DELETE`, etc.
The current `validate_mql` only checks feature **quoting**; a statement with no
`name=value` constraints (e.g. `DROP DATABASE '…' GO`) passes validation clean
and reaches `env.executeString`. The runner opens SQLite writable. Without a fix,
a stranger could destroy the database for everyone. This is the single most
important change in this spec.

Three independent backstops:

1. **Validator read-only allowlist.** `validate_mql` rejects any query that is
   not a read-only statement. Implementation: strip string literals (so a
   keyword inside `lex='…'` cannot trip it), then reject if any mutating verb
   appears (`CREATE`, `DROP`, `UPDATE`, `DELETE`, `INSERT`, `ALTER`, `REPLACE`,
   `VACUUM`, `ATTACH`, `DETACH`, `PRAGMA`, `BEGIN`, `COMMIT`, `ROLLBACK`), and
   require the first significant keyword to be a read verb (`SELECT` or `GET`).
2. **Read-only filesystem.** The container runs as a **non-root** user; the
   `bhsa.sqlite3` file is `chmod 444` and its directory is not writable by that
   user. Even if a mutating query slipped past validation, the OS denies the
   write. (Verify Emdros can still open a read-only SQLite file for queries;
   SELECT-only reads need no journal. If Emdros insists on a writable handle,
   fall back to mounting the DB read-only via a copy the user cannot write.)
3. **Ephemeral image.** The DB is baked into the image, so any mutation that
   somehow lands is wiped on the next container start — a last-resort, not a
   substitute for 1 and 2.

This is verified by tests (mutating MQL is rejected) and by a CI check that a
mutating call against the running container does not change a known count.

## Instance lifecycle & cold start

Deferred to measurement, but scoped now so the build is lifecycle-agnostic.

- **Always-on (smallest viable):** no cold start; instant first response, which
  protects the "trust is the product" first impression. Modest fixed monthly
  cost. Lowest risk.
- **Scale-to-zero (cost-first):** spins down when idle, cold-starts on first
  request. The image is heavy (Emdros + baked BHSA SQLite), so cold start is
  process boot + first `EmdrosEnv` open ≈ seconds to ~30s once the image is
  pulled. **MCP-specific risk:** a client's `initialize` or first tool call may
  time out during cold start — a bad first impression. **Render caveat:** verify
  Render actually offers scale-to-zero for our paid Docker service (free
  instances spin down after idle; paid are generally always-on). If Render
  cannot, the cost-first path means the free tier or a different host (Cloud Run
  / Fly auto-stop) running the same image.

**Plan obligation:** a task measures cold-start wall-clock on the built image and
checks whether a representative MCP client tolerates it, then this section is
updated with the numbers and the lifecycle choice. `render.yaml` is written to
make the choice a one-line flip.

### Measured (docker-smoke CI, 2026-06-09)

- **Cold start:** ~2.2s, container start to first `200` from `/health` (which
  includes the real self-test query). Small enough that an MCP client's
  `initialize` will not time out, so scale-to-zero is technically viable.
- **Peak memory:** ~154 MiB under 2 concurrent queries (≈75 MiB per live Emdros
  env over a small base). The `standard` (2 GB) plan was wildly oversized.

**Decision:** `render.yaml` set to `starter` (512 MB, ~3x headroom at
`MAX_CONCURRENT_QUERIES=2`), **always-on** for an instant first impression. The
fixed cost at this size is small, and always-on removes the only UX risk of the
cost-first path. Scale-to-zero stays a one-line option if cost ever matters more
than the ~2s first-call latency. (Whether Render offers true paid scale-to-zero
is still unverified; the always-on choice sidesteps that question.) The final
deploy + plan selection is the owner's call, since it involves a Render account
and billing.

## Behavior of the three tools on the deploy

- `lookup_feature` — unchanged; works.
- `run_mql` — validate (now including the read-only allowlist) → run on Emdros →
  glossed results. The workhorse. Rejects mutating MQL with a clear error.
- `search_bhsa` — with no translator configured (`LLM_PROVIDER=none`), returns a
  **concise** MQL-writing primer: the quoting rules, a pointer to
  `lookup_feature` for specific features, and a pointer to the `write-mql` prompt
  for the full reference. (It does **not** dump the entire 237-constant reference
  on every call — that lives in the `write-mql` prompt, invoked deliberately.)

## MQL-writing guidance for client models

On the deploy the client's own model writes the MQL. It will not know the BHSA
features or the critical quoting rule (enums UNQUOTED `vs=nif`; strings QUOTED
`lex='BR>['`; verb lexemes carry a trailing `[`) unless we hand it that
knowledge through the MCP surface. README prose only helps the human; the model
needs it through the protocol.

Three delivery mechanisms:

1. **Enriched tool descriptions** — `run_mql` and `search_bhsa` docstrings state
   the quoting rule and tell the model to call `lookup_feature`. Models read tool
   descriptions automatically.
2. **`search_bhsa` concise primer response** — the no-translator path returns the
   short primer above instead of a dead-end error.
3. **`write-mql` MCP Prompt** — a Prompts-primitive template the scholar invokes
   explicitly; returns the **full** reference (`translate.build_prompt`) + the
   question + "write the MQL, then call run_mql." This is the one place the heavy
   reference is emitted, and only on demand.

These are server-wide (stdio and HTTP), not deploy-only.

## Architecture

### Transport selection (`server.py`)

`main()` reads `MCP_TRANSPORT` (default `stdio`):
- `stdio` → `mcp.run()` (unchanged behavior; local/dev/test).
- `http` → streamable-HTTP bound to `0.0.0.0:$PORT` (Render supplies `PORT`).

**FastMCP API confidence:** the exact shapes of `mcp.settings.host/port`,
`@mcp.custom_route`, `@mcp.prompt`, and `mcp.run(transport="streamable-http")`
are pinned by a **first task** that installs a specific `mcp` version and prints
the real APIs, so later tasks code against confirmed signatures, not guesses.

### Health check (must be able to go red)

`/health` reports a **startup self-test**, not a static OK. At boot in `http`
mode the server runs one real read-only query against the baked DB; if it fails
(DB missing/corrupt, Emdros won't load), the process exits non-zero so the deploy
is marked failed instead of "healthy but broken." `/health` returns 200 only
after the self-test passed, 503 otherwise. The per-poll cost is nil (it reports a
cached boot result, it does not re-query on every poll).

### Configuration (env)

| Var | Purpose | Deploy value |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` or `http` | `http` |
| `BHSA_SQLITE` | path to the baked, read-only DB | `/app/data/bhsa.sqlite3` |
| `LLM_PROVIDER` | translation provider | `none` |
| `PORT` | bind port (Render-supplied) | (Render) |
| `QUERY_TIMEOUT_SECONDS` | per-query wall-clock limit (hard kill) | tuned during impl |
| `MAX_CONCURRENT_QUERIES` | simultaneous Emdros executions (memory bound) | tuned during impl |

`BHSA_REF` (a pinned ETCBC commit/tag) is a **build arg** of the image, not a
runtime env.

### Image (multi-stage Dockerfile)

- **Build stage:** the CI recipe. Build Emdros `rel-3-9-0` from source (SQLite
  backend + Python3 bindings; GUI/`doc` stripped, `pdflatex` stubbed). Download
  the ETCBC MQL dump **at a pinned commit** (`BHSA_REF`, not `master`), build
  `bhsa.sqlite3` with the `mql` CLI, relocate the file (the dump's
  `CREATE DATABASE 'shebanq_etcbc2021'` makes `mql` write under that internal
  name, not the `-d` path).
- **Runtime stage:** slim Python base + only the Emdros runtime libs (closure via
  `ldd`) and the `EmdrosPy3` bindings, the `bhsa.sqlite3` file (`chmod 444`), and
  our installed package. Runs as a **non-root** user. A build-time
  `import EmdrosPy3` fails the build loudly if a lib is missing. No `mql` CLI and
  no build toolchain at runtime.
- `render.yaml` blueprint pins the service: Docker, an instance size chosen after
  the memory measurement, health-check path, and the env vars above.

### Guardrails (corrected)

The read-only allowlist removes the *data-integrity* threat. The remaining threat
is a **valid but expensive** query pinning CPU/RAM. Bounds:

- **Concurrency cap (`MAX_CONCURRENT_QUERIES`):** a semaphore limits simultaneous
  Emdros executions, bounding peak memory (each execution opens an `EmdrosEnv`).
- **Per-query hard timeout (`QUERY_TIMEOUT_SECONDS`):** each query runs in a
  worker **process**. On overrun the parent sends SIGTERM, waits a short grace,
  then **SIGKILL** (`proc.kill()`) — the escalation matters because a process
  pinned in Emdros's synchronous C call may not honor SIGTERM promptly. The
  client gets a clean timeout error.

**Accepted tradeoff (was a hidden contradiction before):** the worker is spawned
**per query**, not a warm pool. This costs cold-start latency per call (process
start + `EmdrosEnv` open). We accept it because traffic is low/niche and, under
scale-to-zero, per-query startup is negligible beside whole-instance cold start.
A warm pool is noted as a future optimization, not built now. (The earlier spec
claimed warm pool; the plan built per-query. This reconciles them honestly.)

This guard sits between the tool handlers and `runner.run_query`. The in-process
`run_query` path stays for stdio/local/tests; the guard is engaged in `http`
mode.

## CI / verification

- The existing `emdros-tests` workflow stays (verifies the engine, extracts
  showcase). Its dump URL is **also pinned** to `BHSA_REF` so CI and the image
  agree.
- A **Docker smoke job** builds the image and runs the container in `http` mode,
  then asserts more than one happy path:
  - `/health` returns 200.
  - `run_mql` string query: bara `lex='BR>['` → 48.
  - `run_mql` enum query: `sp=verb` → 73710.
  - `run_mql` mutating query (`DROP …` / `UPDATE …`) is **rejected** by
    validation, and a follow-up count confirms the DB is unchanged.
  - Tools and the `write-mql` prompt are listed over MCP.
- A **resource measurement** step records peak container memory under
  `MAX_CONCURRENT_QUERIES` concurrent queries (to size the instance) and the
  **cold-start wall-clock** of the container (to inform the lifecycle decision).
- Render auto-deploys from `main` via the Dockerfile.

## Documentation deliverable

Add a **"Use it in Claude Desktop"** README section with verified copy-paste
steps and the real URL, covering both the Custom Connector and the `mcp-remote`
bridge, and **stating the real requirements** (paid plan / OAuth caveat for
connectors; Node for the bridge). Include what a scholar sees after connecting,
and that `write-mql` is available for composing queries.

## Testing strategy

- Existing unit tests unchanged.
- New unit tests:
  - Validator rejects mutating MQL (`DROP`, `UPDATE`, `DELETE`, `CREATE`,
    `PRAGMA`) and accepts `SELECT`/`GET`; a mutating keyword inside a quoted
    string value does **not** trigger rejection.
  - `main()` transport selection.
  - Guard: a fake slow worker is hard-killed and yields `QueryTimeout`; a fake
    error propagates; the concurrency cap serializes.
  - Startup self-test passes/fails wiring; `/health` payload reflects readiness.
  - Concise `search_bhsa` primer; `write-mql` prompt text.
- New integration (CI, Emdros-backed): the expanded Docker smoke job + the
  read-only/mutation check + memory + cold-start measurement.
- Manual acceptance: connect the URL in Claude Desktop; call all three tools;
  attempt a mutating query and confirm it is refused.

## Success criteria

- A stable public HTTPS MCP URL.
- **The endpoint is read-only:** a mutating MQL call is rejected, and (defense in
  depth) the DB file is non-writable by the runtime user. Verified in CI.
- `/health` can actually fail: a broken DB/Emdros makes the deploy go red rather
  than green.
- Claude Desktop can call all three tools; `run_mql` returns verified counts
  (`sp=verb` 73710, bara 48); `search_bhsa` returns the concise primer.
- A runaway (valid) query is hard-killed by the timeout and does not take down
  the container; peak memory under the concurrency cap fits the chosen instance.
- The image builds **reproducibly** from a pinned ETCBC commit (no `master`).
- Cold-start time is measured and the lifecycle choice (always-on vs
  scale-to-zero) is recorded with data.
- The README has verified, honest setup steps (including real requirements).
- A client model with no prior BHSA knowledge can write correct MQL via the tool
  descriptions, the `search_bhsa` primer, and the `write-mql` prompt.

## Known limitations (explicit, not hand-waved)

- **No IP rate-limiting / connection cap.** The semaphore bounds Emdros
  execution but not pending HTTP connections; a determined flood could exhaust
  the server's threadpool. Acceptable for a niche early demo; revisit (a reverse
  proxy / Render rate limit / per-IP cap) if abused. This is a deliberate
  deferral, recorded so it is not mistaken for "handled."
- **Per-query process latency** (see Guardrails) until a warm pool is built.
- **Single instance**, no HA.

## Out of scope (deliberately)

- The demo web app and any server-side NL→MQL.
- Auth/tokens.
- Multi-instance / autoscaling beyond the lifecycle decision.
- Legacy HTTP+SSE transport (deprecated).

## Open implementation questions (resolve at plan time)

- Confirmed FastMCP APIs and the exact pinned `mcp` version (first task).
- Whether Emdros opens a read-only SQLite file cleanly, or needs a fallback.
- Whether Claude Desktop reaches the streamable-HTTP endpoint directly or via
  `mcp-remote`; document whichever works.
- Tuned `QUERY_TIMEOUT_SECONDS` / `MAX_CONCURRENT_QUERIES` and the instance size,
  from the memory measurement.
