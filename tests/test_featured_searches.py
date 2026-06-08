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
