import os
import re
import sys

from mcp.server.fastmcp import FastMCP

from time import monotonic

from .feature_reference import FeatureReference
from .guard import QueryGuard, QueryTimeout, ServerBusy, WorkerCrashed
from .validator import validate_mql
from .tf_validator import validate_tf
from .tf_to_mql import ConversionError, tf_to_mql
from .convert import detect_and_convert
from .mql_to_tf import mql_to_tf
from . import tf_runner
from .runner import run_query
from .formatter import format_results
from .translate import build_translator, build_prompt
from .web import RateLimiter

DB_PATH = os.environ.get("BHSA_SQLITE", "data/bhsa.sqlite3")


def _resolve_transport() -> str:
    """Map the MCP_TRANSPORT env var to a FastMCP transport name."""
    raw = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if raw in ("", "stdio"):
        return "stdio"
    if raw in ("http", "streamable-http"):
        return "streamable-http"
    raise ValueError(f"unknown MCP_TRANSPORT '{raw}' (supported: stdio, http)")


# Matches the feature list inside an MQL `GET a, b, c` clause.
_GET_CLAUSE = re.compile(r"\bGET\s+([A-Za-z0-9_,\s]+?)\s*\]")

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
    if re.match(r"\[\s*verse\b", block, re.IGNORECASE):
        return mql                      # already verse-nested; don't double-wrap
    return f"{head}[verse GET book, chapter, verse {block}]{tail}".strip()


# Matches exactly the reference wrapper _wrap_in_verse adds (which the LLM also
# emits on its own): a verse block whose sole content is GET book, chapter,
# verse around one inner block. A verse block carrying its own conditions
# (e.g. [verse book=Genesis ...]) is query semantics and never matches.
_VERSE_WRAP = re.compile(
    r"(?is)^(\s*SELECT\s+ALL\s+OBJECTS\s+WHERE\s+)"
    r"\[\s*verse\s+GET\s+book\s*,\s*chapter\s*,\s*verse\s+(\[.*\])\s*\]"
    r"(\s+GO\s*)$")


def _unwrap_verse(mql: str) -> str:
    m = _VERSE_WRAP.match(mql.strip())
    if not m:
        return mql
    return f"{m.group(1)}{m.group(2)}{m.group(3)}".strip()

_QUOTING_RULE = (
    "MQL quoting rule: enumeration features compare UNQUOTED (sp=verb, vs=nif); "
    "string features compare QUOTED (lex='BR>[', gloss='create'). BHSA verb "
    "lexemes carry a trailing '['. Queries must be read-only (SELECT/GET)."
)

_ref = FeatureReference.load()
# The configured LLM translator (None if LLM_PROVIDER=none -> translation-free).
_translator = build_translator()
# Global throttle on the paid translation path (the MCP transport has no per-IP
# limit). LLM_RATE_PER_MIN bounds bursts; the Anthropic spend cap is the ceiling.
# One charge, one model call; the TF artifact is derived, not generated.
_TRANSLATE_LIMITER = RateLimiter(int(os.environ.get("LLM_RATE_PER_MIN", "20")))

# Which engine produces RESULTS for search_bhsa. Default tf per the design spec;
# a deploy without baked TF data sets BHSA_RESULT_ENGINE=emdros.
_RESULT_ENGINE = os.environ.get("BHSA_RESULT_ENGINE", "tf").strip().lower()
if _RESULT_ENGINE not in ("tf", "emdros"):
    raise ValueError(
        f"unknown BHSA_RESULT_ENGINE '{_RESULT_ENGINE}' (supported: tf, emdros)")

mcp = FastMCP("shebanq")


def handle_lookup_feature(name_or_term: str) -> dict:
    spec = _ref.lookup(name_or_term)
    if spec is None:
        return {"error": f"unknown feature '{name_or_term}'"}
    return {
        "feature": name_or_term,
        "objects": {
            ot: {"kind": s["kind"], "gloss": s.get("gloss"),
                 "values": s.get("values")}
            for ot, s in spec["objects"].items()
        },
    }


def _get_features(mql: str) -> list[str]:
    """Extract the GET-clause feature list (in order) so the runner harvests
    exactly the features the query requested, by their GET index."""
    m = _GET_CLAUSE.search(mql)
    if not m:
        return []
    return [f.strip() for f in m.group(1).split(",") if f.strip()]


def _default_executor(mql: str, features: list[str]):
    """Default execution path: run directly in-process (stdio/local/tests)."""
    return run_query(mql, DB_PATH, features, limit=_RESULT_LIMIT)


# Swappable execution backend. HTTP mode replaces this with the QueryGuard.
_executor = _default_executor

# Startup self-test result; /health reports this. False until proven.
_ready = False
SELFTEST_MQL = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"  # bara; expect > 0

# Cap on the number of formatted results returned in a single response. A broad
# query can match thousands of objects; returning them all floods a client's
# context. result_count still reports the true total, so counts stay honest.
_RESULT_LIMIT = int(os.environ.get("MAX_RESULTS", "100"))


def _run_pipeline(mql: str) -> dict:
    validation = validate_mql(mql, _ref)
    if not validation.ok:
        return {"mql": mql, "error": "MQL failed validation",
                "validation_errors": validation.errors}
    try:
        result = _executor(mql, _get_features(mql))
    except (RuntimeError, QueryTimeout, ServerBusy, WorkerCrashed) as exc:
        return {"mql": mql, "error": str(exc)}
    # The cap is applied in the executor/runner (harvest stops at the limit),
    # so result.matches is already bounded; result.count is the true total.
    out = {"mql": mql, "result_count": result.count,
           "results": format_results(result.matches)}
    if result.count > len(result.matches):
        out["results_truncated"] = True
        out["results_shown"] = len(result.matches)
    return out


def _install_guard(max_concurrent: int, timeout_seconds: int) -> None:
    """Swap the executor to a process-isolated, timeout-bounded guard."""
    global _executor
    guard = QueryGuard(DB_PATH, max_concurrent=max_concurrent,
                       timeout_seconds=timeout_seconds)
    _executor = guard.run


def _tf_default_executor(template: str, features: list[str]):
    """Default TF execution path: in-process warm corpus (stdio/local/tests)."""
    return tf_runner.run_template(template, features=features or None,
                                  limit=_RESULT_LIMIT)


# Swappable TF execution backend. HTTP mode replaces this with a QueryGuard.
_tf_executor = _tf_default_executor


def _run_tf_pipeline(template: str) -> dict:
    validation = validate_tf(template, _ref)
    if not validation.ok:
        return {"tf_template": template, "error": "TF template failed validation",
                "validation_errors": validation.errors}
    try:
        result = _tf_executor(template, [])
    except (RuntimeError, QueryTimeout, ServerBusy, WorkerCrashed) as exc:
        return {"tf_template": template, "error": str(exc)}
    out = {"tf_template": template, "result_count": result.count,
           "results": format_results(result.matches)}
    if result.count > len(result.matches):
        out["results_truncated"] = True
        out["results_shown"] = len(result.matches)
    return out


def handle_run_tf(template: str) -> dict:
    return _run_tf_pipeline(template)


def handle_to_citable_mql(template: str) -> dict:
    try:
        mql = tf_to_mql(template, _ref)
    except ConversionError as exc:
        return {"tf_template": template, "error": str(exc)}
    return {"tf_template": template, "mql": mql,
            "next": "Paste this MQL into SHEBANQ and save the query for a "
                    "citable permalink. Note the data version: this server "
                    "is pinned to ETCBC 2021."}


def handle_to_tf_template(mql: str) -> dict:
    try:
        result = mql_to_tf(mql, _ref)
    except ConversionError as exc:
        return {"mql": mql, "error": str(exc)}
    out = {"mql": mql, "tf_template": result.text,
           "next": "Run this template with run_tf, or in a Text-Fabric "
                   "notebook against the BHSA 2021 release."}
    if result.notes:
        out["notes"] = result.notes
    return out


def handle_convert(text: str) -> dict:
    return detect_and_convert(text, _ref)


def _derive_tf(mql: str) -> dict:
    """The Text-Fabric equivalent of an MQL artifact, derived by the
    deterministic converter (row-level equivalence is CI-proven). Returns
    {template, notes} or {error}; never raises."""
    try:
        r = mql_to_tf(mql, _ref)
        return {"template": r.text, "notes": r.notes}
    except ConversionError as exc:
        return {"error": str(exc)}


def _install_tf_guard(max_concurrent: int, timeout_seconds: int) -> None:
    """Warm TF and swap the TF executor to a guarded worker. Fork only on
    Linux (the deploy target): glibc+CPython reinit their locks at fork.
    macOS has fork but no such guarantees. If TF is unavailable, leave the
    default executor in place to raise a clear per-request error."""
    global _tf_executor
    tf_runner.warm()        # before serving: COW benefit + quiet-thread fork
    ctx = "fork" if sys.platform == "linux" else "spawn"
    guard = QueryGuard(DB_PATH, max_concurrent=max_concurrent,
                       timeout_seconds=timeout_seconds,
                       target=tf_runner.tf_target, mp_context=ctx)
    _tf_executor = guard.run


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


def handle_run_mql(mql: str) -> dict:
    return _run_pipeline(mql)


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
    if not _TRANSLATE_LIMITER.allow("global", monotonic()):
        return {"question": question,
                "error": "translation rate limit reached; try again shortly"}
    out: dict = {"question": question}

    # One model call: MQL. The TF equivalent is DERIVED, not generated, so
    # the two artifacts cannot disagree (row-level equivalence is CI-proven).
    try:
        mql = _translator.translate(question, _ref)
        out["mql"] = mql
    except Exception:  # noqa: BLE001 - API error / spend cap -> degrade
        out["error"] = ("translation is unavailable right now. Use run_mql or "
                        "run_tf with a query you write by hand.")
        out["guidance"] = _QUOTING_RULE
        return out

    v = validate_mql(mql, _ref)
    if not v.ok:
        out["mql_validation_errors"] = v.errors
        out["error"] = "the generated MQL failed validation"
        return out

    out["tf"] = _derive_tf(mql)
    tf_template = out["tf"].get("template")

    # Run ONE engine for results. If derivation refused (out["tf"] carries
    # an error), the tf engine has nothing to run; fall back to emdros.
    engine = _RESULT_ENGINE
    if engine == "tf" and tf_template is None:
        engine = "emdros"
    if engine == "tf":
        run = _run_tf_pipeline(tf_template)
    else:
        run = _run_pipeline(mql)
    out["engine"] = engine
    for key in ("result_count", "results", "results_truncated",
                "results_shown", "error"):
        if key in run:
            out[key] = run[key]
    return out


def _degraded_payload(question: str) -> dict:
    """Returned when auto-translation is unavailable (no LLM, API error, spend
    cap). Has no 'mql', so the UI offers the manual edit-and-run path."""
    return {
        "question": question,
        "degraded": True,
        "guidance": _QUOTING_RULE,
        "hint": "Auto-translation is unavailable right now. Write or edit an "
                "MQL query below and run it.",
    }


def handle_ask(question: str) -> dict:
    """Web /api/ask: translate + run in one shot, with graceful degrade. The
    web UI shows the MQL next to the results, so degrade unless there is a
    VALID MQL artifact — TF-only successes would pair results with a query
    that did not produce them."""
    try:
        result = handle_search_bhsa(question)
    except Exception:  # noqa: BLE001 - any LLM/translate failure degrades
        result = None
    if not result or "mql" not in result or "mql_validation_errors" in result:
        return _degraded_payload(question)
    return result


def handle_translate(question: str, references: bool = False) -> dict:
    """Web /api/translate: translate a question to MQL only, without running it.

    Translates ONCE and returns both forms of that single query: `mql_flat` (no
    verse wrapper) and `mql_ref` (wrapped to carry book/chapter/verse). The
    reference checkbox toggles between these client-side, so it never triggers a
    fresh, possibly-different translation. `mql` mirrors the requested flag for
    back-compat. Degrades like handle_ask when translation is unavailable."""
    if _translator is None:
        return _degraded_payload(question)
    try:
        mql = _translator.translate(question, _ref)
    except Exception:  # noqa: BLE001 - any LLM/translate failure degrades
        return _degraded_payload(question)
    flat = _unwrap_verse(mql)               # normalise: strip any wrapper the LLM added
    wrapped = _wrap_in_verse(flat)
    return {"question": question,
            "mql": wrapped if references else flat,
            "mql_flat": flat,
            "mql_ref": wrapped,
            "tf_flat": _derive_tf(flat),
            "tf_ref": _derive_tf(wrapped)}


def _web_api_enabled() -> bool:
    return os.environ.get("WEB_API", "").strip().lower() in ("1", "true", "on", "yes")


def _load_asset_text(env_var: str, default: str, fallback: str) -> str:
    from pathlib import Path
    path = Path(os.environ.get(env_var, default))
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return fallback


def _load_web_page() -> str:
    """The web app's main page, baked into the image (or repo, in dev)."""
    return _load_asset_text("WEB_PAGE", "demo/index.html",
                            "<!doctype html><title>shebanq</title>"
                            "<p>Page not found.</p>")


def _load_about_page() -> str:
    return _load_asset_text("WEB_ABOUT", "demo/about.html",
                            "<!doctype html><title>About</title>"
                            "<p>About page not found.</p>")


def _load_og_image() -> bytes:
    from pathlib import Path
    try:
        return Path(os.environ.get("WEB_OG", "demo/og.png")).read_bytes()
    except OSError:
        return b""


def _mql_prompt_text(question: str) -> str:
    return (
        build_prompt(_ref)
        + f"\n\nQuestion: {question}\n\n"
        "Write a read-only MQL SELECT for this question, then call run_mql with it."
    )


@mcp.tool()
def lookup_feature(name_or_term: str) -> dict:
    """Look up a BHSA feature: its gloss and valid values."""
    return handle_lookup_feature(name_or_term)


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
def run_tf(template: str) -> dict:
    """Validate and run a Text-Fabric search template; return glossed results.

    A template is one object per line, indentation = containment, constraints
    as unquoted feature=value pairs (sp=verb, lex=BR>[). Put the object you
    want results for on the LAST line. Call lookup_feature(name) to check a
    feature's values. Pinned to the BHSA 2021 release.
    """
    return handle_run_tf(template)


@mcp.tool()
def to_citable_mql(template: str) -> dict:
    """Convert a Text-Fabric search template to equivalent MQL for SHEBANQ.

    Deterministic, no model involved: indentation becomes brackets, spaces
    become AND, string features get quoted from the catalogue. Use this to
    turn a notebook query into a citable SHEBANQ saved query. Templates using
    TF constructs beyond '<object_type> feature=value ...' lines are refused
    with an explanation. The mirror of to_tf_template.
    """
    return handle_to_citable_mql(template)


@mcp.tool()
def to_tf_template(mql: str) -> dict:
    """Convert an Emdros MQL query to the equivalent Text-Fabric search template.

    Deterministic, no model involved: brackets become indentation, AND
    becomes a space, quoted string values lose their quotes. GET clauses are
    dropped with a note (TF results expose all features). MQL using OR, NOT,
    FOCUS, or sequence operators is refused with an explanation. The mirror
    of to_citable_mql.
    """
    return handle_to_tf_template(mql)


@mcp.tool()
def search_bhsa(question: str) -> dict:
    """Answer a plain-language question about the Hebrew Bible.

    With server-side translation enabled, returns generated MQL + results. On
    the public deploy (no server-side LLM) it returns a concise MQL-writing
    primer so you compose a read-only query yourself and call run_mql. Use the
    write-mql prompt for the full feature reference. The response also carries
    the query's Text-Fabric equivalent, derived deterministically from the MQL.
    """
    return handle_search_bhsa(question)


@mcp.prompt()
def write_mql(question: str) -> str:
    """Compose a read-only BHSA MQL query for a plain-language question."""
    return _mql_prompt_text(question)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ANN001 - Starlette Request
    # Local import: keep stdio mode free of HTTP-stack imports.
    from starlette.responses import JSONResponse
    return JSONResponse(_health_payload(), status_code=200 if _ready else 503)


def _configure_http_security() -> None:
    """Set transport security for the public HTTP deploy.

    FastMCP defaults to DNS-rebinding/Host protection that only trusts
    localhost, so behind a proxy host (e.g. Render) every MCP request gets a
    421. That protection exists to shield LOCAL servers from browser-driven
    attacks; this server is public, holds no credentials/cookies, and makes no
    localhost-trust assumption, so it does not apply. Disable it by default; set
    MCP_ALLOWED_HOSTS (comma-separated) to re-enable a strict host allowlist.
    """
    from mcp.server.transport_security import TransportSecuritySettings

    allowed = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
    if allowed:
        hosts = [h.strip() for h in allowed.split(",") if h.strip()]
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=["*"],
        )
    else:
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )


def main() -> None:
    transport = _resolve_transport()
    if transport == "streamable-http":
        max_concurrent = int(os.environ.get("MAX_CONCURRENT_QUERIES", "2"))
        timeout_seconds = int(os.environ.get("QUERY_TIMEOUT_SECONDS", "15"))
        if max_concurrent < 1:
            raise SystemExit("MAX_CONCURRENT_QUERIES must be >= 1")
        if timeout_seconds < 1:
            raise SystemExit("QUERY_TIMEOUT_SECONDS must be >= 1")
        _install_guard(max_concurrent, timeout_seconds)
        try:
            _install_tf_guard(max_concurrent, timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - TF optional in HTTP mode
            print(f"WARNING: TF engine unavailable ({exc}); "
                  "run_tf will error per-request", flush=True)
        # Self-test through the guard: bounds a hung engine at timeout_seconds
        # and exercises the real production execution path.
        if not _run_startup_selftest(
            query_fn=lambda: _executor(SELFTEST_MQL, [])
        ):
            # Do not crash: boot and serve /health as 503 so the platform's
            # health check marks the deploy unhealthy with a clear signal.
            print("WARNING: startup self-test failed; /health will report 503",
                  flush=True)
        _configure_http_security()
        if _web_api_enabled():
            from .web import register_web_routes
            limiter = RateLimiter(int(os.environ.get("WEB_RATE_PER_MIN", "10")))
            register_web_routes(mcp, ask=handle_ask, run=handle_run_mql,
                                translate=handle_translate,
                                page_html=_load_web_page(), limiter=limiter,
                                convert=handle_convert,
                                about_html=_load_about_page(),
                                og_png=_load_og_image())
        mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
