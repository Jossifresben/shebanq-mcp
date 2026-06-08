import pytest
from shebanq_mcp.runner import run_query, RunResult


@pytest.mark.emdros
def test_known_query_returns_matches(require_emdros, db_path):
    # Niphal verbs: a real, stable, sizeable set in the BHSA.
    mql = "SELECT ALL OBJECTS WHERE [word sp='verb' AND vs='nif'] GO"
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


@pytest.mark.emdros
def test_run_query_with_features_returns_values(require_emdros, db_path):
    mql = (
        "SELECT ALL OBJECTS WHERE "
        "[word sp='verb' AND vs='nif' GET sp, vs, gloss] GO"
    )
    result = run_query(mql, db_path, features=["sp", "vs", "gloss"])
    assert result.count > 0
    first = result.matches[0]
    assert "sp" in first and "gloss" in first
