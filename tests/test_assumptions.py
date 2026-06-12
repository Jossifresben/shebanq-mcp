import pytest

from shebanq_mcp.assumptions import assumptions_for
from shebanq_mcp.feature_reference import FeatureReference


@pytest.fixture(scope="module")
def ref():
    return FeatureReference.load()


def test_constraint_feature_triggers(ref):
    out = assumptions_for("SELECT ALL OBJECTS WHERE [word gn=f] GO", ref)
    assert any("gender" in n.lower() for n in out)


def test_get_only_feature_triggers(ref):
    # gloss appears only in GET, never as a constraint; it must still fire
    out = assumptions_for(
        "SELECT ALL OBJECTS WHERE [word sp=verb GET g_word_utf8, gloss] GO", ref)
    assert any("dictionary" in n.lower() for n in out)


def test_no_trap_features_gives_empty(ref):
    out = assumptions_for("SELECT ALL OBJECTS WHERE [word sp=verb] GO", ref)
    assert out == []


def test_gn_and_nu_are_two_distinct_notes(ref):
    out = assumptions_for(
        "SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl] GO", ref)
    assert len(out) == 2
    assert any("gender" in n.lower() for n in out)
    assert any("number" in n.lower() for n in out)


def test_prs_trio_dedups_to_one_note(ref):
    out = assumptions_for(
        "SELECT ALL OBJECTS WHERE [word prs_ps=p3 AND prs_gn=m AND prs_nu=sg] GO",
        ref)
    assert len(out) == 1
    assert "pronominal suffix" in out[0].lower()


def test_tf_template_input(ref):
    out = assumptions_for("word gn=f nu=pl", ref)
    assert len(out) == 2


def test_tf_template_get_equivalent_via_constraints(ref):
    # TF templates have no GET; features appear as constraints only
    out = assumptions_for("word sp=subs st=c", ref)
    assert any("state" in n.lower() for n in out)


def test_stable_order_catalogue_order(ref):
    a = assumptions_for("SELECT ALL OBJECTS WHERE [word gn=f AND nu=pl] GO", ref)
    b = assumptions_for("SELECT ALL OBJECTS WHERE [word nu=pl AND gn=f] GO", ref)
    assert a == b                              # order independent of query order


def test_malformed_input_returns_empty_not_raise(ref):
    assert assumptions_for("not a query at all", ref) == []
    assert assumptions_for("", ref) == []
