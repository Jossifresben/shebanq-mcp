from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.validator import validate_mql, ValidationResult


def _ref():
    return FeatureReference.load()


def test_valid_query_passes():
    mql = "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True
    assert result.errors == []


def test_unknown_value_fails_with_message():
    mql = "SELECT ALL OBJECTS WHERE [word vs='niphal'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("niphal" in e and "vs" in e for e in result.errors)


def test_unknown_feature_fails():
    mql = "SELECT ALL OBJECTS WHERE [word bogus='x'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("bogus" in e for e in result.errors)


def test_open_valued_feature_passes():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_double_quotes_are_handled():
    mql = 'SELECT ALL OBJECTS WHERE [word vs="nif"] GO'
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_multiple_constraints_all_checked():
    mql = "SELECT ALL OBJECTS WHERE [word sp='verb' AND vs='nif' AND vt='wayq'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True
