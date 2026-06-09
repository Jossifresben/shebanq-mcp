# Demo Showcase — Design

**Date:** 2026-06-08
**Status:** Approved design, pre-implementation

## Purpose

A static, self-contained showcase page that visualizes what the SHEBANQ MCP
server does: ask a question about the Hebrew Bible in plain language, get back a
verifiable MQL query plus real results. Built so Jossi can open it locally on a
Mac, screenshot it, and share in the ETCBC Slack to gather early feedback. No
backend, no install, no build step. Live free-form querying and Render
deployment come later, after feedback.

### Audience
ETCBC scholars and PhD candidates viewing screenshots. Trust matters: every
query shown is real and runnable, every result row came out of the database.

## Scope

**In scope (v1):**
- One self-contained `demo/index.html` (data embedded inline) that opens by
  double-click, no server.
- A curated set (~5) of pre-validated featured searches, each showing the
  plain-language question, the generated MQL, the real result count, and ~5 real
  sample rows.
- A one-off extraction script that produces the real data from the BHSA database
  in CI.

**Out of scope (v1):**
- Any live backend or free-form query box (deferred to the Render deploy).
- A build toolchain (Astro/npm). Single HTML file only.
- Fabricated or hand-authored result data.

## Architecture

Three small pieces:

### Extraction script — `scripts/extract_showcase.py`
Runs in CI (where Emdros + the BHSA database exist). Reads a list of featured
searches (question + MQL), executes each against the database, and collects:
the count and ~5 real sample rows. Each row carries the Hebrew word
(`g_word_utf8`), the English gloss (`gloss`), and a verse reference
(`book chapter:verse`) obtained via a nested book/chapter/verse MQL query when
clean; if a reference cannot be extracted cleanly, the row degrades to Hebrew +
gloss without a reference. Outputs `demo/showcase.json`.

### Data file — `demo/showcase.json`
Committed to the repo. Shape:
```json
{
  "version": "bhsa-2021",
  "searches": [
    {
      "id": "niphal-verbs",
      "question": "Find all Niphal verbs in the Hebrew Bible.",
      "mql": "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif GET g_word_utf8, gloss] GO",
      "count": 4145,
      "samples": [
        {"reference": "Genesis 2:3", "hebrew": "...", "gloss": "..."}
      ]
    }
  ]
}
```

### Page generator — `scripts/build_demo.py`
Reads `demo/showcase.json` and an HTML template, inlines the JSON into a
`<script>` block (so the page works from `file://` with no fetch), and writes the
final `demo/index.html`. Re-run whenever the data changes.

### Data flow
```
featured searches (question + MQL)
  -> extract_showcase.py (in CI, real Emdros + BHSA)
  -> demo/showcase.json (committed)
  -> build_demo.py (inline data into template)
  -> demo/index.html (open locally, screenshot)
```

## Page content and layout

A single column, generous whitespace.

- **Header:** the project name, a one-line description ("Ask the Hebrew Bible a
  question in plain language; get a citable MQL query and real results"), and a
  short paragraph framing the idea for a scholarly reader.
- **Featured-search cards** (one per search), each showing in order:
  1. the plain-language question (prominent)
  2. the generated MQL as a styled code block (the verifiable artifact)
  3. the result count ("4,145 results")
  4. ~5 real sample rows: Hebrew word (right-to-left), English gloss, and a
     verse reference when available
  5. a "verify in SHEBANQ" link (SHEBANQ shares queries by saved-query ID, not
     arbitrary MQL-by-URL, so the link points to SHEBANQ's query page and the
     card's MQL block is what the scholar pastes to reproduce the result; later,
     links can be swapped for direct saved-query URLs)
- **Footer:** a line noting the data version (BHSA 2021) and that the queries run
  on the same Emdros engine behind SHEBANQ.

## Featured searches (~5, showing range)

A diverse, validated set. Candidates (final counts pinned from CI runs):
- Niphal verbs — `[word sp=verb AND vs=nif]` (count 4145, known)
- the verb *bara* "to create" — `[word lex='BR>[']` (count 48, known)
- feminine plural nouns — `[word sp=subs AND gn=f AND nu=pl]`
- imperative verbs — `[word vt=impv]`
- a phrase-level search such as subjects — `[phrase function=Subj]`

Each is added to `tests/fixtures/featured_searches.json` with its real count, so
the regression suite covers them too. Final selection and any substitutions are
settled during implementation based on what yields clean, screenshot-worthy
sample rows.

## Styling

Quiet, scholarly, typography-forward. Serif headings, clean sans-serif body,
generous whitespace, thin dividers, one restrained accent color (not the Cosmic
Coach gold). Hebrew rendered right-to-left in a serif Hebrew-capable font. All
CSS inline in the single HTML file. Readable as a screenshot at normal zoom.

## Testing

- The featured searches used by the showcase are also `{question, mql,
  expected_count}` fixtures in `tests/fixtures/featured_searches.json`, run
  against the real database in CI (existing `test_featured_searches.py`).
- `build_demo.py` has a unit test: given a small `showcase.json`, the generated
  HTML contains the question text, the MQL, the count, and a sample row's gloss,
  and contains no unfilled template placeholders.
- `extract_showcase.py` is exercised in CI against the real database (it is the
  producer of the committed `showcase.json`); its output JSON is validated to
  have a count and at least one sample per search.

## Open questions / deferred
- Whether verse references can be extracted cleanly for word-level matches via
  nested MQL; if not, sample rows show Hebrew + gloss only (decided during
  implementation, not a blocker).
- Live free-form query box and Render deployment (separate follow-on).
- Exact final set of featured searches (settled in implementation).
