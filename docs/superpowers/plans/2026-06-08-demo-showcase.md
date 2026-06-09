# Demo Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained static `demo/index.html` that showcases ~5 pre-validated featured searches — each with its plain-language question, generated MQL, real result count, and real sample rows — so it can be opened locally and screenshotted.

**Architecture:** A CI extraction script runs the searches against the real BHSA database (reusing the tested `run_query`) and emits `demo/showcase.json` (real counts + Hebrew/gloss sample rows). A generator inlines that JSON into an HTML template to produce a single self-contained `demo/index.html` (no fetch, no server). Verse references are a best-effort enhancement that degrades to Hebrew+gloss.

**Tech Stack:** Python (extraction + generator), the existing `shebanq_mcp.runner`, plain HTML/CSS/JS (no framework), GitHub Actions (for real data), `pytest`.

**Scope note:** Static showcase only. Live free-form querying and the Render deploy are a separate follow-on plan.

---

## File Structure

```
shebanq-mcp/
  demo/
    template.html       # HTML+CSS+JS template with a {{DATA}} placeholder
    showcase.json       # real data extracted from the BHSA db (committed)
    index.html          # generated: template with showcase.json inlined (committed)
  scripts/
    extract_showcase.py # runs in CI; prints showcase JSON (count + samples)
    build_demo.py       # inlines showcase.json into template -> index.html
  tests/
    test_build_demo.py  # unit test for the generator
    fixtures/featured_searches.json  # add the showcase searches' counts
  .github/workflows/emdros-tests.yml # add a step to run extract_showcase.py + upload artifact
```

**Responsibilities:**
- `extract_showcase.py` — produce real showcase data from the database. No HTML.
- `build_demo.py` — pure transform: showcase.json + template -> index.html. No DB.
- `template.html` — all presentation (CSS) and client-side rendering (JS). No data.
- `showcase.json` — the only data; committed so the page is reproducible offline.

---

## Task 1: Extraction script (count + Hebrew/gloss samples)

**Files:**
- Create: `scripts/extract_showcase.py`

The five showcase searches are word-level (uniform Hebrew+gloss samples). Counts
for niphal-verbs (4145) and bara (48) are known; the other three are pinned from
CI in Task 2.

- [ ] **Step 1: Write `scripts/extract_showcase.py`**

```python
"""Extract real showcase data from the BHSA database.

Runs each featured search via the tested run_query, collecting the total count
and up to SAMPLE_N real sample rows (Hebrew word + English gloss). Prints the
showcase JSON to stdout. Run in CI where Emdros + the DB exist:

    python scripts/extract_showcase.py data/bhsa.sqlite3 > demo/showcase.json
"""
import json
import sys

from shebanq_mcp.runner import run_query

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"
SAMPLE_N = 5

SEARCHES = [
    {
        "id": "niphal-verbs",
        "question": "Find all Niphal verbs in the Hebrew Bible.",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif GET g_word_utf8, gloss] GO",
    },
    {
        "id": "bara-create",
        "question": "Where does the verb בָּרָא (bara, 'to create') occur?",
        "mql": "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO",
    },
    {
        "id": "feminine-plural-nouns",
        "question": "Find feminine plural nouns.",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl GET g_word_utf8, gloss] GO",
    },
    {
        "id": "imperative-verbs",
        "question": "Find all imperative verbs.",
        "mql": "SELECT ALL OBJECTS WHERE [word vt=impv GET g_word_utf8, gloss] GO",
    },
    {
        "id": "proper-nouns",
        "question": "Find all proper nouns (names).",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=nmpr GET g_word_utf8, gloss] GO",
    },
]


def extract(db: str) -> dict:
    searches = []
    for s in SEARCHES:
        res = run_query(s["mql"], db, features=["g_word_utf8", "gloss"])
        samples = [
            {
                "hebrew": m.get("g_word_utf8", ""),
                "gloss": m.get("gloss", ""),
                "reference": None,
            }
            for m in res.matches[:SAMPLE_N]
        ]
        searches.append({
            "id": s["id"],
            "question": s["question"],
            "mql": s["mql"],
            "count": res.count,
            "samples": samples,
        })
    return {"version": "bhsa-2021", "searches": searches}


if __name__ == "__main__":
    print(json.dumps(extract(DB), ensure_ascii=False, indent=2))
```

- [ ] **Step 2: Commit**

```bash
git add scripts/extract_showcase.py
git commit -m "feat: showcase data extraction script (count + Hebrew/gloss samples)"
```

---

## Task 2: Produce real `showcase.json` in CI and pin counts

This task runs the extraction against the real database in CI, retrieves the
output, commits it, and pins the new counts into the regression fixtures. It is
an ops task (no unit test); the data it produces is the input to later tasks.

**Files:**
- Modify: `.github/workflows/emdros-tests.yml`
- Create: `demo/showcase.json` (from CI output)
- Modify: `tests/fixtures/featured_searches.json`

- [ ] **Step 1: Add an extraction + artifact step to the workflow**

In `.github/workflows/emdros-tests.yml`, after the "Print real featured-search
counts (diagnostic)" step, add:

```yaml
      - name: Extract showcase data
        if: always()
        env:
          BHSA_SQLITE: data/bhsa.sqlite3
        run: |
          mkdir -p demo
          python3 scripts/extract_showcase.py data/bhsa.sqlite3 > demo/showcase.json
          echo "=== showcase.json head ==="
          head -40 demo/showcase.json

      - name: Upload showcase data
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: showcase
          path: demo/showcase.json
```

- [ ] **Step 2: Commit and push to trigger CI**

```bash
git add .github/workflows/emdros-tests.yml
git commit -m "ci: extract showcase data and upload as artifact"
git push origin <branch>
```

- [ ] **Step 3: Wait for the run, then download the artifact**

```bash
gh run list --branch <branch> --limit 1            # get the run id, wait for success
gh run download <run-id> -n showcase -D demo/      # writes demo/showcase.json
```
Expected: `demo/showcase.json` exists locally with five searches, each having a
numeric `count` and a non-empty `samples` array of `{hebrew, gloss, reference}`.

- [ ] **Step 4: Pin the three new counts into the fixtures**

Read the `count` for `feminine-plural-nouns`, `imperative-verbs`, and
`proper-nouns` from `demo/showcase.json`, then add matching entries to
`tests/fixtures/featured_searches.json` (alongside the existing niphal-verbs and
bara-occurrences entries), e.g.:

```json
{
  "id": "feminine-plural-nouns",
  "question": "Find feminine plural nouns.",
  "mql": "SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl] GO",
  "expected_count": 0
}
```
Replace each `expected_count` with the real number from `showcase.json`. Do the
same for `imperative-verbs` (`[word vt=impv]`) and `proper-nouns`
(`[word sp=nmpr]`).

- [ ] **Step 5: Run the validity tests locally (counts skip without a db)**

Run: `pytest tests/test_featured_searches.py -q`
Expected: the `test_featured_mql_is_valid` cases all pass (the new MQL validates:
enums unquoted, valid constants); count tests skip locally.

- [ ] **Step 6: Commit**

```bash
git add demo/showcase.json tests/fixtures/featured_searches.json
git commit -m "data: real showcase.json from BHSA db + pinned fixture counts"
```

---

## Task 3: Page template + generator

**Files:**
- Create: `demo/template.html`
- Create: `scripts/build_demo.py`
- Create: `demo/index.html` (generated)
- Test: `tests/test_build_demo.py`

- [ ] **Step 1: Write `demo/template.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SHEBANQ MCP — Ask the Hebrew Bible in plain language</title>
<style>
  :root {
    --ink: #1a1a1a; --muted: #6b6b6b; --line: #e3e0d8;
    --bg: #faf8f3; --card: #ffffff; --accent: #7a5c2e;
    --code-bg: #f4f1ea;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: Georgia, "Times New Roman", serif;
    line-height: 1.55;
  }
  .wrap { max-width: 820px; margin: 0 auto; padding: 56px 24px 80px; }
  header h1 {
    font-size: 30px; font-weight: 600; margin: 0 0 8px; letter-spacing: -0.01em;
  }
  header .lede { font-size: 18px; color: var(--accent); margin: 0 0 18px; }
  header p { font-size: 16px; color: var(--muted); max-width: 64ch; }
  .rule { height: 1px; background: var(--line); margin: 36px 0; border: 0; }
  .card {
    background: var(--card); border: 1px solid var(--line);
    border-radius: 8px; padding: 24px; margin: 0 0 24px;
  }
  .question { font-size: 20px; font-weight: 600; margin: 0 0 14px; }
  .mql {
    font-family: "SFMono-Regular", Menlo, Consolas, monospace;
    font-size: 13px; background: var(--code-bg); color: #2b2b2b;
    border-radius: 6px; padding: 12px 14px; overflow-x: auto;
    white-space: pre-wrap; margin: 0 0 12px;
  }
  .count { font-size: 14px; color: var(--muted); margin: 0 0 14px; }
  .count b { color: var(--ink); }
  table.samples { width: 100%; border-collapse: collapse; font-size: 15px; }
  table.samples td {
    padding: 7px 10px; border-top: 1px solid var(--line); vertical-align: middle;
  }
  td.heb {
    direction: rtl; text-align: right; font-size: 22px;
    font-family: "Times New Roman", "SBL Hebrew", serif; white-space: nowrap;
  }
  td.ref { color: var(--muted); font-size: 13px; white-space: nowrap; width: 1%; }
  td.gloss { color: var(--ink); }
  .verify { margin: 14px 0 0; font-size: 14px; }
  .verify a { color: var(--accent); text-decoration: none; }
  .verify a:hover { text-decoration: underline; }
  footer { margin-top: 28px; font-size: 13px; color: var(--muted); }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Ask the Hebrew Bible in plain language</h1>
    <p class="lede">A natural-language question becomes a citable MQL query — and real results.</p>
    <p>Each example below was produced by translating an English question into an
       Emdros MQL query and running it against the BHSA database (the same data
       behind SHEBANQ). The query is always shown, so it can be verified,
       reproduced, and cited.</p>
  </header>
  <hr class="rule">
  <main id="cards"></main>
  <footer id="footer"></footer>
</div>
<script>window.SHOWCASE = {{DATA}};</script>
<script>
  var SHEBANQ_URL = "https://shebanq.ancient-data.org/hebrew/queries";
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function card(s) {
    var c = el("section", "card");
    c.appendChild(el("h2", "question", s.question));
    c.appendChild(el("pre", "mql", s.mql));
    var count = el("p", "count");
    count.innerHTML = "<b>" + s.count.toLocaleString() + "</b> result" + (s.count === 1 ? "" : "s");
    c.appendChild(count);
    var table = el("table", "samples");
    s.samples.forEach(function (row) {
      var tr = el("tr");
      tr.appendChild(el("td", "heb", row.hebrew));
      tr.appendChild(el("td", "gloss", row.gloss));
      tr.appendChild(el("td", "ref", row.reference || ""));
      table.appendChild(tr);
    });
    c.appendChild(table);
    var v = el("p", "verify");
    var a = el("a", null, "verify in SHEBANQ →");
    a.href = SHEBANQ_URL; a.target = "_blank"; a.rel = "noopener";
    v.appendChild(a);
    c.appendChild(v);
    return c;
  }
  var data = window.SHOWCASE || { searches: [], version: "" };
  var cards = document.getElementById("cards");
  data.searches.forEach(function (s) { cards.appendChild(card(s)); });
  document.getElementById("footer").textContent =
    "Data: BHSA " + (data.version || "") +
    ". Queries run on the Emdros engine that powers SHEBANQ.";
</script>
</body>
</html>
```

- [ ] **Step 2: Write the failing test for the generator**

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_demo import render  # noqa: E402

TEMPLATE = '<html><body><script>window.SHOWCASE = {{DATA}};</script></body></html>'

SHOWCASE = {
    "version": "bhsa-2021",
    "searches": [
        {
            "id": "x", "question": "Find Niphal verbs.",
            "mql": "SELECT ALL OBJECTS WHERE [word vs=nif] GO",
            "count": 4145,
            "samples": [{"hebrew": "ברא", "gloss": "create", "reference": None}],
        }
    ],
}


def test_render_inlines_data_and_drops_placeholder():
    out = render(SHOWCASE, TEMPLATE)
    assert "{{DATA}}" not in out
    assert "Find Niphal verbs." in out
    assert "vs=nif" in out
    assert "create" in out
    assert "4145" in out


def test_render_output_parses_back():
    out = render(SHOWCASE, TEMPLATE)
    blob = out.split("window.SHOWCASE = ", 1)[1].split(";</script>", 1)[0]
    assert json.loads(blob)["searches"][0]["count"] == 4145
```

Note: `scripts/` needs to be importable. Add an empty `scripts/__init__.py` if
import fails (Step 4 handles this).

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_build_demo.py -v`
Expected: FAIL with `ModuleNotFoundError: scripts.build_demo`.

- [ ] **Step 4: Write `scripts/build_demo.py` (and `scripts/__init__.py` if needed)**

```python
"""Inline demo/showcase.json into demo/template.html -> demo/index.html.

Pure transform: no database, no network. Re-run whenever showcase.json changes:
    python scripts/build_demo.py
"""
import json
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"


def render(showcase: dict, template: str) -> str:
    return template.replace("{{DATA}}", json.dumps(showcase, ensure_ascii=False))


def main() -> None:
    showcase = json.loads((DEMO / "showcase.json").read_text(encoding="utf-8"))
    template = (DEMO / "template.html").read_text(encoding="utf-8")
    (DEMO / "index.html").write_text(render(showcase, template), encoding="utf-8")
    print(f"wrote {DEMO / 'index.html'}")


if __name__ == "__main__":
    main()
```

If Step 3 failed on import of `scripts`, also create an empty
`scripts/__init__.py`:

```python
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_build_demo.py -v`
Expected: 2 passed.

- [ ] **Step 6: Generate the real page and confirm it built**

Run: `python scripts/build_demo.py && test -s demo/index.html && grep -c "card" demo/index.html`
Expected: prints the output path; `demo/index.html` is non-empty.

- [ ] **Step 7: Commit**

```bash
git add demo/template.html scripts/build_demo.py scripts/__init__.py tests/test_build_demo.py demo/index.html
git commit -m "feat: demo page template + generator (self-contained index.html)"
```

---

## Task 4: Verse references (best-effort enhancement)

**Files:**
- Modify: `scripts/extract_showcase.py`
- Modify: `demo/showcase.json` (re-extracted)
- Modify: `demo/index.html` (re-generated)

Per the spec, references are best-effort: if extraction fails for any reason,
samples keep `reference: null` and the page simply omits the reference column
value (already handled by the template's `row.reference || ""`).

Approach: a nested MQL query returns words together with their enclosing verse,
so the engine resolves containment. The verse object's section features are
discovered first, then harvested from the inner/outer sheaf. Wrapped in
try/except so any failure degrades gracefully.

- [ ] **Step 1: Discover the verse object's reference features (CI diagnostic)**

Add a temporary line to the workflow's schema step, or run `dump_schema.py` with
`SELECT FEATURES FROM OBJECT TYPE [verse] GO`, `[chapter]`, `[book]` to find the
feature names that hold the book name, chapter number, and verse number. Record
them (e.g. `book`, `chapter`, `verse`). This is discovery only; it informs the
nested query below.

- [ ] **Step 2: Add a reference-aware sample extractor with graceful fallback**

Add to `scripts/extract_showcase.py`:

```python
from shebanq_mcp.runner import _import_emdros


def _samples_with_refs(inner_where: str, db: str, n: int) -> list | None:
    """Run a verse>word nested query and harvest up to n samples with refs.
    Returns None on any failure (caller then falls back to flat samples)."""
    try:
        emdros = _import_emdros()
        env = emdros.EmdrosEnv(
            emdros.kOKConsole, emdros.kCSUTF8, "", "", "", db, emdros.kSQLite3,
        )
        mql = (
            "SELECT ALL OBJECTS WHERE "
            "[verse GET book, chapter, verse "
            "  [word " + inner_where + " GET g_word_utf8, gloss] "
            "] GO"
        )
        if not env.executeString(mql, True, False, True):
            return None
        out = []
        sheaf = env.getSheaf()
        it = sheaf.const_iterator()
        while it.hasNext() and len(out) < n:
            straw = it.next()
            sit = straw.const_iterator()
            while sit.hasNext() and len(out) < n:
                vmo = sit.next()
                ref = f"{vmo.getFeatureAsString(0)} {vmo.getFeatureAsString(1)}:{vmo.getFeatureAsString(2)}"
                inner = vmo.getSheaf()
                iit = inner.const_iterator()
                while iit.hasNext() and len(out) < n:
                    istraw = iit.next()
                    wit = istraw.const_iterator()
                    while wit.hasNext() and len(out) < n:
                        wmo = wit.next()
                        out.append({
                            "hebrew": wmo.getFeatureAsString(0),
                            "gloss": wmo.getFeatureAsString(1),
                            "reference": ref,
                        })
        return out or None
    except Exception:
        return None
```

- [ ] **Step 3: Use refs when available, else fall back to flat samples**

In `extract()`, change the per-search sample construction to prefer refs. Each
search needs its inner WHERE clause; add a `where` field to each entry in
`SEARCHES` (e.g. `"where": "sp=verb AND vs=nif"`), then:

```python
    for s in SEARCHES:
        res = run_query(s["mql"], db, features=["g_word_utf8", "gloss"])
        samples = _samples_with_refs(s["where"], db, SAMPLE_N)
        if samples is None:
            samples = [
                {"hebrew": m.get("g_word_utf8", ""), "gloss": m.get("gloss", ""),
                 "reference": None}
                for m in res.matches[:SAMPLE_N]
            ]
        searches.append({
            "id": s["id"], "question": s["question"], "mql": s["mql"],
            "count": res.count, "samples": samples,
        })
```

Add the matching `where` to each SEARCHES entry, for example:
`{"id": "niphal-verbs", ..., "where": "sp=verb AND vs=nif"}`,
`{"id": "bara-create", ..., "where": "lex='BR>['"}`,
`{"id": "feminine-plural-nouns", ..., "where": "sp=subs AND gn=f AND nu=pl"}`,
`{"id": "imperative-verbs", ..., "where": "vt=impv"}`,
`{"id": "proper-nouns", ..., "where": "sp=nmpr"}`.

- [ ] **Step 4: Re-run CI extraction, download, and verify refs**

Push, wait for CI, then `gh run download <run-id> -n showcase -D demo/`. Inspect
`demo/showcase.json`: each sample should now have a `reference` like
`"Genesis 1:1"`. If references are still null (nested harvest unsupported in this
build), that is an acceptable degraded outcome — proceed with Hebrew+gloss only.

- [ ] **Step 5: Rebuild the page and commit**

```bash
python scripts/build_demo.py
git add scripts/extract_showcase.py demo/showcase.json demo/index.html
git commit -m "feat: best-effort verse references in showcase samples"
```

---

## Task 5: README and open instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Demo section to `README.md`**

```markdown
## Demo showcase

A static, self-contained showcase of example searches (question -> MQL ->
real results) lives in `demo/index.html`. Open it directly in a browser:

    open demo/index.html        # macOS

It needs no server and no install — the data is inlined from `demo/showcase.json`.

To regenerate after changing the data or template:

    python scripts/build_demo.py      # rebuilds demo/index.html

`demo/showcase.json` is produced from the real BHSA database by
`scripts/extract_showcase.py`, which runs in CI (Emdros + the database are not
required locally to view the demo).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: how to open and regenerate the demo showcase"
```

---

## Done criteria

- `pytest -q` passes (build_demo unit tests green; new featured-search validity
  tests green; emdros count tests skip locally, pass in CI).
- `demo/index.html` opens locally with no server and shows five cards, each with
  question, MQL, real count, and real Hebrew+gloss sample rows (references when
  available).
- No fabricated data: every count and sample row came from `extract_showcase.py`
  against the real BHSA database.

## Deferred
- Live free-form query box + Render deploy (separate plan).
- Direct SHEBANQ saved-query deep links (cards currently link to the SHEBANQ
  query page; the MQL is shown for pasting).
