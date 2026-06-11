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


def test_rejects_mutation_smuggled_after_select():
    # The denylist must scan the whole query, not just the first statement.
    res = validate_mql(
        "SELECT ALL OBJECTS WHERE [word sp=verb] GO DROP DATABASE 'x' GO", _ref()
    )
    assert not res.ok


# ---------------------------------------------------------------------------
# v2 object-type-aware tests
# ---------------------------------------------------------------------------
import json
from pathlib import Path


def _ok(mql):
    from shebanq_mcp.feature_reference import FeatureReference
    return validate_mql(mql, FeatureReference.load())


def test_v2_valid_clause_value():
    assert _ok("SELECT ALL OBJECTS WHERE [clause typ=Ellp] GO").ok


def test_v2_clause_value_on_phrase_is_rejected():
    r = _ok("SELECT ALL OBJECTS WHERE [phrase typ=Ellp] GO")
    assert not r.ok and any("Ellp" in e for e in r.errors)


def test_v2_feature_on_wrong_object_type():
    r = _ok("SELECT ALL OBJECTS WHERE [word rela=Objc] GO")
    assert not r.ok and any("rela" in e for e in r.errors)


def test_v2_unknown_object_type():
    r = _ok("SELECT ALL OBJECTS WHERE [paragraph typ=Ellp] GO")
    assert not r.ok and any("paragraph" in e for e in r.errors)


def test_v2_string_feature_with_bracket_literal_ok():
    assert _ok("SELECT ALL OBJECTS WHERE [word lex='BR>['] GO").ok


def test_v2_enum_quoted_rejected():
    r = _ok("SELECT ALL OBJECTS WHERE [word sp='verb'] GO")
    assert not r.ok and any("unquoted" in e for e in r.errors)


def test_v2_nested_blocks_scope_correctly():
    assert _ok("SELECT ALL OBJECTS WHERE [clause typ=Ellp [phrase function=Objc]] GO").ok


def test_v2_read_only_still_enforced():
    assert not _ok("SELECT ALL OBJECTS WHERE [word] GO; DROP DATABASE x GO").ok


def test_v2_every_fixture_query_validates():
    # Guard against false positives: every engine-verified fixture query must pass.
    from shebanq_mcp.feature_reference import FeatureReference
    ref = FeatureReference.load()
    base = Path(__file__).parent / "fixtures"
    for fname, key in (("mql_constructs.json", "constructs"),
                       ("scholar_questions.json", "questions")):
        for c in json.loads((base / fname).read_text())[key]:
            r = validate_mql(c["mql"], ref)
            assert r.ok, f"{c['name']} should validate: {r.errors}"
