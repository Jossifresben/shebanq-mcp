# SHEBANQ MCP Server — Design

**Date:** 2026-06-08
**Status:** Approved design, pre-implementation

## Purpose

An MCP server that lets biblical-studies scholars and PhD candidates query the
BHSA Hebrew Bible (the ETCBC database behind SHEBANQ) in plain language and get
back two things together:

1. A correct, citable **MQL query**.
2. The matching **results** — glossed and verse-referenced.

Both are produced by the *same* Emdros engine that powers SHEBANQ, so the query
pastes into SHEBANQ verbatim for saving, sharing, and citation. The tool removes
the need to already know MQL while preserving everything a scholar needs to
trust, verify, reproduce, and cite a result.

### Audience

Scholars and PhD candidates who currently use MQL on SHEBANQ, or who are having
to learn MQL in order to run queries. The design optimizes for *their* trust
requirements, not for casual users.

### Why this is valuable

Today, asking the Hebrew Bible a linguistic question ("every clause where the
subject follows the verb in Genesis") requires knowing MQL, the BHSA feature
vocabulary, and the SHEBANQ interface. This tool makes the question answerable
in plain language while still returning the exact, runnable query a dissertation
or peer review demands. No existing MCP server covers SHEBANQ or BHSA as of this
writing.

## Scope

**In scope (v1):**
- Read-only querying of the Hebrew BHSA dataset.
- NL → MQL translation, validation, execution, and result formatting.
- A small, well-bounded set of MCP tools.
- A thin demo web app with curated, pre-validated featured searches.

**Out of scope (v1):**
- Text-Fabric as an execution engine.
- The SHEBANQ website itself (we link to it, we don't reimplement it).
- Write/annotation operations.
- Datasets other than the Hebrew BHSA.

## Engine decision

The execution engine is **Emdros running MQL directly**, not Text-Fabric.

Rationale: the entire value proposition rests on the query shown to the scholar
being the query that produced the results, on the same engine SHEBANQ uses. Any
design that executes on a different engine (e.g. Text-Fabric's search-template
language) and generates MQL separately reintroduces divergence risk: a reviewer
reruns the cited MQL on SHEBANQ, gets a different count, and the tool loses all
credibility. Running real Emdros/MQL collapses that risk to zero.

Install friction (the usual objection to Emdros) is mitigated by ETCBC's
`shebanq-local`, which packages Emdros + the MQL BHSA data as a runnable stack.
The server ships as a container in front of that stack rather than asking users
to build Emdros from source.

## Architecture

Four units, each independently testable, communicating through defined
interfaces.

### MCP server (front)
Exposes the MCP tools and orchestrates the pipeline. Holds no Hebrew-grammar
knowledge itself. Python, using the official `mcp` SDK.

### Feature reference
A static, versioned knowledge layer: the BHSA feature catalogue — every
queryable feature, its valid values, and a plain-English gloss (e.g. `vs` =
verbal stem; value `nif` = Niphal). This is what lets the model emit *correct*
MQL instead of guessing feature codes. Generated once from the ETCBC feature
documentation and shipped with the server. Versioned against the BHSA data
version it describes.

### MQL builder + validator
Takes a candidate MQL string and checks, before anything runs, that it parses
and references only features and values that exist in the feature reference.
Catches hallucinated features/values (e.g. `vs=niphal` instead of `vs=nif`)
loudly, rather than letting them silently return zero matches.

### Emdros runner
Executes validated MQL against the local Emdros/BHSA database and returns raw
node matches. Pure execution — no intelligence, no grammar awareness.

### Data flow
```
NL question
  → model drafts MQL (guided by feature reference)
  → validator (reject unknown features/values; reject unparseable MQL)
  → Emdros runner (execute on local BHSA)
  → results formatter (verse refs + Hebrew + glosses)
  → { mql, result_count, results[] }
```

## MCP tools

Three tools, deliberately small surface:

### `search_bhsa(question)`
The primary tool. NL question → `{ mql, result_count, results[] }`, where each
result carries a verse reference, the Hebrew text, and glosses. Internally:
draft MQL → validate → run → format.

### `run_mql(mql)`
Escape hatch for scholars who already have MQL, or who want to tweak the
generated query, and just want it validated and executed. Returns the same
result shape as `search_bhsa`.

### `lookup_feature(name_or_term)`
Queries the feature reference: "what's the code for Niphal?" → `vs=nif`; "what
values can `function` take?" → the list. Lets the model (and curious users)
ground themselves before composing a query.

## Trust layer

The design centers on scholarly trust. Concretely:

- **Show the query, always.** Every result carries the exact MQL that produced
  it. Nothing is returned without its query.
- **Validate before executing.** MQL referencing features/values absent from the
  reference is rejected, so wrong codes fail loudly instead of silently
  returning zero matches.
- **Honest empty results.** Zero matches returns the query plus an explicit "0
  results" — never an invented answer. A scholar can distinguish "the query is
  wrong" from "the phenomenon is genuinely absent."
- **SHEBANQ-ready.** The MQL is plain SHEBANQ-compatible MQL: paste, save, cite.

The core engineering risk lives here too: reliable NL → *correct* MQL
translation over a large feature vocabulary. The feature reference and the
validator are the two mechanisms that manage that risk.

## Demo web app

A thin static front-end (consistent with the existing Netlify + Astro setup)
that talks to a hosted instance of the MCP server. Its job is to *show* the
server, not to be the product.

- **Featured searches.** A curated gallery of pre-validated questions
  ("subject-after-verb clauses in Genesis", "Niphal verbs in Psalms", etc.).
  Each shows the NL question, the generated MQL, and live results. These are
  validated ahead of time so the demo is dependable, and they double as the
  regression test set (see Testing).
- **Free-form box.** Type a question, watch it produce MQL + results.
- **SHEBANQ links.** Each result links out to SHEBANQ so a visitor can see the
  query running in the real tool.

## Testing

- **Featured searches as fixtures.** Each featured search is a
  `{ question → expected MQL shape → expected count }` fixture, run against the
  real Emdros BHSA database in CI. This is the backbone test set and the demo
  content at once.
- **Validator unit tests.** Rejects unknown features/values; accepts valid ones;
  rejects unparseable MQL.
- **Runner unit tests.** Known MQL → known count against the local BHSA DB.

## Open questions / deferred

- Exact hosting model for the demo server instance (the Emdros stack is heavier
  than a static site — needs a real backend host, not just Netlify static).
- Whether `lookup_feature` should also surface usage examples per feature.
- BHSA data version to pin against for v1.
