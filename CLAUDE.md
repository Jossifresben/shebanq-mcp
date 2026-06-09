# shebanq-mcp — project context

An **MCP server** that lets biblical-studies scholars query the BHSA Hebrew Bible
(the ETCBC data behind SHEBANQ) in plain language and get back a **citable MQL
query + real results**, run on a local **Emdros** engine. Audience: scholars /
PhD candidates who use or are learning MQL. **Trust is the product:** always show
the query, validate before running, honest empty results. "AI as a way in, not a
way around."

- **Repo:** https://github.com/Jossifresben/shebanq-mcp (public, MIT). Owner Jossifresben.
- **Founder/user:** Jossi Fresco. The assistant is named **Hermes**.
- **Status:** core server built + verified against the real BHSA database in CI;
  enum/string MQL handling done; a static demo showcase is built. Awaiting ETCBC
  feedback before building further (a live UI + deploy).

## Writing style (for any prose: Slack, docs, README)
Grounded, direct, warm. **No em-dashes.** Vary sentence length. Avoid AI-tells
(delve, comprehensive, leverage, resonate, transformative, etc.). Max one
negation-reframe ("not X but Y") per piece. Plain over fancy.

## What's built
- **MCP server** (`src/shebanq_mcp/`), tools: `search_bhsa(question)`,
  `run_mql(mql)`, `lookup_feature(name_or_term)`.
  - `feature_reference.py` — loads `features.json` (feature catalogue + the shared
    `all_enum` constant set). `validator.py` — enum/string-aware MQL validation.
    `runner.py` — executes MQL via Emdros. `formatter.py` — glossed results.
    `translate.py` — NL→MQL, LLM-agnostic behind a `Translator` interface
    (default Anthropic; `LLM_PROVIDER=none` runs translation-free). `server.py` —
    wires the 3 tools (FastMCP).
- **Demo showcase** (`demo/index.html`) — self-contained static page (open by
  double-click, no server), generated from `demo/showcase.json` by
  `scripts/build_demo.py` (template at `demo/template.html`). Shows 5 word-level
  searches as an input-box → mock "Generate query" → MQL → mock "Run query" →
  results flow, with real vocalized Hebrew, lexeme glosses, and verse references.
- **CI** (`.github/workflows/emdros-tests.yml`) builds Emdros from source +
  the BHSA SQLite db and runs the `emdros`-marked tests. Also extracts
  `demo/showcase.json` and uploads it as the `showcase` artifact.
- Docs: design specs in `docs/specs/`, implementation plans in
  `docs/superpowers/plans/`.

## Hard-won Emdros / MQL facts (verified in CI)
- No apt package for Emdros; emdros.org is unreachable from CI runners. Build
  from the GitHub source archive tag **`rel-3-9-0`**; needs autotools bootstrap +
  `re2c bison flex`; strip the `doc` subdir and stub `pdflatex` to skip the GUI
  LaTeX build; configure `--with-sqlite3=yes --with-wx=no`.
- Python SWIG module is **`EmdrosPy3`** (not `emdros`/`EmdrosPy`), in
  `/usr/local/lib/emdros/`. The runner's `_import_emdros()` tries all three names.
- `EmdrosEnv(kOKConsole, kCSUTF8, host, user, password, initial_db, kSQLite3)` —
  backend enum is **`kSQLite3`**; needs all 7 args. `MatchedObject` has **no
  `getFirst`** (monad dropped). Nested queries: `MatchedObject.getSheaf()` gives
  the inner sheaf (used for verse references).
- The MQL dump's `CREATE DATABASE 'shebanq_etcbc2021'` makes `mql` write the
  SQLite file under that internal name, not the `-d` path — relocate it.
- **CRITICAL MQL rule:** enumeration features (sp, vs, vt, gn, nu, ps, function,
  typ, …) compare **UNQUOTED** (`sp=verb`, `vs=nif`); string features (lex,
  gloss, g_word_utf8 …) compare **QUOTED** (`lex='BR>['`). Quoting an enum →
  "Typechecking failed". All enum features share one enumeration `all_enum`
  (237 constants, embedded in `features.json`). BHSA verb lexemes carry a
  trailing `[` (bara = `BR>[`).
- `gloss` is the LEXEME (dictionary) gloss, not an inflected translation (so a
  plural form like עֲצָמַי shows gloss "bone"). This is faithful to BHSA.
- Verified counts: sp=verb 73710; sp=verb AND vs=nif (Niphal verbs) 4145;
  lex='BR>[' (bara) 48; feminine plural nouns 5992; imperatives 4306; proper
  nouns 33002.

## Running things
- Tests (no Emdros needed locally; emdros tests skip): `pytest -q`
- Rebuild the demo page after editing data/template: `python scripts/build_demo.py`
- Emdros + the BHSA database are **not installed locally** (Mac). All DB-backed
  work (real counts, sample extraction, refs) runs **in CI**. To get fresh data:
  push to a branch, wait for the run, then
  `gh run download <run-id> -n showcase -D demo/`, then `python scripts/build_demo.py`.

## Deploy plan (not done)
Render Pro Web Service, Docker, single always-on container, **Emdros-on-SQLite**
with the BHSA data baked into the image. Demo front-end on Netlify static. The
same Emdros build recipe as the CI workflow.

## Next milestone (open, pending ETCBC feedback)
Wire the demo to a **live backend** (real free-form query box: NL → MQL → results)
and **deploy on Render Pro**. Brainstorm → spec → plan → execute when ready.

## Workflow norms (this project)
- Work on a feature branch, verify, then merge to `main` and push (solo repo, no PRs).
- End commit messages with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Brainstorm before building (superpowers brainstorming → writing-plans →
  execution). Specs in `docs/specs/`, plans in `docs/superpowers/plans/`.
