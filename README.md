# shebanq-mcp

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20625355-1682D4.svg)](https://doi.org/10.5281/zenodo.20625355)

Ask the Hebrew Bible a linguistic question in plain language and get back a real,
citable query plus the **actual results**. The server drafts an
[Emdros](https://github.com/emdros/emdros) MQL query over the
[BHSA](https://github.com/ETCBC/bhsa) (the ETCBC's linguistic database of the
Hebrew Bible, the same data behind [SHEBANQ](https://shebanq.ancient-data.org/)),
validates it against the feature catalogue, runs it, and shows you everything.
Beside the MQL it also shows the equivalent
[Text-Fabric](https://github.com/annotation/text-fabric) search template, derived
from the MQL by deterministic code. The query is always shown, validated before
it runs, and empty results are reported honestly.

This is an [MCP](https://modelcontextprotocol.io/) server: it plugs into clients
like Claude as a set of tools. It is also a hosted web app, so you can use it
with no install.

> **Status: early, but live.** A public read-only MCP endpoint and a
> [web app](https://shebanq-web.onrender.com) both run on Render with
> server-side translation. Results run on Emdros; the Text-Fabric template shown
> beside every answer is derived from the MQL, not executed on the live server.
> A CI suite executes both engines on every push and checks that they return the
> same result rows. Feedback welcome, especially from people who teach or use
> MQL or Text-Fabric.

## Try it

A hosted web app where you ask in plain language and watch the query run:
**https://shebanq-web.onrender.com**

Type a question and click **Translate to MQL**. The server drafts an MQL query
and derives its Text-Fabric equivalent; both appear in side-by-side boxes. The
MQL box is editable and runs against the live BHSA engine. The Text-Fabric box
is read-only and shows the derived template with a copy button. The **reference
checkbox** swaps both boxes between the verse-scoped and bare versions in place,
with no re-translation. If you hand-edit the MQL and run it, the Text-Fabric box
dims until the server re-derives the equivalent.

The **Examples gallery** shows pre-built searches in both languages, each with
real results; an example whose query cannot be expressed in Text-Fabric shows a
plain "no Text-Fabric equivalent" note rather than a silent omission. The
**TF → MQL converter** turns a Text-Fabric notebook template into SHEBANQ-citable
MQL, the direction a scholar needs for a citation. The **/about page** explains
what the tool is for and how it works.

The app is read-only. Translation is capped by a monthly budget.

## Use it in Claude Desktop

The server is hosted as a remote MCP endpoint. You do not install Emdros or the
BHSA database. Point your client at the URL and ask in plain language. It is a
**read-only** query engine: you can search the data, you cannot modify it.

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

Ask in plain language. `search_bhsa` translates server-side: it prompts the
configured model (`LLM_MODEL`) with an engine-verified MQL curriculum and the
BHSA feature catalogue, validates the generated query, runs it on the BHSA, and
returns the MQL, its derived Text-Fabric equivalent, and the results. No
dependency on your client's own model to write MQL. `run_mql`, `to_citable_mql`,
`to_tf_template`, and `lookup_feature` are also available if you want to work
with queries directly.

### How translation works

When you call `search_bhsa`, the server prompts the configured model with two
things: an engine-verified MQL curriculum (the primer, covering nesting,
sequence and adjacency, FOCUS, quoting rules, and verse references) and the BHSA
feature catalogue scoped per object type. Before the query runs, the validator
checks object-type correctness: a wrong-level query fails loudly with a clear
error rather than silently returning zero results. The Text-Fabric equivalent is
then derived from the validated MQL by deterministic code, with no second model
call. Honest counts come back every time: zero matches returns the query and a
plain "0 results", so you can tell "the query is wrong" from "the phenomenon is
not there". The model is set by the `LLM_MODEL` environment variable and bounded
by a monthly spend cap.

**Example prompts**

Ask the way you would ask a colleague:

- "How many Niphal verbs are in the Hebrew Bible?"
- "Where does the verb בָּרָא (bara, to create) occur? Show me the first few."
- "Find feminine plural nouns and give me ten examples."
- "Show me every imperative in Genesis 1."
- "Find ellipsis clauses that start with a conjunction and an object." (Returns a
  nested clause/phrase MQL query with real results; clause-level and
  phrase-level questions work.)
- "Which words carry a third person masculine singular pronominal suffix?" (Uses
  the word-morphology features `prs_ps`/`prs_gn`/`prs_nu`.)

**Getting the verse for each hit.** A word does not carry its own location; that
lives on the verse around it. So to see where each match occurs, ask for the
book, chapter, and verse, and the model nests the word query inside its verse:

```
SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse
  [word lex='BR>[' GET g_word_utf8, gloss]] GO
```

The plain `[word lex='BR>[' GET g_word_utf8, gloss]` returns the words alone;
wrapping it in `[verse GET book, chapter, verse ...]` attaches `Genesis 1:1` to
each one. If results come back without locations, say "include the verse
references" and the model will re-nest the query. (The web app does this
wrapping for you when the reference box is ticked.)

## Run it locally with Docker

A prebuilt image bundles Emdros and the BHSA database, so you can run the whole
thing offline with no build:

```bash
docker run --rm -p 8000:8000 -e WEB_API=on \
  ghcr.io/jossifresben/shebanq-mcp:latest
```

Open http://localhost:8000. Out of the box it is read-only and works offline:
`run_mql` and the MQL/Text-Fabric converter run with no key. To enable
plain-language translation, add your own model key:

```bash
docker run --rm -p 8000:8000 -e WEB_API=on \
  -e LLM_PROVIDER=anthropic -e ANTHROPIC_API_KEY=sk-... \
  ghcr.io/jossifresben/shebanq-mcp:latest
```

Drop `-e WEB_API=on` to run the MCP server instead of the web app. The image
bundles BHSA data under CC BY-NC 4.0 (attribution required, non-commercial use
only); see [ATTRIBUTION.md](ATTRIBUTION.md).

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
  MQL that produced it, plus the derived Text-Fabric equivalent. Both are
  reproducible: the MQL pastes straight into SHEBANQ to save, share, and cite;
  the Text-Fabric template goes into a research notebook. Nothing comes back as
  a black box.
- **Validation before execution.** A query is checked against the BHSA feature
  catalogue first, so a wrong code like `vs=niphal` (the correct code is
  `vs=nif`) fails loudly instead of silently returning zero.
- **Honest empty results.** Zero matches returns the query and a clear "0
  results", so you can tell "the query is wrong" from "the phenomenon is not
  there".

AI as a way in, not a way around.

## Two query languages, one answer

`search_bhsa` drafts an Emdros MQL query (one model call) and derives the
Text-Fabric equivalent from it by deterministic code, no second model call. The
MQL runs and returns results; the Text-Fabric template is shown beside it for
anyone who works in notebooks. The converter maps one language to the other
mechanically, so the two cannot drift apart, and CI proves on every push that
the derived template returns the **same result rows** on Text-Fabric as the
source MQL does on Emdros (down to a sibling-block case that exercises
combination multiplicity). Both engines are pinned to BHSA 2021.

It also works the other way round. `to_citable_mql` converts a Text-Fabric
template into the equivalent MQL, with no model involved, so a query written in a
research notebook can become a saved SHEBANQ query with a citable permalink.
`to_tf_template` is its mirror, MQL in and template out. The web app's
**TF → MQL converter** wraps the citation direction in one paste box.

One caution the tool enforces rather than hides: where the two languages would
mean different things, conversion is refused with the reason instead of
silently changing the query. Sibling blocks are the current example. MQL orders
them while Text-Fabric template siblings are unordered, so both converters
refuse that shape (faithful ordered conversion is on the roadmap).

The converter is pure code and runs anywhere. Actually **executing** a
Text-Fabric template (the `run_tf` tool) needs the BHSA Text-Fabric corpus
present, so it works in CI, locally with the optional extra, or on a deploy that
bakes the data in. The hosted endpoint runs Emdros and derives Text-Fabric; it
does not execute it. To run Text-Fabric yourself, install the extra:
`pip install "shebanq-mcp[tf]"` (the corpus downloads from GitHub on first use).

## Tools

| Tool | Purpose |
| --- | --- |
| `search_bhsa(question)` | Plain-language question to generated MQL, its Text-Fabric equivalent, and results |
| `run_mql(mql)` | Validate and run MQL you already have |
| `to_citable_mql(template)` | Convert a Text-Fabric template to SHEBANQ-citable MQL; deterministic, no model |
| `to_tf_template(mql)` | Convert MQL to the equivalent Text-Fabric template; deterministic, no model |
| `run_tf(template)` | Validate and run a Text-Fabric template (needs the BHSA TF corpus; not active on the hosted endpoint) |
| `lookup_feature(name_or_term)` | A BHSA feature's gloss and valid values |

Only `search_bhsa` calls a model. Every other tool, including both converters,
is deterministic and makes no external calls.

### LLM provider

Translation is isolated behind a `Translator` interface, so the provider is
swappable. Select it with the `LLM_PROVIDER` environment variable:

- `anthropic` (default): drafts MQL with the Anthropic API. Needs
  `ANTHROPIC_API_KEY`.
- `none`: runs translation-free. `search_bhsa` is disabled and returns an error
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
so the $10/month spend cap covers about 450 translations; every other tool makes
no model calls and costs nothing.

Adding another provider (OpenAI, a local model) is a small adapter: a class with
a `translate()` method plus a branch in `build_translator()`. Re-run the
benchmark to measure any model's count-match reliability before switching.

## How it works

![From a plain-language question to a verified MQL query: shared guidance feeds a pluggable translator (the server's built-in model or the MCP host's own), which writes an MQL query; the query is always shown, then validated read-only and for object-type correctness, then run on the Emdros engine over BHSA, returning glossed results with references.](docs/assets/pipeline.png)

*Who writes the query is a pluggable seam: the server's built-in model
(`search_bhsa`) or the MCP host's own model (`run_mql`). Either way the query is
shown, validated, and run read-only on Emdros. The blue steps are where a model
helps; the rest is deterministic and checkable. The diagram predates the
Text-Fabric layer: after validation the server now also derives the query's
Text-Fabric equivalent, again by deterministic code.*

The code is a handful of small, independently testable units: a static feature
reference, the MQL validator and the Text-Fabric template validator, the two
converters (`mql_to_tf` and `tf_to_mql`), an Emdros runner, a Text-Fabric runner,
and a formatter, wired together behind the MCP tools.

## Setup

For development you mostly need the package and its dev extras. Emdros and the
BHSA Text-Fabric corpus are only needed to execute queries, not to work on the
pure-Python parts (translation, validation, conversion, the web routes).

1. `pip install -e ".[dev]"` (Python 3.10+).
2. To execute MQL, install [Emdros](https://github.com/emdros/emdros) (it
   provides the `mql` CLI and the `emdros` Python binding) and build the
   database (see [Data](#data)).
3. To execute Text-Fabric templates, add the extra: `pip install -e ".[tf,dev]"`.
   The BHSA 2021 corpus downloads from GitHub on first use.
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

Most of the suite is pure Python and runs anywhere, with no database or corpus:

```bash
pip install -e ".[dev]"
pytest -q
```

That covers the validators, both converters, the dispatch layer, the translator
prompt assembly, the formatter, and the web routes (about 250 tests). The
data-backed tests below skip cleanly when their data is absent, so `pytest -q`
stays green on a plain checkout.

Two kinds of test need real data and run in CI, not on a typical laptop:

- **Emdros-backed** (`-m emdros`): pinned counts and MQL execution against a
  built BHSA SQLite database. Run locally with
  `BHSA_SQLITE=data/bhsa.sqlite3 pytest -m emdros` if you have the database.
- **Text-Fabric and cross-engine equivalence** (`-m tf`): these download the
  BHSA 2021 Text-Fabric corpus and execute it. The cross-engine tests run the
  same query on both engines and assert the full result-row sets match,
  including a sibling-block case that exercises combination multiplicity. This
  is what backs the "same results" claim. Run them locally with
  `pip install -e ".[tf]"` plus the one-time corpus download.

CI runs all of this on every push: the `emdros-tests` workflow builds Emdros and
the BHSA database, installs Text-Fabric and the corpus, and runs the Emdros,
Text-Fabric, and equivalence tests; `docker-smoke` builds the deploy image and
exercises the live routes (including `/about`, the share image, and the
converter).

After building the database you can confirm the Emdros Python API and pin the
featured-search counts:

```bash
python scripts/spike_emdros.py data/bhsa.sqlite3
```

then fill in the `expected_count` values in
[`tests/fixtures/featured_searches.json`](tests/fixtures/featured_searches.json)
from real runs. Those fixtures are the regression backbone and the gallery
content source.

## Feature coverage

The translation prompt and the validator are driven by a feature catalogue
(`features.json`). It exposes the high-frequency core of the BHSA feature set:
part of speech (`sp`), verbal stem and tense (`vs`, `vt`), gender, number, person
and state (`gn`, `nu`, `ps`, `st`), phrase function (`function`), clause and
phrase type (`typ`), relation (`rela`), clause kind (`kind`), lexeme (`lex`), and
gloss. It also covers the word-level morphology layer: pronominal-suffix
agreement (`prs_ps`, `prs_gn`, `prs_nu`), phrase-dependent part of speech
(`pdp`), lexical set (`ls`), and name type (`nametype`). Each value set was
confirmed against the live ETCBC2021 engine. Together that is about a third of
the queryable features, weighted toward the ones that appear in most scholarly
queries, so the tool can answer questions like "words with a third person
masculine singular suffix", "place-name proper nouns", or "cardinal numbers".

What it still does not expose is mostly the specialist tail: the morpheme-string
features (`prs`, `pfm`, `nme`, `vbs`, `vbe`, `uvf`), the alternate word encodings
(`g_cons`, `phono`, ketiv/qere), and frequency statistics. Generating the full
catalogue from the ETCBC feature docs is a roadmap item.

## Roadmap

- [x] Core MCP server: feature reference, validator, Emdros runner, formatter,
      three tools
- [x] Pin featured-search counts against a built BHSA database
- [x] Web app: free-form question to MQL to results, with the query shown and
      editable
- [x] Deploy tooling: Docker image, Render blueprint, CI smoke (Emdros-on-SQLite,
      data baked in)
- [x] Live deploy on Render (MCP endpoint + web app), connectable from Claude
      Desktop and other MCP clients
- [x] Verse references in results: each hit shows `book chapter:verse` (opt-in,
      default on; the server nests the word query inside its verse)
- [x] Clause-level and phrase-level querying: engine-verified MQL curriculum
      (primer) in the translation prompt; object-type validation catches
      wrong-level queries loudly
- [x] Word-level morphology layer: pronominal-suffix agreement
      (`prs_ps`/`prs_gn`/`prs_nu`), phrase-dependent part of speech (`pdp`),
      lexical set (`ls`), name type (`nametype`), value sets engine-confirmed
- [x] Two query languages: every answer shows the MQL and its derived
      Text-Fabric equivalent; `to_citable_mql` and `to_tf_template` converters;
      cross-engine row-level equivalence proven in CI; the web app shows both
      languages and an about page
- [ ] Ordered sibling-block conversion via Text-Fabric relational operators.
      MQL sibling blocks are ordered while Text-Fabric template siblings are not
      (measured: 25827 vs 46968 rows on the same query shape), so both
      converters currently refuse the shape rather than change its meaning
- [ ] Per-feature provenance notes ("what this query assumes"): surface the
      encoding caveats at answer time (gender is word-level form, gloss is the
      lexeme gloss), so a valid-but-wrong-question query is caught, not cited
- [ ] Full feature-catalogue generation from the ETCBC feature docs

## Deploy

Two Render services run from the same image (`Dockerfile`, declared in
`render.yaml`), distinguished by environment:

- **`shebanq-mcp`**: the public MCP endpoint. Server-side translation via
  `LLM_MODEL`; needs an API key. The validator rejects any non-read-only MQL
  before it reaches Emdros.
- **`shebanq-web`**: the web app. Same image with `WEB_API=on` and an API key,
  serving the page plus `/api/translate` (question to MQL), `/api/run` (run an
  MQL), `/api/ask` (one-shot translate and run), and `/api/convert`
  (bidirectional MQL/Text-Fabric conversion, pure code) same-origin.

**Engine.** Both services set `BHSA_RESULT_ENGINE=emdros`. The image bakes the
BHSA SQLite database but not the Text-Fabric corpus, so results run on Emdros and
the Text-Fabric template is derived, not executed. A future deploy that bakes the
corpus in could flip the results engine to Text-Fabric.

**What the image does.** The build stage compiles Emdros (`rel-3-9-0`) from
source and builds the BHSA SQLite database from a pinned ETCBC commit. The
runtime stage is slim and non-root, with the database mounted read-only, the web
pages and share image copied in, and nothing else.

**Health check.** A startup self-test backs the `/health` endpoint. If the
database is missing or broken, the deploy fails loudly rather than serving errors
silently.

**Guardrails.** `QUERY_TIMEOUT_SECONDS` and `MAX_CONCURRENT_QUERIES` hard-kill
runaway queries and bound memory. `WEB_RATE_PER_MIN` caps how many translate and
run calls the web app accepts per minute across all users. A Run on a
hand-edited query costs up to two limiter tokens (one for the run, one for the
`/api/convert` call that re-derives the Text-Fabric view). All values are
declared in `render.yaml`.

**CI smoke test.** The `docker-smoke` workflow builds the image and verifies
multiple queries, mutation rejection, the converter, the about page, and the
share image on every push.

**Instance lifecycle.** Measured cold start is about 2.2 seconds (container boot
plus the first query), and peak memory about 154 MiB under two concurrent
queries. Both services run on Render's `starter` tier (512 MB, always-on), so
there is no idle spin-down and the first request is instant.

## Credits

Built on the work of the [Eep Talstra Centre for Bible and Computer
(ETCBC)](https://vu.nl/en/about-vu/faculties/school-of-religion-and-theology/more-about/eep-talstra-centre-for-bible-and-computer):
the BHSA dataset and SHEBANQ; the [Emdros](https://github.com/emdros/emdros)
query engine; and [Text-Fabric](https://github.com/annotation/text-fabric). This
project wraps that work; it does not replace it.

## Citation

If you use this software, please cite it via its DOI:

> Fresco Benaim, Jose. (2026). *shebanq-mcp: a Model Context Protocol server for
> querying the BHSA Hebrew Bible in plain language* (v0.4.0). Zenodo.
> https://doi.org/10.5281/zenodo.20625355

A machine-readable `CITATION.cff` is in the repository, and GitHub's "Cite this
repository" button reads it. Please also cite the underlying work: the BHSA
dataset (ETCBC), the Emdros engine (Petersen 2004), and SHEBANQ.

## License

The shebanq-mcp software is [MIT](LICENSE).

The BHSA data is the work of the ETCBC, licensed
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/): attribution
required, non-commercial use only (DOI
[10.17026/dans-z6y-skyh](https://doi.org/10.17026/dans-z6y-skyh)). The source
repository does not include the data; the published container image bundles it
under those terms. See [ATTRIBUTION.md](ATTRIBUTION.md) for the full notice.
