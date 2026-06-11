import json
from pathlib import Path

import pytest

from shebanq_mcp.runner import run_query

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _cases(fname, key):
    return [(c["name"], c) for c in _load(fname)[key]]


@pytest.mark.emdros
@pytest.mark.parametrize("name,case", _cases("mql_constructs.json", "constructs"))
def test_construct_runs_and_count(name, case, require_emdros, db_path):
    result = run_query(case["mql"], db_path, limit=5)
    if case["expected_count"] is not None:
        assert result.count == case["expected_count"], name
    else:
        assert result.count >= 0   # proves the construct executes on rel-3-9-0


@pytest.mark.emdros
@pytest.mark.parametrize("name,case", _cases("scholar_questions.json", "questions"))
def test_scholar_question_count(name, case, require_emdros, db_path):
    result = run_query(case["mql"], db_path, limit=5)
    if case["expected_count"] is not None:
        assert result.count == case["expected_count"], name
    else:
        assert result.count >= 0
