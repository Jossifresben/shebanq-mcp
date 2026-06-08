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
