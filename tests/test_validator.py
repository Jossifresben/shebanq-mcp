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


def test_rejects_drop_database():
    result = validate_mql("DROP DATABASE 'shebanq_etcbc2021' GO", _ref())
    assert not result.ok
    assert any("read-only" in e or "mutating" in e for e in result.errors)


def test_rejects_update_delete_create_pragma():
    for mql in [
        "UPDATE OBJECTS BY MONADS = 1 [word sp:=noun] GO",
        "DELETE OBJECTS BY MONADS = 1 [word] GO",
        "CREATE OBJECT FROM MONADS = 1 [word] GO",
        "PRAGMA journal_mode = WAL",
    ]:
        result = validate_mql(mql, _ref())
        assert not result.ok, mql


def test_accepts_plain_select():
    result = validate_mql("SELECT ALL OBJECTS WHERE [word sp=verb] GO", _ref())
    assert result.ok, result.errors


def test_mutating_keyword_inside_string_value_is_ok():
    # 'DELETE' as a string-feature value must not trip the read-only guard.
    result = validate_mql("SELECT ALL OBJECTS WHERE [word lex='DELETE'] GO", _ref())
    assert result.ok, result.errors
