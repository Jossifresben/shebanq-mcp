"""Cross-engine equivalence: the Rosetta guarantee. Each pair below is the
same question expressed in both languages; equal counts on the same pinned
2021 data prove the artifacts are interchangeable. Runs only where BOTH
engines are available (the emdros CI job, which also installs TF)."""
import pytest

from shebanq_mcp import tf_runner
from shebanq_mcp.runner import run_query

PAIRS = [
    ("SELECT ALL OBJECTS WHERE [word sp=verb] GO",
     "word sp=verb"),
    ("SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO",
     "word sp=verb vs=nif"),
    ("SELECT ALL OBJECTS WHERE [word lex='BR>['] GO",
     "word lex=BR>["),
    ("SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl] GO",
     "word sp=subs gn=f nu=pl"),
    ("SELECT ALL OBJECTS WHERE [word vt=impv] GO",
     "word vt=impv"),
    ("SELECT ALL OBJECTS WHERE [word sp=nmpr] GO",
     "word sp=nmpr"),
    # Nested: exercises Emdros leaf-counting (_harvest_nested) vs TF
    # tuple-counting, and the converter's indentation-to-bracket logic.
    ("SELECT ALL OBJECTS WHERE "
     "[clause [phrase function=Pred [word sp=verb AND vs=nif]]] GO",
     "clause\n  phrase function=Pred\n    word sp=verb vs=nif"),
]


@pytest.mark.tf
@pytest.mark.emdros
@pytest.mark.parametrize("mql,template", PAIRS)
def test_engines_agree(require_emdros, require_tf, db_path, mql, template):
    emdros_count = run_query(mql, db_path, [], limit=1).count
    tf_count = tf_runner.run_template(template, limit=1).count
    assert emdros_count == tf_count


@pytest.mark.tf
@pytest.mark.emdros
@pytest.mark.parametrize("_mql,template", PAIRS)
def test_citable_mql_round_trip(require_emdros, require_tf, db_path,
                                _mql, template):
    """The converter's output, run on Emdros, must match the template run on
    TF. This is the to_citable_mql guarantee: what the scholar cites on
    SHEBANQ returns what their notebook returned."""
    from shebanq_mcp.feature_reference import FeatureReference
    from shebanq_mcp.tf_to_mql import tf_to_mql
    converted = tf_to_mql(template, FeatureReference.load())
    emdros_count = run_query(converted, db_path, [], limit=1).count
    tf_count = tf_runner.run_template(template, limit=1).count
    assert emdros_count == tf_count


@pytest.mark.tf
@pytest.mark.emdros
@pytest.mark.parametrize("mql,template", PAIRS)
def test_mql_to_tf_round_trip(require_emdros, require_tf, db_path,
                              mql, template):
    """The MQL->TF direction: converting the pinned MQL must yield a
    template that returns the same count on TF as the MQL does on Emdros."""
    from shebanq_mcp.feature_reference import FeatureReference
    from shebanq_mcp.mql_to_tf import mql_to_tf
    converted = mql_to_tf(mql, FeatureReference.load()).text
    emdros_count = run_query(mql, db_path, [], limit=1).count
    tf_count = tf_runner.run_template(converted, limit=1).count
    assert emdros_count == tf_count


@pytest.mark.tf
@pytest.mark.emdros
def test_get_query_count_unchanged_by_conversion(require_emdros, require_tf,
                                                 db_path):
    """Dropping GET must not change what matches: the verse-wrapped
    reference shape converts to a verse/word template with equal count."""
    from shebanq_mcp.feature_reference import FeatureReference
    from shebanq_mcp.mql_to_tf import mql_to_tf
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    r = mql_to_tf(mql, FeatureReference.load())
    assert r.notes                              # the GET note fired
    emdros_count = run_query(mql, db_path, [], limit=1).count
    tf_count = tf_runner.run_template(r.text, limit=1).count
    assert emdros_count == tf_count == 48       # bara, the pinned count
