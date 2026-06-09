# Deploy the shebanq MCP server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the existing shebanq-mcp server as a public, always-on, remote MCP endpoint over streamable-HTTP on Render Pro, as a pure (LLM-free) query engine with safety guardrails, while keeping the local stdio path intact.

**Architecture:** Add a transport switch to `main()` (`MCP_TRANSPORT=stdio|http`). In HTTP mode, route `run_mql` execution through a `QueryGuard` that runs each Emdros query in a short-lived worker process with a concurrency cap and a hard timeout (terminate-on-overrun). Package everything in a multi-stage Docker image that builds Emdros + the BHSA SQLite DB from source, then ships a slim runtime. Deploy via a `render.yaml` blueprint; verify with a CI Docker smoke test and document Claude Desktop setup in the README.

**Tech Stack:** Python 3.11, `mcp` (FastMCP, streamable-HTTP), Emdros `rel-3-9-0` (SQLite backend + `EmdrosPy3` SWIG bindings), `multiprocessing`, Docker (multi-stage), Render Pro, GitHub Actions.

**Spec:** `docs/specs/2026-06-09-mcp-deploy-design.md`

**Branch:** `deploy-mcp` (already created).

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `pyproject.toml` | bump `mcp` to a streamable-HTTP-capable version | Modify |
| `src/shebanq_mcp/server.py` | transport switch, `/health` route, execution seam | Modify |
| `src/shebanq_mcp/guard.py` | `QueryGuard`: concurrency cap + per-query timeout via worker process | Create |
| `tests/__init__.py` | make `tests` an importable package (spawn needs it) | Create |
| `tests/guard_targets.py` | top-level worker targets used by guard tests (picklable under spawn) | Create |
| `tests/test_guard.py` | tests for `QueryGuard` | Create |
| `tests/test_server_transport.py` | tests for transport resolution + execution seam | Create |
| `Dockerfile` | multi-stage build: Emdros + BHSA DB → slim runtime | Create |
| `.dockerignore` | keep build context small | Create |
| `render.yaml` | Render Pro blueprint (Docker, env, health check) | Create |
| `scripts/smoke_mcp.py` | MCP client that calls `run_mql` against a running container | Create |
| `.github/workflows/docker-smoke.yml` | build image, run container, curl `/health`, MCP `run_mql` smoke | Create |
| `README.md` | "Connect in Claude Desktop" + deploy section | Modify |

---

## Task 1: Bump the `mcp` dependency for streamable-HTTP

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update the dependency pin**

In `pyproject.toml`, change the `mcp` line under `[project].dependencies`:

```toml
dependencies = [
    "mcp>=1.9.0",
    "anthropic>=0.40.0",
]
```

- [ ] **Step 2: Reinstall and verify the streamable-HTTP APIs exist**

Run:

```bash
python3 -m pip install -e ".[dev]"
python3 -c "from mcp.server.fastmcp import FastMCP; from mcp.client.streamable_http import streamablehttp_client; print('apis ok')"
```

Expected: prints `apis ok` with no ImportError. If `streamablehttp_client` is missing, raise the pin (try `mcp>=1.12.0`) and rerun.

- [ ] **Step 3: Confirm the existing suite still passes**

Run: `pytest -q`
Expected: all currently-passing tests pass (emdros-marked tests skip locally).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: require mcp>=1.9.0 for streamable-HTTP transport"
```

---

## Task 2: Introduce the execution seam in `server.py`

This decouples `_run_pipeline` from `run_query` so HTTP mode can swap in the guard without breaking existing tests (which monkeypatch `server.run_query`).

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_server_transport.py`:

```python
from shebanq_mcp import server
from shebanq_mcp.runner import RunResult


def test_run_pipeline_uses_executor_seam(monkeypatch):
    seen = {}

    def fake_executor(mql, features):
        seen["mql"] = mql
        seen["features"] = features
        return RunResult(count=2, matches=[])

    monkeypatch.setattr(server, "_executor", fake_executor)
    out = server.handle_run_mql(
        "SELECT ALL OBJECTS WHERE [word vs=nif GET sp, gloss] GO"
    )
    assert out["result_count"] == 2
    assert seen["features"] == ["sp", "gloss"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_server_transport.py::test_run_pipeline_uses_executor_seam -v`
Expected: FAIL with `AttributeError: ... has no attribute '_executor'`.

- [ ] **Step 3: Add the seam to `server.py`**

In `src/shebanq_mcp/server.py`, replace the `_run_pipeline` function with a seam-based version and add a default executor just above it:

```python
def _default_executor(mql: str, features: list[str]):
    """Default execution path: run directly in-process (stdio/local/tests)."""
    return run_query(mql, DB_PATH, features)


# Swappable execution backend. HTTP mode replaces this with the QueryGuard.
_executor = _default_executor


def _run_pipeline(mql: str) -> dict:
    validation = validate_mql(mql, _ref)
    if not validation.ok:
        return {"mql": mql, "error": "MQL failed validation",
                "validation_errors": validation.errors}
    result = _executor(mql, _get_features(mql))
    return {"mql": mql, "result_count": result.count,
            "results": format_results(result.matches)}
```

- [ ] **Step 4: Run the new test and the existing server tests**

Run: `pytest tests/test_server_transport.py tests/test_server.py -v`
Expected: all PASS. (Existing tests monkeypatch `server.run_query`, which `_default_executor` still calls, so they remain green.)

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "refactor: route run_mql through a swappable executor seam"
```

---

## Task 3: Transport resolution in `main()`

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_transport.py`:

```python
def test_resolve_transport_defaults_to_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    assert server._resolve_transport() == "stdio"


def test_resolve_transport_http(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    assert server._resolve_transport() == "streamable-http"


def test_resolve_transport_unknown_raises(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "carrier-pigeon")
    try:
        server._resolve_transport()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "carrier-pigeon" in str(exc)
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server_transport.py -v -k resolve_transport`
Expected: FAIL with `AttributeError: ... '_resolve_transport'`.

- [ ] **Step 3: Implement `_resolve_transport`**

In `src/shebanq_mcp/server.py`, add near the top (after `DB_PATH`):

```python
def _resolve_transport() -> str:
    """Map the MCP_TRANSPORT env var to a FastMCP transport name."""
    raw = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if raw in ("", "stdio"):
        return "stdio"
    if raw in ("http", "streamable-http"):
        return "streamable-http"
    raise ValueError(
        f"unknown MCP_TRANSPORT '{raw}' (supported: stdio, http)"
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_server_transport.py -v -k resolve_transport`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "feat: resolve MCP transport from MCP_TRANSPORT env"
```

---

## Task 4: `QueryGuard` — concurrency cap + per-query timeout

**Files:**
- Create: `src/shebanq_mcp/guard.py`
- Create: `tests/__init__.py`
- Create: `tests/guard_targets.py`
- Test: `tests/test_guard.py`

- [ ] **Step 1: Create the picklable worker targets and package marker**

Create empty `tests/__init__.py`:

```python
```

Create `tests/guard_targets.py` (top-level functions so `multiprocessing` spawn can import them by qualified name):

```python
"""Worker targets for QueryGuard tests. Must be importable (spawn pickles by
qualified name), so they live in an importable module, not inside a test."""
import time

from shebanq_mcp.runner import RunResult


def fast(mql, db_path, features, q):
    q.put(("ok", RunResult(count=3, matches=[])))


def slow(mql, db_path, features, q):
    time.sleep(3)
    q.put(("ok", RunResult(count=0, matches=[])))


def boom(mql, db_path, features, q):
    q.put(("err", "deliberate failure"))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_guard.py`:

```python
import time

import pytest

from shebanq_mcp.guard import QueryGuard, QueryTimeout
from shebanq_mcp.runner import RunResult
from tests import guard_targets


def test_guard_returns_result_on_success():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=5, target=guard_targets.fast)
    result = guard.run("SELECT ... GO", features=["sp"])
    assert isinstance(result, RunResult)
    assert result.count == 3


def test_guard_raises_on_timeout():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=0.5, target=guard_targets.slow)
    with pytest.raises(QueryTimeout):
        guard.run("SELECT ... GO")


def test_guard_propagates_worker_error():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=5, target=guard_targets.boom)
    with pytest.raises(RuntimeError) as exc:
        guard.run("SELECT ... GO")
    assert "deliberate failure" in str(exc.value)


def test_guard_caps_concurrency():
    # max_concurrent=1 forces two slow queries to serialize.
    guard = QueryGuard("unused.db", max_concurrent=1,
                       timeout_seconds=10, target=guard_targets.slow)
    import threading
    start = time.monotonic()
    threads = [threading.Thread(target=guard.run, args=("SELECT ... GO",))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start
    # Each slow target sleeps 3s; serialized => >= ~6s. Generous lower bound.
    assert elapsed >= 5.0
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shebanq_mcp.guard'`.

- [ ] **Step 4: Implement `guard.py`**

Create `src/shebanq_mcp/guard.py`:

```python
"""Concurrency- and timeout-bounded execution of Emdros queries.

A public, single-container deploy must survive a pathological MQL query that
would otherwise pin the CPU. Each query runs in a short-lived worker process so
the synchronous Emdros C call can be hard-killed on timeout (signals/threads
cannot reliably cancel it). A semaphore caps how many run at once.
"""
import multiprocessing
import queue as _queue
import threading

from .runner import RunResult, run_query


class QueryTimeout(Exception):
    """Raised when a query exceeds the configured wall-clock budget."""


def _default_target(mql, db_path, features, q):
    """Run a query in the worker process and ship the result over the queue."""
    try:
        res = run_query(mql, db_path, features)
        q.put(("ok", res))
    except Exception as exc:  # noqa: BLE001 - report any failure to the parent
        q.put(("err", repr(exc)))


class QueryGuard:
    """Runs each query in a worker process with a concurrency cap + timeout."""

    def __init__(self, db_path, max_concurrent=4, timeout_seconds=15,
                 target=_default_target):
        self._db_path = db_path
        self._timeout = timeout_seconds
        self._target = target
        self._sem = threading.Semaphore(max_concurrent)
        self._ctx = multiprocessing.get_context("spawn")

    def run(self, mql, features=None) -> RunResult:
        with self._sem:
            q = self._ctx.Queue()
            proc = self._ctx.Process(
                target=self._target,
                args=(mql, self._db_path, features or [], q),
            )
            proc.start()
            try:
                status, payload = q.get(timeout=self._timeout)
            except _queue.Empty:
                proc.terminate()
                proc.join()
                raise QueryTimeout(
                    f"query exceeded {self._timeout}s and was terminated"
                )
            proc.join()
            if status == "err":
                raise RuntimeError(payload)
            return payload
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_guard.py -v`
Expected: all PASS. (The concurrency test takes ~6s; that is expected.)

- [ ] **Step 6: Confirm the whole suite is green**

Run: `pytest -q`
Expected: PASS (emdros tests skip locally).

- [ ] **Step 7: Commit**

```bash
git add src/shebanq_mcp/guard.py tests/__init__.py tests/guard_targets.py tests/test_guard.py
git commit -m "feat: QueryGuard runs Emdros queries with a timeout + concurrency cap"
```

---

## Task 5: Wire the guard + `/health` + HTTP run into `main()`

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_transport.py`:

```python
def test_install_guard_swaps_executor(monkeypatch):
    monkeypatch.setattr(server, "_executor", server._default_executor)
    server._install_guard(max_concurrent=2, timeout_seconds=3)
    try:
        assert server._executor is not server._default_executor
    finally:
        server._executor = server._default_executor


def test_health_payload_is_ok():
    assert server._health_payload() == {"status": "ok", "service": "shebanq"}
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server_transport.py -v -k "install_guard or health_payload"`
Expected: FAIL with `AttributeError` for `_install_guard` / `_health_payload`.

- [ ] **Step 3: Implement guard install, health payload, the `/health` route, and the HTTP branch in `main()`**

In `src/shebanq_mcp/server.py`:

(a) Add an import near the top:

```python
from .guard import QueryGuard
```

(b) Add these helpers (place them after `_run_pipeline`):

```python
def _health_payload() -> dict:
    return {"status": "ok", "service": "shebanq"}


def _install_guard(max_concurrent: int, timeout_seconds: int) -> None:
    """Swap the executor to a process-isolated, timeout-bounded guard."""
    global _executor
    guard = QueryGuard(DB_PATH, max_concurrent=max_concurrent,
                       timeout_seconds=timeout_seconds)
    _executor = lambda mql, features: guard.run(mql, features)  # noqa: E731
```

(c) Register a health route (place after the `@mcp.tool()` definitions). The
`Request`/`JSONResponse` import is local to avoid pulling Starlette into the
stdio import path:

```python
@mcp.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ANN001 - Starlette Request
    from starlette.responses import JSONResponse
    return JSONResponse(_health_payload())
```

(d) Replace `main()`:

```python
def main() -> None:
    transport = _resolve_transport()
    if transport == "streamable-http":
        max_concurrent = int(os.environ.get("MAX_CONCURRENT_QUERIES", "4"))
        timeout_seconds = int(os.environ.get("QUERY_TIMEOUT_SECONDS", "15"))
        _install_guard(max_concurrent, timeout_seconds)
        mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_server_transport.py -v`
Expected: all PASS.

- [ ] **Step 5: Smoke-check that HTTP mode boots and serves `/health` locally**

Run (no Emdros needed for `/health`):

```bash
MCP_TRANSPORT=http PORT=8765 LLM_PROVIDER=none python3 -m shebanq_mcp.server &
sleep 3
curl -fsS http://localhost:8765/health
kill %1
```

Expected: prints `{"status":"ok","service":"shebanq"}`. If `mcp.settings.host/port` raise `AttributeError`, inspect the installed FastMCP settings object (`python3 -c "from mcp.server.fastmcp import FastMCP; print(FastMCP('x').settings)"`) and adjust attribute names; otherwise leave as-is.

- [ ] **Step 6: Confirm full suite green**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "feat: HTTP mode installs QueryGuard, binds 0.0.0.0:PORT, serves /health"
```

---

## Task 5b: MQL-writing guidance for client models

Deliver BHSA/MQL knowledge to the connecting model through the MCP surface:
enriched tool descriptions, an authoring primer from `search_bhsa`, and a
`write-mql` Prompt. All reuse `translate.build_prompt`. These apply in both
stdio and HTTP modes.

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Modify: `tests/test_server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Replace the search_bhsa no-translator test with a primer test**

In `tests/test_server.py`, replace `test_search_bhsa_without_translator_returns_error`
(the last test in the file) with:

```python
def test_search_bhsa_without_translator_returns_primer(monkeypatch):
    # The translation-free deploy: search_bhsa hands back an MQL-writing primer
    # (feature reference + quoting rules) instead of a dead-end error.
    monkeypatch.setattr(server, "_translator", None)
    out = server.handle_search_bhsa("all niphal verbs")
    assert out["question"] == "all niphal verbs"
    assert "UNQUOTED" in out["guidance"]   # the quoting rule from build_prompt
    assert "run_mql" in out["next"]
    assert "error" not in out
```

- [ ] **Step 2: Add the prompt-text test**

Append to `tests/test_server_transport.py`:

```python
def test_mql_prompt_text_includes_rules_and_question():
    text = server._mql_prompt_text("all niphal verbs")
    assert "UNQUOTED" in text
    assert "all niphal verbs" in text
    assert "run_mql" in text
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_server.py::test_search_bhsa_without_translator_returns_primer tests/test_server_transport.py::test_mql_prompt_text_includes_rules_and_question -v`
Expected: FAIL — `KeyError: 'question'` / `AttributeError: ... '_mql_prompt_text'`.

- [ ] **Step 4: Implement primer response, prompt text, enriched docstrings, and the prompt**

In `src/shebanq_mcp/server.py`:

(a) Change the translate import:

```python
from .translate import build_translator, build_prompt
```

(b) Replace `handle_search_bhsa`:

```python
def handle_search_bhsa(question: str) -> dict:
    if _translator is None:
        return {
            "question": question,
            "guidance": build_prompt(_ref),
            "next": "Use the rules above to write an MQL query for this "
                    "question, then call run_mql with it.",
        }
    mql = _translator.translate(question, _ref)
    return _run_pipeline(mql)
```

(c) Add the prompt-text helper (place it near the other helpers, after
`_run_pipeline`):

```python
def _mql_prompt_text(question: str) -> str:
    return (
        build_prompt(_ref)
        + f"\n\nQuestion: {question}\n\n"
        "Write the MQL query for this question, then call run_mql with it."
    )
```

(d) Enrich the `run_mql` and `search_bhsa` tool docstrings (replace the existing
two decorated functions' docstrings):

```python
@mcp.tool()
def run_mql(mql: str) -> dict:
    """Validate and run an MQL query; return the query and glossed results.

    MQL quoting rule (getting it wrong fails typechecking): enumeration features
    compare UNQUOTED (e.g. sp=verb, vs=nif); string features compare QUOTED
    (e.g. lex='BR>['). Verb lexemes carry a trailing '['. Call
    lookup_feature(name) to check a feature's kind and valid values.
    """
    return handle_run_mql(mql)


@mcp.tool()
def search_bhsa(question: str) -> dict:
    """Answer a plain-language question about the Hebrew Bible.

    With server-side translation enabled, returns generated MQL + results. On
    the public deploy (no server-side LLM) it returns an MQL-writing primer
    (feature reference + quoting rules) so you compose the query yourself and
    call run_mql.
    """
    return handle_search_bhsa(question)
```

(e) Register the `write-mql` Prompt (place after the tool definitions):

```python
@mcp.prompt()
def write_mql(question: str) -> str:
    """Compose a BHSA MQL query for a plain-language question."""
    return _mql_prompt_text(question)
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_server.py tests/test_server_transport.py -v`
Expected: all PASS, including the two new tests.

- [ ] **Step 6: Verify tools and the prompt are exposed over HTTP**

Run (lists only; no Emdros needed):

```bash
MCP_TRANSPORT=http PORT=8766 LLM_PROVIDER=none python3 -m shebanq_mcp.server &
sleep 3
python3 - <<'PY'
import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client("http://localhost:8766/mcp") as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            prompts = {p.name for p in (await s.list_prompts()).prompts}
            print("tools:", tools)
            print("prompts:", prompts)
            assert {"run_mql", "lookup_feature", "search_bhsa"} <= tools
            assert "write_mql" in prompts
            print("OK")
anyio.run(main)
PY
kill %1
```

Expected: prints the tool set, `prompts: {'write_mql'}`, and `OK`. (Prompt name may render as `write_mql`; if your FastMCP version slugifies it differently, note the actual name for the README.)

- [ ] **Step 7: Confirm full suite green**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server.py tests/test_server_transport.py
git commit -m "feat: expose MQL-writing guidance via tool docs, search_bhsa primer, write-mql prompt"
```

---

## Task 6: Multi-stage Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create `.dockerignore`:

```
.git
.github
__pycache__
*.pyc
.pytest_cache
demo
docs
data
*.sqlite3
*.mql*
.DS_Store
src/*.egg-info
```

- [ ] **Step 2: Create the `Dockerfile`**

Create `Dockerfile`:

```dockerfile
# ---- Build stage: Emdros from source + BHSA SQLite DB ----
FROM python:3.11-slim AS builder

ENV EMDROS_TAG=rel-3-9-0
ENV MQL_URL=https://github.com/ETCBC/bhsa/raw/master/shebanq/2021/shebanq_etcbc2021.mql.bz2

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential python3-dev swig \
        autoconf automake libtool gettext pkg-config \
        re2c bison flex libpcre3-dev libsqlite3-dev bzip2 wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN wget --tries=3 --timeout=30 -O emdros.tar.gz \
        "https://github.com/emdros/emdros/archive/refs/tags/${EMDROS_TAG}.tar.gz" \
    && tar xzf emdros.tar.gz

WORKDIR /build/emdros-${EMDROS_TAG}
RUN ( [ -f autogen.sh ] && sh autogen.sh ) || autoreconf -fi
RUN ./configure --prefix=/usr/local \
        --with-sqlite3=yes --with-mysql=no --with-postgresql=no --with-wx=no \
        --with-swig-language-python3=yes --with-swig-language-python2=no \
        --with-swig-language-java=no --with-swig-language-csharp=no \
        --with-swig-language-php7=no --disable-debug
# Drop the LaTeX doc subdir and stub pdflatex (same as CI).
RUN sed -i -E 's/^(SUBDIRS *= *)doc /\1/' Makefile \
    && printf '%s\n' '#!/bin/sh' \
        'for a in "$@"; do case "$a" in *.tex) : > "${a%.tex}.pdf";; esac; done' \
        'exit 0' > /usr/local/bin/pdflatex \
    && chmod +x /usr/local/bin/pdflatex
RUN make -j"$(nproc)" && make install && ldconfig

# Build the BHSA SQLite DB. The dump's CREATE DATABASE names the file
# internally, so relocate if mql did not write the -d path.
WORKDIR /build/db
RUN wget -q -O bhsa.mql.bz2 "$MQL_URL" \
    && bunzip2 -kf bhsa.mql.bz2 \
    && /usr/local/bin/mql --backend sqlite3 -d bhsa.sqlite3 bhsa.mql \
    && if [ ! -s bhsa.sqlite3 ]; then \
         mv "$(find . -maxdepth 1 -name 'shebanq_etcbc2021*' ! -name '*.mql*' | head -1)" bhsa.sqlite3; \
       fi \
    && test -s bhsa.sqlite3

# Stage exactly the runtime libs the Python binding needs (closure via ldd).
RUN mkdir -p /stage/lib/emdros \
    && cp -a /usr/local/lib/emdros/. /stage/lib/emdros/ \
    && ldd /usr/local/lib/emdros/_EmdrosPy3.so \
        | awk '/=> \/usr\/local/ {print $3}' \
        | xargs -r -I{} cp -a {} /stage/lib/

# ---- Runtime stage: slim ----
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlite3-0 libpcre3 \
    && rm -rf /var/lib/apt/lists/*

# Emdros shared libs + Python bindings.
COPY --from=builder /stage/lib/ /usr/local/lib/
RUN ldconfig
ENV PYTHONPATH=/usr/local/lib/emdros
ENV LD_LIBRARY_PATH=/usr/local/lib
# Fail the build loudly if the binding cannot import.
RUN python -c "import EmdrosPy3; print('emdros import ok')"

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY --from=builder /build/db/bhsa.sqlite3 /app/data/bhsa.sqlite3

ENV BHSA_SQLITE=/app/data/bhsa.sqlite3
ENV LLM_PROVIDER=none
ENV MCP_TRANSPORT=http
ENV PORT=8000
EXPOSE 8000
CMD ["shebanq-mcp"]
```

- [ ] **Step 3: Build the image locally (or note for CI)**

Run: `docker build -t shebanq-mcp:local .`
Expected: build completes; the `emdros import ok` line appears in build output. (Build takes ~10 min. If Docker is unavailable on the dev machine, this verification happens in Task 8's CI job — note that and proceed.)

- [ ] **Step 4: Run the container and hit `/health`**

Run:

```bash
docker run -d --name shebanq-test -p 8000:8000 shebanq-mcp:local
sleep 5
curl -fsS http://localhost:8000/health
docker rm -f shebanq-test
```

Expected: prints `{"status":"ok","service":"shebanq"}`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: multi-stage Dockerfile building Emdros + BHSA into a slim runtime"
```

---

## Task 7: Render blueprint

**Files:**
- Create: `render.yaml`

- [ ] **Step 1: Create `render.yaml`**

Create `render.yaml`:

```yaml
services:
  - type: web
    name: shebanq-mcp
    runtime: docker
    plan: pro
    dockerfilePath: ./Dockerfile
    healthCheckPath: /health
    autoDeploy: true
    branch: main
    envVars:
      - key: MCP_TRANSPORT
        value: http
      - key: LLM_PROVIDER
        value: none
      - key: BHSA_SQLITE
        value: /app/data/bhsa.sqlite3
      - key: QUERY_TIMEOUT_SECONDS
        value: "15"
      - key: MAX_CONCURRENT_QUERIES
        value: "4"
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml; yaml.safe_load(open('render.yaml')); print('render.yaml ok')"`
Expected: prints `render.yaml ok`.

- [ ] **Step 3: Commit**

```bash
git add render.yaml
git commit -m "feat: Render Pro blueprint for the MCP web service"
```

> **Note (manual, not automated):** First deploy is wired in the Render dashboard by pointing a new Blueprint at this repo. `PORT` is injected by Render and consumed by `main()`. Record the resulting public URL for the README in Task 9.

---

## Task 8: CI Docker smoke test

**Files:**
- Create: `scripts/smoke_mcp.py`
- Create: `.github/workflows/docker-smoke.yml`

- [ ] **Step 1: Create the MCP smoke client**

Create `scripts/smoke_mcp.py`:

```python
"""Smoke test: connect to a running shebanq MCP container over streamable-HTTP
and assert run_mql returns the known 'bara' (lex='BR>[') count of 48.

Usage: python scripts/smoke_mcp.py http://localhost:8000/mcp
"""
import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BARA_MQL = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
EXPECTED_COUNT = 48


def _extract_count(result) -> int:
    # Prefer structured content; fall back to scanning text blocks.
    data = getattr(result, "structuredContent", None)
    if isinstance(data, dict) and "result_count" in data:
        return int(data["result_count"])
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", "")
        if "result_count" in text:
            import json, re
            m = re.search(r'"result_count"\s*:\s*(\d+)', text)
            if m:
                return int(m.group(1))
    raise AssertionError(f"could not find result_count in: {result!r}")


async def _main(url: str) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            assert {"run_mql", "lookup_feature", "search_bhsa"} <= names, names
            result = await session.call_tool("run_mql", {"mql": BARA_MQL})
            count = _extract_count(result)
            assert count == EXPECTED_COUNT, f"got {count}, want {EXPECTED_COUNT}"
            print(f"SMOKE OK: run_mql bara count = {count}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
    anyio.run(_main, url)
```

- [ ] **Step 2: Create the workflow**

Create `.github/workflows/docker-smoke.yml`:

```yaml
name: docker-smoke

on:
  push:
    branches: ["**"]
  workflow_dispatch:

jobs:
  smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build image
        run: docker build -t shebanq-mcp:ci .

      - name: Run container
        run: |
          docker run -d --name shebanq -p 8000:8000 shebanq-mcp:ci
          for i in $(seq 1 30); do
            if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
              echo "health ok after ${i}s"; break
            fi
            sleep 1
          done
          curl -fsS http://localhost:8000/health

      - name: Set up Python + MCP client
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python3 -m pip install "mcp>=1.9.0" anyio

      - name: MCP run_mql smoke (bara == 48)
        run: python3 scripts/smoke_mcp.py http://localhost:8000/mcp

      - name: Container logs on failure
        if: failure()
        run: docker logs shebanq || true
```

- [ ] **Step 3: Local dry-run of the smoke client (if Docker is available)**

Run (against the image from Task 6):

```bash
docker run -d --name shebanq-smoke -p 8000:8000 shebanq-mcp:local
sleep 6
python3 -m pip install "mcp>=1.9.0" anyio
python3 scripts/smoke_mcp.py http://localhost:8000/mcp
docker rm -f shebanq-smoke
```

Expected: prints `SMOKE OK: run_mql bara count = 48`. (If Docker is unavailable locally, this is verified by the CI run after push.)

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_mcp.py .github/workflows/docker-smoke.yml
git commit -m "ci: build the image and smoke-test run_mql over MCP HTTP"
```

---

## Task 9: README — Connect in Claude Desktop + deploy

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read the current README**

Run: `sed -n '1,60p' README.md` (to see structure and where to insert).

- [ ] **Step 2: Add a "Use it in Claude Desktop" section**

Insert this section into `README.md` (after the intro / before deeper internals). Replace `<DEPLOYED_URL>` with the real Render URL recorded in Task 7 once known; until then leave the placeholder and a TODO note at the top of the section.

```markdown
## Use it in Claude Desktop

The server is hosted as a remote MCP endpoint, so you do not install Emdros or
the BHSA database yourself. Point your client at the URL.

Endpoint: `https://<DEPLOYED_URL>/mcp`

### Option A — Custom Connector
1. Claude Desktop → Settings → Connectors → Add custom connector.
2. Name it `shebanq` and paste `https://<DEPLOYED_URL>/mcp`.
3. Enable it. The tools `run_mql`, `lookup_feature`, and `search_bhsa` appear.

### Option B — `mcp-remote` bridge
If your client/plan does not accept an auth-less remote connector, bridge it
through a local stdio shim. Edit `claude_desktop_config.json` (Settings →
Developer → Edit Config):

​```json
{
  "mcpServers": {
    "shebanq": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<DEPLOYED_URL>/mcp"]
    }
  }
}
​```

Restart Claude Desktop. Requires Node (for `npx`); nothing Emdros-related.

### What you get
Ask in plain language. Your client's own model writes the MQL and calls
`run_mql`; you see the query and the real results. The server hands the model
what it needs to get MQL right: the `run_mql`/`search_bhsa` tool descriptions
carry the quoting rules, `search_bhsa` returns an MQL-writing primer (feature
reference + rules), and a `write-mql` prompt is available in your client for
composing a query from a question.
```

- [ ] **Step 3: Add a short "Deploy" subsection**

Append to `README.md` (or into an existing deploy/dev section):

```markdown
## Deploy

A Render Pro web service runs the server in HTTP mode from `Dockerfile` via
`render.yaml`. The image builds Emdros (`rel-3-9-0`, SQLite backend) and the
BHSA SQLite database from source, then ships a slim runtime. The deployment is
a pure query engine: `LLM_PROVIDER=none`, no API key. Guardrails
(`QUERY_TIMEOUT_SECONDS`, `MAX_CONCURRENT_QUERIES`) bound each query. CI
(`docker-smoke`) builds the image and verifies `run_mql` over MCP on every push.
```

- [ ] **Step 4: Verify the README renders sanely**

Run: `python3 -c "p=open('README.md').read(); assert 'Use it in Claude Desktop' in p and 'mcp-remote' in p and 'write-mql' in p; print('readme ok')"`
Expected: prints `readme ok`.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: how to connect the hosted MCP in Claude Desktop + deploy notes"
```

---

## Task 10: Manual acceptance + merge

These steps are manual and happen after the Render deploy exists.

- [ ] **Step 1: Confirm CI is green on the branch**

Run: `gh run list --branch deploy-mcp --limit 5`
Expected: `emdros-tests` and `docker-smoke` both succeed on the latest commit.

- [ ] **Step 2: Deploy on Render**

In the Render dashboard, create a Blueprint from this repo (`render.yaml`).
Wait for first deploy. Record the public URL.

- [ ] **Step 3: Fill the real URL into the README**

Replace `<DEPLOYED_URL>` in `README.md` with the live host, commit:

```bash
git add README.md
git commit -m "docs: pin the live deployed MCP URL"
```

- [ ] **Step 4: Acceptance — connect in Claude Desktop**

Add the URL as a custom connector (or via `mcp-remote`). In a chat, confirm:
- `lookup_feature("vs")` returns the verbal-stem table.
- A plain-language ask (e.g. "find the verb bara") produces an MQL `run_mql`
  call returning 48 results, with the query visible.
- `search_bhsa("...")` returns its run_mql guidance message.

- [ ] **Step 5: Finish the branch**

Use superpowers:finishing-a-development-branch to merge `deploy-mcp` into `main`
and push (solo repo, no PR per project norms).

---

## Self-review notes

- **Spec coverage:** transport switch (Tasks 3, 5) · pure engine `LLM_PROVIDER=none` (Dockerfile/render env, Tasks 6–7) · both stdio + HTTP (Task 3/5) · multi-stage build-in-image (Task 6) · guardrails timeout + concurrency (Tasks 4–5) · `/health` (Task 5) · MQL-writing guidance: tool descriptions + `search_bhsa` primer + `write-mql` prompt (Task 5b) · CI Docker smoke asserting bara=48 (Task 8) · README Claude Desktop section (Task 9) · success criteria verified in Task 10. All spec sections map to a task.
- **Known verification risks (flagged inline with fallbacks):** exact FastMCP `settings.host/port` attribute names and `custom_route` signature (Task 5 Step 5 has a fallback probe); `mcp` version providing `streamablehttp_client` (Task 1 Step 2 raises the pin if missing); the Emdros runtime-lib closure via `ldd` (Task 6 build-time `import EmdrosPy3` fails loudly if incomplete); spawn-importability of test targets (solved by `tests/__init__.py` + `tests/guard_targets.py`).
- **Type consistency:** `QueryGuard(db_path, max_concurrent, timeout_seconds, target)`, `.run(mql, features) -> RunResult`, `QueryTimeout`, `_executor(mql, features)`, `_resolve_transport() -> str`, `_install_guard(max_concurrent, timeout_seconds)`, `_health_payload() -> dict`, `_mql_prompt_text(question) -> str`, and the `search_bhsa` no-translator response keys (`question`/`guidance`/`next`) are used consistently across tasks.
