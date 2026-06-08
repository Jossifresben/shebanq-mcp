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
