import pytest

from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.mql_to_tf import mql_to_tf
from shebanq_mcp.tf_to_mql import ConversionError, tf_to_mql
from shebanq_mcp.tf_validator import validate_tf


@pytest.fixture(scope="module")
def ref():
    return FeatureReference.load()


def test_flat_enum(ref):
    r = mql_to_tf("SELECT ALL OBJECTS WHERE [word sp=verb] GO", ref)
    assert r.text == "word sp=verb"
    assert r.notes == []


def test_and_becomes_space(ref):
    r = mql_to_tf("SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO", ref)
    assert r.text == "word sp=verb vs=nif"


def test_quoted_string_unquoted(ref):
    r = mql_to_tf("SELECT ALL OBJECTS WHERE [word lex='BR>['] GO", ref)
    assert r.text == "word lex=BR>["


def test_nesting_becomes_indentation(ref):
    r = mql_to_tf(
        "SELECT ALL OBJECTS WHERE "
        "[clause [phrase function=Pred [word sp=verb AND vs=nif]]] GO", ref)
    assert r.text == "clause\n  phrase function=Pred\n    word sp=verb vs=nif"


def test_siblings_align(ref):
    r = mql_to_tf(
        "SELECT ALL OBJECTS WHERE "
        "[clause [phrase function=Pred] [phrase function=Objc]] GO", ref)
    assert r.text == "clause\n  phrase function=Pred\n  phrase function=Objc"


def test_get_dropped_with_note(ref):
    r = mql_to_tf(
        "SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
        "[word lex='BR>[' GET g_word_utf8, gloss]] GO", ref)
    assert r.text == "verse\n  word lex=BR>["
    assert r.notes == ["GET clauses dropped; Text-Fabric results expose all features."]


def test_output_validates_as_tf(ref):
    r = mql_to_tf(
        "SELECT ALL OBJECTS WHERE "
        "[clause [phrase function=Pred [word vt=impv]]] GO", ref)
    assert validate_tf(r.text, ref).ok


def test_or_refused(ref):
    with pytest.raises(ConversionError, match="cannot be converted"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [word sp=verb OR sp=subs] GO", ref)


def test_focus_refused(ref):
    with pytest.raises(ConversionError, match="cannot be converted"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [word FOCUS sp=verb] GO", ref)


def test_sequence_operator_refused(ref):
    with pytest.raises(ConversionError, match="cannot be converted"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [word sp=verb]![word] GO", ref)


def test_not_refused(ref):
    with pytest.raises(ConversionError, match="cannot be converted"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [word NOT sp=verb] GO", ref)


def test_having_monads_refused(ref):
    with pytest.raises(ConversionError):
        mql_to_tf("SELECT ALL OBJECTS HAVING MONADS IN {1-100} GO", ref)


def test_keyword_inside_string_value_is_safe(ref):
    # OR inside a quoted value must NOT trip the unsupported-construct scan
    r = mql_to_tf("SELECT ALL OBJECTS WHERE [word g_word_utf8='OR'] GO", ref)
    assert r.text == "word g_word_utf8=OR"


def test_space_in_string_value_refused(ref):
    # TF feature=value pairs cannot carry spaces
    with pytest.raises(ConversionError, match="space"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [word gloss='be strong'] GO", ref)


def test_invalid_mql_refused(ref):
    with pytest.raises(ConversionError, match="unknown object type"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [wibble sp=verb] GO", ref)


def test_not_a_select_refused(ref):
    with pytest.raises(ConversionError, match="SELECT ALL OBJECTS WHERE"):
        mql_to_tf("DROP DATABASE x", ref)


def test_round_trip_tf_mql_tf(ref):
    # tf -> mql -> tf is the identity on the v1 grammar
    for t in ("word sp=verb",
              "word sp=verb vs=nif",
              "word lex=BR>[",
              "clause\n  phrase function=Pred\n    word sp=verb vs=nif",
              "clause\n  phrase function=Pred\n  phrase function=Objc"):
        assert mql_to_tf(tf_to_mql(t, ref), ref).text == t


def test_round_trip_mql_tf_mql(ref):
    # mql -> tf -> mql is the identity on convertible GET-free MQL
    for q in ("SELECT ALL OBJECTS WHERE [word sp=verb] GO",
              "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO",
              "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"):
        assert tf_to_mql(mql_to_tf(q, ref).text, ref) == q


def test_get_inside_string_value_refused(ref):
    with pytest.raises(ConversionError, match="cannot be converted safely"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [word gloss='GET x ]'] GO", ref)


def test_missing_close_bracket_refused(ref):
    with pytest.raises(ConversionError, match="never closed"):
        mql_to_tf("SELECT ALL OBJECTS WHERE [clause [word sp=verb] GO", ref)


def test_extra_close_bracket_refused(ref):
    with pytest.raises(ConversionError, match="more '\\]'"):
        mql_to_tf(
            "SELECT ALL OBJECTS WHERE [clause [word sp=verb]]] [phrase] GO",
            ref)


def test_empty_body_refused(ref):
    with pytest.raises(ConversionError, match="no object blocks"):
        mql_to_tf("SELECT ALL OBJECTS WHERE  GO", ref)
