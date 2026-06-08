from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.validator import validate_mql, ValidationResult


def _ref():
    return FeatureReference.load()


def test_enum_unquoted_valid_passes():
    mql = "SELECT ALL OBJECTS WHERE [word vs=nif] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True
    assert result.errors == []


def test_enum_quoted_fails_with_quoting_message():
    mql = "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("unquoted" in e and "vs" in e for e in result.errors)


def test_enum_unknown_value_fails():
    mql = "SELECT ALL OBJECTS WHERE [word vs=niphal] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("niphal" in e for e in result.errors)


def test_string_quoted_passes():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_string_unquoted_fails_with_quoting_message():
    mql = "SELECT ALL OBJECTS WHERE [word lex=BR] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("quoted" in e and "lex" in e for e in result.errors)


def test_unknown_feature_fails():
    mql = "SELECT ALL OBJECTS WHERE [word bogus=x] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is False
    assert any("bogus" in e for e in result.errors)


def test_multiple_enum_constraints_all_checked():
    mql = "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_mixed_enum_and_string_passes():
    mql = "SELECT ALL OBJECTS WHERE [word sp=verb AND lex='BR>['] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True


def test_get_clause_features_not_treated_as_constraints():
    # GET lists features without '=', so they must not trip the validator.
    mql = "SELECT ALL OBJECTS WHERE [word vs=nif GET sp, gloss] GO"
    result = validate_mql(mql, _ref())
    assert result.ok is True
