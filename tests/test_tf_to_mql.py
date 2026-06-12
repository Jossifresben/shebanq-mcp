import pytest

from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.mql_to_tf import mql_to_tf
from shebanq_mcp.tf_to_mql import ConversionError, tf_to_mql
from shebanq_mcp.validator import validate_mql


@pytest.fixture(scope="module")
def ref():
    return FeatureReference.load()


def test_flat_enum_constraint(ref):
    assert tf_to_mql("word sp=verb", ref) == \
        "SELECT ALL OBJECTS WHERE [word sp=verb] GO"


def test_multiple_constraints_join_with_and(ref):
    assert tf_to_mql("word sp=verb vs=nif", ref) == \
        "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO"


def test_string_feature_gets_quoted(ref):
    assert tf_to_mql("word lex=BR>[", ref) == \
        "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"


def test_nesting_becomes_brackets(ref):
    mql = tf_to_mql("clause\n  phrase function=Pred\n    word sp=verb vs=nif", ref)
    assert mql == ("SELECT ALL OBJECTS WHERE "
                   "[clause [phrase function=Pred [word sp=verb AND vs=nif]]] GO")


def test_ordered_siblings_convert(ref):
    out = tf_to_mql(
        "clause\n  p1:phrase function=Pred\n  p2:phrase function=Objc\np1 << p2",
        ref)
    assert out == ("SELECT ALL OBJECTS WHERE "
                   "[clause [phrase function=Pred] [phrase function=Objc]] GO")


def test_unordered_siblings_refused_with_fixit(ref):
    with pytest.raises(ConversionError, match="ordering"):
        tf_to_mql("clause\n  phrase function=Pred\n  phrase function=Objc", ref)


def test_ordering_against_textual_order(ref):
    # p2 << p1 puts Objc first
    out = tf_to_mql(
        "clause\n  p1:phrase function=Pred\n  p2:phrase function=Objc\np2 << p1",
        ref)
    assert out == ("SELECT ALL OBJECTS WHERE "
                   "[clause [phrase function=Objc] [phrase function=Pred]] GO")


def test_cyclic_ordering_refused(ref):
    with pytest.raises(ConversionError, match="cycle|contradict|consistent"):
        tf_to_mql("clause\n  p1:phrase\n  p2:phrase\np1 << p2\np2 << p1", ref)


def test_cross_parent_ordering_refused(ref):
    with pytest.raises(ConversionError, match="sibling"):
        tf_to_mql("clause\n  p1:phrase\n    w1:word\n  p2:phrase\nw1 << p2", ref)


def test_partial_order_refused(ref):
    with pytest.raises(ConversionError, match="partial|total"):
        tf_to_mql("clause\n  p1:phrase\n  p2:phrase\n  p3:phrase\np1 << p2", ref)


def test_output_validates_as_mql(ref):
    mql = tf_to_mql("clause\n  phrase function=Pred\n    word vt=impv", ref)
    assert validate_mql(mql, ref).ok


def test_invalid_template_refused(ref):
    with pytest.raises(ConversionError, match="unknown object type"):
        tf_to_mql("wibble sp=verb", ref)


def test_out_of_grammar_construct_refused(ref):
    # regex match (~) is valid TF search but has no place in our v1 grammar
    with pytest.raises(ConversionError, match="cannot be converted"):
        tf_to_mql("word lex~BR", ref)


def test_quantifier_refused(ref):
    with pytest.raises(ConversionError, match="cannot be converted"):
        tf_to_mql("word sp=verb\n/without/\nclause\n/-/", ref)


def test_quote_in_string_value_refused(ref):
    with pytest.raises(ConversionError, match="quote or backslash"):
        tf_to_mql("word lex=A'B", ref)


def test_tab_indentation_refused(ref):
    with pytest.raises(ConversionError, match="tab"):
        tf_to_mql("clause\n\tword", ref)


def test_multi_root_refused(ref):
    # Two top-level roots are siblings at root level; same ordering-semantics problem
    with pytest.raises(ConversionError, match="ordering"):
        tf_to_mql("word sp=verb\nclause", ref)


def test_sibling_round_trip(ref):
    mql = ("SELECT ALL OBJECTS WHERE [clause [phrase function=Pred] "
           "[phrase function=Objc]] GO")
    assert tf_to_mql(mql_to_tf(mql, ref).text, ref) == mql


def test_three_sibling_round_trip(ref):
    mql = ("SELECT ALL OBJECTS WHERE [clause [phrase function=Pred] "
           "[phrase function=Objc] [phrase function=Subj]] GO")
    assert tf_to_mql(mql_to_tf(mql, ref).text, ref) == mql
