# shebanq-mcp

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20625355-1682D4.svg)](https://doi.org/10.5281/zenodo.20625355)

Ask the Hebrew Bible a linguistic question in plain language and get back two
things together: the **MQL query** and the **results**. An LLM drafts the query,
a local [Emdros](https://github.com/emdros/emdros) engine runs it against the
[BHSA](https://github.com/ETCBC/bhsa) database (the same data behind
[SHEBANQ](https://shebanq.ancient-data.org/)), and the server returns both. The
query is always shown, so it stays the thing you read, verify, and cite.

This is an [MCP](https://modelcontextprotocol.io/) server: it plugs into clients
like Claude as a set of tools.

> **Status: early.** The core server is built and unit-tested. The Emdros
> execution path is implemented but exercised only where a built BHSA database
> is present (those tests skip otherwise). The deploy path is built and proven
> in CI: a Docker image bakes Emdros plus the BHSA database, and a smoke
> workflow runs `run_mql` over MCP on every push. A live read-only instance runs
> on Render (see [Use it in Claude Desktop](#use-it-in-claude-desktop)). The demo
> web app is still future work. Feedback welcome, especially from people who
> teach or use MQL.

## Try it (live demo)

A hosted page where you ask in plain language and watch the query run:
**https://shebanq-web.onrender.com**

Type a question and click **Translate to MQL** to see the generated query.
Review or edit it, then **Run query** against the live BHSA engine. References
are on by default, so each hit shows its `book chapter:verse`; untick "Include
the reference (book chapter:verse)" for a plainer query. The worked examples run
live too. It is read-only. Hosted on a free instance, so the first request after
an idle spell can take up to a minute while the server wakes. The
auto-translation (Anthropic's Claude) is capped by a monthly budget.

## Use it in Claude Desktop

The server is hosted as a remote MCP endpoint. You do not install Emdros or the
BHSA database. Point your client at the URL and ask questions in plain language.
It is a **read-only** query engine: you can search the data, you cannot modify
it.

Endpoint: `https://shebanq-mcp.onrender.com/mcp`

> Runs on a free Render instance, so it spins down when idle. The first request
> after a quiet spell may take a few seconds to wake.

**Option A: Custom Connector** (Claude.ai and supported clients)

Settings → Connectors → Add custom connector → name it `shebanq` → paste the
`/mcp` URL. This requires a Claude plan that supports custom connectors. Some
clients expect OAuth, which this open server does not implement. If yours refuses
to connect, use Option B.

**Option B: `mcp-remote` bridge** (any client that loads local servers)

Requires Node so that `npx` is available. Edit `claude_desktop_config.json`
(Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "shebanq": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://shebanq-mcp.onrender.com/mcp"]
    }
  }
}
```

Then restart Claude Desktop.

**What you get**

Ask in plain language. Your client's own model writes a read-only MQL query and
calls `run_mql`; you see the query and the real results. The server guides the
model: tool descriptions carry the quoting rules, `search_bhsa` returns a
concise primer, and a `write-mql` prompt provides the full feature reference on
demand.

## Why

Querying BHSA today means knowing MQL, the BHSA feature vocabulary, and the
SHEBANQ interface. Generative AI can draft a query from a plain-language
question, which raises a real worry for scholarship and teaching: if a machine
writes the query, does the scholar still learn anything?

This tool takes a position on that question. The translation was never the whole
of the work. The scholarly act is judging whether a query faithfully captures a
form-to-function question, reading what a result does and does not show, and
catching a query that quietly asks the wrong thing. So the design keeps the
query visible and central rather than hiding it:

- **The query is the product, not the answer.** Every result carries the exact
  MQL that produced it. It is reproducible and pastes straight into SHEBANQ to
  save, share, and cite. Nothing comes back as a black box.
- **Validation before execution.** A query is checked against the BHSA feature
  catalogue first, so a wrong code like `vs=niphal` (the correct code is
  `vs=nif`) fails loudly instead of silently returning zero.
- **Honest empty results.** Zero matches returns the query and a clear "0
  results", so you can tell "the query is wrong" from "the phenomenon is not
  there".

AI as a way in, not a way around.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_bhsa(question)` | Plain-language question to generated MQL plus results |
| `run_mql(mql)` | Validate and run MQL you already have |
| `lookup_feature(name_or_term)` | A BHSA feature's gloss and valid values |

`run_mql` and `lookup_feature` need no LLM. `search_bhsa` drafts the query with
an LLM, with the feature catalogue injected into the prompt.

### LLM provider

Translation is isolated behind a `Translator` interface, so the provider is
swappable. Select it with the `LLM_PROVIDER` environment variable:

- `anthropic` (default) — drafts MQL with the Anthropic API. Needs
  `ANTHROPIC_API_KEY`.
- `none` — runs translation-free. `search_bhsa` is disabled and returns an error
  pointing you at `run_mql`. Use this inside an MCP client (Claude can draft the
  query itself and call `run_mql`), so the server makes no external calls and
  needs no key.

Adding another provider (OpenAI, a local model) is a small adapter: a class with
a `translate()` method plus a branch in `build_translator()`. Query quality
varies by model, so use the featured-search regression set to measure any given
model's reliability.

## How it works

```
question
  -> LLM drafts MQL (guided by the feature catalogue)
  -> validator (reject unknown features/values; reject unparseable MQL)
  -> Emdros runner (execute on the local BHSA SQLite database)
  -> formatter (verse references, Hebrew, glosses)
  -> { mql, result_count, results }
```

Four small, independently testable units: a static feature reference, a
validator, an Emdros runner, and a formatter, wired together behind the MCP
tools. See [`docs/specs`](docs/specs) for the design and
[`docs/superpowers/plans`](docs/superpowers/plans) for the implementation plan.

## Setup

1. Install [Emdros](https://github.com/emdros/emdros) (provides the `mql` CLI and the
   `emdros` Python binding).
2. Build the database (see [Data](#data)).
3. `pip install -e ".[dev]"` (Python 3.10+).
4. Choose an LLM provider (see [LLM provider](#llm-provider)). For the default,
   set `ANTHROPIC_API_KEY`; or set `LLM_PROVIDER=none` to run translation-free.
5. Run: `BHSA_SQLITE=data/bhsa.sqlite3 shebanq-mcp`

## Data

BHSA version: **2021** (pinned). Download the MQL dump from the
[ETCBC/bhsa](https://github.com/ETCBC/bhsa) release assets to `data/bhsa.mql`,
then build the read-only SQLite database:

```bash
mql --backend sqlite3 -d data/bhsa.sqlite3 data/bhsa.mql
```

Data files are gitignored and never committed.

## Tests

```bash
pytest -q                                   # unit tests, no database needed
BHSA_SQLITE=data/bhsa.sqlite3 pytest -m emdros   # database-backed tests
```

Emdros-backed tests skip cleanly when the binding or database is absent. After
building the database, confirm the Emdros Python API and pin the
featured-search counts:

```bash
python scripts/spike_emdros.py data/bhsa.sqlite3
```

then fill in the `expected_count` values in
[`tests/fixtures/featured_searches.json`](tests/fixtures/featured_searches.json)
from real runs. Those fixtures are the regression backbone and, later, the demo
gallery content.

## Roadmap

- [x] Core MCP server: feature reference, validator, Emdros runner, formatter,
      three tools
- [x] Pin featured-search counts against a built BHSA database
- [x] Live web demo: free-form question to MQL to results, with the query shown
      and editable
- [x] Deploy tooling: Docker image, Render blueprint, CI smoke (Emdros-on-SQLite,
      data baked in)
- [x] Live deploy on Render (MCP endpoint + web demo), connectable from Claude
      Desktop and other MCP clients
- [x] Verse references in results: each hit shows `book chapter:verse` (opt-in,
      default on; the server nests the word query inside its verse)
- [ ] Full feature-catalogue generation from the ETCBC feature docs

## Deploy

Two Render services run from the same image (`Dockerfile`, declared in
`render.yaml`), distinguished by environment:

- **`shebanq-mcp`** — the public MCP endpoint. `LLM_PROVIDER=none`, no API key.
- **`shebanq-web`** — the live demo. Same image with `WEB_API=on` and an
  Anthropic key, serving the page plus `/api/translate` (question to MQL),
  `/api/run` (run an MQL), and `/api/ask` (one-shot translate+run) same-origin.

**What the image does**

The build stage compiles Emdros (`rel-3-9-0`) from source and builds the BHSA
SQLite database from a pinned ETCBC commit. The runtime stage is slim and
non-root, with the database mounted read-only. Nothing else ships.

**No LLM key required**

The server runs with `LLM_PROVIDER=none`. The client model drafts MQL; the
server only validates and executes. The validator rejects any non-read-only MQL
before it reaches Emdros.

**Health check**

A startup self-test backs the `/health` endpoint. If the database is missing or
broken, the deploy fails loudly rather than serving errors silently.

**Guardrails**

`QUERY_TIMEOUT_SECONDS` and `MAX_CONCURRENT_QUERIES` hard-kill runaway queries
and bound memory. They are declared in `render.yaml`.

**CI smoke test**

The `docker-smoke` workflow builds the image and verifies multiple queries plus
mutation rejection on every push.

**Instance lifecycle**

Measured cold start is about 2.2 seconds (container boot plus the first query),
and peak memory about 154 MiB under two concurrent queries. The blueprint runs on
Render's free tier, which spins the service down when idle and cold-starts it on
the next request; the fast boot keeps that tolerable for a low-traffic,
pre-feedback deployment. Switch `plan: free` to `plan: starter` in `render.yaml`
for an always-on instance with an instant first response.

## Credits

Built on the work of the [Eep Talstra Centre for Bible and Computer
(ETCBC)](https://vu.nl/en/about-vu/faculties/school-of-religion-and-theology/more-about/eep-talstra-centre-for-bible-and-computer): the BHSA dataset, SHEBANQ, and the Emdros query
engine. This project wraps that work; it does not replace it.

## Citation

If you use this software, please cite it via its DOI:

> Fresco Benaim, Jose. (2026). *shebanq-mcp: a Model Context Protocol server for
> querying the BHSA Hebrew Bible in plain language* (v0.1.1). Zenodo.
> https://doi.org/10.5281/zenodo.20625355

A machine-readable `CITATION.cff` is in the repository, and GitHub's "Cite this
repository" button reads it. Please also cite the underlying work: the BHSA
dataset (ETCBC), the Emdros engine (Petersen 2004), and SHEBANQ.

## License

[MIT](LICENSE). The BHSA data is licensed separately by the ETCBC and is not
included in this repository.
