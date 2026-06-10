# Deploy the shebanq MCP server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the existing shebanq-mcp server as a public remote MCP endpoint over streamable-HTTP on Render, as a **read-only, LLM-free query engine** with bounded resources, keeping the local stdio path intact. Instance lifecycle (always-on vs scale-to-zero) is decided after measuring cold start.

**Architecture:** `main()` switches transport on `MCP_TRANSPORT`. The validator is hardened to reject any non-read-only MQL; the runtime container runs non-root with the DB file read-only (defense in depth). In HTTP mode, `run_mql` execution is routed through a `QueryGuard` that runs each query in a worker process with a concurrency cap and a hard timeout (SIGTERM → grace → SIGKILL). A startup self-test backs a `/health` endpoint that can actually go red. A multi-stage Docker image builds Emdros + the BHSA DB from a **pinned** ETCBC commit. CI builds the image and runs an expanded MCP smoke test plus memory/cold-start measurements.

**Tech Stack:** Python 3.11, `mcp` (FastMCP, streamable-HTTP), Emdros `rel-3-9-0` (SQLite backend + `EmdrosPy3` SWIG bindings), `multiprocessing`, Docker (multi-stage), Render, GitHub Actions.

**Spec:** `docs/specs/2026-06-09-mcp-deploy-design.md`

**Branch:** `deploy-mcp` (already created).

**Local constraint:** the dev machine has no Docker or Emdros. Tasks 8 and 10 are verified by CI after push, not locally — this is called out where it applies.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `pyproject.toml` | pin `mcp` to the confirmed streamable-HTTP version | Modify |
| `src/shebanq_mcp/validator.py` | reject non-read-only MQL (critical safety) | Modify |
| `src/shebanq_mcp/server.py` | transport switch, execution seam, startup self-test, `/health`, guidance | Modify |
| `src/shebanq_mcp/guard.py` | `QueryGuard`: concurrency cap + hard-kill timeout via worker process | Create |
| `tests/__init__.py` | make `tests` an importable package (spawn needs it) | Create |
| `tests/guard_targets.py` | top-level worker targets for guard tests | Create |
| `tests/test_guard.py` | `QueryGuard` tests (incl. SIGKILL escalation) | Create |
| `tests/test_server_transport.py` | transport, seam, self-test, prompt tests | Create |
| `tests/test_validator.py` | read-only rejection tests | Modify |
| `tests/test_server.py` | search_bhsa primer test | Modify |
| `Dockerfile` | multi-stage build; non-root; read-only DB; pinned dump | Create |
| `.dockerignore` | keep build context small | Create |
| `render.yaml` | Render blueprint (lifecycle-agnostic, provisional size) | Create |
| `scripts/smoke_mcp.py` | MCP client: multi-query + mutation-rejection smoke | Create |
| `.github/workflows/docker-smoke.yml` | build, smoke, measure memory + cold start | Create |
| `.github/workflows/emdros-tests.yml` | pin the dump URL to `BHSA_REF` | Modify |
| `README.md` | "Use it in Claude Desktop" + deploy (honest requirements) | Modify |

---

## Task 0: Pin the `mcp` version, confirm FastMCP APIs, pin the BHSA dump

This removes the four guessed FastMCP APIs and the moving `master` dump in one upfront step. Nothing else is coded against unconfirmed shapes.

**Files:** none yet (records values used by later tasks).

- [ ] **Step 1: Install a current `mcp` and print the real APIs**

Run:

```bash
python3 -m pip install --upgrade "mcp" anyio
python3 - <<'PY'
import inspect, mcp
from mcp.server.fastmcp import FastMCP
print("mcp version:", getattr(mcp, "__version__", "unknown"))
m = FastMCP("probe")
print("run signature:", inspect.signature(m.run))
print("has custom_route:", hasattr(m, "custom_route"))
print("has prompt:", hasattr(m, "prompt"))
print("has tool:", hasattr(m, "tool"))
print("settings type:", type(m.settings).__name__)
print("settings host attr:", hasattr(m.settings, "host"), "port attr:", hasattr(m.settings, "port"))
from mcp.client.streamable_http import streamablehttp_client  # import must succeed
print("streamablehttp_client import: ok")
PY
```

Expected: prints a concrete version (record it), `run signature` accepting a `transport` argument, `has custom_route: True`, `has prompt: True`, `settings host attr: True port attr: True`, and `streamablehttp_client import: ok`.

- [ ] **Step 2: Record the confirmed version and any API deviations**

Note the printed `mcp version` (call it `MCP_VERSION`). If `custom_route` is **False**, the `/health` route in Task 6 must instead be added to the Starlette app returned by `m.streamable_http_app()`; record that. If `settings.host/port` are **False**, record the real attribute names (or that host/port are passed to `m.run(...)` / the `FastMCP(...)` constructor instead). Later tasks use exactly what this step prints — do not proceed on assumptions.

- [ ] **Step 3: Pin the BHSA dump to a commit (kills the `master` non-reproducibility)**

Run:

```bash
git ls-remote https://github.com/ETCBC/bhsa.git refs/heads/master
```

Expected: prints `<40-char-sha>\trefs/heads/master`. Record that SHA (call it `BHSA_REF`). Every place that downloads the dump (the Dockerfile in Task 8 and `emdros-tests.yml`) uses this SHA in the URL path instead of `master`, so the built database — and the smoke counts (bara 48, sp=verb 73710) — stay reproducible.

- [ ] **Step 4: Pin the existing CI workflow's dump URL**

In `.github/workflows/emdros-tests.yml`, change the `MQL_URL` env value, replacing `master` with the recorded SHA:

```yaml
      MQL_URL: "https://github.com/ETCBC/bhsa/raw/<BHSA_REF>/shebanq/2021/shebanq_etcbc2021.mql.bz2"
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/emdros-tests.yml
git commit -m "build: pin BHSA dump to a fixed ETCBC commit for reproducibility"
```

---

## Task 1: Pin the `mcp` dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Pin to the confirmed version**

In `pyproject.toml`, set the `mcp` dependency to the `MCP_VERSION` confirmed in Task 0 (example shown; use the real number):

```toml
dependencies = [
    "mcp>=1.12.0",
    "anthropic>=0.40.0",
]
```

- [ ] **Step 2: Reinstall and confirm the suite is green**

Run:

```bash
python3 -m pip install -e ".[dev]"
pytest -q
```

Expected: install succeeds; all currently-passing tests pass (emdros-marked tests skip locally).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: pin mcp to the confirmed streamable-HTTP version"
```

---

## Task 2: Read-only MQL enforcement (CRITICAL — do not skip)

The endpoint will accept arbitrary MQL from anonymous callers. MQL includes `DROP`, `UPDATE`, `DELETE`, `CREATE`. Today `validate_mql` only checks feature quoting, so `DROP DATABASE '…' GO` passes clean. This task makes the validator reject any non-read-only query. (The container also enforces read-only at the filesystem in Task 8 — defense in depth.)

**Files:**
- Modify: `src/shebanq_mcp/validator.py`
- Modify: `tests/test_validator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_validator.py`:

```python
from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.validator import validate_mql

_REF = FeatureReference.load()


def test_rejects_drop_database():
    res = validate_mql("DROP DATABASE 'shebanq_etcbc2021' GO", _REF)
    assert not res.ok
    assert any("read-only" in e or "mutating" in e for e in res.errors)


def test_rejects_update_delete_create_pragma():
    for mql in [
        "UPDATE OBJECTS BY MONADS = 1 [word sp:=noun] GO",
        "DELETE OBJECTS BY MONADS = 1 [word] GO",
        "CREATE OBJECT FROM MONADS = 1 [word] GO",
        "PRAGMA journal_mode = WAL",
    ]:
        res = validate_mql(mql, _REF)
        assert not res.ok, mql


def test_accepts_plain_select():
    res = validate_mql("SELECT ALL OBJECTS WHERE [word sp=verb] GO", _REF)
    assert res.ok, res.errors


def test_mutating_keyword_inside_string_value_is_ok():
    # 'DELETE' as a string-feature value must not trip the read-only guard.
    res = validate_mql("SELECT ALL OBJECTS WHERE [word lex='DELETE'] GO", _REF)
    assert res.ok, res.errors
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_validator.py -v -k "rejects or accepts_plain or inside_string"`
Expected: the `rejects_*` tests FAIL (the mutating queries currently pass validation).

- [ ] **Step 3: Implement the read-only guard in `validator.py`**

In `src/shebanq_mcp/validator.py`, add these module-level patterns (after the existing `_CONSTRAINT`):

```python
# Read-only enforcement. Strip string literals first so a keyword inside a
# quoted feature value (e.g. lex='DELETE') cannot trip the guard.
_STRING_LITERAL = re.compile(r"""(['"]).*?\1""", re.DOTALL)
_MUTATING = re.compile(
    r"\b(CREATE|DROP|UPDATE|DELETE|INSERT|ALTER|REPLACE|VACUUM|ATTACH|DETACH"
    r"|PRAGMA|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)
_READ_VERB = re.compile(r"^\s*(SELECT|GET)\b", re.IGNORECASE)


def _read_only_errors(mql: str) -> list[str]:
    stripped = _STRING_LITERAL.sub("''", mql)
    errors: list[str] = []
    if not _READ_VERB.match(stripped):
        errors.append(
            "only read-only queries are allowed; the query must begin with "
            "SELECT or GET"
        )
    m = _MUTATING.search(stripped)
    if m:
        errors.append(
            "mutating MQL is not permitted on this read-only endpoint "
            f"(found '{m.group(1).upper()}')"
        )
    return errors
```

Then, in `validate_mql`, make the read-only check run first by changing the
`errors` initialization line:

```python
def validate_mql(mql: str, ref: FeatureReference) -> ValidationResult:
    errors: list[str] = _read_only_errors(mql)
    for match in _CONSTRAINT.finditer(mql):
```

(The rest of `validate_mql` is unchanged.)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_validator.py -v`
Expected: all PASS, including the existing quoting tests.

- [ ] **Step 5: Confirm the existing server tests still pass**

Run: `pytest tests/test_server.py -q`
Expected: PASS. (The invalid-MQL server test uses a `SELECT` with a quoted enum, still read-only, so the read-only guard adds no new error there.)

- [ ] **Step 6: Commit**

```bash
git add src/shebanq_mcp/validator.py tests/test_validator.py
git commit -m "feat: reject non-read-only MQL (no DROP/UPDATE/DELETE/CREATE on the public endpoint)"
```

---

## Task 3: Execution seam in `server.py`

Decouples `_run_pipeline` from `run_query` so HTTP mode can swap in the guard without breaking tests that monkeypatch `server.run_query`.

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

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server_transport.py::test_run_pipeline_uses_executor_seam -v`
Expected: FAIL with `AttributeError: ... '_executor'`.

- [ ] **Step 3: Add the seam**

In `src/shebanq_mcp/server.py`, replace `_run_pipeline` and add a default executor above it:

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

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_server_transport.py tests/test_server.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "refactor: route run_mql through a swappable executor seam"
```

---

## Task 4: Transport resolution in `main()`

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

In `src/shebanq_mcp/server.py`, add after `DB_PATH`:

```python
def _resolve_transport() -> str:
    """Map the MCP_TRANSPORT env var to a FastMCP transport name."""
    raw = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if raw in ("", "stdio"):
        return "stdio"
    if raw in ("http", "streamable-http"):
        return "streamable-http"
    raise ValueError(f"unknown MCP_TRANSPORT '{raw}' (supported: stdio, http)")
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

## Task 5: `QueryGuard` — concurrency cap + hard-kill timeout

The read-only guard (Task 2) removes the data threat. The guard bounds the remaining threat: a valid-but-expensive query. Key correctness point vs the first draft: on timeout we escalate **SIGTERM → grace → SIGKILL**, because a process pinned in Emdros's C call may ignore SIGTERM.

**Files:**
- Create: `src/shebanq_mcp/guard.py`
- Create: `tests/__init__.py`
- Create: `tests/guard_targets.py`
- Test: `tests/test_guard.py`

- [ ] **Step 1: Create the package marker and picklable worker targets**

Create empty `tests/__init__.py`:

```python
```

Create `tests/guard_targets.py`:

```python
"""Worker targets for QueryGuard tests. Top-level so multiprocessing spawn can
import them by qualified name."""
import signal
import time

from shebanq_mcp.runner import RunResult


def fast(mql, db_path, features, q):
    q.put(("ok", RunResult(count=3, matches=[])))


def slow(mql, db_path, features, q):
    time.sleep(3)
    q.put(("ok", RunResult(count=0, matches=[])))


def boom(mql, db_path, features, q):
    q.put(("err", "deliberate failure"))


def stubborn(mql, db_path, features, q):
    # Ignore SIGTERM, then sleep long. Only SIGKILL can stop this — it proves
    # the guard escalates terminate() -> kill().
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)
    q.put(("ok", RunResult(count=0, matches=[])))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_guard.py`:

```python
import threading
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


def test_guard_sigkills_a_sigterm_ignoring_worker():
    # Worker ignores SIGTERM and would sleep 30s; the guard must SIGKILL it and
    # return promptly, not hang for 30s.
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=0.5, target=guard_targets.stubborn)
    start = time.monotonic()
    with pytest.raises(QueryTimeout):
        guard.run("SELECT ... GO")
    assert time.monotonic() - start < 8.0


def test_guard_caps_concurrency():
    guard = QueryGuard("unused.db", max_concurrent=1,
                       timeout_seconds=10, target=guard_targets.slow)
    start = time.monotonic()
    threads = [threading.Thread(target=guard.run, args=("SELECT ... GO",))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Two 3s queries serialized by a cap of 1 => >= ~6s.
    assert time.monotonic() - start >= 5.0
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_guard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shebanq_mcp.guard'`.

- [ ] **Step 4: Implement `guard.py`**

Create `src/shebanq_mcp/guard.py`:

```python
"""Concurrency- and timeout-bounded execution of Emdros queries.

A public single-container deploy must survive a valid-but-expensive MQL query.
Each query runs in a worker process so a synchronous Emdros C call can be
hard-killed on timeout. On overrun we send SIGTERM, wait a short grace, then
SIGKILL — escalation matters because a process pinned in C may ignore SIGTERM.
A semaphore caps how many run at once (bounding memory).
"""
import multiprocessing
import queue as _queue
import threading

from .runner import RunResult, run_query

_TERM_GRACE_SECONDS = 2.0


class QueryTimeout(Exception):
    """Raised when a query exceeds the configured wall-clock budget."""


def _default_target(mql, db_path, features, q):
    """Run a query in the worker process; ship the result over the queue."""
    try:
        res = run_query(mql, db_path, features)
        q.put(("ok", res))
    except Exception as exc:  # noqa: BLE001 - report any failure to the parent
        q.put(("err", repr(exc)))


class QueryGuard:
    """Runs each query in a worker process with a concurrency cap + hard timeout."""

    def __init__(self, db_path, max_concurrent=4, timeout_seconds=15,
                 target=_default_target):
        self._db_path = db_path
        self._timeout = timeout_seconds
        self._target = target
        self._sem = threading.Semaphore(max_concurrent)
        self._ctx = multiprocessing.get_context("spawn")

    def _kill(self, proc):
        proc.terminate()                       # SIGTERM
        proc.join(timeout=_TERM_GRACE_SECONDS)
        if proc.is_alive():
            proc.kill()                        # SIGKILL
            proc.join()

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
                self._kill(proc)
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
Expected: all PASS. (Total ~9s: the concurrency test ~6s, the SIGKILL test ~2.5s.)

- [ ] **Step 6: Confirm the whole suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/shebanq_mcp/guard.py tests/__init__.py tests/guard_targets.py tests/test_guard.py
git commit -m "feat: QueryGuard with concurrency cap and SIGTERM->SIGKILL timeout"
```

---

## Task 6: Wire guard + startup self-test + red-capable `/health` + HTTP run

The health check reports a **startup self-test** (one real query), so a broken DB/Emdros makes the deploy go red instead of "healthy but broken."

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_transport.py`:

```python
def test_install_guard_swaps_executor():
    server._executor = server._default_executor
    try:
        server._install_guard(max_concurrent=2, timeout_seconds=3)
        assert server._executor is not server._default_executor
    finally:
        server._executor = server._default_executor


def test_startup_selftest_sets_ready_on_success():
    from shebanq_mcp.runner import RunResult
    server._ready = False
    ok = server._run_startup_selftest(query_fn=lambda: RunResult(count=48, matches=[]))
    assert ok is True and server._ready is True
    assert server._health_payload()["status"] == "ok"


def test_startup_selftest_marks_unready_on_failure():
    server._ready = True

    def boom():
        raise RuntimeError("no db")

    ok = server._run_startup_selftest(query_fn=boom)
    assert ok is False and server._ready is False
    assert server._health_payload()["status"] != "ok"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_server_transport.py -v -k "install_guard or selftest"`
Expected: FAIL with `AttributeError` for `_install_guard` / `_run_startup_selftest` / `_ready`.

- [ ] **Step 3: Implement guard install, self-test, health, route, and `main()`**

In `src/shebanq_mcp/server.py`:

(a) Add the import near the top:

```python
from .guard import QueryGuard
```

(b) Add a readiness flag near `_executor`:

```python
# Startup self-test result; /health reports this. False until proven.
_ready = False
SELFTEST_MQL = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"  # bara; expect > 0
```

(c) Add these helpers after `_run_pipeline`:

```python
def _install_guard(max_concurrent: int, timeout_seconds: int) -> None:
    """Swap the executor to a process-isolated, timeout-bounded guard."""
    global _executor
    guard = QueryGuard(DB_PATH, max_concurrent=max_concurrent,
                       timeout_seconds=timeout_seconds)
    _executor = lambda mql, features: guard.run(mql, features)  # noqa: E731


def _run_startup_selftest(query_fn=None) -> bool:
    """Run one real read-only query to prove the engine works. Sets _ready."""
    global _ready
    fn = query_fn or (lambda: run_query(SELFTEST_MQL, DB_PATH, []))
    try:
        _ready = fn().count > 0
    except Exception:
        _ready = False
    return _ready


def _health_payload() -> dict:
    return {"status": "ok" if _ready else "unavailable",
            "service": "shebanq", "ready": _ready}
```

(d) Register the `/health` route (use the form Task 0 confirmed; the
`custom_route` decorator is shown). The Starlette import is local so stdio mode
never imports it:

```python
@mcp.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ANN001 - Starlette Request
    from starlette.responses import JSONResponse
    return JSONResponse(_health_payload(), status_code=200 if _ready else 503)
```

> If Task 0 found `custom_route` absent, instead register `/health` on
> `mcp.streamable_http_app()` before `mcp.run(...)` using a Starlette `Route`;
> the handler body is identical.

(e) Replace `main()`:

```python
def main() -> None:
    transport = _resolve_transport()
    if transport == "streamable-http":
        max_concurrent = int(os.environ.get("MAX_CONCURRENT_QUERIES", "4"))
        timeout_seconds = int(os.environ.get("QUERY_TIMEOUT_SECONDS", "15"))
        _install_guard(max_concurrent, timeout_seconds)
        if not _run_startup_selftest():
            # Do not crash: boot and serve /health as 503 so the platform's
            # health check marks the deploy unhealthy with a clear signal.
            print("WARNING: startup self-test failed; /health will report 503",
                  flush=True)
        mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_server_transport.py -v`
Expected: all PASS.

- [ ] **Step 5: Local boot check — `/health` correctly reports 503 without Emdros**

Run (no Emdros locally, so the self-test fails and `/health` must go red — this is the point):

```bash
MCP_TRANSPORT=http PORT=8765 LLM_PROVIDER=none python3 -m shebanq_mcp.server &
sleep 3
echo "HTTP $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8765/health)"
curl -s http://localhost:8765/health
kill %1
```

Expected: `HTTP 503` and a body with `"status": "unavailable"`. (In the container, with the DB present, this is `200` / `ok` — verified in Task 8 Step 4.) If the server fails to bind or `settings.host/port` error, use the attribute form recorded in Task 0.

- [ ] **Step 6: Confirm full suite**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server_transport.py
git commit -m "feat: HTTP mode with QueryGuard, startup self-test, and a red-capable /health"
```

---

## Task 7: MQL-writing guidance for client models

Enriched tool descriptions, a **concise** `search_bhsa` primer (not the full reference — that would bloat the model's context every call), and a `write-mql` Prompt that emits the full reference only on demand.

**Files:**
- Modify: `src/shebanq_mcp/server.py`
- Modify: `tests/test_server.py`
- Test: `tests/test_server_transport.py`

- [ ] **Step 1: Replace the search_bhsa no-translator test**

In `tests/test_server.py`, replace `test_search_bhsa_without_translator_returns_error` with:

```python
def test_search_bhsa_without_translator_returns_concise_primer(monkeypatch):
    monkeypatch.setattr(server, "_translator", None)
    out = server.handle_search_bhsa("all niphal verbs")
    assert out["question"] == "all niphal verbs"
    assert "UNQUOTED" in out["guidance"]
    assert "lookup_feature" in out["hint"]
    assert "run_mql" in out["next"]
    assert "error" not in out
    # Concise: it must NOT dump the full 237-constant reference.
    assert len(out["guidance"]) < 600
```

- [ ] **Step 2: Add the prompt-text test**

Append to `tests/test_server_transport.py`:

```python
def test_mql_prompt_text_includes_full_reference_and_question():
    text = server._mql_prompt_text("all niphal verbs")
    assert "UNQUOTED" in text
    assert "all niphal verbs" in text
    assert "run_mql" in text
    # The prompt carries the full reference (much larger than the primer).
    assert len(text) > 600
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/test_server.py::test_search_bhsa_without_translator_returns_concise_primer tests/test_server_transport.py::test_mql_prompt_text_includes_full_reference_and_question -v`
Expected: FAIL (`KeyError`/`AttributeError`).

- [ ] **Step 4: Implement primer, prompt text, docstrings, prompt**

In `src/shebanq_mcp/server.py`:

(a) Change the translate import:

```python
from .translate import build_translator, build_prompt
```

(b) Add the concise rule constant near the top:

```python
_QUOTING_RULE = (
    "MQL quoting rule: enumeration features compare UNQUOTED (sp=verb, vs=nif); "
    "string features compare QUOTED (lex='BR>[', gloss='create'). BHSA verb "
    "lexemes carry a trailing '['. Queries must be read-only (SELECT/GET)."
)
```

(c) Replace `handle_search_bhsa`:

```python
def handle_search_bhsa(question: str) -> dict:
    if _translator is None:
        return {
            "question": question,
            "guidance": _QUOTING_RULE,
            "hint": "Call lookup_feature(name) to check a feature's kind and "
                    "values, or use the write-mql prompt for the full reference.",
            "next": "Write a read-only MQL SELECT for this question, then call "
                    "run_mql with it.",
        }
    mql = _translator.translate(question, _ref)
    return _run_pipeline(mql)
```

(d) Add the prompt-text helper after `_run_pipeline`:

```python
def _mql_prompt_text(question: str) -> str:
    return (
        build_prompt(_ref)
        + f"\n\nQuestion: {question}\n\n"
        "Write a read-only MQL SELECT for this question, then call run_mql with it."
    )
```

(e) Enrich the two tool docstrings (replace the existing decorated functions):

```python
@mcp.tool()
def run_mql(mql: str) -> dict:
    """Validate and run a read-only MQL query; return the query and glossed results.

    Only read-only queries (SELECT/GET) are accepted. Quoting rule (getting it
    wrong fails typechecking): enumeration features compare UNQUOTED (sp=verb,
    vs=nif); string features compare QUOTED (lex='BR>['). Verb lexemes carry a
    trailing '['. Call lookup_feature(name) to check a feature's kind/values.
    """
    return handle_run_mql(mql)


@mcp.tool()
def search_bhsa(question: str) -> dict:
    """Answer a plain-language question about the Hebrew Bible.

    With server-side translation enabled, returns generated MQL + results. On
    the public deploy (no server-side LLM) it returns a concise MQL-writing
    primer so you compose a read-only query yourself and call run_mql. Use the
    write-mql prompt for the full feature reference.
    """
    return handle_search_bhsa(question)
```

(f) Register the prompt after the tools:

```python
@mcp.prompt()
def write_mql(question: str) -> str:
    """Compose a read-only BHSA MQL query for a plain-language question."""
    return _mql_prompt_text(question)
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_server.py tests/test_server_transport.py -v`
Expected: all PASS.

- [ ] **Step 6: Verify tools + prompt over HTTP (lists only; no Emdros needed)**

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
            print("tools:", tools, "prompts:", prompts)
            assert {"run_mql", "lookup_feature", "search_bhsa"} <= tools
            assert "write_mql" in prompts
            print("OK")
anyio.run(main)
PY
kill %1
```

Expected: prints the tool set, `prompts: {'write_mql'}`, `OK`. (Record the actual prompt name for the README if it differs.)

- [ ] **Step 7: Commit**

```bash
git add src/shebanq_mcp/server.py tests/test_server.py tests/test_server_transport.py
git commit -m "feat: tool-description, concise search_bhsa primer, and write-mql prompt guidance"
```

---

## Task 8: Multi-stage Dockerfile — non-root, read-only DB, pinned dump

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

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

- [ ] **Step 2: Create the `Dockerfile`** (set `BHSA_REF` to the SHA from Task 0)

```dockerfile
# ---- Build stage: Emdros from source + BHSA SQLite DB ----
FROM python:3.11-slim AS builder

ENV EMDROS_TAG=rel-3-9-0
# Pinned ETCBC commit (from Task 0), NOT master — makes the DB reproducible.
ARG BHSA_REF=PUT_BHSA_SHA_HERE
ENV MQL_URL=https://github.com/ETCBC/bhsa/raw/${BHSA_REF}/shebanq/2021/shebanq_etcbc2021.mql.bz2

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
RUN sed -i -E 's/^(SUBDIRS *= *)doc /\1/' Makefile \
    && printf '%s\n' '#!/bin/sh' \
        'for a in "$@"; do case "$a" in *.tex) : > "${a%.tex}.pdf";; esac; done' \
        'exit 0' > /usr/local/bin/pdflatex \
    && chmod +x /usr/local/bin/pdflatex
RUN make -j"$(nproc)" && make install && ldconfig

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

# ---- Runtime stage: slim, non-root, read-only DB ----
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlite3-0 libpcre3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

COPY --from=builder /stage/lib/ /usr/local/lib/
RUN ldconfig
ENV PYTHONPATH=/usr/local/lib/emdros
ENV LD_LIBRARY_PATH=/usr/local/lib
ENV SQLITE_TMPDIR=/tmp
RUN python -c "import EmdrosPy3; print('emdros import ok')"

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Read-only database: file 444, directory 555 (not writable by appuser).
COPY --from=builder /build/db/bhsa.sqlite3 /app/data/bhsa.sqlite3
RUN chmod 0444 /app/data/bhsa.sqlite3 && chmod 0555 /app/data

ENV BHSA_SQLITE=/app/data/bhsa.sqlite3
ENV LLM_PROVIDER=none
ENV MCP_TRANSPORT=http
ENV PORT=8000

USER appuser
# Build-time read-only self-test: prove appuser can query a 444 DB in a 555 dir
# (catches the "Emdros wants a writable handle" failure the spec flags).
RUN python -c "from shebanq_mcp.server import _run_startup_selftest; \
import sys; sys.exit(0 if _run_startup_selftest() else 1)"

EXPOSE 8000
CMD ["shebanq-mcp"]
```

- [ ] **Step 3: Build the image** (CI verifies if Docker is absent locally)

Run: `docker build --build-arg BHSA_REF=<BHSA_REF> -t shebanq-mcp:local .`
Expected: build completes; both `emdros import ok` and the read-only self-test
RUN succeed. If the read-only self-test fails, Emdros needs a writable handle:
fall back to copying the DB to a tmpfs/world-readable path the user still cannot
overwrite, or open via SQLite URI `?mode=ro&immutable=1` in `runner._make_env`,
and re-build. (~10 min build.)

- [ ] **Step 4: Run the container and confirm `/health` is green**

```bash
docker run -d --name shebanq-test -p 8000:8000 shebanq-mcp:local
sleep 6
echo "HTTP $(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health)"
curl -s http://localhost:8000/health
docker rm -f shebanq-test
```

Expected: `HTTP 200` and `"status": "ok"` (the self-test ran a real query).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: multi-stage Dockerfile, non-root, read-only DB, pinned dump"
```

---

## Task 9: Render blueprint (lifecycle-agnostic, provisional size)

**Files:**
- Create: `render.yaml`

- [ ] **Step 1: Create `render.yaml`**

```yaml
# Instance size and lifecycle are PROVISIONAL. After Task 10 measures peak
# memory and cold-start time, either keep this always-on `standard` size or
# switch to a scale-to-zero option (see the spec's "Instance lifecycle"
# section). The smoke counts depend on the pinned BHSA_REF build arg.
services:
  - type: web
    name: shebanq-mcp
    runtime: docker
    plan: standard            # ~2GB; confirm vs the Task 10 memory measurement
    dockerfilePath: ./Dockerfile
    dockerContext: .
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
        value: "2"            # conservative until memory is measured
```

- [ ] **Step 2: Validate YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('render.yaml')); print('render.yaml ok')"`
Expected: prints `render.yaml ok`.

- [ ] **Step 3: Commit**

```bash
git add render.yaml
git commit -m "feat: Render blueprint (provisional size, lifecycle decided after measuring)"
```

> **Manual:** the `BHSA_REF` build arg must be supplied to Render's build (set it
> in the Blueprint/Dashboard build args, matching the Dockerfile default).

---

## Task 10: CI smoke (multi-query + mutation rejection) + measurements

**Files:**
- Create: `scripts/smoke_mcp.py`
- Create: `.github/workflows/docker-smoke.yml`

- [ ] **Step 1: Create the smoke client**

Create `scripts/smoke_mcp.py`:

```python
"""Smoke test against a running shebanq MCP container over streamable-HTTP.

Checks: tools + write-mql prompt are listed; a string query (bara=48) and an
enum query (sp=verb=73710) return the right counts; a mutating query is REJECTED
and leaves the data unchanged.

Usage: python scripts/smoke_mcp.py http://localhost:8000/mcp
"""
import re
import sys

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

BARA = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
VERBS = "SELECT ALL OBJECTS WHERE [word sp=verb] GO"
DROP = "DROP DATABASE 'shebanq_etcbc2021' GO"


def _count(result) -> int:
    data = getattr(result, "structuredContent", None)
    if isinstance(data, dict) and "result_count" in data:
        return int(data["result_count"])
    for block in getattr(result, "content", []) or []:
        m = re.search(r'"result_count"\s*:\s*(\d+)', getattr(block, "text", ""))
        if m:
            return int(m.group(1))
    raise AssertionError(f"no result_count in {result!r}")


def _text(result) -> str:
    parts = [getattr(b, "text", "") for b in getattr(result, "content", []) or []]
    data = getattr(result, "structuredContent", None)
    return (str(data) if data else "") + " ".join(parts)


async def _main(url: str) -> None:
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert {"run_mql", "lookup_feature", "search_bhsa"} <= tools, tools
            prompts = {p.name for p in (await session.list_prompts()).prompts}
            assert "write_mql" in prompts, prompts

            assert _count(await session.call_tool("run_mql", {"mql": BARA})) == 48
            assert _count(await session.call_tool("run_mql", {"mql": VERBS})) == 73710

            # Mutation must be refused by validation, not executed.
            drop = await session.call_tool("run_mql", {"mql": DROP})
            assert "read-only" in _text(drop) or "mutating" in _text(drop), _text(drop)
            # And the data is still intact afterwards.
            assert _count(await session.call_tool("run_mql", {"mql": BARA})) == 48

            print("SMOKE OK: bara=48, verbs=73710, mutation rejected, data intact")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"
    anyio.run(_main, url)
```

- [ ] **Step 2: Create the workflow** (set `<BHSA_REF>` to the Task 0 SHA)

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
        run: docker build --build-arg BHSA_REF=<BHSA_REF> -t shebanq-mcp:ci .

      - name: Measure cold start (run -> first 200 from /health)
        run: |
          start=$(date +%s.%N)
          docker run -d --name shebanq -p 8000:8000 shebanq-mcp:ci
          for i in $(seq 1 60); do
            code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health || true)
            if [ "$code" = "200" ]; then break; fi
            sleep 1
          done
          end=$(date +%s.%N)
          echo "COLD_START_SECONDS=$(echo "$end - $start" | bc)"
          curl -s http://localhost:8000/health

      - name: Set up Python + MCP client
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: python3 -m pip install "mcp" anyio

      - name: MCP smoke (multi-query + mutation rejection)
        run: python3 scripts/smoke_mcp.py http://localhost:8000/mcp

      - name: Measure memory under concurrent load
        run: |
          for n in 1 2; do
            python3 scripts/smoke_mcp.py http://localhost:8000/mcp >/dev/null &
          done
          sleep 2
          echo "PEAK_MEM=$(docker stats --no-stream --format '{{.MemUsage}}' shebanq)"
          wait || true

      - name: Container logs on failure
        if: failure()
        run: docker logs shebanq || true
```

- [ ] **Step 3: Local dry-run (only if Docker is available)**

```bash
docker run -d --name shebanq-smoke -p 8000:8000 shebanq-mcp:local
sleep 6
python3 -m pip install "mcp" anyio
python3 scripts/smoke_mcp.py http://localhost:8000/mcp
docker rm -f shebanq-smoke
```

Expected: `SMOKE OK: bara=48, verbs=73710, mutation rejected, data intact`. (Otherwise this runs in CI after push.)

- [ ] **Step 4: Commit**

```bash
git add scripts/smoke_mcp.py .github/workflows/docker-smoke.yml
git commit -m "ci: multi-query + mutation-rejection smoke, plus memory and cold-start measurement"
```

---

## Task 11: README — honest setup + deploy

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read the current README**

Run: `sed -n '1,60p' README.md`

- [ ] **Step 2: Add the "Use it in Claude Desktop" section** (replace `<DEPLOYED_URL>` once Task 12 records it)

```markdown
## Use it in Claude Desktop

The server is hosted as a remote MCP endpoint, so you do not install Emdros or
the BHSA database. Point your client at the URL. It is a **read-only** query
engine: you can search, not modify, the data.

Endpoint: `https://<DEPLOYED_URL>/mcp`

### Option A — Custom Connector
Settings → Connectors → Add custom connector → name `shebanq`, paste the `/mcp`
URL. **Requires** a Claude plan that supports custom connectors; some clients
expect OAuth, which this open server does not implement — if it refuses, use
Option B.

### Option B — `mcp-remote` bridge
Works on any client that loads local servers. **Requires** Node (for `npx`).
Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

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

Restart Claude Desktop.

### What you get
Ask in plain language. Your client's own model writes a read-only MQL query and
calls `run_mql`; you see the query and the real results. The server guides the
model: tool descriptions carry the quoting rules, `search_bhsa` returns a concise
primer, and a `write-mql` prompt provides the full feature reference on demand.
```

- [ ] **Step 3: Add a "Deploy" subsection**

```markdown
## Deploy

A Render web service runs the server in HTTP mode from `Dockerfile` via
`render.yaml`. The image builds Emdros (`rel-3-9-0`) and the BHSA SQLite database
from a **pinned** ETCBC commit, then ships a slim, **non-root** runtime with the
database mounted **read-only**. It is a pure query engine (`LLM_PROVIDER=none`,
no API key). The validator rejects any non-read-only MQL. A startup self-test
backs `/health`, so a broken database fails the deploy instead of serving errors.
Guardrails (`QUERY_TIMEOUT_SECONDS`, `MAX_CONCURRENT_QUERIES`) hard-kill runaway
queries and bound memory. CI (`docker-smoke`) builds the image and verifies
multiple queries plus mutation rejection on every push. Instance lifecycle
(always-on vs scale-to-zero) is chosen from the measured cold-start time.
```

- [ ] **Step 4: Verify**

Run: `python3 -c "p=open('README.md').read(); assert all(s in p for s in ['Use it in Claude Desktop','mcp-remote','write-mql','read-only']); print('readme ok')"`
Expected: prints `readme ok`.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: honest Claude Desktop setup + read-only deploy notes"
```

---

## Task 12: Deploy, measure, decide lifecycle, accept, merge

Manual; after CI is green.

- [ ] **Step 1: Confirm CI green**

Run: `gh run list --branch deploy-mcp --limit 5`
Expected: `emdros-tests` and `docker-smoke` both succeed on the latest commit.

- [ ] **Step 2: Read the measurements**

In the latest `docker-smoke` run logs, record `COLD_START_SECONDS` and
`PEAK_MEM`. These drive the next two decisions.

- [ ] **Step 3: Decide instance size + lifecycle, update `render.yaml` and the spec**

- If `PEAK_MEM` comfortably fits a smaller plan, downsize `plan:`. If it is
  tight, keep `standard` (or larger) and/or lower `MAX_CONCURRENT_QUERIES`.
- If `COLD_START_SECONDS` is small enough that an MCP client tolerates it (test:
  connect a cold instance in Claude Desktop and confirm `initialize` + first
  call succeed), scale-to-zero is viable for cost; otherwise keep always-on.
- Record the numbers and the choice in the spec's "Instance lifecycle" section;
  commit any `render.yaml` change.

```bash
git add render.yaml docs/specs/2026-06-09-mcp-deploy-design.md
git commit -m "chore: set instance size/lifecycle from measured cold start and memory"
```

- [ ] **Step 4: Deploy on Render**

Create a Blueprint from this repo (`render.yaml`), supplying the `BHSA_REF`
build arg. Wait for first deploy; confirm `/health` is 200. Record the URL.

- [ ] **Step 5: Fill the real URL into the README**

```bash
git add README.md
git commit -m "docs: pin the live deployed MCP URL"
```

- [ ] **Step 6: Acceptance in Claude Desktop**

Connect the URL. Confirm:
- `lookup_feature("vs")` returns the verbal-stem table.
- A plain-language ask ("find the verb bara") yields a `run_mql` call returning
  48, query visible.
- `search_bhsa("…")` returns the concise primer.
- A mutating request ("delete all verbs" → if the model emits `DELETE`/`DROP`)
  is **refused** with a read-only error. Verify a `run_mql` of bara still
  returns 48.

- [ ] **Step 7: Finish the branch**

Use superpowers:finishing-a-development-branch to merge `deploy-mcp` into `main`
and push (solo repo, no PR per project norms).

---

## Self-review notes

- **Spec coverage:** read-only validator + tests (Task 2) and read-only
  filesystem (Task 8) · `LLM_PROVIDER=none` pure engine (Tasks 8–9) · both
  transports (Tasks 4, 6) · pinned reproducible dump (Tasks 0, 8, and CI) ·
  hardened `/health` self-test (Task 6) · guard with SIGKILL escalation (Task 5)
  · MQL-writing guidance, concise primer + full-reference prompt (Task 7) ·
  expanded smoke incl. enum query + mutation rejection (Task 10) · memory +
  cold-start measurement and the lifecycle decision (Tasks 10, 12) · honest
  README requirements (Task 11) · FastMCP APIs pinned upfront (Task 0). All spec
  sections map to a task.
- **Residual risks (explicit, not hidden):** Emdros may demand a writable SQLite
  handle even for reads — caught at image build time (Task 8 Step 3) with a named
  fallback (`?mode=ro&immutable=1` / tmpfs copy). FastMCP `custom_route`/settings
  shapes are confirmed before use (Task 0) with a Starlette-app fallback noted
  (Task 6). No IP rate-limiting (spec "Known limitations") — deferred on purpose.
  Per-query process latency accepted until a warm pool is built.
- **Type consistency:** `QueryGuard(db_path, max_concurrent, timeout_seconds, target)`,
  `.run(mql, features) -> RunResult`, `QueryTimeout`, `_executor(mql, features)`,
  `_resolve_transport() -> str`, `_install_guard(max_concurrent, timeout_seconds)`,
  `_run_startup_selftest(query_fn=None) -> bool`, `_ready: bool`,
  `_health_payload() -> dict`, `_mql_prompt_text(question) -> str`,
  `_read_only_errors(mql) -> list[str]`, and the `search_bhsa` no-translator keys
  (`question`/`guidance`/`hint`/`next`) are used consistently across tasks.
```
