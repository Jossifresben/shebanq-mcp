import pytest

from shebanq_mcp.feature_reference import FeatureReference
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


def test_siblings_become_sibling_blocks(ref):
    mql = tf_to_mql("clause\n  phrase function=Pred\n  phrase function=Objc", ref)
    assert mql == ("SELECT ALL OBJECTS WHERE "
                   "[clause [phrase function=Pred] [phrase function=Objc]] GO")


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
