import os
import re

from mcp.server.fastmcp import FastMCP

from .feature_reference import FeatureReference
from .guard import QueryGuard, QueryTimeout, ServerBusy, WorkerCrashed
from .validator import validate_mql
from .runner import run_query
from .formatter import format_results
from .translate import build_translator, build_prompt

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
    return f"{head}[verse GET book, chapter, verse {block}]{tail}".strip()

_QUOTING_RULE = (
    "MQL quoting rule: enumeration features compare UNQUOTED (sp=verb, vs=nif); "
    "string features compare QUOTED (lex='BR>[', gloss='create'). BHSA verb "
    "lexemes carry a trailing '['. Queries must be read-only (SELECT/GET)."
)

_ref = FeatureReference.load()
# The configured LLM translator (None if LLM_PROVIDER=none -> translation-free).
_translator = build_translator()
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
    mql = _translator.translate(question, _ref)
    return _run_pipeline(mql)


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
    """Web /api/ask: translate + run in one shot, with graceful degrade."""
    try:
        result = handle_search_bhsa(question)
    except Exception:  # noqa: BLE001 - any LLM/translate failure degrades
        result = None
    if not result or "mql" not in result:
        return _degraded_payload(question)
    return result


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


def _web_api_enabled() -> bool:
    return os.environ.get("WEB_API", "").strip().lower() in ("1", "true", "on", "yes")


def _load_web_page() -> str:
    """Read the built demo page baked into the image (or repo, in dev)."""
    from pathlib import Path
    path = Path(os.environ.get("WEB_PAGE", "demo/index.html"))
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return "<!doctype html><title>shebanq</title><p>Demo page not found.</p>"


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
def search_bhsa(question: str) -> dict:
    """Answer a plain-language question about the Hebrew Bible.

    With server-side translation enabled, returns generated MQL + results. On
    the public deploy (no server-side LLM) it returns a concise MQL-writing
    primer so you compose a read-only query yourself and call run_mql. Use the
    write-mql prompt for the full feature reference.
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
            from .web import RateLimiter, register_web_routes
            limiter = RateLimiter(int(os.environ.get("WEB_RATE_PER_MIN", "10")))
            register_web_routes(mcp, ask=handle_ask, run=handle_run_mql,
                                translate=handle_translate,
                                page_html=_load_web_page(), limiter=limiter)
        mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT", "8000"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
