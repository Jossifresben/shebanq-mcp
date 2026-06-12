# shebanq-mcp

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20625355-1682D4.svg)](https://doi.org/10.5281/zenodo.20625355)

Ask the Hebrew Bible a linguistic question in plain language and get back two
things together: a citable query in two languages (an Emdros MQL query and a
[Text-Fabric](https://github.com/annotation/text-fabric) search template), plus
the **real results**. The server has a built-in NL→MQL translator: it takes your
question, drafts a query using the BHSA feature catalogue, validates it, runs it
against one of the two engines on the [BHSA](https://github.com/ETCBC/bhsa)
database (the same data behind [SHEBANQ](https://shebanq.ancient-data.org/)),
and returns both. The query is always shown, validated before it runs, and empty
results are honest.

This is an [MCP](https://modelcontextprotocol.io/) server: it plugs into clients
like Claude as a set of tools.

> **Status: early, but live.** The server is built, unit-tested, and deployed:
> a public read-only MCP endpoint and a [web app](https://shebanq-web.onrender.com)
> both run on Render, each with server-side NL→MQL translation. A Docker image
> bakes Emdros plus the BHSA database; a CI smoke workflow runs `run_mql` over MCP
> on every push, and the MQL curriculum's example counts are pinned against the
> real engine. Feedback welcome, especially from people who teach or use MQL.

## Try it (live demo)

A hosted page where you ask in plain language and watch the query run:
**https://shebanq-web.onrender.com**

Type a question and click **Translate to MQL** to see the generated query.
Review or edit it, then **Run query** against the live BHSA engine. References
are on by default, so each hit shows its `book chapter:verse`; untick "Include
the reference (book chapter:verse)" for a plainer query. The worked examples run
live too. It is read-only, and the auto-translation is capped by a monthly budget.

## Use it in Claude Desktop

The server is hosted as a remote MCP endpoint. You do not install Emdros or the
BHSA database. Point your client at the URL and ask questions in plain language.
It is a **read-only** query engine: you can search the data, you cannot modify
it.

Endpoint: `https://shebanq-mcp.onrender.com/mcp`

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

Ask in plain language. `search_bhsa` translates server-side: the server prompts
the configured model (`LLM_MODEL`) with an engine-verified MQL curriculum and the
BHSA feature catalogue, validates the generated query for object-type correctness,
runs it against the local BHSA database, and returns the MQL plus results. No
dependency on your client's own model to write MQL. `run_mql`, `run_tf`,
`to_citable_mql`, and `lookup_feature` are also available if you want to work
with queries directly.

### How translation works

When you call `search_bhsa`, the server prompts the configured model (`LLM_MODEL`)
with two things: an engine-verified MQL curriculum (the primer, covering nesting,
sequence and adjacency, FOCUS, quoting rules, and verse references) and the BHSA
feature catalogue scoped per object type. Before the query runs, the
validator checks object-type correctness: a wrong-level query fails loudly with
a clear error rather than silently returning zero results. Honest counts come
back every time: zero matches returns the query and a plain "0 results" so you
can tell "the query is wrong" from "the phenomenon is not there." The model is
configurable via the `LLM_MODEL` environment variable and bounded by a monthly
spend cap.

**Example prompts**

Ask the way you would ask a colleague:

- "How many Niphal verbs are in the Hebrew Bible?"
- "Where does the verb בָּרָא (bara, to create) occur? Show me the first few."
- "Find feminine plural nouns and give me ten examples."
- "Show me every imperative in Genesis 1."
- "Find ellipsis clauses that start with a conjunction and an object." (Returns a
  nested clause/phrase MQL query with real results; clause-level and phrase-level
  questions work.)
- "Which words carry a third person masculine singular pronominal suffix?" (Uses
  the word-morphology features `prs_ps`/`prs_gn`/`prs_nu`.)

**Getting the verse for each hit.** A word does not carry its own location;
that lives on the verse around it. So to see where each match occurs, ask for
the book, chapter, and verse, and the model nests the word query inside its
verse:

```
SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse
  [word lex='BR>[' GET g_word_utf8, gloss]] GO
```

The plain `[word lex='BR>[' GET g_word_utf8, gloss]` returns the words alone;
wrapping it in `[verse GET book, chapter, verse ...]` attaches `Genesis 1:1` to
each one. If results come back without locations, say "include the verse
references" and the model will re-nest the query. (The web app does this
wrapping for you when the reference box is ticked.)

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

## Two query languages, one answer

`search_bhsa` drafts an Emdros MQL query (one model call) and derives the
Text-Fabric equivalent from it by deterministic code, no second model call.
Row-level equivalence is proven in CI on every push: the derived template
returns the same result rows on Text-Fabric as the source MQL does on Emdros.
`run_tf` executes a template directly, the way `run_mql` executes a query.
Both engines are pinned to BHSA 2021.

It also works the other way round. `to_citable_mql` converts a Text-Fabric
template into the equivalent MQL, with no model involved, so a query from a
research notebook can become a saved SHEBANQ query with a citable permalink.
`to_tf_template` is its mirror, MQL in and template out, and the web app's
converter modal wraps both directions behind one paste box.

The live web demo shows both languages side by side for every answer (MQL runs,
TF displayed beside it) and in the Examples gallery, with build-time derivation
so every gallery card shows the exact TF equivalent of its MQL.

The TF engine needs the optional extra: `pip install "shebanq-mcp[tf]"`. The
corpus downloads from GitHub on first use.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_bhsa(question)` | Plain-language question to generated MQL plus results |
| `run_mql(mql)` | Validate and run MQL you already have |
| `run_tf(template)` | Validate and run a Text-Fabric search template |
| `to_citable_mql(template)` | Convert a TF template to SHEBANQ-citable MQL, no model |
| `to_tf_template(mql)` | MQL to the equivalent Text-Fabric template; deterministic, no LLM |
| `lookup_feature(name_or_term)` | A BHSA feature's gloss and valid values |

`run_mql`, `run_tf`, `to_citable_mql`, `to_tf_template`, and `lookup_feature` need no LLM. `search_bhsa` drafts the query with
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

The model is set with the `LLM_MODEL` env var (default `claude-sonnet-4-6`). We
chose it with a benchmark (`scripts/eval_translator.py`): each candidate
translated the scholar-question set, and each generated query's result count was
checked against the engine-verified answer. Claude Sonnet 4.6 matched the
strongest model, Claude Opus 4.8, at 11 of 11, for about 2.3 times less cost; the
cheapest, Claude Haiku 4.5, got 8 of 11, missing the harder nested clause and
phrase queries (it dropped a verse scope, mis-built a construct chain). So Sonnet
4.6 is the default. A translation averages about **$0.022** (roughly two cents),
so the $10/month spend cap covers about 450 translations; the other tools
(`run_mql`, `run_tf`, `to_citable_mql`, `lookup_feature`) make no model calls
and cost nothing.

Adding another provider (OpenAI, a local model) is a small adapter: a class with
a `translate()` method plus a branch in `build_translator()`. Re-run the
benchmark to measure any model's count-match reliability before switching.

## How it works

![From a plain-language question to a verified MQL query: shared guidance feeds a pluggable translator (the server's built-in model or the MCP host's own), which writes an MQL query; the query is always shown, then validated read-only and for object-type correctness, then run on the Emdros engine over BHSA, returning glossed results with references.](docs/assets/pipeline.png)

*Who writes the query is a pluggable seam: the server's built-in model
(`search_bhsa`) or the MCP host's own model (`run_mql`). Either way the query is
shown, validated, and run read-only. The blue steps are where a model helps; the
rest is deterministic and checkable.*

Five small, independently testable units: a static feature reference, a
validator, an Emdros runner, a Text-Fabric runner, and a formatter, wired
together behind the MCP tools.

## Setup

1. Install [Emdros](https://github.com/emdros/emdros) (provides the `mql` CLI and
   the `emdros` Python binding). Needed for `run_mql` and the MQL execution path;
   skip if you plan to use only the TF engine.
2. Build the database (see [Data](#data)). Also Emdros-only; skip for TF-only use.
3. `pip install -e ".[dev]"` (Python 3.10+). For TF support add the extra:
   `pip install -e ".[tf,dev]"`.
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

## Feature coverage

The translation prompt and the validator are driven by a feature catalogue
(`features.json`). It exposes the high-frequency core of the BHSA feature set:
part of speech (`sp`), verbal stem and tense (`vs`, `vt`), gender, number, person
and state (`gn`, `nu`, `ps`, `st`), phrase function (`function`), clause and
phrase type (`typ`), relation (`rela`), clause kind (`kind`), lexeme (`lex`), and
gloss. As of v0.3.0 it also covers the word-level morphology layer:
pronominal-suffix agreement (`prs_ps`, `prs_gn`, `prs_nu`), phrase-dependent part
of speech (`pdp`), lexical set (`ls`), and name type (`nametype`). Each value set
was confirmed against the live ETCBC2021 engine. Together that is about a third of
the queryable features, weighted toward the ones that appear in most scholarly
queries, so the tool can now answer questions like "words with a third person
masculine singular suffix," "place-name proper nouns," or "cardinal numbers."

What it still does not expose is mostly the specialist tail: the morpheme-string
features (`prs`, `pfm`, `nme`, `vbs`, `vbe`, `uvf`), the alternate word encodings
(`g_cons`, `phono`, ketiv/qere), and frequency statistics. Generating the full
catalogue from the ETCBC feature docs is the remaining roadmap item.

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
- [x] Clause-level and phrase-level querying: engine-verified MQL curriculum
      (primer) in the translation prompt; object-type validation catches
      wrong-level queries loudly
- [x] Wider feature coverage: word-level morphology layer (pronominal-suffix
      agreement `prs_ps`/`prs_gn`/`prs_nu`, phrase-dependent part of speech `pdp`,
      lexical set `ls`, name type `nametype`), value sets engine-confirmed
- [x] Text-Fabric engine: dual-language output (MQL + TF template), `run_tf`,
      `to_citable_mql`, equivalence-tested against Emdros on BHSA 2021
- [x] v0.4.0 Rosetta display: derived TF beside every MQL, row-level equivalence
      proven in CI, citation converter, about page
- [ ] Full feature-catalogue generation from the ETCBC feature docs

## Deploy

Two Render services run from the same image (`Dockerfile`, declared in
`render.yaml`), distinguished by environment:

- **`shebanq-mcp`** — the public MCP endpoint. Server-side NL→MQL translation
  via `LLM_MODEL`; needs an API key. The validator rejects any non-read-only MQL
  before it reaches Emdros.
- **`shebanq-web`** — the live demo. Same image with `WEB_API=on` and an
  API key, serving the page plus `/api/translate` (question to MQL),
  `/api/run` (run an MQL), and `/api/ask` (one-shot translate+run) same-origin.

**What the image does**

The build stage compiles Emdros (`rel-3-9-0`) from source and builds the BHSA
SQLite database from a pinned ETCBC commit. The runtime stage is slim and
non-root, with the database mounted read-only. Nothing else ships.

**LLM key and model**

Both services translate server-side. Set `LLM_MODEL` to select which model
handles translation; set the matching API key environment variable. The validator
rejects any non-read-only MQL before it reaches Emdros, regardless of what the
model produces.

**Health check**

A startup self-test backs the `/health` endpoint. If the database is missing or
broken, the deploy fails loudly rather than serving errors silently.

**Guardrails**

`QUERY_TIMEOUT_SECONDS` and `MAX_CONCURRENT_QUERIES` hard-kill runaway queries
and bound memory. `WEB_RATE_PER_MIN` caps how many translate/run calls the web
demo accepts per minute across all users. Note: a Run on a hand-edited query
costs up to two limiter tokens (one for the run, one for the `/api/convert`
call that re-derives the TF view). All values are declared in `render.yaml`.

**CI smoke test**

The `docker-smoke` workflow builds the image and verifies multiple queries plus
mutation rejection on every push.

**Instance lifecycle**

Measured cold start is about 2.2 seconds (container boot plus the first query),
and peak memory about 154 MiB under two concurrent queries. Both services run on
Render's `starter` tier (512 MB, always-on), so there is no idle spin-down and the
first request is instant.

## Credits

Built on the work of the [Eep Talstra Centre for Bible and Computer
(ETCBC)](https://vu.nl/en/about-vu/faculties/school-of-religion-and-theology/more-about/eep-talstra-centre-for-bible-and-computer): the BHSA dataset, SHEBANQ, and the Emdros query
engine. This project wraps that work; it does not replace it.

## Citation

If you use this software, please cite it via its DOI:

> Fresco Benaim, Jose. (2026). *shebanq-mcp: a Model Context Protocol server for
> querying the BHSA Hebrew Bible in plain language* (v0.3.0). Zenodo.
> https://doi.org/10.5281/zenodo.20625355

A machine-readable `CITATION.cff` is in the repository, and GitHub's "Cite this
repository" button reads it. Please also cite the underlying work: the BHSA
dataset (ETCBC), the Emdros engine (Petersen 2004), and SHEBANQ.

## License

[MIT](LICENSE). The BHSA data is licensed separately by the ETCBC and is not
included in this repository.
