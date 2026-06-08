# SHEBANQ MCP Core Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that turns plain-language questions about the Hebrew Bible (BHSA) into citable MQL queries and runs them on a local Emdros engine, returning the query plus glossed, verse-referenced results.

**Architecture:** Four units behind a small MCP surface. A static **feature reference** (the BHSA feature catalogue as JSON) grounds MQL composition. A **validator** rejects MQL that references unknown features/values before anything runs. An **Emdros runner** executes validated MQL against a read-only BHSA SQLite database. A **formatter** turns raw node matches into glossed results. The MCP **server** exposes `run_mql`, `lookup_feature` (both LLM-free) and `search_bhsa` (which calls the Anthropic API to translate NL→MQL, then reuses the same pipeline).

**Tech Stack:** Python 3.11+, `mcp` SDK, Emdros (SQLite backend, SWIG Python binding), `anthropic` SDK, `pytest`, Docker (Render Pro deploy — separate plan).

**Scope note:** This plan delivers the core server only. The demo web app (Netlify front-end + precomputed featured searches) is a separate follow-on plan that consumes this server.

---

## File Structure

```
shebanq-mcp/
  pyproject.toml                      # package + deps + pytest config
  .gitignore                          # ignore data/*.mql, data/*.sqlite3
  README.md
  data/
    bhsa.mql                          # source MQL dump (gitignored, large)
    bhsa.sqlite3                      # built Emdros DB (gitignored, large)
  src/shebanq_mcp/
    __init__.py
    features.json                     # generated BHSA feature catalogue
    feature_reference.py              # load + query the catalogue
    validator.py                      # validate MQL against the catalogue
    runner.py                         # execute MQL via Emdros, return raw matches
    formatter.py                      # raw matches -> glossed result dicts
    translate.py                      # NL -> MQL via Anthropic API
    server.py                         # MCP server, 3 tools
  scripts/
    spike_emdros.py                   # one-off: confirm Emdros Python API + data
    build_features.py                 # generate features.json
  tests/
    conftest.py                       # shared fixtures (db path, feature ref)
    test_feature_reference.py
    test_validator.py
    test_runner.py
    test_formatter.py
    test_translate.py
    test_featured_searches.py         # end-to-end fixtures (backbone tests)
    fixtures/
      featured_searches.json          # {question, mql, expected_count} cases
```

**Responsibilities (each file does one thing):**
- `feature_reference.py` — read-only access to `features.json`; no MQL knowledge.
- `validator.py` — pure function: MQL string + feature reference → ok / errors.
- `runner.py` — pure execution: validated MQL → raw node matches. No grammar.
- `formatter.py` — raw matches → display dicts (refs, Hebrew, glosses).
- `translate.py` — NL question + feature reference → candidate MQL (LLM call).
- `server.py` — wiring only; orchestrates the above into 3 MCP tools.

---

## Task 0: Project skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/shebanq_mcp/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "shebanq-mcp"
version = "0.1.0"
description = "MCP server for querying the BHSA Hebrew Bible via Emdros/MQL"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.2.0",
    "anthropic>=0.40.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
shebanq_mcp = ["features.json"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["emdros: requires a built BHSA Emdros database"]
```

Note: the Emdros Python binding is installed at the system/Docker level (it is a
SWIG-built C extension, not a pip wheel), so it is intentionally absent from
`dependencies`. Tests that need it use the `emdros` marker and skip when it is
unavailable (see Task 4).

- [ ] **Step 2: Create `.gitignore`**

```gitignore
data/*.mql
data/*.sqlite3
__pycache__/
*.egg-info/
.pytest_cache/
.venv/
```

- [ ] **Step 3: Create empty `src/shebanq_mcp/__init__.py`**

```python
"""SHEBANQ MCP server: NL -> MQL -> Emdros results over the BHSA Hebrew Bible."""
```

- [ ] **Step 4: Create `tests/conftest.py` with the shared db-path fixture**

```python
import os
import shutil
import pytest

DB_PATH = os.environ.get("BHSA_SQLITE", "data/bhsa.sqlite3")


def _emdros_available() -> bool:
    if shutil.which("mql") is None and not os.path.exists(DB_PATH):
        return False
    try:
        import emdros  # noqa: F401
    except ImportError:
        return False
    return os.path.exists(DB_PATH)


@pytest.fixture
def db_path() -> str:
    return DB_PATH


@pytest.fixture(autouse=False)
def require_emdros():
    if not _emdros_available():
        pytest.skip("Emdros binding or BHSA database not available")
```

- [ ] **Step 5: Verify the skeleton installs and pytest collects nothing yet**

Run: `pip install -e ".[dev]" && pytest -q`
Expected: `no tests ran` (exit 0, 0 tests collected).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore src/shebanq_mcp/__init__.py tests/conftest.py
git commit -m "chore: project skeleton for shebanq-mcp"
```

---

## Task 1: Emdros + data spike (verification, not TDD)

This task pins down the real Emdros Python API and produces the BHSA SQLite
database everything else depends on. It is a manual verification spike: its
output is a working `data/bhsa.sqlite3` and a confirmed API contract, not a unit
test. Do this before Task 4.

**Files:**
- Create: `scripts/spike_emdros.py`

- [ ] **Step 1: Acquire the BHSA MQL dump**

The ETCBC ships the data in MQL format. Download the BHSA MQL dump (e.g. the
`shebanq` subdirectory of the `ETCBC/bhsa` release assets) to `data/bhsa.mql`.
Pin a single version; record it in `README.md` (open question in the spec —
default to the latest stable `2021` release unless told otherwise).

- [ ] **Step 2: Build the SQLite database with Emdros**

Run (requires Emdros `mql` CLI installed):
```bash
mql --backend sqlite3 -d data/bhsa.sqlite3 data/bhsa.mql
```
Expected: `data/bhsa.sqlite3` is created (hundreds of MB).

- [ ] **Step 3: Write `scripts/spike_emdros.py` to confirm the Python API**

```python
"""Spike: confirm the Emdros Python binding API against the built BHSA db.

Run: python scripts/spike_emdros.py data/bhsa.sqlite3
Prints the number of matches for a tiny known query and the first object id.
This file documents the exact API the runner depends on.
"""
import sys
import emdros

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"

env = emdros.EmdrosEnv(
    emdros.kOKConsole, emdros.kCSUTF8,
    "", "", DB, emdros.BACKEND_SQLITE3,
)

QUERY = "SELECT ALL OBJECTS WHERE [word lex='BR>' ] GO"
ok = env.executeString(QUERY, True, False, True)
if not ok:
    print("compiler error:", env.getCompilerError())
    sys.exit(1)

sheaf = env.getSheaf()
count = 0
first_id = None
it = sheaf.const_iterator()
while it.hasNext():
    straw = it.next()
    sit = straw.const_iterator()
    while sit.hasNext():
        mo = sit.next()
        if first_id is None:
            first_id = mo.getID_D()
        count += 1

print("matches:", count, "first id:", first_id)
```

- [ ] **Step 4: Run the spike and record the real API**

Run: `python scripts/spike_emdros.py data/bhsa.sqlite3`
Expected: prints a non-zero match count and a numeric object id.

If the installed binding differs (constructor args, iterator method names), edit
`scripts/spike_emdros.py` until it runs, then treat the working version as the
**API contract** for Task 4. The runner code in Task 4 must match whatever this
spike proves to work.

- [ ] **Step 5: Commit the spike (data files stay gitignored)**

```bash
git add scripts/spike_emdros.py
git commit -m "chore: emdros api spike + bhsa db build instructions"
```

---

## Task 2: Feature reference

**Files:**
- Create: `scripts/build_features.py`
- Create: `src/shebanq_mcp/features.json`
- Create: `src/shebanq_mcp/feature_reference.py`
- Test: `tests/test_feature_reference.py`

The catalogue maps each BHSA feature to a human gloss and (for enumerated
features) its valid values with glosses. `build_features.py` generates it; the
runtime only reads the committed `features.json`.

- [ ] **Step 1: Create a minimal hand-seeded `src/shebanq_mcp/features.json`**

Start with a small, correct seed covering the features the featured searches use.
Expand later via `build_features.py`.

```json
{
  "version": "bhsa-2021",
  "features": {
    "lex": {"gloss": "lexeme (dictionary form)", "values": null},
    "sp": {
      "gloss": "part of speech",
      "values": {
        "verb": "verb", "subs": "noun", "nmpr": "proper noun",
        "advb": "adverb", "prep": "preposition", "conj": "conjunction",
        "art": "article", "pron": "pronoun", "intj": "interjection",
        "nega": "negative", "inrg": "interrogative", "prde": "demonstrative",
        "prin": "interrogative pronoun", "prps": "personal pronoun"
      }
    },
    "vs": {
      "gloss": "verbal stem",
      "values": {
        "qal": "Qal", "nif": "Niphal", "piel": "Piel", "pual": "Pual",
        "hif": "Hiphil", "hof": "Hophal", "hit": "Hitpael"
      }
    },
    "vt": {
      "gloss": "verbal tense",
      "values": {
        "perf": "perfect", "impf": "imperfect", "wayq": "wayyiqtol",
        "impv": "imperative", "infa": "infinitive absolute",
        "infc": "infinitive construct", "ptca": "active participle",
        "ptcp": "passive participle"
      }
    },
    "function": {
      "gloss": "phrase function in the clause",
      "values": {
        "Pred": "predicate", "Subj": "subject", "Objc": "object",
        "Cmpl": "complement", "Adju": "adjunct", "Time": "time",
        "Loca": "location", "Modi": "modifier"
      }
    }
  }
}
```

- [ ] **Step 2: Write the failing test for `feature_reference.py`**

```python
from shebanq_mcp.feature_reference import FeatureReference


def test_known_feature_has_gloss():
    ref = FeatureReference.load()
    assert ref.feature_gloss("vs") == "verbal stem"


def test_known_value_is_valid():
    ref = FeatureReference.load()
    assert ref.is_valid("vs", "nif") is True


def test_unknown_value_is_invalid():
    ref = FeatureReference.load()
    assert ref.is_valid("vs", "niphal") is False


def test_unknown_feature_is_invalid():
    ref = FeatureReference.load()
    assert ref.is_valid("bogus", "x") is False


def test_open_valued_feature_accepts_any_value():
    ref = FeatureReference.load()
    assert ref.is_valid("lex", "BR>") is True


def test_lookup_returns_value_table():
    ref = FeatureReference.load()
    result = ref.lookup("vs")
    assert result["gloss"] == "verbal stem"
    assert result["values"]["nif"] == "Niphal"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest tests/test_feature_reference.py -v`
Expected: FAIL with `ModuleNotFoundError: shebanq_mcp.feature_reference`.

- [ ] **Step 4: Implement `src/shebanq_mcp/feature_reference.py`**

```python
import json
from importlib import resources
from dataclasses import dataclass


@dataclass
class FeatureReference:
    version: str
    features: dict

    @classmethod
    def load(cls) -> "FeatureReference":
        text = resources.files("shebanq_mcp").joinpath("features.json").read_text(
            encoding="utf-8"
        )
        data = json.loads(text)
        return cls(version=data["version"], features=data["features"])

    def has_feature(self, name: str) -> bool:
        return name in self.features

    def feature_gloss(self, name: str) -> str | None:
        f = self.features.get(name)
        return f["gloss"] if f else None

    def is_valid(self, feature: str, value: str) -> bool:
        f = self.features.get(feature)
        if f is None:
            return False
        values = f.get("values")
        if values is None:  # open-valued feature (e.g. lex)
            return True
        return value in values

    def lookup(self, feature: str) -> dict | None:
        return self.features.get(feature)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_feature_reference.py -v`
Expected: 6 passed.

- [ ] **Step 6: Write `scripts/build_features.py` (catalogue generator)**

```python
"""Generate src/shebanq_mcp/features.json from the ETCBC BHSA feature docs.

The ETCBC publishes per-feature Markdown docs under bhsa/docs/features/. Each
documents a feature name, description, and (for enumerations) its value codes.
This script parses those docs into the features.json schema used at runtime.

Usage: python scripts/build_features.py <path-to-bhsa/docs/features> <out.json>

This is a build-time tool; runtime never imports it. Keep the hand-seeded
features.json as the source of truth until this generator is validated against
it (the seeded entries must round-trip identically).
"""
import json
import sys
from pathlib import Path


def parse_feature_doc(path: Path) -> dict | None:
    # ETCBC feature docs are Markdown. Extract the gloss (first description line)
    # and any value table. Doc structure varies; this parser targets the common
    # "## Values" table form and returns None for features without one.
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    gloss = next((ln.lstrip("# ").strip() for ln in lines if not ln.startswith("#")), path.stem)
    values: dict[str, str] = {}
    in_values = False
    for ln in lines:
        if ln.lower().startswith("## value"):
            in_values = True
            continue
        if in_values and ln.startswith("|") and "|" in ln[1:]:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("value", "---", ""):
                values[cells[0]] = cells[1]
    return {"gloss": gloss, "values": values or None}


def main() -> None:
    docs_dir = Path(sys.argv[1])
    out = Path(sys.argv[2])
    features = {}
    for doc in sorted(docs_dir.glob("*.md")):
        parsed = parse_feature_doc(doc)
        if parsed:
            features[doc.stem] = parsed
    out.write_text(
        json.dumps({"version": "bhsa-2021", "features": features}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {len(features)} features to {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Commit**

```bash
git add scripts/build_features.py src/shebanq_mcp/features.json src/shebanq_mcp/feature_reference.py tests/test_feature_reference.py
git commit -m "feat: BHSA feature reference + catalogue generator"
```

---

## Task 3: MQL validator

**Files:**
- Create: `src/shebanq_mcp/validator.py`
- Test: `tests/test_validator.py`

The validator extracts `feature=value` and `feature` references from an MQL
string and checks each against the feature reference. It is intentionally
lenient about MQL grammar (Emdros is the real parser) and strict about feature
vocabulary (the thing the model hallucinates).

- [ ] **Step 1: Write the failing tests**

```python
from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.validator import validate_mql, ValidationResult


def _ref():
    return FeatureReference.load()


def test_valid_query_passes():
    mql = "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True
    assert result.errors == []


def test_unknown_value_fails_with_message():
    mql = "SELECT ALL OBJECTS WHERE [word vs='niphal'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("niphal" in e and "vs" in e for e in result.errors)


def test_unknown_feature_fails():
    mql = "SELECT ALL OBJECTS WHERE [word bogus='x'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("bogus" in e for e in result.errors)


def test_open_valued_feature_passes():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_double_quotes_are_handled():
    mql = 'SELECT ALL OBJECTS WHERE [word vs="nif"] GO'
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_multiple_constraints_all_checked():
    mql = "SELECT ALL OBJECTS WHERE [word sp='verb' AND vs='nif' AND vt='wayq'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_validator.py -v`
Expected: FAIL with `ModuleNotFoundError: shebanq_mcp.validator`.

- [ ] **Step 3: Implement `src/shebanq_mcp/validator.py`**

```python
import re
from dataclasses import dataclass, field

from .feature_reference import FeatureReference

# Matches `name='value'` or `name="value"` constraints inside MQL blocks.
_CONSTRAINT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|==)\s*(['\"])(.*?)\2")


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def validate_mql(mql: str, ref: FeatureReference) -> ValidationResult:
    errors: list[str] = []
    for feature, _quote, value in _CONSTRAINT.findall(mql):
        if not ref.has_feature(feature):
            errors.append(
                f"unknown feature '{feature}' (not in BHSA feature reference)"
            )
        elif not ref.is_valid(feature, value):
            errors.append(
                f"invalid value '{value}' for feature '{feature}'"
            )
    return ValidationResult(ok=not errors, errors=errors)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_validator.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/validator.py tests/test_validator.py
git commit -m "feat: MQL validator against BHSA feature reference"
```

---

## Task 4: Emdros runner

**Files:**
- Create: `src/shebanq_mcp/runner.py`
- Test: `tests/test_runner.py`

Executes validated MQL against the BHSA SQLite db and returns raw matches as a
list of dicts: `{monad, id_d}` plus any requested feature values. Uses the API
proven in Task 1's spike — **if the spike's working code differs from below,
the spike wins; update this code to match it.**

- [ ] **Step 1: Write the failing test (marked `emdros`, skips without the db)**

```python
import pytest
from shebanq_mcp.runner import run_query, RunResult


@pytest.mark.emdros
def test_known_lexeme_returns_matches(require_emdros, db_path):
    # BR> ("bara", to create) — appears a small, stable number of times.
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>'] GO"
    result = run_query(mql, db_path)
    assert isinstance(result, RunResult)
    assert result.count > 0
    assert result.count == len(result.matches)
    assert "id_d" in result.matches[0]


@pytest.mark.emdros
def test_empty_result_is_honest(require_emdros, db_path):
    mql = "SELECT ALL OBJECTS WHERE [word lex='THIS_LEX_DOES_NOT_EXIST'] GO"
    result = run_query(mql, db_path)
    assert result.count == 0
    assert result.matches == []
```

- [ ] **Step 2: Run the test to verify it fails (or skips cleanly)**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: shebanq_mcp.runner` when the module is
absent. (After the module exists but before a db is built, it must SKIP, not
error — confirm the `require_emdros` fixture skips.)

- [ ] **Step 3: Implement `src/shebanq_mcp/runner.py`**

```python
from dataclasses import dataclass, field

import emdros


@dataclass
class RunResult:
    count: int
    matches: list[dict] = field(default_factory=list)


def _make_env(db_path: str) -> "emdros.EmdrosEnv":
    return emdros.EmdrosEnv(
        emdros.kOKConsole,
        emdros.kCSUTF8,
        "", "", db_path,
        emdros.BACKEND_SQLITE3,
    )


def run_query(mql: str, db_path: str) -> RunResult:
    env = _make_env(db_path)
    ok = env.executeString(mql, True, False, True)
    if not ok:
        raise RuntimeError(f"Emdros error: {env.getCompilerError()}")

    sheaf = env.getSheaf()
    matches: list[dict] = []
    it = sheaf.const_iterator()
    while it.hasNext():
        straw = it.next()
        sit = straw.const_iterator()
        while sit.hasNext():
            mo = sit.next()
            matches.append({"id_d": mo.getID_D(), "monad": mo.getFirst()})
    return RunResult(count=len(matches), matches=matches)
```

- [ ] **Step 4: Build the db (Task 1) if not done, then run the test**

Run: `BHSA_SQLITE=data/bhsa.sqlite3 pytest tests/test_runner.py -v -m emdros`
Expected: 2 passed (or skipped with a clear message if no db/binding).

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/runner.py tests/test_runner.py
git commit -m "feat: Emdros MQL runner over BHSA SQLite"
```

---

## Task 5: Result formatter

**Files:**
- Create: `src/shebanq_mcp/formatter.py`
- Test: `tests/test_formatter.py`

Turns raw matches into display dicts. To stay unit-testable without a live
Emdros db, the formatter takes already-extracted match dicts (with feature
values the runner can fetch) and shapes them — it does not itself talk to Emdros.
The runner is extended to fetch the display features the formatter needs.

- [ ] **Step 1: Extend the runner to fetch display features (write failing test)**

Add to `tests/test_runner.py`:

```python
@pytest.mark.emdros
def test_run_query_with_features_returns_values(require_emdros, db_path):
    mql = (
        "SELECT ALL OBJECTS WHERE "
        "[word lex='BR>' GET sp, vs, gloss] GO"
    )
    result = run_query(mql, db_path, features=["sp", "vs", "gloss"])
    assert result.count > 0
    first = result.matches[0]
    assert "sp" in first and "gloss" in first
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_runner.py::test_run_query_with_features_returns_values -v -m emdros`
Expected: FAIL — `run_query()` got an unexpected keyword argument `features`.

- [ ] **Step 3: Extend `run_query` to accept and harvest `features`**

Replace the body of `run_query` in `src/shebanq_mcp/runner.py`:

```python
def run_query(mql: str, db_path: str, features: list[str] | None = None) -> RunResult:
    features = features or []
    env = _make_env(db_path)
    ok = env.executeString(mql, True, False, True)
    if not ok:
        raise RuntimeError(f"Emdros error: {env.getCompilerError()}")

    sheaf = env.getSheaf()
    matches: list[dict] = []
    it = sheaf.const_iterator()
    while it.hasNext():
        straw = it.next()
        sit = straw.const_iterator()
        while sit.hasNext():
            mo = sit.next()
            row = {"id_d": mo.getID_D(), "monad": mo.getFirst()}
            for i, feat in enumerate(features):
                row[feat] = mo.getFeatureAsString(i)
            matches.append(row)
    return RunResult(count=len(matches), matches=matches)
```

Note: `getFeatureAsString(i)` returns the i-th feature named in the MQL `GET`
clause, in order. The caller must pass `features` in the same order as the `GET`
clause. This ordering contract is verified by Step 2's test.

- [ ] **Step 4: Run the runner test to verify it passes**

Run: `pytest tests/test_runner.py -v -m emdros`
Expected: 3 passed.

- [ ] **Step 5: Write the failing formatter test**

```python
from shebanq_mcp.formatter import format_results


def test_format_adds_reference_and_keeps_glosses():
    raw = [
        {"id_d": 1, "monad": 5, "sp": "verb", "vs": "qal", "gloss": "create",
         "book": "Genesis", "chapter": 1, "verse": 1},
    ]
    out = format_results(raw)
    assert out[0]["reference"] == "Genesis 1:1"
    assert out[0]["gloss"] == "create"
    assert out[0]["features"]["vs"] == "qal"


def test_format_handles_missing_locator_gracefully():
    raw = [{"id_d": 2, "monad": 9, "gloss": "x"}]
    out = format_results(raw)
    assert out[0]["reference"] is None
    assert out[0]["gloss"] == "x"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/test_formatter.py -v`
Expected: FAIL with `ModuleNotFoundError: shebanq_mcp.formatter`.

- [ ] **Step 7: Implement `src/shebanq_mcp/formatter.py`**

```python
_RESERVED = {"id_d", "monad", "book", "chapter", "verse", "gloss", "text"}


def _reference(row: dict) -> str | None:
    book, chap, verse = row.get("book"), row.get("chapter"), row.get("verse")
    if book and chap and verse:
        return f"{book} {chap}:{verse}"
    return None


def format_results(raw: list[dict]) -> list[dict]:
    out = []
    for row in raw:
        features = {k: v for k, v in row.items() if k not in _RESERVED}
        out.append({
            "id_d": row.get("id_d"),
            "reference": _reference(row),
            "text": row.get("text"),
            "gloss": row.get("gloss"),
            "features": features,
        })
    return out
```

- [ ] **Step 8: Run the formatter test to verify it passes**

Run: `pytest tests/test_formatter.py -v`
Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add src/shebanq_mcp/runner.py src/shebanq_mcp/formatter.py tests/test_runner.py tests/test_formatter.py
git commit -m "feat: harvest display features + format glossed results"
```

---

## Task 6: NL -> MQL translation

**Files:**
- Create: `src/shebanq_mcp/translate.py`
- Test: `tests/test_translate.py`

Translates a plain-language question into candidate MQL by calling the Anthropic
API with the feature reference injected into the system prompt. The Anthropic
client is injected so the unit test uses a fake — no network in tests.

- [ ] **Step 1: Write the failing test with a fake client**

```python
from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.translate import translate_to_mql


class _FakeBlock:
    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeMessage(self._text)


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def test_translate_returns_mql_string():
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    mql = translate_to_mql("all niphal verbs", FeatureReference.load(), client=client)
    assert mql == "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"


def test_translate_injects_feature_reference_into_prompt():
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    translate_to_mql("all niphal verbs", FeatureReference.load(), client=client)
    system = client.messages.last_kwargs["system"]
    assert "vs" in system and "Niphal" in system


def test_translate_strips_code_fences():
    fenced = "```\nSELECT ALL OBJECTS WHERE [word vs='nif'] GO\n```"
    client = _FakeClient(fenced)
    mql = translate_to_mql("x", FeatureReference.load(), client=client)
    assert mql.startswith("SELECT") and "```" not in mql
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_translate.py -v`
Expected: FAIL with `ModuleNotFoundError: shebanq_mcp.translate`.

- [ ] **Step 3: Implement `src/shebanq_mcp/translate.py`**

```python
import json

from .feature_reference import FeatureReference

_MODEL = "claude-opus-4-8"

_INSTRUCTIONS = """You translate questions about the Hebrew Bible into Emdros \
MQL queries over the BHSA database. Output ONLY the MQL query, nothing else: no \
explanation, no code fences. Use only the features and values listed below. \
Prefer querying the appropriate object type (word, phrase, clause, sentence). \
Always end the query with GO. Add a GET clause listing the features needed to \
display results (e.g. GET sp, gloss).

BHSA feature reference (feature: gloss; valid values):
{reference}"""


def _reference_block(ref: FeatureReference) -> str:
    lines = []
    for name, spec in ref.features.items():
        values = spec.get("values")
        if values:
            vals = ", ".join(f"{k}={v}" for k, v in values.items())
            lines.append(f"- {name}: {spec['gloss']}; values: {vals}")
        else:
            lines.append(f"- {name}: {spec['gloss']}; (open value)")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _default_client():
    import anthropic
    return anthropic.Anthropic()


def translate_to_mql(question: str, ref: FeatureReference, client=None) -> str:
    client = client or _default_client()
    system = _INSTRUCTIONS.format(reference=_reference_block(ref))
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return _strip_fences(msg.content[0].text)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_translate.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/translate.py tests/test_translate.py
git commit -m "feat: NL->MQL translation via Anthropic API with feature reference"
```

---

## Task 7: MCP server (3 tools)

**Files:**
- Create: `src/shebanq_mcp/server.py`
- Test: `tests/test_server.py`

Wires the pipeline into three MCP tools. Pure orchestration. The tool handlers
are factored into plain functions so they can be unit-tested without an MCP
transport; the MCP decorators call those functions.

Pipeline shared by `run_mql` and `search_bhsa`:
`validate -> (reject if invalid) -> run -> format -> {mql, count, results}`.

- [ ] **Step 1: Write the failing tests for the handler functions**

```python
from shebanq_mcp import server


def test_get_features_extracts_clause_in_order():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>' GET sp, vs, gloss] GO"
    assert server._get_features(mql) == ["sp", "vs", "gloss"]


def test_get_features_empty_when_no_get_clause():
    mql = "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"
    assert server._get_features(mql) == []


def test_lookup_feature_returns_table():
    out = server.handle_lookup_feature("vs")
    assert out["gloss"] == "verbal stem"
    assert out["values"]["nif"] == "Niphal"


def test_lookup_feature_unknown_returns_error_field():
    out = server.handle_lookup_feature("bogus")
    assert out["error"]


def test_run_mql_rejects_invalid_before_running(monkeypatch):
    called = {"ran": False}

    def _should_not_run(*a, **k):
        called["ran"] = True

    monkeypatch.setattr(server, "run_query", _should_not_run)
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word vs='niphal'] GO")
    assert out["error"]
    assert "niphal" in " ".join(out["validation_errors"])
    assert called["ran"] is False


def test_run_mql_valid_runs_and_formats(monkeypatch):
    from shebanq_mcp.runner import RunResult

    def _fake_run(mql, db_path, features=None):
        return RunResult(count=1, matches=[
            {"id_d": 1, "monad": 5, "gloss": "create",
             "book": "Genesis", "chapter": 1, "verse": 1}
        ])

    monkeypatch.setattr(server, "run_query", _fake_run)
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    assert out["mql"].startswith("SELECT")
    assert out["result_count"] == 1
    assert out["results"][0]["reference"] == "Genesis 1:1"


def test_search_bhsa_translates_then_runs(monkeypatch):
    from shebanq_mcp.runner import RunResult

    monkeypatch.setattr(
        server, "translate_to_mql",
        lambda q, ref: "SELECT ALL OBJECTS WHERE [word vs='nif'] GO",
    )
    monkeypatch.setattr(
        server, "run_query",
        lambda mql, db_path, features=None: RunResult(count=0, matches=[]),
    )
    out = server.handle_search_bhsa("all niphal verbs")
    assert out["mql"].startswith("SELECT")
    assert out["result_count"] == 0
    assert out["results"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: shebanq_mcp.server`.

- [ ] **Step 3: Implement `src/shebanq_mcp/server.py`**

```python
import os
import re

from mcp.server.fastmcp import FastMCP

from .feature_reference import FeatureReference
from .validator import validate_mql
from .runner import run_query
from .formatter import format_results
from .translate import translate_to_mql

DB_PATH = os.environ.get("BHSA_SQLITE", "data/bhsa.sqlite3")

# Matches the feature list inside an MQL `GET a, b, c` clause.
_GET_CLAUSE = re.compile(r"\bGET\s+([A-Za-z0-9_,\s]+?)\s*\]")

_ref = FeatureReference.load()
mcp = FastMCP("shebanq")


def handle_lookup_feature(name_or_term: str) -> dict:
    spec = _ref.lookup(name_or_term)
    if spec is None:
        return {"error": f"unknown feature '{name_or_term}'"}
    return {"feature": name_or_term, "gloss": spec["gloss"], "values": spec.get("values")}


def _get_features(mql: str) -> list[str]:
    """Extract the GET-clause feature list (in order) so the runner harvests
    exactly the features the query requested, by their GET index."""
    m = _GET_CLAUSE.search(mql)
    if not m:
        return []
    return [f.strip() for f in m.group(1).split(",") if f.strip()]


def _run_pipeline(mql: str) -> dict:
    validation = validate_mql(mql, _ref)
    if not validation.ok:
        return {"mql": mql, "error": "MQL failed validation",
                "validation_errors": validation.errors}
    result = run_query(mql, DB_PATH, features=_get_features(mql))
    return {"mql": mql, "result_count": result.count,
            "results": format_results(result.matches)}


def handle_run_mql(mql: str) -> dict:
    return _run_pipeline(mql)


def handle_search_bhsa(question: str) -> dict:
    mql = translate_to_mql(question, _ref)
    return _run_pipeline(mql)


@mcp.tool()
def lookup_feature(name_or_term: str) -> dict:
    """Look up a BHSA feature: its gloss and valid values."""
    return handle_lookup_feature(name_or_term)


@mcp.tool()
def run_mql(mql: str) -> dict:
    """Validate and run an MQL query; return the query and glossed results."""
    return handle_run_mql(mql)


@mcp.tool()
def search_bhsa(question: str) -> dict:
    """Answer a plain-language question: returns the generated MQL and results."""
    return handle_search_bhsa(question)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: 7 passed.

- [ ] **Step 5: Add the console entry point to `pyproject.toml`**

Add under `[project]`:

```toml
[project.scripts]
shebanq-mcp = "shebanq_mcp.server:main"
```

- [ ] **Step 6: Reinstall and verify the entry point exists**

Run: `pip install -e ".[dev]" && which shebanq-mcp`
Expected: prints a path to the `shebanq-mcp` executable.

- [ ] **Step 7: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server.py pyproject.toml
git commit -m "feat: MCP server exposing run_mql, lookup_feature, search_bhsa"
```

---

## Task 8: Featured-search backbone tests

**Files:**
- Create: `tests/fixtures/featured_searches.json`
- Test: `tests/test_featured_searches.py`

These are the regression backbone and (later) the demo gallery content. Each case
is a question with a known-good MQL and an expected match count, run end-to-end
against the real db. They are marked `emdros` and skip without it.

- [ ] **Step 1: Create `tests/fixtures/featured_searches.json`**

Seed with cases whose MQL has been confirmed by running it (counts are filled in
from real runs during Step 3 — do not invent counts).

```json
[
  {
    "id": "niphal-verbs",
    "question": "Find all Niphal verbs in the Hebrew Bible.",
    "mql": "SELECT ALL OBJECTS WHERE [word sp='verb' AND vs='nif' GET sp, vs, gloss] GO",
    "expected_count": null
  },
  {
    "id": "bara-occurrences",
    "question": "Where does the verb BR> (to create) occur?",
    "mql": "SELECT ALL OBJECTS WHERE [word lex='BR>' GET lex, gloss] GO",
    "expected_count": null
  }
]
```

- [ ] **Step 2: Write the test that runs every fixture and checks validity + count**

```python
import json
from pathlib import Path

import pytest

from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.validator import validate_mql
from shebanq_mcp.runner import run_query

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "featured_searches.json").read_text()
)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_featured_mql_is_valid(case):
    result = validate_mql(case["mql"], FeatureReference.load())
    assert result.ok, f"{case['id']}: {result.errors}"


@pytest.mark.emdros
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_featured_count_matches(require_emdros, db_path, case):
    if case["expected_count"] is None:
        pytest.skip(f"{case['id']}: expected_count not yet pinned")
    result = run_query(case["mql"], db_path)
    assert result.count == case["expected_count"]
```

- [ ] **Step 3: Pin the expected counts from real runs**

Run each fixture's MQL against the db and record the real count:
```bash
BHSA_SQLITE=data/bhsa.sqlite3 python -c "
import json
from shebanq_mcp.runner import run_query
for c in json.load(open('tests/fixtures/featured_searches.json')):
    print(c['id'], run_query(c['mql'], 'data/bhsa.sqlite3').count)
"
```
Edit `featured_searches.json`, replacing each `null` `expected_count` with the
printed number. Re-run and confirm the count tests now pass instead of skip.

- [ ] **Step 4: Run the full featured-search suite**

Run: `BHSA_SQLITE=data/bhsa.sqlite3 pytest tests/test_featured_searches.py -v`
Expected: validity tests pass; count tests pass (no longer skipped).

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/featured_searches.json tests/test_featured_searches.py
git commit -m "test: featured-search backbone fixtures and regression tests"
```

---

## Task 9: README and run instructions

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# shebanq-mcp

MCP server for querying the BHSA Hebrew Bible (the ETCBC database behind
SHEBANQ) in plain language. Returns a citable MQL query plus glossed,
verse-referenced results, produced by a local Emdros engine.

## Tools
- `search_bhsa(question)` — NL question -> generated MQL + results
- `run_mql(mql)` — validate and run MQL you already have
- `lookup_feature(name_or_term)` — BHSA feature gloss + valid values

## Setup
1. Install Emdros (provides the `mql` CLI and the `emdros` Python binding).
2. Build the database (see Data below).
3. `pip install -e ".[dev]"`
4. Set `ANTHROPIC_API_KEY` (needed only for `search_bhsa`).
5. Run: `BHSA_SQLITE=data/bhsa.sqlite3 shebanq-mcp`

## Data
BHSA version: **2021** (pinned). Download the MQL dump to `data/bhsa.mql`, then:
`mql --backend sqlite3 -d data/bhsa.sqlite3 data/bhsa.mql`
Data files are gitignored.

## Tests
- `pytest -q` runs unit tests (no db required).
- `BHSA_SQLITE=data/bhsa.sqlite3 pytest -m emdros` runs db-backed tests.

## Deploy
Render Pro Web Service (Docker, Emdros-on-SQLite, data baked into the image).
See the separate deploy plan.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, tools, data, and test instructions"
```

---

## Done criteria

- `pytest -q` (no db) passes: feature reference, validator, formatter,
  translate, server-handler tests all green.
- With a built db, `pytest -m emdros` passes: runner + featured-search counts.
- `shebanq-mcp` starts and exposes three tools.
- Every result carries the exact MQL that produced it; invalid MQL is rejected
  before execution; empty results report honestly.

## Deferred to follow-on plans
- Demo web app (Netlify static + precomputed featured searches calling this server).
- Render Pro Dockerfile + deploy.
- `build_features.py` full catalogue generation validated against the seed.
- Whether `lookup_feature` returns usage examples per feature (spec open question).
