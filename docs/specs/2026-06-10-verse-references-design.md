# Verse references in query results — design

**Date:** 2026-06-10
**Status:** approved design, pending implementation plan
**Scope:** Add `book chapter:verse` to query results, opt-in via a checkbox, for
the live web demo and (structurally) for `run_mql`.

## Problem

Results show the word and gloss but not where it occurs. A scholar asking "where
does shana (year) occur?" gets a word list with no locations. References were
only ever pre-baked into the static showcase by `scripts/extract_showcase.py`
(via a nested verse-over-word query); the live `run_mql` / `/api/run` path never
populated them, because the runner harvests only the matched word's own `GET`
features and never traverses up to the containing verse.

## Approach

In MQL, a word's location comes from the **containing verse** object, reached by
nesting: `[verse GET book, chapter, verse [word … GET g_word_utf8, gloss]]`.

- **References are opt-in** via a checkbox ("Include the reference (book
  chapter:verse)"), **default checked**.
- The model **always translates to the simple flat** `[word … ]` query (the form
  already tuned and trusted). When references are requested, the **server wraps**
  that flat query in the verse nest **deterministically** — the model is never
  asked to write more complex nested MQL, so translation quality is unaffected.
- **What you see is what runs**: the box shows the flat query when unchecked, the
  nested query when checked. Honest in both states (the project's stance).
- The runner is generalized to harvest references from any nested verse-over-word
  result, so a hand-written nested `run_mql` query also gets references.

## Components

### 1. Front end (`demo/template.html`)

- A checkbox by the ask box: **"Include the reference (book chapter:verse)"**,
  **checked by default**.
- On submit (Translate to MQL), send the state:
  `POST /api/translate {question, references: <bool>}`.
- No other UI change — the existing result card already renders a `reference`
  column (currently always empty); it will now populate when present.

### 2. Translate endpoint (`server.py` / `web.py`)

- `handle_translate(question, references=False)`:
  - translate to flat MQL as today;
  - if `references`, wrap via `_wrap_in_verse(mql)`;
  - return `{question, mql}` (or the degraded payload).
- `_wrap_in_verse(mql)`: a deterministic transform on the model's controlled
  output. Match `SELECT ALL OBJECTS WHERE (<block>) GO` and rewrite to
  `SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse <block>] GO`. If the
  query does not match the expected single-block shape, return it unchanged (no
  references rather than a broken query).
- `/api/translate` reads `references` from the JSON body (default false on the
  API; the page sends the checkbox state). The `_post_route` helper currently
  passes a single string; the translate route needs the extra flag — see
  "open questions".

### 3. Runner (`runner.py`) — the core change

Generalize `run_query` to harvest nested results, **without changing the flat
path**:

- Parse **all** `GET` clauses in nesting order into `get_lists`
  (`[["book","chapter","verse"], ["g_word_utf8","gloss"]]` for the nested form).
  Today only one clause is parsed, and on a nested query it parses the wrong one.
- **Branch on nesting:** if `len(get_lists) <= 1`, use the existing flat harvest
  (count = top-level objects) — selftest/smoke unchanged. If `> 1`, use the
  nested harvest.
- **Nested harvest:** recurse the sheaf. At each level, name features by
  `get_lists[depth]`. A level whose features include `book`/`chapter`/`verse`
  sets the reference context. Recurse into an object's inner sheaf when it is a
  container; at a **leaf** (the innermost, e.g. word) emit a row carrying its own
  features **plus** the containing verse's `book/chapter/verse`.
- **Count = leaf rows** in the nested path (the words), not the outer verses, so
  counts stay correct (bara still 48 whether flat or nested).

### 4. Formatter (`formatter.py`) — unchanged

`_reference(row)` already builds `book chap:verse` from those fields and excludes
them from `features`. The runner just needs to put `book/chapter/verse` on each
leaf row.

### 5. Worked examples (`demo/showcase.json`)

For consistency with the default-checked behaviour, the gallery examples show the
nested form and their references. The samples already carry references (from
`extract_showcase.py`); update the displayed `mql` to the nested form so clicking
**Run** on an example yields references too.

## Behaviour & fallbacks

- Checkbox on (default): word searches return `book chap:verse` per hit.
- Checkbox off: the clean flat query, no references — exactly today's behaviour.
- A flat `run_mql` query (MCP tool, or pasted MQL): no references; the runner
  adds them only when the structure provides them. Nothing breaks.
- A query that does not match the wrap shape: returned unwrapped (no refs), never
  a broken query.
- Counts remain the number of matched words.

## Testing

- **Unit (local, no Emdros):** the multi-`GET` parser returns the per-level
  feature lists in order; `_wrap_in_verse` wraps a flat query and leaves an
  unmatched query unchanged; the nested harvest, driven by a **fake env** that
  yields a verse-over-word sheaf, attaches the verse reference to leaf words and
  counts leaves (not verses).
- **Integration (CI, `emdros`-marked):** a nested bara query returns count **48**
  and the first hit's reference is **Genesis 1:1**; a flat bara query still
  returns 48 with `reference: null` (flat path unchanged).
- **Live:** ask "where does X occur" with the box checked → results show
  locations; uncheck → flat query, no locations.

## Risks

- **Emdros `getSheaf()` on a leaf object:** the nested harvest assumes calling
  `getSheaf()` on a word (leaf) returns an empty sheaf, not an error. The
  nesting-count branch avoids calling it on the flat path; verify the leaf
  behaviour in CI and, if needed, drive container-vs-leaf purely from the parsed
  nesting depth instead of probing `getSheaf()`.
- **Translation quality:** unaffected by design — the model keeps emitting flat
  queries; the server does the wrapping.
- **Local testability:** the harvest is only run end-to-end in CI (Emdros is not
  installed locally), so expect an implement → push → CI cycle to confirm the
  Genesis 1:1 assertion.

## Out of scope

- Re-running `extract_showcase.py` against the DB (the existing samples already
  have references; only the displayed `mql` strings change).
- References for non-word leaf objects beyond what the generic harvest yields
  incidentally.
- Persisting the checkbox state across reloads.

## Open implementation questions (resolve at plan time)

- How the `references` flag reaches the translate route: extend `_post_route` to
  pass the whole body to the handler, or add a small dedicated translate route
  that reads both `question` and `references`. (Lean: a dedicated translate route;
  keep `_post_route` for the single-value `/api/run` and `/api/ask`.)
- Exact `GET`-clause parsing regex and how a level with no `GET` maps to depth.
- Container-vs-leaf detection: `getSheaf().hasNext()` vs parsed nesting depth.
