import os
import re

from mcp.server.fastmcp import FastMCP

from .feature_reference import FeatureReference
from .guard import QueryGuard
from .validator import validate_mql
from .runner import run_query
from .formatter import format_results
from .translate import build_translator

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
    return run_query(mql, DB_PATH, features)


# Swappable execution backend. HTTP mode replaces this with the QueryGuard.
_executor = _default_executor

# Startup self-test result; /health reports this. False until proven.
_ready = False
SELFTEST_MQL = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"  # bara; expect > 0


def _run_pipeline(mql: str) -> dict:
    validation = validate_mql(mql, _ref)
    if not validation.ok:
        return {"mql": mql, "error": "MQL failed validation",
                "validation_errors": validation.errors}
    result = _executor(mql, _get_features(mql))
    return {"mql": mql, "result_count": result.count,
            "results": format_results(result.matches)}


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


def handle_run_mql(mql: str) -> dict:
    return _run_pipeline(mql)


def handle_search_bhsa(question: str) -> dict:
    if _translator is None:
        return {"error": "No LLM translator configured (LLM_PROVIDER=none). "
                "Set LLM_PROVIDER (e.g. 'anthropic') with the matching API key, "
                "or use run_mql with a query composed by your MCP client."}
    mql = _translator.translate(question, _ref)
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


@mcp.custom_route("/health", methods=["GET"])
async def health(request):  # noqa: ANN001 - Starlette Request
    from starlette.responses import JSONResponse
    return JSONResponse(_health_payload(), status_code=200 if _ready else 503)


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


if __name__ == "__main__":
    main()
