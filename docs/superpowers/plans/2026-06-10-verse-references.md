# Verse References Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `book chapter:verse` to query results, opt-in via a default-checked checkbox: the model keeps emitting a flat word query, the server wraps it in a verse nest when references are wanted, and the runner harvests the inner words with their containing verse's location.

**Architecture:** A new `_wrap_in_verse(mql)` deterministically nests a flat `[word …]` query inside `[verse GET book, chapter, verse [ … ]]`. `run_query` is generalized: it parses every `GET` clause in nesting order and, when the query is nested (more than one level), recurses the sheaf, drives container-vs-leaf from the parsed depth (so it never probes `getSheaf()` on a leaf), counts the leaf words, and propagates the verse's `book/chapter/verse` onto each leaf row. The flat path is untouched. `formatter._reference` already turns those fields into `book chap:verse`.

**Tech Stack:** Python 3.11, Emdros (`EmdrosPy3`, nested sheaves via `MatchedObject.getSheaf()`), FastMCP/Starlette routes, the existing runner/formatter/translator.

**Spec:** `docs/specs/2026-06-10-verse-references-design.md`

**Branch:** create `verse-references` from `main`.

**Local constraint:** no Emdros locally. The nested-harvest *logic* is unit-tested against a fake env (local); the real verse-reference values are verified by an `emdros`-marked test in CI (Task 6). Expect an implement → push → ~15-min CI cycle to confirm "first bara hit = Genesis 1:1".

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `src/shebanq_mcp/runner.py` | parse all GET levels; nested harvest with verse-reference propagation | Modify |
| `src/shebanq_mcp/server.py` | `_wrap_in_verse`; `handle_translate(question, references)` | Modify |
| `src/shebanq_mcp/web.py` | `/api/translate` reads `references`; dedicated translate route | Modify |
| `tests/test_runner.py` | parser + nested-harvest unit tests; emdros-marked reference test | Modify |
| `tests/test_server_transport.py` | `_wrap_in_verse` + `handle_translate(references)` tests | Modify |
| `tests/test_web.py` | `/api/translate` passes `references` | Modify |
| `demo/template.html` | reference checkbox; send `references`; (index.html regenerated) | Modify |
| `scripts/extract_showcase.py` | store the nested form in the showcase `mql` | Modify |
| `demo/showcase.json` | gallery queries wrapped to nested form | Modify |
| `.github/workflows/docker-smoke.yml` | web check: a nested `/api/run` returns a reference | Modify |
| `README.md` | one line noting the references feature | Modify |

---

## Task 1: Runner — parse all GET levels + nested harvest

**Files:**
- Modify: `src/shebanq_mcp/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_runner.py` (it already has `_FakeIter`, `_FakeStraw`,
`_FakeSheaf` from the cap tests; reuse them):

```python
from shebanq_mcp.runner import _parse_get_lists


def test_parse_get_lists_flat():
    mql = "SELECT ALL OBJECTS WHERE [word sp=verb GET sp, gloss] GO"
    assert _parse_get_lists(mql) == [["sp", "gloss"]]


def test_parse_get_lists_nested_in_order():
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    assert _parse_get_lists(mql) == [["book", "chapter", "verse"],
                                     ["g_word_utf8", "gloss"]]


def test_parse_get_lists_none():
    assert _parse_get_lists("SELECT ALL OBJECTS WHERE [word sp=verb] GO") == []


class _NMo:
    """A matched object with named-by-index features and an optional inner sheaf."""
    def __init__(self, idx, feats, inner=None):
        self.idx, self._feats, self._inner = idx, feats, inner

    def getID_D(self):
        return self.idx

    def getFeatureAsString(self, i):
        return self._feats[i]

    def getSheaf(self):
        return self._inner


def test_run_query_nested_attaches_verse_reference(monkeypatch):
    import shebanq_mcp.runner as runner
    words = [_NMo(101, ["בָּרָא", "create"]), _NMo(102, ["יִּבְרָא", "create"])]
    word_sheaf = _FakeSheaf([_FakeStraw(words)])
    verse = _NMo(1, ["Genesis", "1", "1"], word_sheaf)
    verse_sheaf = _FakeSheaf([_FakeStraw([verse])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    res = run_query(mql, "x.db")
    assert res.count == 2                       # leaf words, NOT the 1 verse
    r0 = res.matches[0]
    assert r0["id_d"] == 101
    assert r0["g_word_utf8"] == "בָּרָא" and r0["gloss"] == "create"
    assert r0["book"] == "Genesis" and r0["chapter"] == "1" and r0["verse"] == "1"


def test_run_query_nested_respects_limit(monkeypatch):
    import shebanq_mcp.runner as runner
    words = [_NMo(200 + i, ["w%d" % i, "g"]) for i in range(5)]
    verse = _NMo(1, ["Exodus", "2", "3"], _FakeSheaf([_FakeStraw(words)]))
    verse_sheaf = _FakeSheaf([_FakeStraw([verse])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word GET g_word_utf8, gloss]] GO")
    res = run_query(mql, "x.db", limit=2)
    assert res.count == 5 and len(res.matches) == 2   # all counted, 2 harvested
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_runner.py -q -k "parse_get_lists or nested"`
Expected: FAIL — `cannot import name '_parse_get_lists'` / nested assertions fail.

- [ ] **Step 3: Implement in `runner.py`**

At the top of `src/shebanq_mcp/runner.py`, add the import and helpers:

```python
import re

# A GET clause lists the features to return; it is always terminated by the
# opening bracket of an inner block ('[') or the closing bracket of its own
# block (']'). Capturing them left-to-right yields the per-nesting-level lists
# in outermost-first order.
_GET_CLAUSE = re.compile(r"\bGET\s+([A-Za-z0-9_,\s]+?)\s*(?=[\[\]])", re.IGNORECASE)

# Verse-level features that form a citation. The runner propagates these from a
# containing object down onto each leaf row; formatter._reference renders them.
_REF_KEYS = ("book", "chapter", "verse")


def _parse_get_lists(mql: str) -> list[list[str]]:
    return [[f.strip() for f in clause.split(",") if f.strip()]
            for clause in _GET_CLAUSE.findall(mql)]


def _harvest_nested(sheaf, get_lists, depth, ctx, matches, total, limit):
    names = get_lists[depth] if depth < len(get_lists) else []
    is_leaf = depth >= len(get_lists) - 1          # deepest level = the result rows
    it = sheaf.const_iterator()
    while it.hasNext():
        sit = it.next().const_iterator()
        while sit.hasNext():
            mo = sit.next()
            feats = {n: mo.getFeatureAsString(i) for i, n in enumerate(names)}
            if not is_leaf:
                child = dict(ctx)
                for k in _REF_KEYS:
                    if k in feats:
                        child[k] = feats[k]
                _harvest_nested(mo.getSheaf(), get_lists, depth + 1,
                                child, matches, total, limit)
            else:
                total[0] += 1
                if limit is not None and len(matches) >= limit:
                    continue
                row = {"id_d": mo.getID_D(), **feats}
                for k in _REF_KEYS:
                    if k in ctx:
                        row[k] = ctx[k]
                matches.append(row)
```

Then replace the body of `run_query` (keep the signature) so it branches on
nesting; the flat branch is the existing code verbatim:

```python
def run_query(mql: str, db_path: str, features: list[str] | None = None,
              limit: int | None = None) -> RunResult:
    """Run an MQL query. `count` is the true total of matched leaf objects;
    `matches` holds the harvested rows (capped at `limit`). A nested
    verse-over-word query attaches the containing verse's book/chapter/verse to
    each word row; a flat query harvests `features` from each matched object as
    before."""
    features = features or []
    get_lists = _parse_get_lists(mql)
    env = _make_env(db_path)
    if not env.executeString(mql, True, False, True):
        raise RuntimeError(f"Emdros error: {env.getCompilerError()}")
    sheaf = env.getSheaf()

    if len(get_lists) > 1:                          # nested: harvest leaf rows
        matches: list[dict] = []
        total = [0]
        _harvest_nested(sheaf, get_lists, 0, {}, matches, total, limit)
        return RunResult(count=total[0], matches=matches)

    matches = []                                    # flat: existing behaviour
    total = 0
    it = sheaf.const_iterator()
    while it.hasNext():
        straw = it.next()
        sit = straw.const_iterator()
        while sit.hasNext():
            mo = sit.next()
            total += 1
            if limit is not None and len(matches) >= limit:
                continue
            row = {"id_d": mo.getID_D()}
            for i, feat in enumerate(features):
                row[feat] = mo.getFeatureAsString(i)
            matches.append(row)
    return RunResult(count=total, matches=matches)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_runner.py -q`
Expected: all PASS (including the pre-existing cap tests — the flat path is
unchanged; `emdros`-marked tests skip locally).

- [ ] **Step 5: Confirm the full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/shebanq_mcp/runner.py tests/test_runner.py
git commit -m "feat: runner harvests verse references from nested queries

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `_wrap_in_verse` (server.py)

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_transport.py`:

```python
def test_wrap_in_verse_wraps_a_flat_word_query():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    wrapped = server._wrap_in_verse(mql)
    assert wrapped == ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
                       "[word lex='BR>[' GET g_word_utf8, gloss]] GO")


def test_wrap_in_verse_leaves_unmatched_query_unchanged():
    weird = "GET OBJECTS HAVING MONADS IN {1-3} GO"
    assert server._wrap_in_verse(weird) == weird
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server_transport.py -q -k wrap_in_verse`
Expected: FAIL — `AttributeError: ... '_wrap_in_verse'`.

- [ ] **Step 3: Implement in `server.py`**

Add near the top (after the imports / `_GET_CLAUSE`):

```python
# Matches `SELECT ALL OBJECTS WHERE <block> GO` so a flat word query can be
# nested inside a verse to fetch book/chapter/verse. If the query is not this
# single-block shape, it is returned unchanged (no references, never broken MQL).
_SELECT_BLOCK = re.compile(
    r"(?is)^(\s*SELECT\s+ALL\s+OBJECTS\s+WHERE\s+)(\[.*\])(\s+GO\s*)$")


def _wrap_in_verse(mql: str) -> str:
    m = _SELECT_BLOCK.match(mql.strip())
    if not m:
        return mql
    head, block, tail = m.group(1), m.group(2), m.group(3)
    return f"{head}[verse GET book, chapter, verse {block}]{tail}".strip()
```

(`re` is already imported in `server.py`.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_server_transport.py -q -k wrap_in_verse`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "feat: _wrap_in_verse nests a flat word query for references

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `handle_translate(question, references)`

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_transport.py`:

```python
def test_handle_translate_with_references_wraps(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    out = server.handle_translate("bara", references=True)
    assert out["mql"].startswith("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse")
    assert "degraded" not in out


def test_handle_translate_without_references_stays_flat(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    out = server.handle_translate("bara", references=False)
    assert "[verse" not in out["mql"]


def test_handle_translate_references_default_false(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word sp=verb GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    assert "[verse" not in server.handle_translate("verbs")["mql"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server_transport.py -q -k "handle_translate_with_references or stays_flat or references_default"`
Expected: FAIL — `handle_translate()` takes no `references` argument.

- [ ] **Step 3: Update `handle_translate` in `server.py`**

Replace the existing `handle_translate` with:

```python
def handle_translate(question: str, references: bool = False) -> dict:
    """Web /api/translate: translate a question to MQL only, without running it.
    When `references`, wrap the (flat) query in a verse nest so the run will carry
    book/chapter/verse. Degrades like handle_ask when translation is unavailable."""
    if _translator is None:
        return _degraded_payload(question)
    try:
        mql = _translator.translate(question, _ref)
    except Exception:  # noqa: BLE001 - any LLM/translate failure degrades
        return _degraded_payload(question)
    if references:
        mql = _wrap_in_verse(mql)
    return {"question": question, "mql": mql}
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_server_transport.py -q -k handle_translate`
Expected: all PASS (the earlier translate tests still pass — `references`
defaults to False).

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "feat: handle_translate wraps in a verse nest when references requested

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `/api/translate` reads `references`

**Files:**
- Modify: `src/shebanq_mcp/web.py`
- Modify: `src/shebanq_mcp/server.py` (main wiring unchanged in args, but the
  `translate` handler now takes 2 args — confirm)
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, update `_client` so the default `translate` takes two
args, and add a references test. Replace the `translate` default line in
`_client`:

```python
    translate = translate or (lambda q, refs=False: {"question": q, "mql": "SELECT t GO"})
```

Append:

```python
def test_api_translate_passes_references_flag():
    seen = {}

    def tr(q, refs=False):
        seen["refs"] = refs
        return {"question": q, "mql": "SELECT z GO"}

    c = _client(translate=tr)
    c.post("/api/translate", json={"question": "x", "references": True})
    assert seen["refs"] is True
    c.post("/api/translate", json={"question": "x"})
    assert seen["refs"] is False
```

Also update the two existing `make_routes(...)` calls in the 500-error tests and
any other direct `translate=lambda q: {}` to `translate=lambda q, refs=False: {}`.

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_web.py -q -k "translate"`
Expected: FAIL — the translate route calls `translate(value)` (one arg) and
ignores `references`.

- [ ] **Step 3: Give `/api/translate` its own route in `web.py`**

In `make_routes`, the `/api/translate` route must read `references` too, so it
can't use the single-value `_post_route`. Add a dedicated route and use it.
Replace the `Route("/api/translate", ...)` line in the returned list with a
dedicated handler defined just above the `return`:

```python
    async def translate_route(request):
        if not limiter.allow(client_ip(request), monotonic()):
            return JSONResponse({"error": "rate limit exceeded; wait a moment"},
                                status_code=429)
        body = await _read_json(request)
        question = (body.get("question") or "").strip()
        if not question:
            return JSONResponse({"error": "missing 'question'"}, status_code=400)
        try:
            return JSONResponse(translate(question, bool(body.get("references"))))
        except Exception:  # noqa: BLE001 - never leak a traceback as 500 HTML
            return JSONResponse({"error": "internal error translating the question"},
                                status_code=500)

    return [
        Route("/", page, methods=["GET"]),
        Route("/api/translate", translate_route, methods=["POST"]),
        Route("/api/ask", _post_route(ask, "question",
              "answering the question"), methods=["POST"]),
        Route("/api/run", _post_route(run, "mql",
              "running the query"), methods=["POST"]),
    ]
```

(The `translate` parameter to `make_routes`/`register_web_routes` now denotes a
`translate(question, references)->dict` callable. The `main()` wiring already
passes `translate=handle_translate`; no change needed there.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_web.py -q`
Expected: all PASS.

- [ ] **Step 5: Confirm the full suite + a local boot of the new route**

Run: `pytest -q` → PASS. Then:

```bash
MCP_TRANSPORT=http PORT=8791 LLM_PROVIDER=none WEB_API=on \
  python3 -m shebanq_mcp.server > /tmp/vr.log 2>&1 &
sleep 3
echo "translate (no key -> degraded, but route accepts references):"
curl -s -X POST http://localhost:8791/api/translate \
  -H 'content-type: application/json' -d '{"question":"bara","references":true}'
kill %1
```

Expected: a JSON body (degraded locally, since no Anthropic key) — the point is
the route accepts the `references` field without error.

- [ ] **Step 6: Commit**

```bash
git add src/shebanq_mcp/web.py tests/test_web.py
git commit -m "feat: /api/translate accepts a references flag

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Front-end reference checkbox

**Files:**
- Modify: `demo/template.html`
- Regenerate: `demo/index.html`

- [ ] **Step 1: Add the checkbox styles**

In `demo/template.html`, in the `<style>` block after the `.hint` rule, add:

```css
  .refs{display:flex;align-items:center;gap:7px;font-size:14px;color:var(--muted);margin:0 0 16px;cursor:pointer}
  .refs input{width:15px;height:15px;accent-color:var(--accent)}
```

- [ ] **Step 2: Add the checkbox markup**

In `demo/template.html`, right after the closing `</form>` of `askForm` (before
the `<p class="hint">`), add:

```html
  <label class="refs"><input type="checkbox" id="refs" checked> Include the reference (book chapter:verse)</label>
```

- [ ] **Step 3: Send the flag from the submit handler**

In the `askForm` submit handler, change the translate call from:

```js
      var res = await postJSON("/api/translate", {question: q});
```

to:

```js
      var withRefs = document.getElementById("refs").checked;
      var res = await postJSON("/api/translate", {question: q, references: withRefs});
```

- [ ] **Step 4: Regenerate and verify the built page**

Run:

```bash
python3 scripts/build_demo.py
python3 -c "p=open('demo/index.html').read(); assert 'id=\"refs\" checked' in p and 'references: withRefs' in p and 'Include the reference (book chapter:verse)' in p; print('checkbox wired')"
```

Expected: prints `checkbox wired`.

- [ ] **Step 5: Browser-verify the flag is sent (degraded locally is fine)**

Boot the server, load the page in a browser, and confirm a submit posts
`references:true` when the box is checked. (If a browser MCP is available, patch
`fetch` to capture the body; otherwise check the server log / network panel.)
Minimum: `GET /` is 200 and the checkbox renders checked.

```bash
MCP_TRANSPORT=http PORT=8792 LLM_PROVIDER=none WEB_API=on python3 -m shebanq_mcp.server > /tmp/vr2.log 2>&1 &
sleep 3
echo "GET / -> $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8792/)"
curl -s http://localhost:8792/ | grep -c 'id="refs" checked'
kill %1
```

Expected: `200` and `1`.

- [ ] **Step 6: Commit**

```bash
git add demo/template.html demo/index.html
git commit -m "feat(demo): reference checkbox (default on) sends references to /api/translate

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Real-DB reference test (CI)

**Files:**
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Add an `emdros`-marked nested-reference test**

Append to `tests/test_runner.py`:

```python
@pytest.mark.emdros
def test_nested_bara_has_reference(require_emdros, db_path):
    # The first occurrence of the lexeme BR>[ ("bara") is Genesis 1:1.
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    result = run_query(mql, db_path)
    assert result.count == 48                       # leaf words, same as flat
    first = result.matches[0]
    assert first["book"] == "Genesis"
    assert first["chapter"] == "1" and first["verse"] == "1"


@pytest.mark.emdros
def test_flat_bara_unchanged(require_emdros, db_path):
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
    result = run_query(mql, db_path)
    assert result.count == 48 and result.matches[0].get("book") is None
```

(`require_emdros` and `db_path` are existing fixtures in `tests/conftest.py`,
used by the other `emdros`-marked tests; `pytest` is already imported there.)

- [ ] **Step 2: Confirm it skips locally (no Emdros)**

Run: `pytest tests/test_runner.py -q -k "nested_bara or flat_bara"`
Expected: `2 skipped` (the `emdros` marker skips without the engine).

- [ ] **Step 3: Commit**

```bash
git add tests/test_runner.py
git commit -m "test: emdros-marked check that nested bara carries Genesis 1:1"
```

> The real assertion runs in the `emdros-tests` CI workflow (Task 8), which
> builds Emdros + the BHSA DB. If `book/chapter/verse` come back under different
> Emdros feature names, adjust the GET list and `_REF_KEYS` to match what the CI
> diagnostic prints.

---

## Task 7: Gallery examples carry references

**Files:**
- Modify: `scripts/extract_showcase.py`
- Modify: `demo/showcase.json`
- Regenerate: `demo/index.html`

- [ ] **Step 1: Wrap the showcase queries (reuse `_wrap_in_verse`)**

Run this one-off to nest each gallery query consistently with the live default:

```bash
python3 - <<'PY'
import json
from shebanq_mcp.server import _wrap_in_verse
p = "demo/showcase.json"
d = json.load(open(p, encoding="utf-8"))
for s in d["searches"]:
    s["mql"] = _wrap_in_verse(s["mql"])
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("wrapped", len(d["searches"]), "gallery queries")
PY
python3 scripts/build_demo.py
```

Expected: prints `wrapped 5 gallery queries` and rebuilds the page.

- [ ] **Step 2: Keep `extract_showcase.py` in sync**

In `scripts/extract_showcase.py`, where each search's `mql` field is built for
output, wrap it in the verse nest so a future re-extract stays consistent. Read
the file; for the dict it emits per search, change the stored query to the
nested form (apply the same `[verse GET book, chapter, verse [ … ]]` wrap around
the existing `[word … ]` block). If the script composes the flat query from a
condition string, wrap the final query string before writing it to the output
dict. Match whatever the file already does — the only requirement is the emitted
`mql` is the nested form.

- [ ] **Step 3: Verify the built gallery uses nested queries**

Run:

```bash
python3 -c "p=open('demo/index.html').read(); assert p.count('[verse GET book, chapter, verse') >= 5; print('gallery queries nested')"
pytest tests/test_build_demo.py -q
```

Expected: prints `gallery queries nested`; build test passes.

- [ ] **Step 4: Commit**

```bash
git add scripts/extract_showcase.py demo/showcase.json demo/index.html
git commit -m "feat(demo): gallery examples carry verse references (nested queries)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: CI check, README, push, verify, merge

**Files:**
- Modify: `.github/workflows/docker-smoke.yml`
- Modify: `README.md`

- [ ] **Step 1: Add a web-smoke reference assertion**

In `.github/workflows/docker-smoke.yml`, in the "Web smoke" step after the DROP
check, add a nested `/api/run` check that a reference comes back:

```yaml
          echo "POST /api/run nested -> first hit has a reference:"
          curl -fsS -X POST http://localhost:8001/api/run \
            -H 'content-type: application/json' \
            -d '{"mql":"SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse [word lex='"'"'BR>['"'"' GET g_word_utf8, gloss]] GO"}' \
            | jq -e '.results[0].reference == "Genesis 1:1"' >/dev/null
```

- [ ] **Step 2: Note the feature in the README**

In `README.md`, in the "Try it (live demo)" section, add one sentence:

```markdown
Tick "Include the reference (book chapter:verse)" to get each hit's location.
```

- [ ] **Step 3: Full suite green, then push the branch**

Run: `pytest -q` (expected PASS), then:

```bash
git add .github/workflows/docker-smoke.yml README.md
git commit -m "ci+docs: verify nested /api/run returns a reference; note the checkbox

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push -u origin verse-references
```

- [ ] **Step 4: Watch both CI workflows**

Run:
```bash
gh run watch "$(gh run list --branch verse-references --workflow emdros-tests --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
gh run watch "$(gh run list --branch verse-references --workflow docker-smoke --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```
Expected: both succeed — `emdros-tests` confirms bara's first hit is Genesis 1:1;
`docker-smoke` confirms the nested `/api/run` returns `"Genesis 1:1"`.

- [ ] **Step 5: Merge + live acceptance**

Merge `verse-references` → `main`. After Render redeploys `shebanq-web`, on the
live page ask "where does the word shana (year) occur?" with the box checked →
results show `book chap:verse`; uncheck and re-translate → the flat query, no
references.

---

## Self-review notes

- **Spec coverage:** checkbox default-on (Task 5) · server-side deterministic wrap (Task 2) · model stays flat / translation unaffected (Task 3 wraps post-translate) · runner nested harvest, flat path unchanged, count = leaves, propagate book/chapter/verse (Task 1) · formatter unchanged (relies on the row keys it already reads) · honest shown=run query (the wrapped query is what's returned and run) · gallery consistency (Task 7) · flat `run_mql` still works / no refs (Task 1 flat branch, Task 6 flat test) · unit tests via fake env + emdros-marked real-DB test (Tasks 1, 6) · CI web check (Task 8). All spec sections map to a task.
- **Risk handled:** container-vs-leaf is driven by parsed nesting depth (`depth >= len(get_lists) - 1`), so `getSheaf()` is only ever called on containers — the "getSheaf on a leaf" Emdros unknown from the spec is avoided.
- **Type consistency:** `_parse_get_lists(mql) -> list[list[str]]`, `_harvest_nested(sheaf, get_lists, depth, ctx, matches, total, limit)`, `run_query(mql, db_path, features=None, limit=None) -> RunResult`, `_wrap_in_verse(mql) -> str`, `handle_translate(question, references=False) -> dict`, the `translate(question, references)` callable in `make_routes`/`register_web_routes`, and the `references` JSON field are used consistently across tasks. `_REF_KEYS = ("book","chapter","verse")` matches `formatter._reference`.
```
